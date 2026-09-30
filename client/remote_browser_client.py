"""
TestHub 远程浏览器客户端
======================

部署在远程执行机器（文档里称为"机器 B"）上的独立脚本，**不依赖** TestHub/Django 后端代码，
只需要 Python 3.8+ 和这一个文件即可运行。

按需启动说明（2026-08 改造）：
  这个脚本不再在启动时就预先开一个固定 headless 配置的 Chrome 常驻着。启动后只会：
    1. 确保 Chromium 已经装好（自动安装一次，之后复用同一个可执行文件路径）；
    2. 常驻一个本地 HTTP"控制接口"（默认端口 9333）；
    3. 向 TestHub 注册这个控制接口的地址（不是 CDP 地址本身）。
  真正执行用例的时候，TestHub 会先 POST /launch（带上这次选择的 headless / browser），
  这里才现开一个 Chrome，把这次专属的 CDP 地址回传回去；执行完 TestHub 会调用
  POST /close 把这个 Chrome 进程真正关掉。

  这台机器上一次只服务一个浏览器（串行排队）：如果上一个用例还没执行完，新的
  /launch 请求会在这里阻塞排队，不会同时起多个 Chrome 抢资源/端口。即使 TestHub
  那边异常退出、网络中断，没能调用到 /close，客户端自己也会在浏览器存活超过
  max_lifetime_seconds（默认 30 分钟）后强制关闭，不会无限占着不释放。

  Selenium 模式不受这次改造影响：Selenium Grid 本来就是每次创建 session 时才真正
  拉起浏览器，headless/有头本来就能按每次执行的请求生效。

关于跨机器连 CDP 的一个坑（2026-08 实测发现，加了转发层）：
  较新版本的 Chrome/Chromium 出于安全考虑，即使传了 `--remote-debugging-address=0.0.0.0`
  也只会监听 127.0.0.1，不会真的对外暴露 CDP 端口（这不是防火墙问题，netstat 能直接看到
  只有 127.0.0.1:xxxx 在 LISTENING）。所以这里加了一层纯本机的 TCP 转发（`CdpRelay`）：
  Chrome 自己只监听内部端口（`playwright.port`，只有 127.0.0.1，不需要开防火墙），转发层
  监听对外的端口（`playwright.relay_port`，需要开防火墙），把流量转发到 Chrome 的内部端口。
  转发层还会改写 Chrome 返回的 /json/version 里的 `webSocketDebuggerUrl`（把 Chrome 自己
  上报的 127.0.0.1 换成外部可达地址），否则 Playwright 后续单独发起的 WebSocket 连接会
  拿着这个错误地址去连、直接失败。

功能:
  1. 常驻一个控制接口，按 TestHub 的请求现开/关一个带 CDP 调试端口的 Chromium；
     和/或启动一个常驻的 Selenium standalone server；
  2. 启动成功后自动调用 TestHub 的 `/remote-browser-services/register/` 接口，把自己
     注册（或更新）成一条"远程浏览器服务"记录，不需要再手动去配置中心填地址；
  3. 常驻运行；Ctrl+C 退出时会把刚才注册的记录标记为 is_active=false，关闭当前活跃的
     浏览器会话（如果有）和控制服务/子进程，不会在配置中心堆积重复/失效的记录。

关于 Playwright 部分的实现说明:
  Playwright 的 Python 绑定一直没有提供 Node.js/JS 版才有的 `launch_server()` API
  （官方长期未实现，参见 microsoft/playwright-python#469、#1149），所以没法直接在
  Python 里起一个能被 `connect(ws_endpoint=...)` 连接的"Playwright Remote"服务端。
  这个脚本改用一个更简单、也是 TestHub 后端本来就支持的方式：直接把 Playwright 管理的
  Chromium 可执行文件当成普通 Chrome 进程启动，带上 `--remote-debugging-port`，注册成
  `playwright_cdp` 类型的远程服务——TestHub 那边本来就是通过 `connect_over_cdp` 去接的，
  跟之前教的"手动开 Chrome 调试端口"效果完全一样，只是这里全自动化、按需化了。

依赖:
  pip install playwright requests

  浏览器二进制不需要预先手动装：脚本启动时会自己检测 Chromium 有没有装好，没装会自动
  执行一次 `playwright install chromium`，失败了才需要按提示手动处理（通常是网络问题，
  可以在配置里设 download_host 换成镜像源）。

  如果要启用 selenium 模式，本机还需要：
    - Java 11+
    - 下载好的 selenium-server-<version>.jar（https://www.selenium.dev/downloads/）
    - 真实安装的 Chrome/Firefox（Selenium 本身不带浏览器，这个没法自动装，
      需要手动确保浏览器已经在本机安装好）

用法:
  直接运行，不需要额外参数：

    python remote_browser_client.py

  配置读取顺序：--config 指定的 JSON 文件 > 同目录下的 config.json（已被 .gitignore 忽略，
  复制 config.example.json 改名得到）> 下面的 CONFIG 字典默认值。Token 等敏感信息请只写在
  config.json 里，不要写进本文件提交到仓库。
"""

import argparse
from pathlib import Path
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests


