"""
浏览器连接工厂
统一封装本地/远程浏览器创建逻辑，供 SeleniumTestEngine 和 PlaywrightTestEngine 复用。

- remote_service 为 None 时：走本地创建逻辑（与原 selenium_engine.py / playwright_engine.py
  的 start() 方法保持完全一致的行为，逐项保留所有浏览器选项）。
- remote_service 不为 None 时：根据 RemoteBrowserService.service_type 走不同的远程连接方式
  （Selenium Grid / BrowserStack / Sauce Labs / Playwright Remote / Playwright CDP）。
"""
import logging

from selenium import webdriver

logger = logging.getLogger(__name__)


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
            return await _connect_playwright_cdp(playwright_instance, remote_service)
        raise ValueError(f"Playwright does not support service_type: {service_type}")


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

    if browser_type == 'chrome':
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
        options.add_argument('--window-size=1920,1080')

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
        options.add_argument('--width=1920')
        options.add_argument('--height=1080')

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
        options.add_argument('--window-size=1920,1080')

        # 使用缓存优先策略，7天内不重新下载
        service = Service(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)

    elif browser_type == 'safari':
        # Safari 不支持 headless 模式
        # 需要先启用：sudo safaridriver --enable
        # 并在 Safari 设置 -> 开发菜单中启用"允许远程自动化"
        try:
            driver = webdriver.Safari()
            driver.set_window_size(1920, 1080)
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

    else:
        # 默认使用Chrome
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
        options.add_argument('--window-size=1920,1080')

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
        }
        options.add_experimental_option('prefs', prefs)

        # 禁用密码泄露检查和其他安全警告
        options.add_argument('--disable-features=PasswordLeakDetection')  # 禁用密码泄露检测
        options.add_argument('--disable-features=PrivacySandboxSettings4')  # 禁用隐私沙盒
        options.add_argument('--disable-features=TranslateUI')  # 禁用翻译提示
        options.add_argument('--disable-infobars')  # 禁用信息栏

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

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


async def _connect_playwright_cdp(playwright_instance, remote_service):
    """通过 CDP 连接远程浏览器"""
    browser = await playwright_instance.chromium.connect_over_cdp(endpoint_url=remote_service.url)
    return browser
