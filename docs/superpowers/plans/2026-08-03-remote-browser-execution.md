# Remote Browser Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add remote browser execution support (Selenium Grid, Playwright Remote/CDP, BrowserStack, Sauce Labs) to TestHub's UI automation module, with a unified browser connection factory and project-level configuration management.

**Architecture:** A `BrowserConnectionFactory` serves as the single entry point for creating browser instances. When `remote_service=None` (default), existing local browser launch logic runs unchanged. When a `RemoteBrowserService` record is provided, the factory dispatches to the appropriate remote connection method based on `service_type`. A new CRUD API and configuration page manage remote browser service records at the project level.

**Tech Stack:** Django 4.2, Django REST Framework, Selenium WebDriver (local + Remote), Playwright (local + connect/connect_over_cdp), Vue 3, Element Plus, Pinia, Axios

## Global Constraints

- Python 3.10+, Django 4.2, DRF 3.14+
- Vue 3 with `<script setup>` composition API, Element Plus components
- All API endpoints prefixed with `/api/ui-automation/`
- i18n required for all user-facing strings (zh-cn + en)
- Database: MySQL 8.0+ with utf8mb4
- Default behavior (local execution) must not change — remote is opt-in
- `url` field uses `CharField` (not `URLField`) to support ws:// and wss:// protocols

---

### Task 1: Model — `RemoteBrowserService` + FK fields + migration

**Files:**
- Modify: `apps/ui_automation/models.py` (insert after line 559, and add FK fields after lines 515, 697, 834)
- Create: `apps/ui_automation/migrations/XXXX_add_remote_browser_service.py` (auto-generated)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `RemoteBrowserService` model with fields: `project` (FK→UiProject), `name` (CharField), `service_type` (CharField), `url` (CharField), `capabilities` (JSONField), `auth_config` (JSONField), `is_active` (BooleanField), `created_by` (FK→User), `created_at`, `updated_at`. Also nullable FK `remote_browser_service` on `TestExecution`, `TestCaseExecution`, `UiScheduledTask`.

- [ ] **Step 1: Add `RemoteBrowserService` model to `models.py`**

Insert after the `TestEnvironment` model (after line 559 in `apps/ui_automation/models.py`):

```python
class RemoteBrowserService(models.Model):
    """远程浏览器服务配置"""
    SERVICE_TYPE_CHOICES = [
        ('selenium_grid', 'Selenium Grid'),
        ('playwright_remote', 'Playwright Remote'),
        ('playwright_cdp', 'Playwright CDP'),
        ('browserstack', 'BrowserStack'),
        ('saucelabs', 'Sauce Labs'),
    ]

    project = models.ForeignKey(
        UiProject, on_delete=models.CASCADE,
        related_name='remote_browser_services', verbose_name='所属项目'
    )
    name = models.CharField(max_length=100, verbose_name='服务名称')
    service_type = models.CharField(
        max_length=30, choices=SERVICE_TYPE_CHOICES, verbose_name='服务类型'
    )
    url = models.CharField(max_length=500, verbose_name='连接地址')
    capabilities = models.JSONField(default=dict, blank=True, verbose_name='浏览器能力配置')
    auth_config = models.JSONField(default=dict, blank=True, verbose_name='认证配置')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name='创建者'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'ui_remote_browser_services'
        verbose_name = '远程浏览器服务'
        verbose_name_plural = '远程浏览器服务'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_service_type_display()})'
```

- [ ] **Step 2: Add FK field to `TestExecution`**

Insert after `report_url` field (line 515 in `apps/ui_automation/models.py`):

```python
    remote_browser_service = models.ForeignKey(
        'RemoteBrowserService', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='test_executions',
        verbose_name='远程浏览器服务'
    )
```

- [ ] **Step 3: Add FK field to `TestCaseExecution`**

Insert after `created_at` field (line 697 in `apps/ui_automation/models.py`):

```python
    remote_browser_service = models.ForeignKey(
        'RemoteBrowserService', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='test_case_executions',
        verbose_name='远程浏览器服务'
    )
```

- [ ] **Step 4: Add FK field to `UiScheduledTask`**

Insert after `updated_at` field (line 834 in `apps/ui_automation/models.py`):

```python
    remote_browser_service = models.ForeignKey(
        'RemoteBrowserService', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scheduled_tasks',
        verbose_name='远程浏览器服务'
    )
```

- [ ] **Step 5: Generate and apply migration**

```bash
source venv/Scripts/activate
python manage.py makemigrations ui_automation
python manage.py migrate
```

Verify: the migration file should create the `ui_remote_browser_services` table and add three nullable FK columns.

- [ ] **Step 6: Verify via Django shell**

```bash
python manage.py shell -c "from apps.ui_automation.models import RemoteBrowserService; print(RemoteBrowserService._meta.db_table)"
```

Expected output: `ui_remote_browser_services`

- [ ] **Step 7: Commit**

```bash
git add apps/ui_automation/models.py apps/ui_automation/migrations/
git commit -m "feat: add RemoteBrowserService model and FK fields for remote execution"
```

---

### Task 2: Browser Connection Factory

**Files:**
- Create: `apps/ui_automation/browser_factory.py`
- Modify: `apps/ui_automation/selenium_engine.py` (lines 26-36 `__init__`, lines 108-287 `start()`)
- Modify: `apps/ui_automation/playwright_engine.py` (lines 19-32 `__init__`, lines 34-68 `start()`)

