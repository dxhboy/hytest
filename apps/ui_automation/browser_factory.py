"""
浏览器连接工厂
统一封装本地/远程浏览器创建逻辑，供 SeleniumTestEngine 和 PlaywrightTestEngine 复用。

- remote_service 为 None 时：走本地创建逻辑（与原 selenium_engine.py / playwright_engine.py
  的 start() 方法保持完全一致的行为，逐项保留所有浏览器选项）。
- remote_service 不为 None 时：根据 RemoteBrowserService.service_type 走不同的远程连接方式
  （Selenium Grid / BrowserStack / Sauce Labs / Playwright Remote / Playwright CDP）。
"""
import asyncio
import logging
import platform
import re
import subprocess

from selenium import webdriver

logger = logging.getLogger(__name__)


def _primary_monitor_work_area():
    """尽力探测"本地执行"这台机器（跑 Django/Celery 的机器）主显示器的工作区大小
    （不含任务栏/Dock），用于让本地有头浏览器窗口正好匹配这台机器实际的屏幕分辨率，
    不再固定用 1920x1080——如果这台机器的屏幕比 1920x1080 小，之前就会出现窗口比
    屏幕还大的问题。

    跟 client/remote_browser_client.py 里的同名函数逻辑完全一致，这里单独复制一份：
    那个脚本按设计要求"不依赖 TestHub/Django 后端代码"独立运行在别的机器上，这边的
    Django 进程也没有理由反过来依赖那个独立脚本，所以两边各自维护一份，不做成共享模块。

    探测失败（无图形环境、未知平台、命令不存在等）时返回 None，调用方应该退回原来
    "固定尺寸"的旧行为，不会比现在更差。
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
        logger.warning(f"探测本机主屏幕分辨率失败，本地有头浏览器窗口大小将使用默认值: {e}")
    return None


class BrowserConnectionFactory:
    """浏览器连接工厂"""

    @staticmethod
    def create_selenium_driver(browser_type='chrome', headless=True, remote_service=None):
        """
        创建 Selenium WebDriver（本地或远程）

        Args:
            browser_type: 浏览器类型 (chrome, firefox, safari, edge)
            headless: 是否无头模式
            remote_service: RemoteBrowserService 实例，为 None 时使用本地浏览器

        Returns:
            selenium.webdriver 的 WebDriver 实例
        """
        if remote_service is None:
            return _create_local_selenium(browser_type, headless)

        service_type = remote_service.service_type
        if service_type == 'selenium_grid':
            return _create_grid_driver(remote_service, browser_type, headless)
        elif service_type in ('browserstack', 'saucelabs'):
            return _create_cloud_driver(remote_service, browser_type, headless, provider=service_type)
        raise ValueError(f"Selenium does not support service_type: {service_type}")

    @staticmethod
    async def create_playwright_browser(playwright_instance, browser_type='chromium', headless=True, remote_service=None):
        """
        创建 Playwright Browser（本地或远程）

        Args:
            playwright_instance: 已启动的 Playwright 实例（async_playwright().start() 的返回值）
            browser_type: 浏览器类型 (chromium, firefox, webkit)
            headless: 是否无头模式
            remote_service: RemoteBrowserService 实例，为 None 时使用本地浏览器

        Returns:
            playwright.async_api.Browser 实例（不包含 context/page，由调用方创建）
        """
        if remote_service is None:
            return await _create_local_playwright(playwright_instance, browser_type, headless)

        service_type = remote_service.service_type
        if service_type == 'playwright_remote':
            return await _connect_playwright_remote(playwright_instance, remote_service)
        elif service_type == 'playwright_cdp':
            return await _connect_playwright_cdp(playwright_instance, remote_service, headless, browser_type)
        raise ValueError(f"Playwright does not support service_type: {service_type}")

    @staticmethod
    async def create_playwright_context_and_page(browser, remote_service=None, viewport=None, user_agent=None):
        """统一的"创建 BrowserContext + Page"入口。

        PlaywrightTestEngine.start() 和 test_executor.py 的套件执行循环都要调用这里，
        不要各自再写一遍 browser.new_context() + new_page()。

        踩过的坑（按时间顺序记录，方便以后别再踩）：
        1. 远程客户端起 Chrome 子进程时没有带任何 URL，Chrome 自己会先打开一个默认窗口
           （空白新标签页），connect_over_cdp 连上来的时候这个窗口/默认 context 就已经
           存在了。如果这里直接调 browser.new_context()，Playwright 会再开一个独立的
           隐身窗口——用户在远程机器屏幕上看到的就是"打开了两次浏览器"。
        2. 第 1 步的第一版修复是"复用/在这个默认 context 里新建 page"，想避免多开一个
           context。上线后发现执行仍然会报 "Target page, context or browser has been
           closed"，一度怀疑是这个默认 context 本身不稳定，改回了下面这种"新建 context
           + 事后关掉默认窗口"的写法——但改完之后同样的报错还是在同一个位置出现（导航、
           某个长时间的 wait 步骤都成功之后，紧跟着的下一步操作立刻报连接已关闭），说明
           当时"默认 context 不稳定"只是误判，真正原因见下面第 4 点。这两种写法在"避免
           打开两次窗口"这件事上都是对的，保留现在这种是因为它更接近本来就验证过没问题
           的旧行为，风险更小。
        3. 测试用的 context/page 用 browser.new_context() + new_page() 创建；额外做的
           事情只是把 Chrome 自己那个默认窗口的标签页关掉，消除"打开两次"的视觉重复，
           不去动、也不在它上面创建任何东西。本地 launch() 启动的浏览器这里天然没有
           默认 context，下面这段清理逻辑对它是没有任何影响的空操作。
        4. 一度怀疑真正原因是"远程执行时测试步骤之间（典型的是一个几十秒的固定 wait
           步骤）如果完全没有 CDP 通信，网络路径上的防火墙/NAT 会把空闲连接断掉"，
           加了下面的 _th_keepalive_task 做后台保活，跟 context 创建方式完全没关系。
           保活能缓解但没能根治——最终定位到真正的根因其实在
           client/remote_browser_client.py 的 CdpRelay._proxy_raw()：转发层自己给
           两个 socket 都留了一个 10 秒的 recv 超时没清掉，只要某个方向连续 10 秒没
           新数据，转发层自己就会把这个完全正常的连接当成"断了"关掉——跟网络环境、
           跟这里怎么创建 context 都没关系，是转发层自己在定期"误杀"。这个根因已经在
           那个文件里修掉了，这里的 _th_keepalive_task 作为额外的保险手段留着，
           不去掉（万一真的遇到网络层面的空闲断连，它还是有用的）。
        """
        # 记录下"这次创建新 context 之前，浏览器上已经存在哪些 context"——对远程 CDP
        # 场景这就是 Chrome 自带的默认窗口；对本地 launch() 的浏览器这里本来就是空列表。
        stale_contexts = list(browser.contexts)

        # 优先用探测到的真实屏幕尺寸（远程执行来自客户端探测机器 B 的屏幕，本地执行
        # 来自 _create_local_playwright() 探测机器 A 自己的屏幕），这样视口大小跟这台
        # 机器上真实打开的窗口大小是对得上的，不会出现"窗口比屏幕还大"的问题；探测
        # 失败（无头模式/无图形环境/未知平台）时 _th_window_size 不存在，退回调用方
        # 传入的默认视口。
        effective_viewport = getattr(browser, '_th_window_size', None) or viewport

        context = await browser.new_context(viewport=effective_viewport, user_agent=user_agent)
        page = await context.new_page()

        for stale_context in stale_contexts:
            for stale_page in list(stale_context.pages):
                try:
                    # 同样套个超时：这一步只是为了消除视觉上的重复窗口，不是关键路径，
                    # 不能让它卡住导致整个用例都跑不起来（万一 Chrome 那边对这个
                    # 默认标签页的关闭请求没有正常响应）
                    await asyncio.wait_for(stale_page.close(), timeout=5)
                except Exception:
                    pass  # 旧标签页可能已经被 Chrome 自己关掉了，或者这一步超时，忽略即可

        if remote_service is not None:
            # 挂在 browser 上，close_playwright_browser() 里会负责取消掉，不会残留任务
            browser._th_keepalive_task = asyncio.ensure_future(_keepalive_loop(page))

        return context, page


def _create_local_selenium(browser_type, headless):
    """
    本地创建 Selenium WebDriver。

    完整迁移自原 selenium_engine.py SeleniumTestEngine.start() 方法中的浏览器创建逻辑，
    逐项保留所有 Chrome/Firefox/Edge/Safari 选项，确保行为完全一致。
    """
    import os
    # 延迟导入，避免与 selenium_engine 模块产生循环导入
    from .selenium_engine import SeleniumTestEngine

    # 配置webdriver_manager使用本地缓存，避免每次下载
    os.environ['WDM_LOG_LEVEL'] = '0'  # 减少日志输出
    os.environ['WDM_PRINT_FIRST_LINE'] = 'False'  # 不打印首行信息

    # 先检查浏览器是否可用
    is_available, error_msg = SeleniumTestEngine.check_browser_available(browser_type)
    if not is_available:
        logger.error(f"浏览器不可用: {error_msg}")
        # 提供安装建议
        install_tips = {
            'chrome': 'brew install --cask google-chrome',
            'firefox': 'brew install --cask firefox',
            'edge': 'brew install --cask microsoft-edge',
        }
        tip = install_tips.get(browser_type, '')
        full_error = f"{error_msg}\n\n💡 安装命令（macOS）：{tip}" if tip else error_msg
        raise Exception(full_error)

    # 有头模式下尽量按这台机器真实的屏幕大小打开窗口，不再固定 1920x1080——避免这台
    # 机器屏幕比 1920x1080 小的时候窗口开得比屏幕还大。探测失败或者无头模式（没有
    # 可见窗口，用什么尺寸都无所谓）就退回原来固定的 1920x1080。
    window_width, window_height = 1920, 1080
    if not headless:
        geometry = _primary_monitor_work_area()
        if geometry:
            window_width, window_height = geometry[0], geometry[1]

    if browser_type == 'chrome' or browser_type not in ('firefox', 'edge', 'safari'):
        # 默认（含未知 browser_type）也使用 Chrome，与显式 'chrome' 分支完全一致
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'--window-size={window_width},{window_height}')

        # 禁用自动化特征检测
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)

        # 禁用密码保存和泄露提醒（解决弹框遮挡元素的问题）
        prefs = {
            'credentials_enable_service': False,  # 禁用密码保存服务
            'profile.password_manager_enabled': False,  # 禁用密码管理器
            'profile.default_content_setting_values.notifications': 2,  # 禁用通知
            'autofill.profile_enabled': False,  # 禁用自动填充
            'profile.default_content_setting_values.automatic_downloads': 1,  # 允许自动下载
            'password_manager_leak_detection': False,  # 禁用密码泄露检测（prefs级别）
            'safebrowsing.enabled': False,  # 禁用安全浏览（可能触发密码警告）
        }
        options.add_experimental_option('prefs', prefs)

        # 禁用密码泄露检查和其他安全警告（更全面的设置）
        options.add_argument('--disable-features=PasswordLeakDetection')  # 禁用密码泄露检测
        options.add_argument('--disable-features=PrivacySandboxSettings4')  # 禁用隐私沙盒
        options.add_argument('--disable-features=TranslateUI')  # 禁用翻译提示
        options.add_argument('--disable-infobars')  # 禁用信息栏
        options.add_argument('--disable-save-password-bubble')  # 禁用保存密码气泡
        options.add_argument('--disable-password-generation')  # 禁用密码生成
        options.add_argument('--disable-password-manager-reauthentication')  # 禁用密码管理器重新认证

        # 额外的安全警告抑制
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_argument('--disable-popup-blocking')  # 禁用弹窗拦截（避免某些警告）
        options.add_argument('--disable-notifications')  # 禁用所有通知

        # 使用缓存优先策略
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

    elif browser_type == 'firefox':
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
        from webdriver_manager.firefox import GeckoDriverManager

        options = Options()
        if headless:
            options.add_argument('--headless')
        options.add_argument(f'--width={window_width}')
        options.add_argument(f'--height={window_height}')

        # 性能优化：禁用不必要的功能加快启动速度
        options.set_preference('browser.cache.disk.enable', False)
        options.set_preference('browser.cache.memory.enable', True)
        options.set_preference('browser.cache.offline.enable', False)
        options.set_preference('network.http.use-cache', False)
        options.set_preference('browser.startup.homepage', 'about:blank')
        options.set_preference('startup.homepage_welcome_url', 'about:blank')
        options.set_preference('startup.homepage_welcome_url.additional', 'about:blank')
        # 禁用自动更新检查
        options.set_preference('app.update.auto', False)
        options.set_preference('app.update.enabled', False)
        # 禁用扩展和插件检查
        options.set_preference('extensions.update.enabled', False)
        options.set_preference('extensions.update.autoUpdateDefault', False)

        # 使用缓存优先策略
        service = Service(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)

    elif browser_type == 'edge':
        from selenium.webdriver.edge.options import Options
        from selenium.webdriver.edge.service import Service
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

        options = Options()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument(f'--window-size={window_width},{window_height}')

        # 使用缓存优先策略，7天内不重新下载
        service = Service(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)

    elif browser_type == 'safari':
        # Safari 不支持 headless 模式
        # 需要先启用：sudo safaridriver --enable
        # 并在 Safari 设置 -> 开发菜单中启用"允许远程自动化"
        try:
            driver = webdriver.Safari()
            driver.set_window_size(window_width, window_height)
        except Exception as e:
            error_msg = str(e)
            if 'Could not create a session' in error_msg or 'InvalidSessionIdException' in error_msg:
                raise Exception(
                    "Safari 远程自动化未启用。\n\n"
                    "请按以下步骤配置：\n"
                    "1. 在终端执行: sudo safaridriver --enable\n"
                    "2. 打开 Safari → 设置 → 高级 → 勾选'在菜单栏中显示开发菜单'\n"
                    "3. Safari 菜单栏 → 开发 → 勾选'允许远程自动化'\n\n"
                    f"原始错误: {error_msg}"
                )
            raise

    return driver


async def _create_local_playwright(playwright_instance, browser_type, headless):
    """
    本地创建 Playwright Browser。

    完整迁移自原 playwright_engine.py PlaywrightTestEngine.start() 方法中的浏览器启动逻辑。
    仅返回 Browser 实例，context/page 由调用方（PlaywrightTestEngine）创建。
    """
    # 根据浏览器类型选择启动方式
    if browser_type == 'chromium':
        browser_launcher = playwright_instance.chromium
    elif browser_type == 'firefox':
        browser_launcher = playwright_instance.firefox
    elif browser_type == 'webkit':
        browser_launcher = playwright_instance.webkit
    else:
        browser_launcher = playwright_instance.chromium

    # 启动浏览器
    browser = await browser_launcher.launch(
        headless=headless,
        args=['--disable-blink-features=AutomationControlled']  # 避免被检测
    )

    if not headless:
        # 有头模式才需要关心真实屏幕大小——无头模式没有可见窗口，用什么视口都无所谓。
        # 探测到的尺寸挂在 browser 上，create_playwright_context_and_page() 里已经有
        # "优先用 _th_window_size，没有才退回调用方传入的默认视口"这段逻辑（原本是给
        # 远程执行用的），这里复用同一套机制，不用再改那边的代码。
        geometry = _primary_monitor_work_area()
        if geometry:
            width, height, _x, _y = geometry
            browser._th_window_size = {'width': width, 'height': height}

    return browser


def _build_selenium_options(browser_type, headless):
    """为远程连接（Selenium Grid / 云厂商）构建基础浏览器 Options"""
    if browser_type == 'chrome':
        from selenium.webdriver.chrome.options import Options
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        return options

    elif browser_type == 'firefox':
        from selenium.webdriver.firefox.options import Options
        options = Options()
        if headless:
            options.add_argument('--headless')
        return options

    elif browser_type == 'edge':
        from selenium.webdriver.edge.options import Options
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        return options

    else:
        from selenium.webdriver.chrome.options import Options
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        return options


def _create_grid_driver(remote_service, browser_type, headless):
    """连接 Selenium Grid"""
    options = _build_selenium_options(browser_type, headless)
    for k, v in (remote_service.capabilities or {}).items():
        options.set_capability(k, v)
    driver = webdriver.Remote(command_executor=remote_service.url, options=options)
    driver.implicitly_wait(3)
    return driver


def _create_cloud_driver(remote_service, browser_type, headless, provider):
    """连接云端 Selenium 服务（BrowserStack / Sauce Labs）"""
    options = _build_selenium_options(browser_type, headless)
    auth = remote_service.auth_config or {}
    if provider == 'browserstack':
        bstack_options = {'userName': auth.get('username', ''), 'accessKey': auth.get('access_key', '')}
        bstack_options.update(remote_service.capabilities or {})
        options.set_capability('bstack:options', bstack_options)
    elif provider == 'saucelabs':
        sauce_options = {'username': auth.get('username', ''), 'accessKey': auth.get('access_key', '')}
        sauce_options.update(remote_service.capabilities or {})
        options.set_capability('sauce:options', sauce_options)
    driver = webdriver.Remote(command_executor=remote_service.url, options=options)
    driver.implicitly_wait(3)
    return driver


async def _connect_playwright_remote(playwright_instance, remote_service):
    """连接 Playwright Remote（ws_endpoint）"""
    browser = await playwright_instance.chromium.connect(ws_endpoint=remote_service.url)
    return browser


async def _keepalive_loop(page, interval=10):
    """远程执行专用的后台保活循环。

    背景：测试步骤之间——最典型的是一个几十秒的固定 wait 步骤——如果完全没有任何 CDP
    通信，机器 A（TestHub/Celery）和机器 B（远程客户端）之间网络路径上的防火墙/NAT/
    负载均衡等中间设备，很容易把"空闲太久"的连接悄悄断掉。下一步操作一发 CDP 命令就会
    报 "Target page, context or browser has been closed"，跟浏览器/页面本身没关系，
    纯粹是网络层面的连接已经死了。

    这里用最省事的办法验证/维持"连接还活着"：每隔 interval 秒读一次页面标题——这是个
    只读、几乎零开销的 CDP 调用，不会对正在跑的测试产生任何副作用。

    由 create_playwright_context_and_page() 创建、挂在 browser._th_keepalive_task
    上，close_playwright_browser() 负责取消，避免任务残留。

    这里故意不会因为某一次 page.title() 失败就自己退出循环：失败可能只是当时正好在
    导航、页面上下文被销毁重建之类的瞬时状态，不代表连接真的断了——真退出循环会导致
    "本来只是这一次保活没打成功，后面的长时间等待又没人保活了"，反而失去了这个函数的
    意义。只有外部显式 cancel()（浏览器正常关闭时）才会停下来。
    """
    while True:
        await asyncio.sleep(interval)
        try:
            # 显式套一个超时：如果连接是那种"被中间设备悄悄丢弃、没有正常 TCP
            # FIN/RST"的死法，page.title() 会一直挂着没有响应也没有异常，这个保活
            # 调用自己就会卡死，反而失去了保活的意义。用 wait_for 保证这里最多等
            # interval 秒就放弃这一轮，不会拖慢下一次心跳。
            await asyncio.wait_for(page.title(), timeout=interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # 忽略：可能只是瞬时状态，不代表连接已经真的断了，下一轮再试


def _remote_control_headers(remote_service):
    """远程客户端控制接口（/launch、/close）的鉴权头

    control_token 是客户端注册自己时（RemoteBrowserServiceViewSet.register）顺带写进
    auth_config 里的，跟客户端配置文件里的 token 是同一个值——只是内部网络里做个简单
    校验，防止同网段其他机器随意调用这个接口起停 Chrome 进程。
    """
    token = (remote_service.auth_config or {}).get('control_token', '')
    return {'Authorization': f'Token {token}'} if token else {}


async def _connect_playwright_cdp(playwright_instance, remote_service, headless, browser_type):
    """通过远程客户端的"控制接口"按本次执行的条件现开一个浏览器，再用 CDP 连接上去

    历史上这里是直接 `connect_over_cdp(remote_service.url)`——远程客户端在自己启动时就
    预先开好了一个固定 headless 配置的 Chrome，`remote_service.url` 存的就是那个 Chrome
    的 CDP 地址，导致：(1) 远程执行的有头/无头设置完全不生效，取决于客户端启动时的固定
    配置；(2) 客户端一启动就常驻一个浏览器进程，不用的时候也占着资源。

    现在改成"按需启动"：`remote_service.url` 存的是远程客户端的控制接口地址（不是 CDP
    地址），这里先 POST /launch 把本次实际选择的 headless/browser 传过去，客户端现开一个
    浏览器后把这次专属的 CDP 地址回传回来，再拿这个地址去 connect_over_cdp。

    远程客户端目前是"一次只服务一个浏览器"（串行排队，见客户端脚本里的说明）：如果这台
    机器上一个用例还没执行完，这次 /launch 请求会在客户端那边阻塞排队，所以这里的超时
    给得比较长（覆盖排队等待+浏览器启动两段时间）。
    """
    import httpx

    base_url = remote_service.url.rstrip('/')
    headers = _remote_control_headers(remote_service)

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{base_url}/launch",
            json={'headless': headless, 'browser': browser_type},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    cdp_url = data['cdp_url']
    session_id = data.get('session_id')
    window_size = data.get('window_size')  # 远程客户端探测到的主屏幕工作区尺寸，可能是 None

    try:
        browser = await playwright_instance.chromium.connect_over_cdp(endpoint_url=cdp_url)
    except Exception:
        # /launch 已经成功了（远程 Chrome 真的起来了、排队锁也被占住了），但这一步
        # connect_over_cdp 失败——常见原因是 launch 时探测用的是客户端自己的
        # 127.0.0.1，这里换成外部地址后防火墙/网络不通。不管什么原因，既然浏览器
        # 已经在远程占着了，这里必须显式告诉客户端 /close 把它关掉、释放排队锁，
        # 否则要一直等到客户端自己的 max_lifetime_seconds 兜底超时（默认 30 分钟）
        # 才会释放，期间这台远程机器没法再服务任何新的执行请求。
        await _close_remote_session(remote_service, session_id)
        raise

    # 挂一个私有属性记下这次会话信息，供 close_playwright_browser() 用完之后
    # 显式调用远程客户端的 /close 接口——Playwright 对 CDP 连接的 browser.close()
    # 只是断开客户端这一侧的连接，不会真正杀掉远程那边的 Chrome 进程。
    browser._th_remote_session = {'remote_service': remote_service, 'session_id': session_id}
    browser._th_window_size = window_size
    return browser


async def _close_remote_session(remote_service, session_id):
    """真正发出 POST /close 请求，通知远程客户端把对应会话关掉、释放排队锁

    release_playwright_cdp_session()（正常收尾路径）和 _connect_playwright_cdp()
    的异常分支（connect_over_cdp 失败时的兜底）都调用这个函数，避免重复代码。
    """
    import httpx

    base_url = remote_service.url.rstrip('/')
    headers = _remote_control_headers(remote_service)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/close",
                json={'session_id': session_id},
                headers=headers,
            )
            resp.raise_for_status()
    except Exception as e:
        logger.warning(
            f"释放远程浏览器会话失败（远程 Chrome 进程要等客户端的超时兜底才会被清理）: {e}"
        )


async def release_playwright_cdp_session(browser):
    """如果这个 browser 是通过远程客户端按需启动的（见 _connect_playwright_cdp），
    执行结束后调用这个函数通知远程客户端把对应的浏览器进程真正关掉、释放排队锁。

    远程客户端本身也维护了一个最大生命周期的兜底定时器：即使这里因为异常/进程被杀掉
    没能调用到，浏览器最终也会被客户端自己强制清理掉，不会永久占着不释放。
    """
    session = getattr(browser, '_th_remote_session', None)
    if not session:
        return
    await _close_remote_session(session['remote_service'], session.get('session_id'))


async def close_playwright_browser(browser):
    """统一的 Playwright Browser 关闭入口。

    本地浏览器/playwright_remote：等价于直接 await browser.close()。
    playwright_cdp 按需启动的远程浏览器：browser.close() 之外，额外调用远程客户端的
    /close 接口真正关掉远程 Chrome 进程、释放排队锁——两步各自 try/except，
    一步失败不影响另一步执行，避免因为断连异常导致远程会话一直没被释放。

    如果 create_playwright_context_and_page() 给这个 browser 挂了后台保活任务
    （_th_keepalive_task，见该函数说明），这里第一步就取消掉，避免浏览器关闭之后
    任务还在空转。
    """
    if browser is None:
        return

    keepalive_task = getattr(browser, '_th_keepalive_task', None)
    if keepalive_task is not None:
        keepalive_task.cancel()

    try:
        await browser.close()
    except Exception as e:
        logger.warning(f"关闭 Playwright browser 失败: {e}")
    await release_playwright_cdp_session(browser)
