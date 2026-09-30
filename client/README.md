# TestHub 远程浏览器客户端

部署在远程执行机器（下文称"机器 B"）上的独立脚本，用于替代"手动开浏览器 / 手动搭 Selenium
Grid + 手动去配置中心填连接地址"这一整套操作。启动一次，脚本会自己：

1. 启动 Playwright 模式时会自动检测本机有没有装好 Chromium，没装会自动下载，不需要
   提前手动跑 `playwright install`；
2. **按需启动浏览器**：Playwright 模式下，脚本启动时**不会**预先开一个 Chrome 常驻着，
   只会常驻一个本地"控制接口"（HTTP，默认端口 9333）；TestHub 真正要执行用例时才会
   调用这个控制接口，把这次实际选择的"有头/无头"传过去，现开一个 Chrome，执行完再
   调用控制接口把它关掉。同一台机器一次只服务一个浏览器（串行排队），不会同时起多个
   Chrome 抢资源。Selenium 模式不受影响，仍然是启动时就常驻一个 Selenium standalone
   server（Selenium Grid 本来就是每次创建 session 时才真正拉起浏览器，有头/无头一直
   都能按每次执行的请求生效）；
3. 自动调用 TestHub 接口，把自己注册成"远程浏览器服务"，配置中心里会自动出现对应记录；
4. 常驻运行，之后每次在 TestHub 套件管理里选"远程执行"，都会自动在机器 B 上按需开关
   浏览器，不需要人工干预，"执行模式"（有头/无头）现在对远程执行也是生效的；
5. **心跳保活**：常驻期间按 `heartbeat_interval_seconds`（默认 30 秒）的固定间隔向
   TestHub 上报一次"我还活着"。这是为了跟 `is_active` 区分开：`is_active` 只是一个
   静态开关，客户端异常退出（被 kill、断电、断网，没走到 `Ctrl+C` 那一步）不会自动
   变成 `false`，TestHub 那边光看 `is_active` 分不清"客户端正常运行只是暂时没执行
   任务"和"客户端早就没了，数据库里还留着一条僵尸记录"。心跳给的是有时效性的
   `last_heartbeat`，超过一定时间没收到新心跳，TestHub 就会认为这条记录已经离线，
   自动从执行时的"远程服务"下拉框里消失，不需要人工去配置中心清理；
6. `Ctrl+C` 退出时会自动把注册记录标成 `is_active=false`，关闭当前活跃的浏览器会话（如果
   有）和控制服务/子进程，不留垂死进程也不留失效记录。即使异常退出没走到这一步，客户端
   自己也会在浏览器存活超过 `max_lifetime_seconds`（默认 30 分钟）后强制关闭，兜底防止
   Chrome 进程永久残留；心跳会随着进程消失而自然停止，TestHub 那边最多等一小段时间
   （默认 90 秒）就会把这条记录判定为离线。

> **关于跨机器连 CDP 的一个坑**（实测发现）：较新版本的 Chrome 出于安全考虑，即使传了
> `--remote-debugging-address=0.0.0.0` 也只会监听 `127.0.0.1`，不会真的对外暴露 CDP 端口——
> 这不是防火墙问题，`netstat` 能直接看到只有 `127.0.0.1:xxxx` 在 `LISTENING`。脚本现在加了
> 一层本机内部的 TCP 转发（`CdpRelay`）：Chrome 自己只监听内部端口（`playwright.port`，
> 只有 127.0.0.1，不需要开防火墙），转发层监听对外的端口（`playwright.relay_port`，需要
> 开防火墙），把流量转发过去，同时改写 Chrome 返回的 `/json/version` 里的地址（否则
> Playwright 后续单独发起的 WebSocket 连接会拿着 Chrome 自己上报的 `127.0.0.1` 去连，直接
> 失败）。这一层对使用者是透明的，不需要额外操作，只是防火墙要放行的是 `relay_port`
> 而不是 `port`（见下面"填写配置"和"常见问题"）。

> Playwright 部分为什么走 CDP：Playwright 的 Python 绑定一直没实现 Node.js/JS 版才有的
> `launch_server()`（官方长期未支持，参见 microsoft/playwright-python#469、#1149），没法
> 在 Python 里直接起一个能被 `ws://` 连接的"Playwright Remote"服务端。脚本改成直接把
> Playwright 管理的 Chromium 当普通 Chrome 进程启动、开 CDP 调试端口，注册成
> `playwright_cdp` 类型——效果跟之前教的"手动开 Chrome 调试端口"完全一样，只是这里全自动
> 化了，同时因为只需要用到 `launch()`（Python 里一直都有），所以稳定可靠。这也意味着这个
> 模式目前只支持 Chromium 内核（Chrome/Edge），不支持 Firefox/WebKit——TestHub 后端本身
> 对 CDP 也只走 Chromium，这一点是一致的。