**Interfaces:**
- Consumes: `RemoteBrowserService` model from Task 1
- Produces:
  - `BrowserConnectionFactory.create_selenium_driver(browser_type: str, headless: bool, remote_service: Optional[RemoteBrowserService] = None) -> WebDriver`
  - `BrowserConnectionFactory.create_playwright_browser(playwright_instance, browser_type: str, headless: bool, remote_service: Optional[RemoteBrowserService] = None) -> Browser`

- [ ] **Step 1: Create `browser_factory.py` with local Selenium logic**

Create `apps/ui_automation/browser_factory.py`. Extract the local browser creation logic from `selenium_engine.py` lines 108-287 into `_create_local_selenium()`. The public method dispatches:

```python
"""浏览器连接工厂 — 统一创建本地或远程浏览器实例"""
import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions

logger = logging.getLogger(__name__)


class BrowserConnectionFactory:

    @staticmethod
    def create_selenium_driver(browser_type='chrome', headless=True, remote_service=None):
        if remote_service is None:
            return _create_local_selenium(browser_type, headless)

        service_type = remote_service.service_type
        if service_type == 'selenium_grid':
            return _create_grid_driver(remote_service, browser_type, headless)
        elif service_type == 'browserstack':
            return _create_cloud_driver(remote_service, browser_type, headless, provider='browserstack')
        elif service_type == 'saucelabs':
            return _create_cloud_driver(remote_service, browser_type, headless, provider='saucelabs')
        else:
            raise ValueError(f"Selenium does not support service_type: {service_type}")

    @staticmethod
    async def create_playwright_browser(playwright_instance, browser_type='chromium', headless=True, remote_service=None):
        if remote_service is None:
            return await _create_local_playwright(playwright_instance, browser_type, headless)

        service_type = remote_service.service_type
        if service_type == 'playwright_remote':
            return await _connect_playwright_remote(playwright_instance, remote_service)
        elif service_type == 'playwright_cdp':
            return await _connect_playwright_cdp(playwright_instance, remote_service)
        else:
            raise ValueError(f"Playwright does not support service_type: {service_type}")
```

- [ ] **Step 2: Implement `_create_local_selenium()`**

Copy the browser creation logic from `selenium_engine.py` `start()` method (lines 108-287) into `_create_local_selenium(browser_type, headless)`. This function returns a `WebDriver` instance. Keep all existing Chrome/Firefox/Edge/Safari options exactly as-is — this is a move, not a rewrite. Include the `webdriver_manager` imports:

```python
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager


def _create_local_selenium(browser_type, headless):
    """Create a local Selenium WebDriver — logic extracted from SeleniumTestEngine.start()"""
    browser_type_lower = browser_type.lower()

    if browser_type_lower == 'chrome':
        options = ChromeOptions()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--window-size=1920,1080')
        # ... (keep ALL existing Chrome options from selenium_engine.py lines 129-175)
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver

    elif browser_type_lower == 'firefox':
        # ... (copy from selenium_engine.py lines 177-205)
        pass

    elif browser_type_lower == 'edge':
        # ... (copy from selenium_engine.py lines 207-220)
        pass

    elif browser_type_lower == 'safari':
        # ... (copy from selenium_engine.py lines 222-240)
        pass

    else:
        # Default to chrome (copy from selenium_engine.py lines 242-278)
        pass
```

Important: copy every single option/argument from the original `start()` method. Do not omit any line.

- [ ] **Step 3: Implement `_create_local_playwright()`**

Copy from `playwright_engine.py` `start()` lines 37-53:

```python
async def _create_local_playwright(playwright_instance, browser_type, headless):
    """Create a local Playwright browser — logic extracted from PlaywrightTestEngine.start()"""
    if browser_type == 'chromium':
        browser_launcher = playwright_instance.chromium
    elif browser_type == 'firefox':
        browser_launcher = playwright_instance.firefox
    elif browser_type == 'webkit':
        browser_launcher = playwright_instance.webkit
    else:
        browser_launcher = playwright_instance.chromium

    browser = await browser_launcher.launch(
        headless=headless,
        args=['--disable-blink-features=AutomationControlled']
    )
    return browser
```

- [ ] **Step 4: Implement remote Selenium connections**

```python
def _build_selenium_options(browser_type, headless):
    """Build browser options for remote Selenium connections."""
    browser_type_lower = browser_type.lower()
    if browser_type_lower == 'firefox':
        options = FirefoxOptions()
        if headless:
            options.add_argument('--headless')
    elif browser_type_lower == 'edge':
        options = EdgeOptions()
        if headless:
            options.add_argument('--headless=new')
    else:
        options = ChromeOptions()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
    return options


def _create_grid_driver(remote_service, browser_type, headless):
    """Connect to a Selenium Grid hub."""
    options = _build_selenium_options(browser_type, headless)
    for k, v in (remote_service.capabilities or {}).items():
        options.set_capability(k, v)
    logger.info(f"Connecting to Selenium Grid: {remote_service.url}")
    driver = webdriver.Remote(command_executor=remote_service.url, options=options)
    driver.implicitly_wait(3)
    return driver


def _create_cloud_driver(remote_service, browser_type, headless, provider):
    """Connect to BrowserStack or Sauce Labs."""
    options = _build_selenium_options(browser_type, headless)
    auth = remote_service.auth_config or {}

    if provider == 'browserstack':
        bstack_options = {
            'userName': auth.get('username', ''),
            'accessKey': auth.get('access_key', ''),
        }
        bstack_options.update(remote_service.capabilities or {})
        options.set_capability('bstack:options', bstack_options)
    elif provider == 'saucelabs':
        sauce_options = {
            'username': auth.get('username', ''),
            'accessKey': auth.get('access_key', ''),
        }
        sauce_options.update(remote_service.capabilities or {})
        options.set_capability('sauce:options', sauce_options)

    logger.info(f"Connecting to {provider}: {remote_service.url}")
    driver = webdriver.Remote(command_executor=remote_service.url, options=options)
    driver.implicitly_wait(3)
    return driver
```

