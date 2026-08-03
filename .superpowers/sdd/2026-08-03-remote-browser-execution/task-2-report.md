# Task 2 Report: Browser Connection Factory

## Files created

- `apps/ui_automation/browser_factory.py` — New `BrowserConnectionFactory` class with two public
  static methods (`create_selenium_driver`, `create_playwright_browser`) plus private helper
  functions for local creation, remote Selenium Grid / cloud connections, and Playwright
  remote/CDP connections. Implements exactly the interface specified in the brief.

## Files changed

- `apps/ui_automation/selenium_engine.py`
  - `SeleniumTestEngine.__init__` now accepts `remote_service=None` and stores it as
    `self.remote_service`.
  - `SeleniumTestEngine.start()` body replaced: now does a lazy `from .browser_factory import
    BrowserConnectionFactory` and delegates driver creation to
    `BrowserConnectionFactory.create_selenium_driver(...)`, then calls
    `self.driver.implicitly_wait(3)` and logs (log line now also reports `remote=`).
  - `check_browser_available` untouched (it has no driver-creation code to begin with).
  - `from selenium import webdriver` (line 12) left in place even though it is currently unused
    in this file (see Deviations below).

- `apps/ui_automation/playwright_engine.py`
  - `PlaywrightTestEngine.__init__` now accepts `remote_service=None` and stores it as
    `self.remote_service`.
  - `PlaywrightTestEngine.start()` body replaced: starts `async_playwright()` itself (unchanged),
    then delegates browser creation to
    `BrowserConnectionFactory.create_playwright_browser(...)`, then creates `context`/`page`
    exactly as before (viewport, user agent unchanged).

## Post-review fix (2026-08-03)

Code review flagged that the default/else Chrome branch in `_create_local_selenium()` was
missing options present in the explicit `'chrome'` branch (missing `password_manager_leak_detection`
and `safebrowsing.enabled` prefs; missing the second `excludeSwitches` overwrite with
`'enable-logging'`; missing `--disable-save-password-bubble`, `--disable-password-generation`,
`--disable-password-manager-reauthentication`, `--disable-popup-blocking`,
`--disable-notifications` arguments).

Note: this asymmetry between the `'chrome'` branch and the default/else branch already existed
in the **original** `selenium_engine.py` before this refactor (the original `else` branch at
lines 242-278 was already a strict subset of the `chrome` branch at lines 129-176) — so the
factory faithfully reproduced the pre-existing inconsistency during extraction, per the brief's
"copy exactly" instruction. Per explicit reviewer direction, this was fixed by eliminating the
duplicate/inconsistent branch entirely: the `if browser_type == 'chrome':` condition was changed
to `if browser_type == 'chrome' or browser_type not in ('firefox', 'edge', 'safari'):`, and the
old `else: # 默认使用Chrome` block (which duplicated the chrome-branch code with fewer options)
was deleted. Now any unrecognized `browser_type` falls through to the exact same Chrome code
path as `browser_type == 'chrome'` — there is only one Chrome option set in the file, so no
further drift between the two is possible.

This is a deliberate, reviewer-directed behavior change from the original code (previously,
passing an unknown `browser_type` produced a Chrome driver with a reduced option set; now it
produces a Chrome driver with the full option set). Committed separately as
`fix: align default Chrome branch options in browser factory`.

## Deviations from the brief and why

1. **Local browser pre-flight check moved into the factory, not dropped.**
   The brief's literal `start()` snippet for `selenium_engine.py` omits the
   `check_browser_available()` call, the install-tip error message, and the
   `WDM_LOG_LEVEL`/`WDM_PRINT_FIRST_LINE` env var setup that exist in the original `start()`.
   Dropping these would silently change local-execution behavior (no more early "Chrome not
   installed, run `brew install ...`" error, and webdriver_manager would use its default
   verbose logging). Since the global constraint says default (local) behavior must not
   change, I moved this exact logic into `_create_local_selenium()` in the factory (with a
   lazy import of `SeleniumTestEngine.check_browser_available` to avoid a circular import),
   so local Selenium execution behaves byte-for-byte the same as before. Remote paths never
   call this function, so remote behavior is unaffected either way.

2. **`from selenium import webdriver` left in `selenium_engine.py` even though currently unused.**
   After extracting all `webdriver.Chrome/Firefox/Edge/Safari(...)` calls into the factory, this
   top-level import has no remaining use in `selenium_engine.py`. The brief explicitly says "Do
   NOT remove `from selenium import webdriver` ... if it's used elsewhere in the file," which
   implies caution about removing it. I left it in place rather than removing it, to minimize
   risk/diff size; it is a harmless unused import (not a behavior change).