# ============================================================
# 配置：按需修改这里就行，改完直接 `python remote_browser_client.py` 运行
# ============================================================
CONFIG = {
    "testhub_url": "http://127.0.0.1:8001",
    "token": "",  # 不要把真实 Token 写进这里提交到仓库，填到 client/config.json（已被 .gitignore 忽略）
    "project_id": 1,
    "advertise_host": "",  # 本机在局域网里真实可达的 IP
    "heartbeat_interval_seconds": 30,  # 常驻期间按这个间隔给已注册服务上报"我还活着"，
                                       # 要跟后端 HEARTBEAT_ONLINE_THRESHOLD_SECONDS（默认
                                       # 90 秒）配合，留够余量，不要调得比它还大

    "playwright": {
        "enabled": True,
        "browser": "chromium",
        "port": 19222,                 # Chrome 自己监听的内部端口（只有 127.0.0.1，不用开防火墙）
        "relay_port": 9222,            # 对外暴露的转发端口，TestHub 连这个端口（需要开防火墙）
        "control_port": 9333,          # 控制接口端口，TestHub 通过它按需开/关浏览器（需要开防火墙）
        "default_headless": False,     # /launch 请求没传 headless 时的兜底值
        "max_lifetime_seconds": 1800,  # 单个浏览器最长存活时间，超时强制关闭（兜底，防泄漏）
        "queue_wait_timeout": 600,     # 排队等待上一个会话释放的最长时间（秒），超时直接报错
        "service_name": "",
        "auto_install": True,
        "download_host": "",
    },

    "selenium": {
        "enabled": False,
        "jar_path": "lib/selenium-server-4.46.0.jar",
        "port": 4444,
        "java_path": "java",
        "path_suffix": "/wd/hub",
        "service_name": "",
    },
}


def log(msg):
    print(f"[remote-client] {msg}", flush=True)