- [ ] **Step 5: Implement remote Playwright connections**

```python
async def _connect_playwright_remote(playwright_instance, remote_service):
    """Connect to a remote Playwright server via WebSocket."""
    logger.info(f"Connecting to Playwright Remote: {remote_service.url}")
    browser = await playwright_instance.chromium.connect(ws_endpoint=remote_service.url)
    return browser


async def _connect_playwright_cdp(playwright_instance, remote_service):
    """Connect to a browser via Chrome DevTools Protocol."""
    logger.info(f"Connecting via CDP: {remote_service.url}")
    browser = await playwright_instance.chromium.connect_over_cdp(endpoint_url=remote_service.url)
    return browser
```

- [ ] **Step 6: Refactor `SeleniumTestEngine` to use factory**

In `apps/ui_automation/selenium_engine.py`:

Change `__init__` (line 26) to accept `remote_service`:

```python
def __init__(self, browser_type='chrome', headless=True, remote_service=None):
    self.browser_type = browser_type
    self.headless = headless
    self.remote_service = remote_service
    self.driver = None
```

Replace the body of `start()` (lines 108-287) — keep the try/except and logging, but replace browser creation with:

```python
def start(self):
    """启动浏览器"""
    try:
        from .browser_factory import BrowserConnectionFactory
        self.driver = BrowserConnectionFactory.create_selenium_driver(
            browser_type=self.browser_type,
            headless=self.headless,
            remote_service=self.remote_service,
        )
        self.driver.implicitly_wait(3)
        logger.info(f"浏览器启动成功: {self.browser_type}, headless={self.headless}, remote={self.remote_service is not None}")
    except Exception as e:
        logger.error(f"启动浏览器失败: {str(e)}")
        raise
```

- [ ] **Step 7: Refactor `PlaywrightTestEngine` to use factory**

In `apps/ui_automation/playwright_engine.py`:

Change `__init__` (line 19) to accept `remote_service`:

```python
def __init__(self, browser_type='chromium', headless=True, remote_service=None):
    self.browser_type = browser_type
    self.headless = headless
    self.remote_service = remote_service
    self.playwright = None
    self.browser: Optional[Browser] = None
    self.context: Optional[BrowserContext] = None
    self.page: Optional[Page] = None
```

Replace the body of `start()` (lines 34-68) — keep try/except and context/page creation, but replace browser launch with:

```python
async def start(self):
    """启动浏览器"""
    try:
        from .browser_factory import BrowserConnectionFactory
        self.playwright = await async_playwright().start()

        self.browser = await BrowserConnectionFactory.create_playwright_browser(
            playwright_instance=self.playwright,
            browser_type=self.browser_type,
            headless=self.headless,
            remote_service=self.remote_service,
        )

        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        )
        self.page = await self.context.new_page()

        logger.info(f"浏览器启动成功: {self.browser_type}, headless={self.headless}, remote={self.remote_service is not None}")
    except Exception as e:
        logger.error(f"启动浏览器失败: {str(e)}")
        raise
```

- [ ] **Step 8: Verify local execution still works**

Start the Django server and manually test that existing local test case execution works exactly as before (both Selenium and Playwright paths). The factory with `remote_service=None` should produce identical behavior.

- [ ] **Step 9: Commit**

```bash
git add apps/ui_automation/browser_factory.py apps/ui_automation/selenium_engine.py apps/ui_automation/playwright_engine.py
git commit -m "feat: add BrowserConnectionFactory, refactor engines to use factory"
```

---

### Task 3: Refactor `test_executor.py` to use factory

**Files:**
- Modify: `apps/ui_automation/test_executor.py` (lines 30-38 `__init__`, lines 258-267 playwright launch, lines 1539-1721 `create_selenium_driver`)

**Interfaces:**
- Consumes: `BrowserConnectionFactory` from Task 2, `RemoteBrowserService` model from Task 1
- Produces: `TestExecutor.__init__` accepts `remote_service=None`; all browser creation goes through factory

- [ ] **Step 1: Update `TestExecutor.__init__` to accept `remote_service`**

In `apps/ui_automation/test_executor.py`, modify `__init__` (lines 30-38):

```python
def __init__(self, test_suite, engine='playwright', browser='chrome', headless=False, executed_by=None, remote_service=None):
    self.test_suite = test_suite
    self.engine = engine
    self.browser = browser
    self.headless = headless
    self.executed_by = executed_by
    self.remote_service = remote_service
    self.execution = None
    self.test_cases = []
    self.results = []
```

- [ ] **Step 2: Replace Playwright browser launch in `run_with_playwright`**

At lines 258-267 (inside the `with sync_playwright() as p:` block), replace the browser type selection and launch with:

```python
from .browser_factory import BrowserConnectionFactory
import asyncio

# Use factory for browser creation (sync wrapper for async factory method)
loop = asyncio.new_event_loop()
try:
    browser = loop.run_until_complete(
        BrowserConnectionFactory.create_playwright_browser(
            playwright_instance=p,
            browser_type=self.browser if self.browser not in ('safari',) else 'webkit',
            headless=self.headless,
            remote_service=self.remote_service,
        )
    )
finally:
    loop.close()
```

Note: `test_executor.py` uses `sync_playwright`, so the async factory method needs a sync wrapper. If there's already a running event loop, use `asyncio.get_event_loop().run_until_complete()` instead. Check the existing code to see if an event loop is already running in that context. If `sync_playwright` already provides a sync context where async calls won't work directly, keep the existing sync Playwright launch for local but add a conditional for remote:

