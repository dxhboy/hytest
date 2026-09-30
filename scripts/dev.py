"""TestHub 开发环境一键启动：后端 + Celery worker（两个队列）+ Celery Beat + 前端

用法（在项目根目录执行；会自动使用项目下的 venv/.venv，不要求先激活虚拟环境）：
    python scripts/dev.py                         # 启动全部服务
    python scripts/dev.py --only backend,frontend # 只启动指定服务
    python scripts/dev.py --skip ai,beat          # 跳过指定服务
    python scripts/dev.py --backend-port 8002 --frontend-port 3001

服务名：backend / worker / ai / beat / frontend
所有输出汇总到当前终端并带服务名前缀；按 Ctrl+C 停止全部服务。
Redis 需要自行提前启动（脚本启动前会检查是否可连接）。
"""
import argparse
import locale
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = sys.platform == 'win32'


def find_project_python():
    """优先使用项目虚拟环境的解释器：用系统 Python 运行本脚本时，子进程也会用系统 Python，
    而系统环境里通常没装 Django 等项目依赖（报 ModuleNotFoundError: No module named 'django'）"""
    candidates = ('venv/Scripts/python.exe', '.venv/Scripts/python.exe') if IS_WINDOWS else ('venv/bin/python', '.venv/bin/python')
    for rel in candidates:
        path = ROOT / rel
        if path.exists():
            return str(path)
    return sys.executable


PY = find_project_python()

COLORS = {
    'backend': '\033[36m',   # 青
    'worker': '\033[32m',    # 绿
    'ai': '\033[35m',        # 紫
    'beat': '\033[33m',      # 黄
    'frontend': '\033[34m',  # 蓝
}
RESET = '\033[0m'
ALL_SERVICES = list(COLORS)
_print_lock = threading.Lock()


def find_npm():
    return shutil.which('npm.cmd' if IS_WINDOWS else 'npm') or shutil.which('npm')


def build_commands(args):
    """各服务的启动命令，与 README「启动服务」一节保持一致"""
    npm = find_npm() or 'npm'
    # Windows 上 npm 是 .cmd 批处理，需经 cmd /c 执行
    npm = ['cmd', '/c', npm] if IS_WINDOWS else [npm]
    celery = [PY, '-m', 'celery', '-A', 'backend']
    # Windows 不支持 prefork，默认队列用 threads 池；ai_automation 队列受 GIF 录制文件名限制只能单并发
    worker_pool = ['--pool=threads', '--concurrency=4'] if IS_WINDOWS else ['--concurrency=4']
    return {
        'backend': ([
            PY, '-m', 'uvicorn', 'backend.asgi:application',
            '--host', args.host, '--port', str(args.backend_port), '--reload',
            # Windows + --reload 时 uvicorn 默认用 SelectorEventLoop，脚本录制启动 Playwright 会失败
            '--loop', 'backend.event_loop:loop_factory',
        ], ROOT),
        'worker': (celery + ['worker', '-Q', 'celery', *worker_pool, '--loglevel=info', '-n', 'default@%h'], ROOT),
        'ai': (celery + ['worker', '-Q', 'ai_automation', '--pool=solo', '--loglevel=info', '-n', 'ai@%h'], ROOT),
        'beat': (celery + ['beat', '--loglevel=info'], ROOT),
        'frontend': (npm + ['run', 'dev', '--', '--port', str(args.frontend_port)], ROOT / 'frontend'),
    }


def log(name, line):
    color = COLORS.get(name, '')
    with _print_lock:
        print(f'{color}[{name:<8}]{RESET} {line}', flush=True)


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


_REDIS_URL = 'redis://127.0.0.1:6379/0'


def check_python_env():
    """确认解释器里装好了项目依赖，并顺便读取 .env 中的 REDIS_URL（本脚本自身可能跑在系统 Python 上）"""
    global _REDIS_URL
    probe = (
        "import django, uvicorn, celery; from decouple import config; "
        "print(config('REDIS_URL', default='redis://127.0.0.1:6379/0'))"
    )
    result = subprocess.run([PY, '-c', probe], cwd=ROOT, capture_output=True)
    if result.returncode != 0:
        err = decode_line(result.stderr).strip().splitlines()
        log('check', f'Python 环境缺少项目依赖（{PY}）：{err[-1] if err else "未知错误"}')
        log('check', '请先创建虚拟环境并安装依赖：python -m venv venv，然后 pip install -r requirements.txt')
        return False
    _REDIS_URL = decode_line(result.stdout).strip().splitlines()[-1] or _REDIS_URL
    log('check', f'使用 Python: {PY}')
    return True


def check_redis():
    url = urlparse(_REDIS_URL)
    host, port = url.hostname or '127.0.0.1', url.port or 6379
    try:
        with socket.create_connection((host, port), timeout=2):
            return True, f'{host}:{port}'
    except OSError:
        return False, f'{host}:{port}'


def check_migrations():
    """只提示不阻断：有未执行的迁移，或模型改动还没生成迁移文件时给出命令"""
    def manage(*cmd):
        return subprocess.run([PY, 'manage.py', *cmd], cwd=ROOT, capture_output=True,
                              env=dict(os.environ, PYTHONIOENCODING='utf-8'))

    if manage('makemigrations', '--check', '--dry-run').returncode != 0:
        log('check', '有模型改动还没生成迁移文件：请执行 python manage.py makemigrations，再执行 python manage.py migrate')
    elif manage('migrate', '--check').returncode != 0:
        log('check', '有未执行的数据库迁移，相关接口会报错：请执行 python manage.py migrate')
    else:
        log('check', '数据库迁移已是最新')