## 前置条件（机器 B 上）

- Python 3.8+
- `pip install playwright requests`
- 如果要启用 Playwright 模式：不需要提前手动装浏览器，脚本自己会检测并下载（见下面
  `auto_install` 说明）；如果机器 B 完全没有联网权限，也可以自己先手动跑一遍
  `playwright install chromium firefox webkit`，脚本检测到已经装好就不会重复下载。
- 如果要启用 Selenium 模式：
  - Java 11+
  - 下载好的 `selenium-server-<version>.jar`。当前最新版是 4.46.0，直接下载地址：
    <https://github.com/SeleniumHQ/selenium/releases/download/selenium-4.46.0/selenium-server-4.46.0.jar>
    （更新版本看 <https://www.selenium.dev/downloads/>）。默认配置约定放在脚本同目录下的
    `lib/` 文件夹里，也就是 `scripts/remote_browser_client/lib/selenium-server-4.46.0.jar`，
    这个 `lib` 目录需要自己创建，把下载好的 jar 放进去。
  - 机器 B 上要有真实安装的 Chrome/Firefox（Selenium 本身不带浏览器，也没法像 Playwright
    那样自动下载，这一步没法自动化，需要手动确认）

## 1. 获取 API Token

登录 Django Admin（`/admin/`），进入 **AUTH TOKEN → Tokens**，为要用来注册的账号新建一个
Token，把生成的 key 填进配置文件的 `token` 字段。这是长期有效的静态 Token，不是登录密码，
也不会像 JWT 一样过期，适合给这种常驻脚本用。

## 2. 确认 project_id

打开 TestHub 前端，进入 UI 自动化测试对应的项目，看地址栏或调用一次
`GET /api/ui-automation/projects/` 接口，找到对应项目的 `id`。

## 3. 填写配置

直接打开 `remote_browser_client.py`，改文件顶部的 `CONFIG` 字典就行，不需要额外的配置文件。
（如果更喜欢配置文件和代码分开放，也可以照旧参考 `config.example.json` 写一个 JSON 文件，
运行时加 `--config 你的文件.json` 传进去，不传就直接用脚本里的 `CONFIG`。）字段含义：

- `testhub_url`：机器 A 上 Django 后端的访问地址。
- `token`：第 1 步拿到的 Token。
- `project_id`：第 2 步确认的项目 ID。
- `advertise_host`：机器 B 在局域网里**真实可达**的 IP。注意不要填 Docker/WSL2 的虚拟网卡
  地址（常见的坑是 `172.17.x.x` 这种默认桥接网段，那是虚拟适配器地址，机器 A 连不进来），
  用 `ipconfig` 找跟机器 A 同网段的那张网卡。
- `heartbeat_interval_seconds`：常驻期间上报心跳的间隔（秒），默认 30。要跟 TestHub 后端
  判定"离线"的阈值配合（默认 90 秒，即 3 倍心跳间隔），不需要跟着改的话保持默认就行；
  如果改大了这个值，记得同步确认后端阈值够不够用，否则会出现"客户端明明还活着，
  却被判定成离线"的误判。
- `playwright` / `selenium`：按需把 `enabled` 设成 `true`，两个可以同时开，也可以只开一个。
- `playwright.service_name` / `selenium.service_name`：留空字符串 `""`（默认值）就会自动拼一个
  "主机名(IP地址)"的服务名，比如主机名是 `WIN-B0X01`、`advertise_host` 填的是
  `192.168.1.50`，Playwright 和 Selenium 两个服务默认会注册成同一个名字
  `WIN-B0X01(192.168.1.50)`——不用担心两个服务类型互相覆盖，也不需要在名字里再拼
  `-playwright`/`-selenium` 后缀区分，TestHub 那边执行时选择远程服务的下拉框本来就会
  在名字后面额外显示服务类型（比如"WIN-B0X01(192.168.1.50) (Playwright CDP)"），
  同一个名字对应两条不同服务类型的记录也能正常并存、分别更新；主机名让人一眼就能
  认出是哪台机器，括号里的 IP 用来在主机名重名/不唯一时兜底区分，不用自己再想名字；
  也可以填个自定义名字覆盖掉这个默认行为。