```python
if self.remote_service and self.remote_service.service_type in ('playwright_remote', 'playwright_cdp'):
    import asyncio
    from .browser_factory import BrowserConnectionFactory
    loop = asyncio.new_event_loop()
    try:
        browser = loop.run_until_complete(
            BrowserConnectionFactory.create_playwright_browser(
                playwright_instance=p,
                browser_type='chromium',
                headless=self.headless,
                remote_service=self.remote_service,
            )
        )
    finally:
        loop.close()
else:
    # Existing local launch logic
    if self.browser == 'firefox':
        browser = p.firefox.launch(headless=self.headless)
    elif self.browser == 'safari':
        browser = p.webkit.launch(headless=self.headless)
    else:
        browser = p.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
```

- [ ] **Step 3: Replace `create_selenium_driver` method**

Replace the body of `create_selenium_driver` (lines 1539-1721) to use factory:

```python
def create_selenium_driver(self):
    """Create a Selenium WebDriver using the browser connection factory."""
    from .browser_factory import BrowserConnectionFactory
    driver = BrowserConnectionFactory.create_selenium_driver(
        browser_type=self.browser,
        headless=self.headless,
        remote_service=self.remote_service,
    )
    return driver
```

- [ ] **Step 4: Verify suite execution still works locally**

Start Django server, trigger a suite execution with Selenium engine and Playwright engine to confirm no regression.

- [ ] **Step 5: Commit**

```bash
git add apps/ui_automation/test_executor.py
git commit -m "refactor: test_executor uses BrowserConnectionFactory for browser creation"
```

---

### Task 4: Serializer + ViewSet + URL for `RemoteBrowserService`

**Files:**
- Modify: `apps/ui_automation/serializers.py` (insert after line 627, before `UiScheduledTaskSerializer`)
- Modify: `apps/ui_automation/views.py` (add ViewSet, modify `run_suite` at line 776, modify `run` at line 1241)
- Modify: `apps/ui_automation/urls.py` (add router registration after line 48)

**Interfaces:**
- Consumes: `RemoteBrowserService` model from Task 1, `BrowserConnectionFactory` from Task 2, updated `TestExecutor` from Task 3
- Produces: REST API at `/api/ui-automation/remote-browser-services/` with CRUD + `test-connection` action; `run_suite` and `run` accept `remote_browser_service_id`

- [ ] **Step 1: Add serializers in `serializers.py`**

Insert before `UiScheduledTaskSerializer` (around line 629) in `apps/ui_automation/serializers.py`:

```python
class RemoteBrowserServiceSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)

    class Meta:
        model = RemoteBrowserService
        fields = [
            'id', 'project', 'name', 'service_type', 'service_type_display',
            'url', 'capabilities', 'auth_config', 'is_active',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class RemoteBrowserServiceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RemoteBrowserService
        fields = ['project', 'name', 'service_type', 'url', 'capabilities', 'auth_config', 'is_active']
```

Add `RemoteBrowserService` to the imports at the top of the file (where other models are imported from `.models`).

- [ ] **Step 2: Add `RemoteBrowserServiceViewSet` in `views.py`**

Add to `apps/ui_automation/views.py`. Import the serializers and model at the top. Add the ViewSet class:

```python
class RemoteBrowserServiceViewSet(viewsets.ModelViewSet):
    """远程浏览器服务配置 CRUD"""
    serializer_class = RemoteBrowserServiceSerializer
    filterset_fields = ['project', 'service_type', 'is_active']

    def get_queryset(self):
        return RemoteBrowserService.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return RemoteBrowserServiceCreateSerializer
        return RemoteBrowserServiceSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """测试远程浏览器服务连接"""
        service = self.get_object()
        try:
            if service.service_type in ('selenium_grid', 'browserstack', 'saucelabs'):
                from .browser_factory import BrowserConnectionFactory
                driver = BrowserConnectionFactory.create_selenium_driver(
                    browser_type='chrome', headless=True, remote_service=service,
                )
                driver.quit()
            elif service.service_type == 'playwright_remote':
                import asyncio
                from playwright.async_api import async_playwright
                async def _test():
                    pw = await async_playwright().start()
                    browser = await pw.chromium.connect(ws_endpoint=service.url)
                    await browser.close()
                    await pw.stop()
                asyncio.run(_test())
            elif service.service_type == 'playwright_cdp':
                import asyncio
                from playwright.async_api import async_playwright
                async def _test():
                    pw = await async_playwright().start()
                    browser = await pw.chromium.connect_over_cdp(endpoint_url=service.url)
                    await browser.close()
                    await pw.stop()
                asyncio.run(_test())
            return Response({'status': 'success', 'message': '连接成功'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)
```

- [ ] **Step 3: Modify `run_suite` to accept `remote_browser_service_id`**

In `apps/ui_automation/views.py`, in `TestSuiteViewSet.run_suite` method, after lines 776-778 (where `engine`, `browser`, `headless` are read), add:

```python
remote_browser_service_id = request.data.get('remote_browser_service_id', None)
remote_service = None
if remote_browser_service_id:
    try:
        remote_service = RemoteBrowserService.objects.get(
            id=remote_browser_service_id, is_active=True
        )
    except RemoteBrowserService.DoesNotExist:
        return Response({'error': '远程浏览器服务不存在或未启用'}, status=400)
```

Then where `TestExecutor` is instantiated (around lines 797-803), pass `remote_service=remote_service`.

Also where `TestExecution` is created, set `remote_browser_service=remote_service`.