def _primary_monitor_work_area():
    """尽力探测这台机器主显示器的工作区大小（不含任务栏/Dock），用于给 Chrome 传
    --window-size / --window-position，让「有头模式」打开的窗口正好匹配这台机器实际的
    屏幕分辨率——不这么做的话 Chrome 只会用自己内置的默认尺寸算，如果这台机器接了多个
    分辨率不同的屏幕，默认尺寸可能是照着更大的那个屏幕算的，摆到分辨率较小的屏幕上就会
    比屏幕还大。

    只处理"主屏幕"：新窗口默认也是显示在主屏幕上，跟这个假设保持一致，不需要额外配置
    去选屏幕。

    探测失败（未知平台、没有图形环境、命令不存在等）时返回 None，调用方应该退回"不显式
    指定窗口大小"的旧行为，让 Chrome 自己决定——不会比现在更差。
    """
    system = platform.system()
    try:
        if system == 'Windows':
            import ctypes

            class _RECT(ctypes.Structure):
                _fields_ = [
                    ('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long),
                ]

            SPI_GETWORKAREA = 0x0030
            rect = _RECT()
            ok = ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
            if ok:
                width, height = rect.right - rect.left, rect.bottom - rect.top
                if width > 0 and height > 0:
                    return width, height, rect.left, rect.top

        elif system == 'Linux':
            # 依赖本机已经装了 xrandr（带图形界面的桌面发行版基本都自带）；纯无图形
            # 界面的服务器本来就跑不了有头模式，探测失败也无所谓，走兜底逻辑就好
            result = subprocess.run(
                ['xrandr', '--query'], capture_output=True, text=True, timeout=5,
            )
            connected_lines = [line for line in result.stdout.splitlines() if ' connected' in line]
            primary_lines = [line for line in connected_lines if 'primary' in line] or connected_lines
            if primary_lines:
                m = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', primary_lines[0])
                if m:
                    width, height, x, y = (int(g) for g in m.groups())
                    return width, height, x, y
    except Exception as e:
        log(f"探测主屏幕分辨率失败，Chrome 窗口大小将使用系统默认值: {e}")
    return None


class RegisteredService:
    """跟踪一条已经注册到 TestHub 的远程浏览器服务，方便退出时反注册"""

    def __init__(self, name, service_type, url):
        self.name = name
        self.service_type = service_type
        self.url = url


class BrowserSession:
    """一次"按需启动"的浏览器会话：一个 Chrome 子进程 + 它专属的临时用户数据目录 + 转发层"""

    def __init__(self, session_id, process, profile_dir, port, window_size=None):
        self.session_id = session_id
        self.process = process
        self.profile_dir = profile_dir
        self.port = port      # Chrome 自己监听的内部端口（只有 127.0.0.1）
        self.window_size = window_size  # 探测到的主屏幕工作区尺寸，见 _primary_monitor_work_area()
        self.relay = None     # CdpRelay 实例，负责把外部端口的流量转发到上面这个内部端口
        self.timer = None
        self._cleanup_lock = threading.Lock()
        self._cleaned_up = False


class CdpRelay:
    """把 0.0.0.0:public_port 收到的连接转发到 127.0.0.1:chrome_port 上真正的 Chrome CDP

    背景：较新版本的 Chrome 出于安全考虑，即使传了 --remote-debugging-address=0.0.0.0
    也只会监听 127.0.0.1（实测确认：netstat 显示只有 127.0.0.1:xxxx 在 LISTENING），
    没法让另一台机器直接连上，需要在这台机器本地搭一层转发。

    纯字节转发不够用：CDP 客户端（比如 Playwright 的 connect_over_cdp）会先 GET
    /json/version 拿到里面的 webSocketDebuggerUrl，然后单独开一个新连接去连这个 URL——
    而 Chrome 自己写在这个字段里的地址是它自己看到的 127.0.0.1:chrome_port，如果不改写，
    调用方拿着这个地址会去连自己机器的 127.0.0.1，根本连不到这台机器。所以这里对
    /json/version、/json、/json/list 这几个只读的发现接口做特殊处理：转发请求给真正的
    Chrome，拿到响应后把里面的 127.0.0.1:chrome_port 替换成外部可达的
    advertise_host:public_port 再回给调用方；其他所有请求（包括真正的 WebSocket 升级和
    后续帧）原样透明转发，不关心内容也不需要理解 WebSocket 协议本身。
    """

    _DISCOVERY_PATHS = ('/json/version', '/json', '/json/list')

    def __init__(self, public_port, chrome_port, advertise_host):
        self.public_port = public_port
        self.chrome_port = chrome_port
        self.advertise_host = advertise_host
        self._server_sock = None
        self._accept_thread = None

    def start(self):
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(('0.0.0.0', self.public_port))
        self._server_sock.listen(50)
        self._accept_thread = threading.Thread(target=self._accept_loop, name='cdp-relay-accept', daemon=True)
        self._accept_thread.start()

    def stop(self):
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass

    def _accept_loop(self):
        while True:
            try:
                client_sock, _addr = self._server_sock.accept()
            except OSError:
                return  # stop() 把 server socket 关了，accept 抛异常，正常退出循环
            threading.Thread(target=self._handle_conn, args=(client_sock,), daemon=True).start()

    @staticmethod
    def _read_http_head(sock, timeout=10):
        """读到请求头结束（空行）为止，返回 (请求行, headers原始字节, 多读到的body字节)"""
        sock.settimeout(timeout)
        buf = b''
        while b'\r\n\r\n' not in buf and len(buf) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        head, _, leftover = buf.partition(b'\r\n\r\n')
        lines = head.split(b'\r\n')
        request_line = lines[0].decode('latin-1', errors='replace') if lines and lines[0] else ''
        headers_blob = b'\r\n'.join(lines[1:])
        return request_line, headers_blob, leftover

    def _handle_conn(self, client_sock):
        try:
            request_line, headers_blob, leftover = self._read_http_head(client_sock)
        except Exception:
            client_sock.close()
            return

        parts = request_line.split(' ')
        path = parts[1] if len(parts) > 1 else ''

        if path in self._DISCOVERY_PATHS:
            self._proxy_discovery_request(client_sock, request_line, headers_blob)
        else:
            # 未知路径 / WebSocket 升级请求：原样把已经读到的这部分请求头连同后面所有
            # 字节透明转发给真正的 Chrome，不再关心内容（升级成 WebSocket 之后的帧也是
            # 靠这个双向字节泵原样转发）
            already_read = (request_line + '\r\n').encode('latin-1') + headers_blob + b'\r\n\r\n' + leftover
            self._proxy_raw(client_sock, already_read)

    def _proxy_discovery_request(self, client_sock, request_line, headers_blob):
        try:
            upstream = socket.create_connection(('127.0.0.1', self.chrome_port), timeout=10)
            upstream.sendall((request_line + '\r\n').encode('latin-1') + headers_blob + b'\r\n\r\n')
            upstream.settimeout(10)
            resp = b''
            while True:
                chunk = upstream.recv(65536)
                if not chunk:
                    break
                resp += chunk
            upstream.close()

            head, _, body = resp.partition(b'\r\n\r\n')
            # Chrome 自己上报的是 127.0.0.1:chrome_port，统一替换成外部可达地址，
            # 这样调用方后续单独发起的 WebSocket 连接才能连回这个转发层而不是原地失败
            old = f'127.0.0.1:{self.chrome_port}'.encode('latin-1')
            new = f'{self.advertise_host}:{self.public_port}'.encode('latin-1')
            body = body.replace(old, new)

            head_lines = [
                line for line in head.split(b'\r\n')
                if not line.lower().startswith(b'content-length:')
            ]
            head_lines.append(f'Content-Length: {len(body)}'.encode('latin-1'))
            head_lines.append(b'Connection: close')
            client_sock.sendall(b'\r\n'.join(head_lines) + b'\r\n\r\n' + body)
        except Exception as e:
            log(f"CDP 转发层处理发现接口请求失败: {e}")
        finally:
            client_sock.close()

    def _proxy_raw(self, client_sock, already_read):
        try:
            upstream = socket.create_connection(('127.0.0.1', self.chrome_port), timeout=10)
        except Exception as e:
            log(f"CDP 转发层连接本机 Chrome（127.0.0.1:{self.chrome_port}）失败: {e}")
            client_sock.close()
            return

        # 这里是真正的坑：client_sock 在 _read_http_head() 里被 settimeout(10) 过，
        # 用来防止读请求头那一下卡死；upstream 是用 create_connection(..., timeout=10)
        # 建的，Python 不会在连接成功后自动把这个超时清掉，同一个 10 秒会一直留在这个
        # socket 对象上。这两个超时如果不在进入下面长连接阶段之前清掉，就会带进接下来
        # 整个 WebSocket 会话里：只要某个方向连续 10 秒没有新数据（哪怕整个连接完全正常、
        # 只是这段时间双方刚好没发东西——比如用例里一个几十秒的固定等待步骤），
        # 下面 recv() 就会抛 socket.timeout，被 pump() 当成连接异常处理，直接把两边的
        # socket 都关掉——表现就是"用例前面几步都好好的，等了一会儿之后突然报连接已关闭"，
        # 跟远程机器、跟网络环境都没关系，是这个转发层自己在按时"误杀"活连接。
        client_sock.settimeout(None)
        upstream.settimeout(None)

        try:
            upstream.sendall(already_read)
        except Exception:
            client_sock.close()
            upstream.close()
            return

        def pump(src, dst):
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                for sock in (src, dst):
                    try:
                        sock.close()
                    except Exception:
                        pass

        threading.Thread(target=pump, args=(client_sock, upstream), daemon=True).start()
        threading.Thread(target=pump, args=(upstream, client_sock), daemon=True).start()


class RemoteBrowserClient:
    def __init__(self, config):
        self.config = config
        self.testhub_url = config['testhub_url'].rstrip('/')
        self.token = config['token']
        self.project_id = config['project_id']
        self.advertise_host = config['advertise_host']

        self.chromium_executable_path = None  # prepare_playwright() 里解析一次并缓存
        self.control_server = None
        self.selenium_process = None          # Selenium standalone 子进程（这部分仍是常驻的）

        self._queue_lock = threading.Lock()   # 串行排队：一次只允许一个浏览器会话活着
        self._current_session = None          # 当前持有 _queue_lock 期间对应的 BrowserSession

        self.registered = []                  # 已注册成功的服务，退出时用来反注册
        self._shutting_down = threading.Event()  # stop() 里置位，让还在后台重试注册的线程尽快退出

    # ---------------- TestHub API ----------------

    def _headers(self):
        return {
            'Authorization': f"Token {self.token}",
            'Content-Type': 'application/json',
        }

    def register(self, name, service_type, url, is_active=True, auth_config=None):
        """调用 TestHub 自注册接口，按 (project, name) upsert，不会产生重复记录"""
        payload = {
            'project': self.project_id,
            'name': name,
            'service_type': service_type,
            'url': url,
            'is_active': is_active,
        }
        if auth_config is not None:
            payload['auth_config'] = auth_config
        api = f"{self.testhub_url}/api/ui-automation/remote-browser-services/register/"
        try:
            resp = requests.post(api, json=payload, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
            action = '创建' if data.get('created') else '更新'
            log(f"已向 TestHub {action}注册服务 \"{name}\" -> {url}")
            return True
        except requests.RequestException as e:
            log(f"注册服务 \"{name}\" 失败: {e}")
            return False

    def register_with_retry(self, name, service_type, url, auth_config=None, interval=10):
        """在后台线程里注册，失败就按固定间隔重试，直到成功或者客户端退出

        常见场景：TestHub 后端这时候还没起来，或者刚好在重启/热重载（比如后端代码
        改动触发了 runserver 的自动重载，短暂几秒钟拒绝连接）。老版本客户端遇到这种
        情况会直接 sys.exit(1) 整个进程退出——但本地该起的服务（控制接口/Selenium）
        其实都已经正常启动了，只是这一次注册请求没打通，没必要因此放弃整个客户端。
        这里改成后台持续重试，注册成功一次后线程自动退出，不影响本地服务已经在跑。
        """

        def _loop():
            while not self._shutting_down.is_set():
                if self.register(name, service_type, url, auth_config=auth_config):
                    self.registered.append(RegisteredService(name, service_type, url))
                    return
                if self._shutting_down.wait(timeout=interval):
                    return
            log(f"客户端正在退出，放弃重试注册 \"{name}\"")

        threading.Thread(target=_loop, name=f'register-retry-{name}', daemon=True).start()

    def heartbeat(self, name):
        """给已注册的服务发一次心跳，只更新时间戳，不像 register() 那样重复上报
        url/capabilities/auth_config 这些连接信息——payload 更小，适合频繁调用。
        """
        payload = {'project': self.project_id, 'name': name}
        api = f"{self.testhub_url}/api/ui-automation/remote-browser-services/heartbeat/"
        try:
            resp = requests.post(api, json=payload, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            log(f"心跳上报失败（\"{name}\"）: {e}")
            return False

    def start_heartbeat_loop(self, interval=30):
        """常驻的心跳线程：按固定间隔给所有已成功注册的服务上报一次"我还活着"

        背景：TestHub 那边只靠 is_active 这一个静态开关的话，没法区分"客户端正常
        运行、只是暂时没有执行任务"和"客户端早就异常退出（被 kill、断电、断网），
        进程都不在了，数据库里还留着 is_active=True 的僵尸记录"——这两种情况在
        is_active 上看起来完全一样，执行时的"远程服务"下拉框会一直显示一个实际上
        已经联系不上的服务。

        这里改成额外维护一个有时效性的 last_heartbeat 时间戳：TestHub 那边超过
        3 倍心跳间隔没收到新的心跳，就会认为这条记录已经离线（见后端
        RemoteBrowserService.HEARTBEAT_ONLINE_THRESHOLD_SECONDS，默认 90 秒），
        不会再出现在执行时的下拉框里，不需要人工去配置中心手动清理。

        默认 30 秒一次，跟后端默认阈值 90 秒配合，留了 3 倍余量，单次心跳偶尔慢了/
        丢了也不会被误判离线；真的联系不上时，最多 90 秒内也会被正确标记成离线。
        """

        def _loop():
            while not self._shutting_down.wait(timeout=interval):
                for svc in list(self.registered):
                    self.heartbeat(svc.name)

        threading.Thread(target=_loop, name='heartbeat-loop', daemon=True).start()

    # ---------------- Playwright（按需启动，通过 CDP） ----------------

    def _install_browser(self, browser_type):
        """自动执行 `playwright install <browser>`，支持通过配置指定镜像源"""
        env = os.environ.copy()
        download_host = self.config.get('playwright', {}).get('download_host')
        if download_host:
            env['PLAYWRIGHT_DOWNLOAD_HOST'] = download_host

        log(f"检测到 {browser_type} 浏览器未安装，开始自动下载（第一次可能要几分钟）...")
        try:
            subprocess.run(
                [sys.executable, '-m', 'playwright', 'install', browser_type],
                check=True, env=env,
            )
            log(f"{browser_type} 下载完成")
            return True
        except subprocess.CalledProcessError as e:
            log(
                f"自动下载 {browser_type} 失败: {e}\n"
                f"  常见原因是网络被拦截（公司防火墙拦了官方 CDN），可以在配置文件的 "
                f"playwright.download_host 里填一个镜像源（比如 "
                f"https://npmmirror.com/mirrors/playwright/）后重试，"
                f"或者手动执行: python -m playwright install {browser_type}"
            )
            return False

    def _chromium_executable_path(self, browser_type):
        """借用 Playwright 定位（必要时触发下载）Chromium 可执行文件的路径

        只是查路径/确保下载好，不用 Playwright 管理浏览器的生命周期——真正启动
        浏览器是下面 _start_chrome() 里用 subprocess 起的普通 Chrome 进程。
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser_type_obj = getattr(p, browser_type)
            # BrowserType.executable_path 是 Playwright 官方公开的属性，直接告诉你
            # 这个版本的 playwright 期望的浏览器二进制具体在哪个路径——用它判断
            # "装没装"，比自己猜 ms-playwright 目录结构/版本号靠谱。
            return browser_type_obj.executable_path

    def _wait_for_cdp(self, port, timeout=30):
        """轮询 CDP 的 /json/version 接口，确认这个端口上跑的真的是 Chrome CDP

        不能只看有没有 HTTP 响应——很多本地开发服务器（webpack-dev-server、vite 之类）
        对任意路径都会返回 200 + index.html（SPA fallback），如果端口刚好被这类服务
        占用，"有响应"不代表 Chrome 真的绑定成功了，所以这里要求响应体必须是能解析出
        webSocketDebuggerUrl 的合法 CDP JSON，否则视为没就绪。
        """
        last_error = None
        for _ in range(timeout):
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1)
                if resp.ok:
                    try:
                        data = resp.json()
                    except ValueError:
                        last_error = (
                            f"端口 {port} 上有 HTTP 服务响应，但内容不是合法 JSON"
                            f"（开头: {resp.text[:60]!r}），这个端口大概率被别的服务占用了，"
                            f"不是 Chrome CDP"
                        )
                    else:
                        if 'webSocketDebuggerUrl' in data:
                            return True
                        last_error = f"端口 {port} 返回了 JSON，但不像 Chrome CDP 的响应: {data}"
            except requests.RequestException as e:
                last_error = str(e)
            time.sleep(1)
        if last_error:
            log(f"CDP 端口检测失败: {last_error}")
        return False

    def prepare_playwright(self):
        """启动控制服务之前先确保 Chromium 已经装好，只做一次

        避免每次 /launch 都重复调用 Playwright API 去查路径/装浏览器，那样会给每次
        用例执行都多出几秒不必要的开销。
        """
        pw_cfg = self.config['playwright']
        browser_type = pw_cfg.get('browser', 'chromium')
        auto_install = pw_cfg.get('auto_install', True)

        if browser_type != 'chromium':
            log(
                f"警告: CDP 按需启动目前只支持 chromium（Chrome/Edge 内核），"
                f"配置里的 \"{browser_type}\" 会被忽略，强制使用 chromium"
            )
            browser_type = 'chromium'

        executable_path = self._chromium_executable_path(browser_type)
        if not os.path.exists(executable_path):
            if not auto_install:
                raise RuntimeError(f"{browser_type} 未安装（期望路径: {executable_path}），且 auto_install=false")
            log(f"检测到 {browser_type} 浏览器未安装（期望路径: {executable_path}）")
            if not self._install_browser(browser_type):
                raise RuntimeError(f"{browser_type} 未安装成功，控制服务无法启动")
            executable_path = self._chromium_executable_path(browser_type)

        self.chromium_executable_path = executable_path
        log(f"Chromium 可执行文件已就绪: {executable_path}")

    def _start_chrome(self, headless, browser_type):
        """现开一个 Chrome 子进程，等它的 CDP 端口就绪后返回对应的 BrowserSession

        调用方（handle_launch）保证这里被调用时已经持有 _queue_lock，同一时刻只会有
        一个 Chrome 进程存在，所以固定复用配置里的端口不会冲突。
        """
        pw_cfg = self.config['playwright']
        port = pw_cfg.get('port', 9222)

        # 每次都用一个全新、独立的临时目录做 --user-data-dir，不要用固定路径。
        # Chrome 对同一个 user-data-dir 是单实例的：如果上一次的进程没被彻底关掉，
        # 下次用同一个目录再启动时，Chrome 会把这次启动请求转发给那个还活着的旧进程，
        # 新的 --remote-debugging-port 参数直接被忽略。用全新目录能从根上避免这个问题。
        profile_dir = tempfile.mkdtemp(prefix='testhub-remote-browser-')
        crash_log_path = os.path.join(profile_dir, 'chrome-output.log')

        args = [
            self.chromium_executable_path,
            f'--remote-debugging-port={port}',
            '--remote-debugging-address=0.0.0.0',
            '--remote-allow-origins=*',
            f'--user-data-dir={profile_dir}',
            '--no-first-run',
            '--no-default-browser-check',
            # 以 root / Windows 服务账号等受限身份常驻运行这个脚本时，Chrome 的沙箱经常会
            # 导致进程刚起来就自己退出——不会报错、也不会绑定 CDP 端口，表现跟"端口冲突"
            # 一模一样，很难从外面区分。这台浏览器本来就跑在受控的执行机器上，关掉沙箱可接受。
            '--no-sandbox',
            # 一些 Linux 容器/服务器的 /dev/shm 空间很小，Chrome 默认拿它做共享内存，
            # 不够用时同样会静默崩溃退出，改用磁盘临时文件规避。
            '--disable-dev-shm-usage',
        ]

        window_geometry = None
        if headless:
            args.append('--headless=new')
        else:
            # 只在有头模式下才需要探测/指定窗口大小和位置——无头模式本来就没有真实窗口，
            # 视口大小交给后端通过 Playwright viewport 控制就够了。
            window_geometry = _primary_monitor_work_area()
            if window_geometry:
                w, h, x, y = window_geometry
                args.append(f'--window-size={w},{h}')
                args.append(f'--window-position={x},{y}')
                log(f"探测到主屏幕工作区 {w}x{h}（位置 {x},{y}），Chrome 窗口将按此大小打开")
            else:
                log("未能探测到本机屏幕分辨率，Chrome 窗口大小将使用系统默认值")

        log(f"按需启动 Chromium (CDP port={port}, headless={headless}) ...")
        # 以前这里 stdout/stderr 直接扔进 DEVNULL：Chrome 启动失败时只能看到"CDP 端口
        # 检测超时"这个表面现象，完全猜不到真正原因（没有图形界面/沙箱冲突/端口冲突，
        # 表现全都一样）。现在改成写进临时目录里的文件，检测失败时读出来一起报错。
        crash_log_file = open(crash_log_path, 'wb')
        process = subprocess.Popen(
            args, stdout=crash_log_file, stderr=subprocess.STDOUT,
        )

        if not self._wait_for_cdp(port):
            exit_code = process.poll()  # 不是 None 说明 Chrome 已经自己退出了，不是还在启动中
            try:
                process.terminate()
                process.wait(timeout=10)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

            crash_log_file.flush()
            crash_log_file.close()
            crash_output = ''
            try:
                with open(crash_log_path, 'rb') as f:
                    crash_output = f.read().decode('utf-8', errors='replace').strip()
            except Exception:
                pass
            shutil.rmtree(profile_dir, ignore_errors=True)

            if exit_code is not None:
                cause_hint = (
                    f"进程已自行退出（exit code={exit_code}），说明 Chrome 启动后很快自己"
                    f"崩溃/退出了，通常不是端口冲突。常见原因：\n"
                    f"  1) 远程机器没有可用的图形界面/显示器（Linux 缺 X server/Xvfb，或 "
                    f"Windows 服务运行在非交互会话），却选择了「有头模式」——可以先改选"
                    f"「无头模式」验证是不是这个原因；\n"
                    f"  2) 以受限账号（root/服务账号）运行本脚本触发沙箱冲突（已默认加上 "
                    f"--no-sandbox，如果仍是这个报错请检查其他系统级权限限制）。"
                )
            else:
                cause_hint = (
                    f"进程还活着但端口一直没绑定成功，更像是端口冲突——机器上已经有别的"
                    f"程序占用了 {port} 端口，检查方式：`netstat -ano | findstr :{port}`"
                )
            detail = f"\nChrome 输出:\n{crash_output}" if crash_output else "\n（Chrome 没有任何输出）"
            raise RuntimeError(
                f"{port} 端口 30 秒内没有出现合法的 Chrome CDP 响应，放弃这次启动。{cause_hint}{detail}"
            )

        crash_log_file.close()  # 子进程已经继承了这个文件描述符，父进程这边关掉不影响它继续写
        session_id = uuid.uuid4().hex
        window_size = {'width': window_geometry[0], 'height': window_geometry[1]} if window_geometry else None
        return BrowserSession(session_id, process, profile_dir, port, window_size=window_size)

    def handle_launch(self, payload):
        """处理控制接口的 POST /launch：按请求里的 headless/browser 现开一个浏览器

        一次只服务一个会话：如果上一个还没关，这里会阻塞排队，等 queue_wait_timeout
        秒还排不上就直接报错，不会无限等下去。
        """
        pw_cfg = self.config['playwright']
        headless = payload.get('headless')
        if headless is None:
            headless = pw_cfg.get('default_headless', False)
        browser_type = payload.get('browser', 'chromium')
        if browser_type != 'chromium':
            log(f"警告: 按需启动目前只支持 chromium，忽略请求里的 \"{browser_type}\"")
            browser_type = 'chromium'

        queue_wait_timeout = pw_cfg.get('queue_wait_timeout', 600)
        log("等待获取浏览器排队锁...")
        acquired = self._queue_lock.acquire(timeout=queue_wait_timeout)
        if not acquired:
            raise RuntimeError(
                f"排队等待超过 {queue_wait_timeout} 秒，远程机器一直被占用，请稍后重试"
            )
        log("已获取排队锁")

        try:
            session = self._start_chrome(headless, browser_type)
        except Exception:
            self._queue_lock.release()
            raise

        relay_port = pw_cfg.get('relay_port', session.port)
        try:
            relay = CdpRelay(public_port=relay_port, chrome_port=session.port, advertise_host=self.advertise_host)
            relay.start()
            session.relay = relay
            log(f"CDP 转发层已启动: 0.0.0.0:{relay_port} -> 127.0.0.1:{session.port}")
        except Exception:
            # 转发层没起来，这次会话没法真正被外部连上，直接当启动失败处理，
            # 别忘了把已经开起来的 Chrome 也关掉、释放排队锁
            self._force_close_session(session, "CDP 转发层启动失败")
            raise

        self._current_session = session
        max_lifetime = pw_cfg.get('max_lifetime_seconds', 1800)
        timer = threading.Timer(max_lifetime, self._force_close_session, args=(session, 'max_lifetime_seconds 超时兜底'))
        timer.daemon = True
        session.timer = timer
        timer.start()

        return {
            'session_id': session.session_id,
            'cdp_url': f"http://{self.advertise_host}:{relay_port}",
            # 探测到的主屏幕工作区尺寸（有头模式才有值），后端拿它替代硬编码的视口大小，
            # 让 Playwright 侧的 viewport 跟这台机器上真实打开的窗口大小对得上
            'window_size': session.window_size,
        }

    def handle_close(self, payload):
        """处理控制接口的 POST /close：关掉当前活跃的浏览器会话、释放排队锁"""
        session = self._current_session
        if session is None:
            return {'closed': False, 'message': '当前没有活跃的浏览器会话'}

        session_id = payload.get('session_id')
        if session_id and session_id != session.session_id:
            log(
                f"警告: /close 传入的 session_id={session_id} 跟当前会话 "
                f"{session.session_id} 不一致，仍然关闭当前这个"
            )
        self._force_close_session(session, '收到 TestHub 的 /close 请求')
        return {'closed': True}

    def _force_close_session(self, session, reason):
        """真正关闭一个会话：杀进程、清理临时目录、释放排队锁

        可能被两个地方并发调用到同一个 session（TestHub 主动 /close 和
        max_lifetime_seconds 超时兜底几乎同时触发），用 session 自己的
        _cleanup_lock + _cleaned_up 保证物理清理和"释放排队锁"只发生一次。
        """
        with session._cleanup_lock:
            if session._cleaned_up:
                return
            session._cleaned_up = True

            if session.timer:
                session.timer.cancel()

            if session.relay:
                session.relay.stop()

            try:
                session.process.terminate()
                session.process.wait(timeout=10)
            except Exception:
                try:
                    session.process.kill()
                except Exception:
                    pass

            shutil.rmtree(session.profile_dir, ignore_errors=True)
            log(f"会话 {session.session_id} 已关闭（{reason}）")

        if self._current_session is session:
            self._current_session = None
        self._queue_lock.release()

    # ---------------- 控制接口（HTTP） ----------------

    def start_control_server(self):
        pw_cfg = self.config['playwright']
        control_port = pw_cfg.get('control_port', 9333)
        server = ThreadingHTTPServer(('0.0.0.0', control_port), _ControlRequestHandler)
        server.client = self  # 挂在 server 对象上，供 Handler 里的 self.server.client 取用
        self.control_server = server

        thread = threading.Thread(target=server.serve_forever, name='control-server', daemon=True)
        thread.start()
        log(f"控制接口已启动: 0.0.0.0:{control_port}（TestHub 通过它按需开/关浏览器）")

    def stop_control_server(self):
        if self.control_server:
            self.control_server.shutdown()
            self.control_server.server_close()

    def _default_service_name(self):
        """没在配置里显式指定 service_name 时，拼一个默认名字。

        以前直接用 advertise_host（纯 IP）拼名字，比如 "172.17.48.6-playwright"——
        机器一多，配置中心里一整排全是 IP，很难一眼看出哪条记录对应哪台物理机器。
        现在改成"主机名(IP地址)"，比如 "WIN-B0X01(172.17.48.6)"：主机名让人好认，
        括号里的 IP 保留下来是因为主机名可能重名/不唯一，两个一起才能唯一定位到
        具体是哪台机器。

        这里不再像早期版本那样拼 "-playwright" / "-selenium" 后缀区分服务类型：
        一是前端三个执行下拉框本来就会在展示时额外拼上 service_type_display（比如
        "WIN-B0X01(172.17.48.6) (Playwright CDP)"），名字里重复一遍类型信息只是
        视觉噪音；二是后端 register 接口的 upsert 定位键已经改成
        (project, name, service_type) 而不是只有 (project, name)，同一个客户端
        同时启用 Playwright 和 Selenium、用同一个名字注册，也不会互相覆盖。
        """
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = 'unknown-host'
        return f"{hostname}({self.advertise_host})"

    def register_playwright_control(self):
        pw_cfg = self.config['playwright']
        control_port = pw_cfg.get('control_port', 9333)
        name = pw_cfg.get('service_name') or self._default_service_name()
        control_url = f"http://{self.advertise_host}:{control_port}"
        # control_token 就是这个客户端自己的 token，TestHub 调 /launch、/close 时要带上，
        # 免得同网段其他机器也能随意调用这个接口起停 Chrome 进程
        auth_config = {'control_token': self.token}

        self.register_with_retry(name, 'playwright_cdp', control_url, auth_config=auth_config)

    # ---------------- Selenium（仍是启动时常驻，不受本次改造影响） ----------------

    def start_selenium(self):
        sel_cfg = self.config['selenium']
        jar_path = sel_cfg['jar_path']
        port = sel_cfg.get('port', 4444)
        java_bin = sel_cfg.get('java_path', 'java')
        name = sel_cfg.get('service_name') or self._default_service_name()
        path_suffix = sel_cfg.get('path_suffix', '/wd/hub')

        log(f"启动 Selenium standalone (port={port}) ...")
        self.selenium_process = subprocess.Popen(
            [java_bin, '-jar', jar_path, 'standalone', '--port', str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        ready = False
        for _ in range(30):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    ready = True
                    break
            time.sleep(1)

        if not ready:
            log("警告: Selenium Server 30 秒内没有监听端口，仍然尝试注册，请手动确认进程状态")

        advertise_url = f"http://{self.advertise_host}:{port}{path_suffix}"
        log(f"对外注册地址: {advertise_url}")

        self.register_with_retry(name, 'selenium_grid', advertise_url)

    def stop_selenium(self):
        if self.selenium_process:
            self.selenium_process.terminate()
            try:
                self.selenium_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.selenium_process.kill()

    # ---------------- 生命周期 ----------------

    def start(self):
        started_any = False

        if self.config.get('playwright', {}).get('enabled'):
            self.prepare_playwright()
            self.start_control_server()
            self.register_playwright_control()  # 注册失败会在后台重试，不阻塞这里
            started_any = True
        if self.config.get('selenium', {}).get('enabled'):
            self.start_selenium()
            started_any = True

        if not started_any:
            log("没有任何服务被启动，请检查配置文件里 playwright/selenium 的 enabled 是否为 true")
            sys.exit(1)

        heartbeat_interval = self.config.get('heartbeat_interval_seconds', 30)
        self.start_heartbeat_loop(interval=heartbeat_interval)

        log(
            "本地服务已就绪，按 Ctrl+C 退出（如果这时候还没看到\"已向 TestHub xx注册服务\"，"
            "说明注册还在后台重试，通常是 TestHub 后端暂时连不上，不影响这里已经启动的服务，"
            "等后端恢复会自动注册成功）"
        )

    def stop(self):
        log("正在退出，反注册服务并关闭浏览器会话/控制服务/子进程 ...")
        self._shutting_down.set()  # 通知还在后台重试注册的线程尽快停下来，别跟下面的反注册赛跑
        for svc in self.registered:
            self.register(svc.name, svc.service_type, svc.url, is_active=False)
        if self._current_session is not None:
            self._force_close_session(self._current_session, '客户端退出')
        self.stop_control_server()
        self.stop_selenium()
        log("已清理完毕")


class _ControlRequestHandler(BaseHTTPRequestHandler):
    """处理 TestHub 打过来的 POST /launch、POST /close 控制请求

    通过 self.server.client 拿到 start_control_server() 里挂上去的 RemoteBrowserClient
    实例；用同一个 token 做简单鉴权（Authorization: Token <token>），跟客户端调用
    TestHub API 用的是同一个值，仅用于同一个内部网络里防止误调用/乱调用。
    """

    def _client(self):
        return self.server.client

    def _check_auth(self):
        token = self._client().token
        expected = f'Token {token}'
        if not token or self.headers.get('Authorization') != expected:
            self._respond(401, {'error': '鉴权失败'})
            return False
        return True

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except ValueError:
            return {}

    def _respond(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._check_auth():
            return

        client = self._client()
        payload = self._read_json_body()
        try:
            if self.path == '/launch':
                self._respond(200, client.handle_launch(payload))
            elif self.path == '/close':
                self._respond(200, client.handle_close(payload))
            else:
                self._respond(404, {'error': 'not found'})
        except Exception as e:
            log(f"控制接口处理 {self.path} 失败: {e}")
            self._respond(500, {'error': str(e)})

    def log_message(self, format, *args):
        # 用脚本自己的 log() 输出，跟其他日志格式统一，不用 BaseHTTPRequestHandler 默认的 stderr
        log(f"控制接口 {self.address_string()} - {format % args}")


def load_config(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='TestHub 远程浏览器客户端')
    parser.add_argument(
        '--config', required=False, default=None,
        help='可选：外部配置文件路径（JSON）。不传时自动读取同目录下的 config.json，没有再用脚本里的 CONFIG 字典',
    )
    args = parser.parse_args()

    local_config = Path(__file__).resolve().parent / 'config.json'
    if args.config:
        config = load_config(args.config)
    elif local_config.exists():
        config = load_config(local_config)
        log(f"使用配置文件: {local_config}")
    else:
        config = CONFIG
    if not config.get('token'):
        log("未配置 token：请复制 config.example.json 为 config.json 并填写 TestHub 用户 Token")
        sys.exit(1)
    client = RemoteBrowserClient(config)

    def handle_signal(sig, frame):
        client.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, handle_signal)

    client.start()

    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()