- `playwright.auto_install`：默认 `true`。脚本启动时会检查本机是否已经下载了对应的浏览器
  二进制（用 `browser_type.executable_path` 判断，不需要关心 `chromium-1200` 这种具体
  revision 号），没装会自动跑一次 `playwright install <browser>`。想自己手动管理就设成
  `false`。
- `playwright.download_host`：如果自动下载因为网络被拦截而失败（常见于公司防火墙拦了
  官方 CDN），填一个镜像源地址，比如 `https://npmmirror.com/mirrors/playwright/`，脚本
  会把它设成 `PLAYWRIGHT_DOWNLOAD_HOST` 环境变量再重试下载。不需要就留空字符串。
- `playwright.port`：按需启动 Chrome 时用的**内部** CDP 端口，Chrome 只会监听
  `127.0.0.1`，不需要开防火墙。因为一次只服务一个浏览器，固定用这一个端口不会冲突。
- `playwright.relay_port`：**对外暴露**的转发端口，TestHub 实际连的是这个端口，需要开
  防火墙。客户端内部会起一个转发层把这个端口的流量转发到上面的 `port`（见前面"关于跨
  机器连 CDP 的一个坑"）。
- `playwright.control_port`：客户端自己的控制接口端口，TestHub 通过它按需开/关浏览器
  （不是 CDP 地址本身）。默认 `9333`，需要开防火墙。
- `playwright.default_headless`：TestHub 发起的 `/launch` 请求里没带 `headless` 参数时的
  兜底值（正常情况下 TestHub 会带上执行对话框里选的"执行模式"，用不到这个兜底值）。
- `playwright.max_lifetime_seconds`：单个浏览器最长存活时间（秒），超过就强制关闭，
  防止 TestHub 那边异常/网络中断导致的进程泄漏。默认 1800（30 分钟）。
- `playwright.queue_wait_timeout`：排队等待上一个会话释放的最长时间（秒），超时直接给
  TestHub 返回错误，不会无限等下去。默认 600（10 分钟）。
- `selenium.jar_path`：默认值 `lib/selenium-server-4.46.0.jar` 是相对路径，相对的是
  **运行脚本时的当前工作目录**，不是脚本文件所在目录。按"用法"里的方式在
  `scripts/remote_browser_client/` 目录下直接运行 `python remote_browser_client.py ...`
  就没问题；如果打算从别的目录运行，把这里换成绝对路径更保险。

## 4. 运行

```bash
python remote_browser_client.py
```

看到类似下面的输出说明成功了：

```
[remote-client] Chromium 可执行文件已就绪: C:\Users\xxx\AppData\Local\ms-playwright\chromium-xxxx\chrome-win\chrome.exe
[remote-client] 控制接口已启动: 0.0.0.0:9333（TestHub 通过它按需开/关浏览器）
[remote-client] 已向 TestHub 创建注册服务 "WIN-B0X01(192.168.1.50)" -> http://192.168.1.50:9333
[remote-client] 全部就绪，按 Ctrl+C 退出（退出时会自动向 TestHub 反注册、关闭当前浏览器会话和控制服务）
```

注意这里**不会**出现"启动 Chromium"的日志——浏览器现在是执行用例的时候才现开。真正执行
的时候会看到类似：

```
[remote-client] 等待获取浏览器排队锁...
[remote-client] 已获取排队锁
[remote-client] 按需启动 Chromium (CDP port=9222, headless=True) ...
[remote-client] 会话 3f2a... 已关闭（收到 TestHub 的 /close 请求）
```

这时去 TestHub 配置中心 → 远程浏览器服务，应该已经能看到自动出现的这条记录，不需要手动
添加。之后套件管理里选"远程执行"，选这条服务，"执行模式"（有头/无头）选的值会真正传给
机器 B，按需开关浏览器。

> **安全提醒**：`token` 请写在同目录的 `config.json` 里（复制 `config.example.json` 改名得到，
> 已被 `.gitignore` 忽略；脚本不传 `--config` 时会自动读取它），不要写进 `remote_browser_client.py`
> 的 `CONFIG` 字典再提交/分享，避免真实 Token 泄露；泄露了就回 Django Admin 的 Tokens 页面删掉重建一个。这个 `token` 现在还多了
> 一层用途：客户端注册时会把它作为 `control_token` 存进 TestHub 的远程服务记录里，TestHub
> 调用控制接口的 `/launch`、`/close` 时要带上同一个值做鉴权，防止同网段其他机器随意调用
> 这个接口起停 Chrome 进程——这意味着这个 token 泄露的影响范围比之前大了一点（不只是能
> 冒充身份调 TestHub API，还能直接操控机器 B 上的浏览器进程），更要注意保管。