- [ ] **Step 4: Modify `run` (TestCaseViewSet) to accept `remote_browser_service_id`**

In `apps/ui_automation/views.py`, in `TestCaseViewSet.run` method, after line 1241 (where `engine_type` is read), add the same lookup logic. Pass `remote_service` to the engine constructor. Set `remote_browser_service=remote_service` on `TestCaseExecution` creation.

- [ ] **Step 5: Register URL route in `urls.py`**

In `apps/ui_automation/urls.py`, add import for `RemoteBrowserServiceViewSet` and register:

```python
router.register(r'remote-browser-services', RemoteBrowserServiceViewSet, basename='remote-browser-services')
```

Insert after line 48 (after `operation-records` registration).

- [ ] **Step 6: Verify API with curl/httpie**

```bash
# List (should return empty)
curl http://127.0.0.1:8000/api/ui-automation/remote-browser-services/ -H "Authorization: Bearer <token>"

# Create
curl -X POST http://127.0.0.1:8000/api/ui-automation/remote-browser-services/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"project": 1, "name": "Test Grid", "service_type": "selenium_grid", "url": "http://localhost:4444/wd/hub"}'
```

- [ ] **Step 7: Commit**

```bash
git add apps/ui_automation/serializers.py apps/ui_automation/views.py apps/ui_automation/urls.py
git commit -m "feat: add RemoteBrowserService API with CRUD and test-connection"
```

---

### Task 5: Update existing serializers to include `remote_browser_service`

**Files:**
- Modify: `apps/ui_automation/serializers.py` (update `TestExecutionSerializer` at line 223, `TestCaseExecutionSerializer` at line 559, `UiScheduledTaskSerializer` at line 629)

**Interfaces:**
- Consumes: FK fields added in Task 1
- Produces: `remote_browser_service` and `remote_browser_service_name` included in execution/task serializer responses

- [ ] **Step 1: Update `TestExecutionSerializer`**

In `apps/ui_automation/serializers.py`, in the `TestExecutionSerializer` class (line 223), add a read-only field:

```python
remote_browser_service_name = serializers.CharField(
    source='remote_browser_service.name', read_only=True, default=None
)
```

Add `'remote_browser_service'` and `'remote_browser_service_name'` to the `fields` list in `Meta`.

- [ ] **Step 2: Update `TestCaseExecutionSerializer`**

In the `TestCaseExecutionSerializer` class (line 559), add the same read-only field and update `fields`.

- [ ] **Step 3: Update `UiScheduledTaskSerializer`**

In the `UiScheduledTaskSerializer` class (line 629), add `'remote_browser_service'` to `fields`. This one is writable (user selects it when creating/editing scheduled tasks).

- [ ] **Step 4: Commit**

```bash
git add apps/ui_automation/serializers.py
git commit -m "feat: include remote_browser_service in execution and task serializers"
```

---

### Task 6: Frontend — API service layer + i18n

**Files:**
- Modify: `frontend/src/api/ui_automation.js` (append new functions)
- Modify: `frontend/src/locales/lang/zh-cn/configuration.js`
- Modify: `frontend/src/locales/lang/en/configuration.js`
- Modify: `frontend/src/locales/lang/zh-cn/ui-automation.js`
- Modify: `frontend/src/locales/lang/en/ui-automation.js`

**Interfaces:**
- Consumes: REST API from Task 4
- Produces: `getRemoteBrowserServices(params)`, `createRemoteBrowserService(data)`, `updateRemoteBrowserService(id, data)`, `deleteRemoteBrowserService(id)`, `testRemoteBrowserConnection(id)` functions; i18n keys for remote browser UI

- [ ] **Step 1: Add API functions to `ui_automation.js`**

Append to `frontend/src/api/ui_automation.js`:

```javascript
// ==================== 远程浏览器服务 ====================

export function getRemoteBrowserServices(params) {
  return request({
    url: "/ui-automation/remote-browser-services/",
    method: "get",
    params,
  });
}

export function createRemoteBrowserService(data) {
  return request({
    url: "/ui-automation/remote-browser-services/",
    method: "post",
    data,
  });
}

export function getRemoteBrowserService(id) {
  return request({
    url: `/ui-automation/remote-browser-services/${id}/`,
    method: "get",
  });
}

export function updateRemoteBrowserService(id, data) {
  return request({
    url: `/ui-automation/remote-browser-services/${id}/`,
    method: "put",
    data,
  });
}

export function deleteRemoteBrowserService(id) {
  return request({
    url: `/ui-automation/remote-browser-services/${id}/`,
    method: "delete",
  });
}

export function testRemoteBrowserConnection(id) {
  return request({
    url: `/ui-automation/remote-browser-services/${id}/test_connection/`,
    method: "post",
    timeout: 30000,
  });
}
```

- [ ] **Step 2: Add zh-cn i18n keys for configuration page**

Add to the remote browser section in `frontend/src/locales/lang/zh-cn/configuration.js`:

```javascript
remoteBrowser: {
  title: '远程浏览器服务',
  description: '管理远程浏览器连接配置，支持 Selenium Grid、Playwright Remote、云测试平台',
  addService: '添加服务',
  editService: '编辑服务',
  name: '服务名称',
  serviceType: '服务类型',
  url: '连接地址',
  capabilities: '浏览器能力配置',
  authConfig: '认证配置',
  username: '用户名',
  accessKey: 'Access Key',
  isActive: '启用状态',
  testConnection: '测试连接',
  testSuccess: '连接成功',
  testFailed: '连接失败',
  placeholders: {
    selenium_grid: 'http://hub-host:4444/wd/hub',
    playwright_remote: 'ws://remote-host:3000',
    playwright_cdp: 'http://remote-host:9222',
    browserstack: 'https://hub-cloud.browserstack.com/wd/hub',
    saucelabs: 'https://ondemand.saucelabs.com/wd/hub',
  },
},
```

