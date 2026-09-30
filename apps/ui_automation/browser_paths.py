"""
浏览器可执行文件路径检测——集中维护候选路径列表。

背景：ai_base.py、selenium_engine.py（SeleniumTestEngine.check_browser_available）、
views_config.py（EnvironmentConfigViewSet.check_environment）三处各自独立维护了
一份 Chrome/Firefox/Edge/Safari 的路径候选列表，且三份彼此不一致——比如
/snap/bin/chromium 只在两处出现、selenium_engine.py 缺了 /opt/google/chrome
路径、Safari 检测方式三处互不相同。结果是"环境检测页面显示浏览器已安装，
实际执行时却报错找不到浏览器"这类体验问题。

这里把"候选路径长什么样"集中到一处，三个调用点都只依赖这份数据，不再各自
维护。各调用点原有的返回格式、错误提示文案、安装建议等上层逻辑保持不变，
只是路径列表的来源统一了。
"""
import glob
import os
import platform

# browser_type -> {platform.system() 返回值 -> [候选路径...]}
# 顺序即优先级，找到第一个存在且可执行的就返回。
BROWSER_EXECUTABLE_CANDIDATES = {
    'chrome': {
        'Windows': [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ],
        'Darwin': [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ],
        'Linux': [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/opt/google/chrome/google-chrome',
            '/opt/google/chrome/chrome',
            '/snap/bin/chromium',
        ],
    },
    'firefox': {
        'Windows': [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        'Darwin': [
            '/Applications/Firefox.app/Contents/MacOS/firefox',
        ],
        'Linux': [
            '/usr/bin/firefox',
            '/usr/bin/firefox-esr',
        ],
    },
    'edge': {
        'Windows': [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        'Darwin': [
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        ],
        'Linux': [
            '/usr/bin/microsoft-edge',
            '/usr/bin/microsoft-edge-stable',
            '/opt/microsoft/msedge/msedge',
        ],
    },
    'safari': {
        # Safari 只在 macOS 上可用，其余平台没有候选路径
        'Darwin': [
            '/Applications/Safari.app/Contents/MacOS/Safari',
        ],
    },
}

# Playwright 自己下载安装的浏览器，在 Linux/Docker 环境下常见的缓存目录通配符模式，
# 用于在系统包管理器安装的浏览器都找不到时兜底查找（原来 ai_base.py 里手写的逻辑）。
PLAYWRIGHT_CHROMIUM_GLOB_PATTERNS = [
    '/ms-playwright/**/chromium',
    '/ms-playwright/**/chromium-linux/chromium',
    '/root/.cache/ms-playwright/**/chromium',
    '/root/.cache/ms-playwright/**/chromium-linux/chromium',
    os.path.expanduser('~/.cache/ms-playwright/**/chromium'),
    os.path.expanduser('~/.cache/ms-playwright/**/chromium-linux/chromium'),
]


def get_candidate_paths(browser_type, system=None):
    """返回某个浏览器在当前（或指定）操作系统下的候选可执行文件路径列表。"""
    system = system or platform.system()
    return list(BROWSER_EXECUTABLE_CANDIDATES.get(browser_type, {}).get(system, []))


def find_installed_browser_path(browser_type, system=None, extra_glob_patterns=None):
    """
    按候选路径列表查找第一个存在（且在非 Windows 平台上可执行）的浏览器路径。

    Args:
        browser_type: 'chrome' / 'firefox' / 'edge' / 'safari'
        system: 指定操作系统（默认用 platform.system() 的当前系统）
        extra_glob_patterns: 额外补充的通配符路径列表（比如 Playwright 缓存目录），
            候选路径都找不到时会再尝试这些通配符模式。

    Returns:
        找到的可执行文件路径；都找不到时返回 None。
    """
    system = system or platform.system()

    for path in get_candidate_paths(browser_type, system=system):
        if not os.path.exists(path):
            continue
        if system == 'Windows' or os.access(path, os.X_OK):
            return path

    for pattern in (extra_glob_patterns or []):
        for match in glob.glob(pattern, recursive=True):
            if os.path.exists(match) and os.access(match, os.X_OK):
                return match

    return None


def is_browser_available(browser_type, system=None):
    """只关心"有没有装"，不关心具体安装在哪个路径。"""
    system = system or platform.system()
    if browser_type == 'safari' and system != 'Darwin':
        return False
    return find_installed_browser_path(browser_type, system=system) is not None