def preflight(selected, args):
    ok = True
    needs_python = {'backend', 'worker', 'ai', 'beat'} & set(selected)
    if needs_python and not check_python_env():
        return False
    if needs_python:
        reachable, addr = check_redis()
        if reachable:
            log('check', f'Redis 可连接: {addr}')
        else:
            log('check', f'无法连接 Redis（{addr}），请先启动 Redis 或检查 .env 中的 REDIS_URL')
            ok = False
    if 'backend' in selected:
        check_migrations()
    for name, port in (('backend', args.backend_port), ('frontend', args.frontend_port)):
        if name in selected and port_in_use(port):
            log('check', f'端口 {port} 已被占用（{name}），请先关闭已运行的实例，或用 --{name}-port 指定其他端口')
            ok = False
    if 'frontend' in selected and not find_npm():
        log('check', '找不到 npm，请确认已安装 Node.js 18+ 并加入 PATH')
        ok = False
    if 'frontend' in selected and not (ROOT / 'frontend' / 'node_modules').exists():
        log('check', 'frontend/node_modules 不存在，请先在 frontend 目录执行 npm install')
        ok = False
    return ok


_FALLBACK_ENCODING = locale.getpreferredencoding(False) or 'utf-8'


def decode_line(raw):
    """Python/Node 子进程输出 UTF-8；Windows 下 cmd 自身的报错是本地编码（如 GBK）"""
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode(_FALLBACK_ENCODING, errors='replace')


def pump_output(name, proc):
    for raw in iter(proc.stdout.readline, b''):
        log(name, decode_line(raw).rstrip())


def start(name, cmd, cwd):
    env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', FORCE_COLOR='1')
    kwargs = {}
    if IS_WINDOWS:
        # 独立进程组：Ctrl+C 由本脚本统一处理，再按进程树停止，避免子进程收到信号后各自半途退出
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs,
    )
    threading.Thread(target=pump_output, args=(name, proc), daemon=True).start()
    log(name, f'已启动 (pid={proc.pid}): {" ".join(cmd)}')
    return proc


def stop(name, proc, timeout=10):
    if proc.poll() is not None:
        return
    log(name, '正在停止...')
    try:
        if IS_WINDOWS:
            # uvicorn --reload、npm 都会派生子进程，必须按进程树结束
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
        if not IS_WINDOWS:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def parse_services(value):
    names = [s.strip() for s in value.split(',') if s.strip()]
    unknown = set(names) - set(ALL_SERVICES)
    if unknown:
        raise argparse.ArgumentTypeError(f'未知服务: {", ".join(sorted(unknown))}，可选: {", ".join(ALL_SERVICES)}')
    return names


def main():
    parser = argparse.ArgumentParser(description='TestHub 开发环境一键启动')
    parser.add_argument('--only', type=parse_services, help='只启动这些服务（逗号分隔）')
    parser.add_argument('--skip', type=parse_services, default=[], help='跳过这些服务（逗号分隔）')
    parser.add_argument('--host', default='0.0.0.0', help='后端监听地址，默认 0.0.0.0')
    parser.add_argument('--backend-port', type=int, default=8001, help='后端端口，默认 8001（前端代理指向此端口）')
    parser.add_argument('--frontend-port', type=int, default=3000, help='前端端口，默认 3000')
    args = parser.parse_args()

    if IS_WINDOWS:
        os.system('')  # 打开 Windows 终端的 ANSI 颜色支持

    selected = [s for s in (args.only or ALL_SERVICES) if s not in args.skip]
    if not selected:
        parser.error('没有要启动的服务')
    if 'frontend' in selected and args.backend_port != 8001:
        log('check', f'注意：前端代理固定指向 8001（frontend/vite.config.js），后端改用 {args.backend_port} 时前端请求不会转发到它')
    if not preflight(selected, args):
        sys.exit(1)

    commands = build_commands(args)
    procs = {name: start(name, *commands[name]) for name in selected}
    log('dev', f'已启动: {", ".join(selected)}；前端 http://localhost:{args.frontend_port}  后端 http://localhost:{args.backend_port}  按 Ctrl+C 停止全部服务')

    stopping = threading.Event()

    def request_stop(*_):
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    if IS_WINDOWS:
        signal.signal(signal.SIGBREAK, request_stop)
    else:
        signal.signal(signal.SIGTERM, request_stop)

    reported = set()
    try:
        while not stopping.is_set():
            for name, proc in procs.items():
                if name not in reported and proc.poll() is not None:
                    reported.add(name)
                    log(name, f'进程已退出（exit code {proc.returncode}），其余服务继续运行；按 Ctrl+C 停止全部')
            if len(reported) == len(procs):
                log('dev', '所有服务都已退出')
                break
            stopping.wait(1)
    finally:
        for name, proc in procs.items():
            stop(name, proc)
        log('dev', '全部服务已停止')


if __name__ == '__main__':
    main()