- [ ] **Step 3: Add en i18n keys for configuration page**

Add the equivalent English translations in `frontend/src/locales/lang/en/configuration.js`:

```javascript
remoteBrowser: {
  title: 'Remote Browser Services',
  description: 'Manage remote browser connections for Selenium Grid, Playwright Remote, and cloud testing platforms',
  addService: 'Add Service',
  editService: 'Edit Service',
  name: 'Service Name',
  serviceType: 'Service Type',
  url: 'Connection URL',
  capabilities: 'Browser Capabilities',
  authConfig: 'Authentication',
  username: 'Username',
  accessKey: 'Access Key',
  isActive: 'Active',
  testConnection: 'Test Connection',
  testSuccess: 'Connection successful',
  testFailed: 'Connection failed',
  placeholders: {
    selenium_grid: 'http://hub-host:4444/wd/hub',
    playwright_remote: 'ws://remote-host:3000',
    playwright_cdp: 'http://remote-host:9222',
    browserstack: 'https://hub-cloud.browserstack.com/wd/hub',
    saucelabs: 'https://ondemand.saucelabs.com/wd/hub',
  },
},
```

- [ ] **Step 4: Add zh-cn + en i18n keys for execution dialogs**

Add to `frontend/src/locales/lang/zh-cn/ui-automation.js`:

```javascript
execution: {
  executionMode: '执行方式',
  local: '本地执行',
  remote: '远程执行',
  remoteService: '远程服务',
  selectRemoteService: '请选择远程浏览器服务',
  noRemoteServices: '暂无可用的远程浏览器服务，请先在配置中心添加',
},
```

Add equivalent in `frontend/src/locales/lang/en/ui-automation.js`:

```javascript
execution: {
  executionMode: 'Execution Mode',
  local: 'Local',
  remote: 'Remote',
  remoteService: 'Remote Service',
  selectRemoteService: 'Select a remote browser service',
  noRemoteServices: 'No remote browser services available. Add one in Configuration Center first.',
},
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ui_automation.js frontend/src/locales/
git commit -m "feat: add remote browser service API functions and i18n translations"
```

---

### Task 7: Frontend — `RemoteBrowserConfig.vue` configuration page

**Files:**
- Create: `frontend/src/views/configuration/RemoteBrowserConfig.vue`
- Modify: `frontend/src/router/index.js` (add route at line ~435)
- Modify: `frontend/src/views/configuration/ConfigurationCenter.vue` (add sidebar menu entry)

**Interfaces:**
- Consumes: API functions from Task 6, i18n keys from Task 6
- Produces: `/configuration/remote-browser` page with CRUD table and test-connection

- [ ] **Step 1: Create `RemoteBrowserConfig.vue`**

Create `frontend/src/views/configuration/RemoteBrowserConfig.vue`. Follow the pattern of `NotificationConfig.vue`:

```vue
<template>
  <div class="remote-browser-config-page">
    <!-- Page header -->
    <div class="page-header">
      <div class="header-info">
        <el-icon size="24"><Monitor /></el-icon>
        <div>
          <h3>{{ $t('configuration.remoteBrowser.title') }}</h3>
          <p>{{ $t('configuration.remoteBrowser.description') }}</p>
        </div>
      </div>
      <el-button type="primary" @click="openDialog()">
        <el-icon><Plus /></el-icon>
        {{ $t('configuration.remoteBrowser.addService') }}
      </el-button>
    </div>

    <!-- Services table -->
    <el-table :data="services" v-loading="loading" stripe>
      <el-table-column prop="name" :label="$t('configuration.remoteBrowser.name')" min-width="150" />
      <el-table-column prop="service_type_display" :label="$t('configuration.remoteBrowser.serviceType')" width="160" />
      <el-table-column prop="url" :label="$t('configuration.remoteBrowser.url')" min-width="250" show-overflow-tooltip />
      <el-table-column :label="$t('configuration.remoteBrowser.isActive')" width="100" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.is_active" @change="toggleActive(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="created_by_name" :label="$t('common.creator')" width="120" />
      <el-table-column :label="$t('common.actions')" width="240" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleTestConnection(row)">
            {{ $t('configuration.remoteBrowser.testConnection') }}
          </el-button>
          <el-button link type="primary" @click="openDialog(row)">
            {{ $t('common.edit') }}
          </el-button>
          <el-popconfirm :title="$t('common.confirmDelete')" @confirm="handleDelete(row)">
            <template #reference>
              <el-button link type="danger">{{ $t('common.delete') }}</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add/Edit dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? $t('configuration.remoteBrowser.editService') : $t('configuration.remoteBrowser.addService')"
      width="600"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
        <el-form-item :label="$t('configuration.remoteBrowser.name')" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="$t('configuration.remoteBrowser.serviceType')" prop="service_type">
          <el-select v-model="form.service_type" style="width: 100%">
            <el-option label="Selenium Grid" value="selenium_grid" />
            <el-option label="Playwright Remote" value="playwright_remote" />
            <el-option label="Playwright CDP" value="playwright_cdp" />
            <el-option label="BrowserStack" value="browserstack" />
            <el-option label="Sauce Labs" value="saucelabs" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('configuration.remoteBrowser.url')" prop="url">
          <el-input
            v-model="form.url"
            :placeholder="urlPlaceholder"
          />
        </el-form-item>
        <!-- Auth config: only for cloud services -->
        <template v-if="['browserstack', 'saucelabs'].includes(form.service_type)">
          <el-form-item :label="$t('configuration.remoteBrowser.username')">
            <el-input v-model="form.auth_config.username" />
          </el-form-item>
          <el-form-item :label="$t('configuration.remoteBrowser.accessKey')">
            <el-input v-model="form.auth_config.access_key" type="password" show-password />
          </el-form-item>
        </template>
        <!-- Capabilities: collapsible JSON editor -->
        <el-collapse>
          <el-collapse-item :title="$t('configuration.remoteBrowser.capabilities')">
            <el-input
              v-model="capabilitiesJson"
              type="textarea"
              :rows="6"
              placeholder='{"browserVersion": "latest"}'
            />
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          {{ $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Monitor, Plus } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import {
  getRemoteBrowserServices,
  createRemoteBrowserService,
  updateRemoteBrowserService,
  deleteRemoteBrowserService,
  testRemoteBrowserConnection,
} from '@/api/ui_automation'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const route = useRoute()

const services = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  project: null,
  name: '',
  service_type: 'selenium_grid',
  url: '',
  capabilities: {},
  auth_config: { username: '', access_key: '' },
  is_active: true,
})

const capabilitiesJson = computed({
  get: () => JSON.stringify(form.capabilities, null, 2),
  set: (val) => {
    try { form.capabilities = JSON.parse(val) } catch {}
  },
})

const urlPlaceholder = computed(() => {
  const placeholders = {
    selenium_grid: 'http://hub-host:4444/wd/hub',
    playwright_remote: 'ws://remote-host:3000',
    playwright_cdp: 'http://remote-host:9222',
    browserstack: 'https://hub-cloud.browserstack.com/wd/hub',
    saucelabs: 'https://ondemand.saucelabs.com/wd/hub',
  }
  return placeholders[form.service_type] || ''
})

const rules = {
  name: [{ required: true, message: t('common.required'), trigger: 'blur' }],
  service_type: [{ required: true, message: t('common.required'), trigger: 'change' }],
  url: [{ required: true, message: t('common.required'), trigger: 'blur' }],
}

async function fetchServices() {
  loading.value = true
  try {
    const projectId = route.query.project
    const res = await getRemoteBrowserServices({ project: projectId })
    services.value = res.data?.results || res.data || []
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  if (row) {
    isEdit.value = true
    editId.value = row.id
    Object.assign(form, {
      project: row.project,
      name: row.name,
      service_type: row.service_type,
      url: row.url,
      capabilities: row.capabilities || {},
      auth_config: row.auth_config || { username: '', access_key: '' },
      is_active: row.is_active,
    })
  } else {
    isEdit.value = false
    editId.value = null
    Object.assign(form, {
      project: route.query.project || null,
      name: '',
      service_type: 'selenium_grid',
      url: '',
      capabilities: {},
      auth_config: { username: '', access_key: '' },
      is_active: true,
    })
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    if (isEdit.value) {
      await updateRemoteBrowserService(editId.value, form)
    } else {
      await createRemoteBrowserService(form)
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    fetchServices()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  await deleteRemoteBrowserService(row.id)
  ElMessage.success(t('common.success'))
  fetchServices()
}

async function toggleActive(row) {
  await updateRemoteBrowserService(row.id, { is_active: row.is_active })
}

async function handleTestConnection(row) {
  try {
    const res = await testRemoteBrowserConnection(row.id)
    ElMessage.success(res.data.message || t('configuration.remoteBrowser.testSuccess'))
  } catch (err) {
    ElMessage.error(err.response?.data?.message || t('configuration.remoteBrowser.testFailed'))
  }
}

onMounted(fetchServices)
</script>
```

Add scoped styles consistent with other configuration pages.

- [ ] **Step 2: Add route in `router/index.js`**

In `frontend/src/router/index.js`, add a new child route inside the `/configuration` children array (around line 435, before the closing `]`):

```javascript
{
  path: "remote-browser",
  name: "ConfigRemoteBrowser",
  component: () => import("@/views/configuration/RemoteBrowserConfig.vue"),
  meta: { title: "Remote Browser" },
},
```

- [ ] **Step 3: Add sidebar entry in `ConfigurationCenter.vue`**

In `frontend/src/views/configuration/ConfigurationCenter.vue`, add a menu item in the sidebar navigation to link to `/configuration/remote-browser`. Follow the existing pattern of other sidebar entries (icon + label).

- [ ] **Step 4: Start dev server and verify the page**

```bash
cd frontend
"D:/software/Node/node.exe" node_modules/vite/bin/vite.js
```