3. **`implicitly_wait(3)` called twice for remote Selenium Grid/cloud drivers.**
   Per the brief's exact code, `_create_grid_driver` and `_create_cloud_driver` each call
   `driver.implicitly_wait(3)` internally, and `SeleniumTestEngine.start()` also calls it again
   after the factory returns. This is harmless (idempotent) and follows the brief's given code
   literally for those two functions while also keeping `start()`'s own `implicitly_wait(3)`
   call as specified — no functional impact.

No other deviations. `PlaywrightTestEngine.start()` and `_create_local_playwright()` match the
brief's snippets exactly.

## Chrome options preserved

After the post-review fix, `browser_type == 'chrome'` and any unrecognized `browser_type`
(the former "default" case) share a single code path with one full option set (see
`_create_local_selenium()`, condition `browser_type == 'chrome' or browser_type not in
('firefox', 'edge', 'safari')`):
- `--headless` (conditional on `headless`)
- `--disable-blink-features=AutomationControlled`
- `--disable-gpu`
- `--no-sandbox`
- `--disable-dev-shm-usage`
- `--window-size=1920,1080`
- experimental option `excludeSwitches: ['enable-automation']`
- experimental option `useAutomationExtension: False`
- experimental option `prefs`:
  - `credentials_enable_service: False`
  - `profile.password_manager_enabled: False`
  - `profile.default_content_setting_values.notifications: 2`
  - `autofill.profile_enabled: False`
  - `profile.default_content_setting_values.automatic_downloads: 1`
  - `password_manager_leak_detection: False`
  - `safebrowsing.enabled: False`
- `--disable-features=PasswordLeakDetection`
- `--disable-features=PrivacySandboxSettings4`
- `--disable-features=TranslateUI`
- `--disable-infobars`
- `--disable-save-password-bubble`
- `--disable-password-generation`
- `--disable-password-manager-reauthentication`
- experimental option `excludeSwitches: ['enable-automation', 'enable-logging']` (overwrite, matches original order/behavior)
- `--disable-popup-blocking`
- `--disable-notifications`
- `Service(ChromeDriverManager().install())`

## Firefox options preserved

- `--headless` (conditional on `headless`)
- `--width=1920`
- `--height=1080`
- preference `browser.cache.disk.enable: False`
- preference `browser.cache.memory.enable: True`
- preference `browser.cache.offline.enable: False`
- preference `network.http.use-cache: False`
- preference `browser.startup.homepage: about:blank`
- preference `startup.homepage_welcome_url: about:blank`
- preference `startup.homepage_welcome_url.additional: about:blank`
- preference `app.update.auto: False`
- preference `app.update.enabled: False`
- preference `extensions.update.enabled: False`
- preference `extensions.update.autoUpdateDefault: False`
- `Service(GeckoDriverManager().install())`

## Edge options preserved

- `--headless` (conditional on `headless`)
- `--disable-blink-features=AutomationControlled`
- `--window-size=1920,1080`
- `Service(EdgeChromiumDriverManager().install())`

## Safari handling preserved

- `webdriver.Safari()` with `set_window_size(1920, 1080)`
- try/except catching `'Could not create a session'` / `'InvalidSessionIdException'` and
  re-raising with the full bilingual setup instructions (safaridriver --enable, dev menu, allow
  remote automation), otherwise re-raises original exception.

## Pre-flight check preserved (moved into `_create_local_selenium`)

- `os.environ['WDM_LOG_LEVEL'] = '0'`
- `os.environ['WDM_PRINT_FIRST_LINE'] = 'False'`
- `SeleniumTestEngine.check_browser_available(browser_type)` check with install-tip error message
  for chrome/firefox/edge (via Homebrew commands), raised as `Exception`.

## Playwright local launch preserved

- Browser launcher selection: `chromium` / `firefox` / `webkit`, default `chromium`.
- `browser_launcher.launch(headless=headless, args=['--disable-blink-features=AutomationControlled'])`
- Context/page creation (`viewport 1920x1080`, custom `user_agent`) remains in
  `PlaywrightTestEngine.start()`, unchanged, per the brief.

## Verification performed

- `ast.parse()` syntax check on all three files — passed.
- Django `django.setup()` + import of `browser_factory`, `selenium_engine`, `playwright_engine`
  — succeeded (no circular import issues from the lazy cross-imports).
- Instantiated `SeleniumTestEngine()` and `PlaywrightTestEngine()` with default args, confirmed
  `remote_service` defaults to `None`.
- Confirmed existing call sites in `apps/ui_automation/views.py` (lines 1354, 1559, 2220, 2294)
  construct these engines without `remote_service`, so default (local) behavior is unaffected.