## 常驻 / 开机自启

这个脚本本身要一直挂着才有效。建议：

- Windows：用任务计划程序设置"登录时启动"，或者用 NSSM 包装成 Windows 服务。
- Linux：写个简单的 systemd unit，`Restart=always`。

## 常见问题

- **防火墙**：机器 B 要放行两个端口的入站连接——`playwright.control_port`（默认 9333，
  TestHub 靠它按需开/关浏览器）和 `playwright.relay_port`（默认 9222，转发层对外的端口，
  浏览器活着的时候 TestHub 实际连的是这个端口）；**`playwright.port`（默认 19222，
  Chrome 自己的内部端口）不需要开防火墙，也开不通——Chrome 只监听 127.0.0.1**。
  Selenium 模式再加上 `selenium.port`（默认 4444）。
- **`netstat` 显示只有 127.0.0.1:xxxx 在 LISTENING，没有 0.0.0.0**：这是前面提到的
  "较新 Chrome 不接受 `--remote-debugging-address=0.0.0.0`"那个坑，不是防火墙问题，
  现在已经靠 `CdpRelay` 转发层绕过了，不需要额外处理；如果你查的是
  `playwright.port`（内部端口）本来就该只有 127.0.0.1，查的应该是
  `playwright.relay_port`（对外端口）——转发层进程如果没起来才会导致这个端口上什么都没有，
  去客户端日志里找 "CDP 转发层已启动" 这一行确认。
- **执行时报"提交执行任务失败"/连不上机器 B**：先确认控制接口本身是不是活的
  （`curl -X POST http://机器B的IP:9333/launch -H "Authorization: Token 你的token"
  -d '{}'`，能拿到 `cdp_url` 说明控制接口正常）；如果控制接口都连不上，按
  `advertise_host 填错` 那一条排查。
- **启动时报"注册服务失败"但没有直接退出**：这是正常的——本地的控制接口/Selenium 已经
  启动成功了，只是这一次向 TestHub 注册没打通（最常见的原因是 TestHub 后端这时候还没
  启动，或者刚好在重启/热重载）。客户端会在后台每隔几秒自动重试，不需要手动重启客户端；
  等 TestHub 后端恢复正常，日志里会自动出现"已向 TestHub 创建注册服务"。如果一直没恢复，
  按 `advertise_host 填错` 那一条排查 `testhub_url`/网络是否有问题。
- **一直卡在"等待获取浏览器排队锁"**：说明上一个执行请求还没释放浏览器——可能是上一个
  用例还在跑，也可能是 TestHub 那边异常退出没调用到 `/close`。正常情况下会在
  `max_lifetime_seconds`（默认 30 分钟）之后被兜底强制关闭并释放排队锁，等一下会自动
  恢复；如果不想等，可以直接重启客户端脚本（会清掉当前排队状态）。
- **端口被占用导致的"connect_over_cdp ... is not valid JSON"**：TestHub 执行时报
  `Unexpected token '<', "<!DOCTYPE "... is not valid JSON`，说明 `playwright.port`
  这个端口上其实跑的不是 Chrome CDP，而是别的服务（很多本地开发服务器对任意路径都会
  返回一段 HTML，包括 `/json/version` 这个 CDP 专用路径，看起来像是"有响应"，其实是
  假的）。脚本按需启动时会自己校验响应是否为合法 CDP JSON，校验不过这次 `/launch` 会
  直接失败并报错，日志里会提示用 `netstat -ano | findstr :端口号` 排查是不是被别的进程
  占用了；确认冲突后把 `playwright.port` 换成一个不常用的端口（避开
  3000/8080/5173/4200 这类常见开发端口）重启客户端即可。
- **advertise_host 填错**：表现是 TestHub 侧点"测试连接"报 `ECONNREFUSED` 或超时，先在机器 A
  上用 `Test-NetConnection -ComputerName 机器B的IP -Port 端口` 验证端口能不能连通，跟这个
  脚本本身无关。
- **Selenium 地址后缀**：不同 Selenium 版本对 `/wd/hub` 路径的支持不完全一致，如果注册后测试
  连接失败，把配置里的 `path_suffix` 改成空字符串 `""` 再试一次。
- **想换台机器跑**：把 `advertise_host` 改成新机器的 IP，重新运行即可，`service_name` 不变
  的话会直接覆盖更新旧记录，不会产生重复项。