Navigate to `http://localhost:3000/configuration/remote-browser`. Verify: table renders, add dialog opens, form validation works.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/configuration/RemoteBrowserConfig.vue frontend/src/views/configuration/ConfigurationCenter.vue frontend/src/router/index.js
git commit -m "feat: add remote browser configuration page"
```

---

### Task 8: Frontend — Execution dialog changes (SuiteList, ScheduledTasks, TestCaseViewSet)

**Files:**
- Modify: `frontend/src/views/ui-automation/suites/SuiteList.vue` (dialog at lines 342-389, runConfig at lines 470-474, submit at lines 706-710)
- Modify: `frontend/src/views/ui-automation/scheduled-tasks/ScheduledTasks.vue` (form at lines 480-508, taskForm at lines 642-655, submit at lines 821-823)

**Interfaces:**
- Consumes: `getRemoteBrowserServices` API from Task 6, i18n keys from Task 6
- Produces: Execution dialogs with local/remote toggle and remote service dropdown

- [ ] **Step 1: Modify `SuiteList.vue` run dialog**

In `frontend/src/views/ui-automation/suites/SuiteList.vue`:

Add to `runConfig` reactive (around line 470):
```javascript
const runConfig = reactive({
  engine: "playwright",
  browser: "chrome",
  headless: false,
  executionMode: "local",           // new
  remote_browser_service_id: null,  // new
});
```

Add import at the top:
```javascript
import { getRemoteBrowserServices } from '@/api/ui_automation'
```

Add reactive data for remote services:
```javascript
const remoteServices = ref([])
async function fetchRemoteServices() {
  try {
    const res = await getRemoteBrowserServices({ project: currentProjectId, is_active: true })
    remoteServices.value = res.data?.results || res.data || []
  } catch {}
}
```

In the template, after the headless radio group (after line 378), add:

```html
<el-form-item :label="$t('uiAutomation.execution.executionMode')">
  <el-radio-group v-model="runConfig.executionMode" @change="onExecutionModeChange">
    <el-radio value="local">{{ $t('uiAutomation.execution.local') }}</el-radio>
    <el-radio value="remote">{{ $t('uiAutomation.execution.remote') }}</el-radio>
  </el-radio-group>
</el-form-item>
<el-form-item
  v-if="runConfig.executionMode === 'remote'"
  :label="$t('uiAutomation.execution.remoteService')"
>
  <el-select
    v-model="runConfig.remote_browser_service_id"
    :placeholder="$t('uiAutomation.execution.selectRemoteService')"
    style="width: 100%"
    @change="onRemoteServiceChange"
  >
    <el-option
      v-for="svc in remoteServices"
      :key="svc.id"
      :label="`${svc.name} (${svc.service_type_display})`"
      :value="svc.id"
    />
  </el-select>
</el-form-item>
```

Add handler for engine auto-lock:
```javascript
function onExecutionModeChange(mode) {
  if (mode === 'local') {
    runConfig.remote_browser_service_id = null
  } else {
    fetchRemoteServices()
  }
}

function onRemoteServiceChange(serviceId) {
  const svc = remoteServices.value.find(s => s.id === serviceId)
  if (!svc) return
  if (['selenium_grid', 'browserstack', 'saucelabs'].includes(svc.service_type)) {
    runConfig.engine = 'selenium'
  } else if (['playwright_remote', 'playwright_cdp'].includes(svc.service_type)) {
    runConfig.engine = 'playwright'
  }
}
```

Update submit data (around lines 706-710) to include:
```javascript
remote_browser_service_id: runConfig.executionMode === 'remote' ? runConfig.remote_browser_service_id : null,
```

- [ ] **Step 2: Modify `ScheduledTasks.vue` task form**

In `frontend/src/views/ui-automation/scheduled-tasks/ScheduledTasks.vue`:

Add to `taskForm` reactive (around line 642):
```javascript
executionMode: "local",
remote_browser_service_id: null,
```

Add the same `remoteServices` ref, `fetchRemoteServices()`, `onExecutionModeChange()`, `onRemoteServiceChange()` functions.

In the template after the headless checkbox (after line 508), add the same execution mode radio + remote service select as SuiteList.

Update submit data (around lines 821-823) to include `remote_browser_service_id`.

Update reset function (around lines 790-792) to reset `executionMode: "local"` and `remote_browser_service_id: null`.

When editing an existing task that has `remote_browser_service`, set `executionMode: "remote"` and populate the dropdown.

- [ ] **Step 3: Start dev server and test**

Verify in browser:
1. Suite run dialog: switching to "Remote" shows dropdown, selecting a Selenium Grid service locks engine to Selenium
2. Scheduled task form: same behavior
3. Submitting with "Local" mode sends no `remote_browser_service_id`
4. Submitting with "Remote" mode sends the selected service ID

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ui-automation/suites/SuiteList.vue frontend/src/views/ui-automation/scheduled-tasks/ScheduledTasks.vue
git commit -m "feat: add remote execution option to suite run dialog and scheduled task form"
```

---

### Task 9: Execution result display + final verification

**Files:**
- Modify: Execution result/detail views (wherever `TestExecution` and `TestCaseExecution` results are displayed) to show remote service info
- Verify: End-to-end flow

**Interfaces:**
- Consumes: Serializer changes from Task 5 (response includes `remote_browser_service_name`)
- Produces: Visual indicator of local vs remote in execution results

- [ ] **Step 1: Identify execution result display locations**

Search the frontend for where `TestExecution` or `TestCaseExecution` data is rendered. Look in `SuiteList.vue` (execution history section) and any execution detail views. The serializer already returns `remote_browser_service_name`.

- [ ] **Step 2: Add execution mode indicator**

In each execution result display, add a tag showing:
```html
<el-tag v-if="row.remote_browser_service" type="warning" size="small">
  {{ $t('uiAutomation.execution.remote') }}: {{ row.remote_browser_service_name }}
</el-tag>
<el-tag v-else type="info" size="small">
  {{ $t('uiAutomation.execution.local') }}
</el-tag>
```

- [ ] **Step 3: End-to-end verification**

With Django and Vite dev servers running:
1. Go to Configuration Center → Remote Browser, add a test service (e.g., Selenium Grid pointing to a local grid if available, or just verify CRUD works)
2. Go to a test suite, click Run, verify "Remote" option appears
3. If a Selenium Grid is available, run a test remotely and verify the execution record shows the remote service name
4. If no remote grid is available, at minimum verify: local execution still works identically, the remote service dropdown loads, the API accepts and stores `remote_browser_service_id`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/
git commit -m "feat: show remote browser service info in execution results"
```