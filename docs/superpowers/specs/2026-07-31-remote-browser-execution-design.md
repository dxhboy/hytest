# Remote Browser Execution Design Spec

> 为 TestHub UI 自动化模块新增远程浏览器执行能力，支持 Selenium Grid、Playwright Remote/CDP、云浏览器服务（BrowserStack / Sauce Labs）。

## 1. 背景

当前 UI 自动化的 Selenium 引擎和 Playwright 引擎均只支持本地启动浏览器。服务端部署场景下无法利用远程浏览器资源，也无法接入云测试平台进行多浏览器/多 OS 覆盖。

## 2. 目标

- 支持 5 种远程浏览器服务类型：Selenium Grid、Playwright Remote (WebSocket)、Playwright CDP、BrowserStack、Sauce Labs
- 配置在项目级别管理，全员可见
- 默认本地执行不变，远程执行为可选项，对现有功能零影响
- 统一浏览器创建入口，消除引擎类与 test_executor 之间的重复逻辑

## 3. 架构方案：浏览器连接工厂（方案 B）

抽取 `BrowserConnectionFactory` 作为浏览器实例创建的单一入口。引擎类和 `test_executor.py` 均通过工厂获取浏览器实例。

```
执行入口 (Views / ScheduledTask)
    │
    ▼
引擎 (SeleniumTestEngine / PlaywrightTestEngine / TestExecutor)
    │
    ▼
BrowserConnectionFactory
    ├── remote_service=None → 本地创建（现有逻辑）
    ├── selenium_grid       → webdriver.Remote(hub_url)
    ├── browserstack        → webdriver.Remote(cloud_url + auth)
    ├── saucelabs           → webdriver.Remote(cloud_url + auth)
    ├── playwright_remote   → playwright.chromium.connect(ws_endpoint)
    └── playwright_cdp      → playwright.chromium.connect_over_cdp(url)
```

## 4. 数据模型

### 4.1 新增模型：`RemoteBrowserService`

文件：`apps/ui_automation/models.py`

| 字段 | 类型 | 说明 |
|------|------|------|
| `project` | FK → UiProject | 所属项目 |
| `name` | CharField(100) | 服务名称，如"公司内网 Grid" |
| `service_type` | CharField(30) | 枚举：`selenium_grid` / `playwright_remote` / `playwright_cdp` / `browserstack` / `saucelabs` |
| `url` | CharField(500) | 连接地址（支持 http/https/ws/wss 协议） |
| `capabilities` | JSONField(default=dict) | 额外浏览器能力配置 |
| `auth_config` | JSONField(default=dict) | 认证信息（username / access_key） |
| `is_active` | BooleanField(True) | 是否启用 |
| `created_by` | FK → User | 创建者 |
| `created_at` | DateTimeField(auto_now_add) | 创建时间 |
| `updated_at` | DateTimeField(auto_now) | 更新时间 |

表名：`ui_remote_browser_services`

### 4.2 现有模型新增字段

以下三个模型各新增一个可选外键：

- `TestExecution.remote_browser_service` → FK(RemoteBrowserService, null=True, blank=True, on_delete=SET_NULL)
- `TestCaseExecution.remote_browser_service` → 同上
- `UiScheduledTask.remote_browser_service` → 同上

`null` 表示本地执行，有值表示远程执行。同时用于执行记录追溯。

## 5. 浏览器连接工厂

新增文件：`apps/ui_automation/browser_factory.py`

### 5.1 公开接口

```python
class BrowserConnectionFactory:
    @staticmethod
    def create_selenium_driver(browser_type, headless, remote_service=None):
        """返回 selenium WebDriver 实例"""
    
    @staticmethod
    async def create_playwright_browser(playwright_instance, browser_type, headless, remote_service=None):
        """返回 Playwright Browser 实例"""
```

### 5.2 连接方式实现

**Selenium Grid**：
```python
options = _build_selenium_options(browser_type, headless)
options.set_capability('browserName', browser_type)
for k, v in remote_service.capabilities.items():
    options.set_capability(k, v)
driver = webdriver.Remote(command_executor=remote_service.url, options=options)
```

**BrowserStack / Sauce Labs**：
```python
options = _build_selenium_options(browser_type, headless)
auth = remote_service.auth_config  # {"username": "...", "access_key": "..."}
# BrowserStack: 将 auth 写入 capabilities 的 bstack:options
# SauceLabs: 将 auth 写入 capabilities 的 sauce:options
for k, v in remote_service.capabilities.items():
    options.set_capability(k, v)
driver = webdriver.Remote(command_executor=remote_service.url, options=options)
```

**Playwright Remote**：
```python
browser = await playwright_instance.chromium.connect(ws_endpoint=remote_service.url)
```

**Playwright CDP**：
```python
browser = await playwright_instance.chromium.connect_over_cdp(endpoint_url=remote_service.url)
```

### 5.3 现有代码改造

- `SeleniumTestEngine.__init__` 新增 `remote_service=None` 参数
- `SeleniumTestEngine.start()` 改为调用 `BrowserConnectionFactory.create_selenium_driver()`
- `PlaywrightTestEngine.__init__` 新增 `remote_service=None` 参数
- `PlaywrightTestEngine.start()` 改为调用 `BrowserConnectionFactory.create_playwright_browser()`
- `test_executor.py` 中的 `create_selenium_driver()` 方法和 `sync_playwright` 启动逻辑改为调用工厂
- 本地创建逻辑原封不动搬到工厂的 `_create_local_selenium()` / `_create_local_playwright()` 私有函数

## 6. API 接口

### 6.1 RemoteBrowserService CRUD

前缀：`/api/ui-automation/remote-browser-services/`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 列表（按 `project` 查询参数筛选） |
| POST | `/` | 创建 |
| GET | `/{id}/` | 详情 |
| PUT | `/{id}/` | 更新 |
| DELETE | `/{id}/` | 删除 |
| POST | `/{id}/test-connection/` | 测试连接可用性 |

ViewSet：`RemoteBrowserServiceViewSet`，继承 `ModelViewSet`。

`test-connection` action 实现：
- `selenium_grid` → 尝试 `webdriver.Remote` 创建后立即 `quit()`
- `playwright_remote` → `connect()` 后 `close()`
- `playwright_cdp` → `connect_over_cdp()` 后 `close()`
- `browserstack` / `saucelabs` → HTTP 请求验证 API 认证

### 6.2 执行入口改动

三个执行入口的请求体新增可选字段 `remote_browser_service_id`：

- `TestSuiteViewSet.run_suite` — `request.data.get('remote_browser_service_id', None)`
- `TestCaseViewSet.run` — 同上
- 定时任务触发 — 从 `UiScheduledTask.remote_browser_service` 读取

流程：`remote_browser_service_id` → 查库得到实例 → 传入引擎/工厂 → 工厂分发。不传时行为完全不变。

## 7. 前端 UI

### 7.1 配置中心 — 远程浏览器管理页

新增路由：`/configuration/remote-browser`

页面组件：`frontend/src/views/configuration/RemoteBrowserConfig.vue`

参考 `NotificationConfig.vue` 风格：

**表格列**：名称 | 服务类型 | URL | 状态 | 创建者 | 操作(编辑/测试连接/删除)

**新增/编辑对话框字段**：
- 名称（el-input）
- 服务类型（el-select，5 种类型）
- URL（el-input，placeholder 根据服务类型动态变化）
- 认证配置（仅 BrowserStack / Sauce Labs 时显示 username + access_key）
- 额外能力配置（JSON 编辑器，折叠面板）
- 「测试连接」按钮

### 7.2 执行对话框改动

涉及：套件执行对话框、单用例执行对话框、定时任务表单

在现有「引擎 / 浏览器 / 无头模式」下方新增：

```
执行方式：  ○ 本地执行（默认）  ○ 远程执行
[远程执行时展开]
远程服务：  [下拉选择，from RemoteBrowserService where project=当前项目 and is_active=true]
```

**引擎自动锁定规则**：
- `selenium_grid` / `browserstack` / `saucelabs` → 引擎锁定为 Selenium
- `playwright_remote` / `playwright_cdp` → 引擎锁定为 Playwright

浏览器类型下拉仍保留供用户选择。

### 7.3 执行结果展示

执行记录详情中增加：
- 执行方式标签：本地 / 远程
- 远程服务名称（远程执行时显示）

## 8. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `apps/ui_automation/models.py` | 修改 | 新增 `RemoteBrowserService`；3 个模型加 FK |
| `apps/ui_automation/browser_factory.py` | 新增 | 浏览器连接工厂 |
| `apps/ui_automation/selenium_engine.py` | 修改 | `start()` 改为调用工厂 |
| `apps/ui_automation/playwright_engine.py` | 修改 | `start()` 改为调用工厂 |
| `apps/ui_automation/test_executor.py` | 修改 | 浏览器创建逻辑改为调用工厂 |
| `apps/ui_automation/serializers.py` | 修改 | 新增 `RemoteBrowserServiceSerializer` |
| `apps/ui_automation/views.py` | 修改 | 新增 ViewSet + 执行入口加参数 |
| `apps/ui_automation/urls.py` | 修改 | 注册新路由 |
| `frontend/src/api/ui_automation.js` | 修改 | 新增远程浏览器服务 API 调用 |
| `frontend/src/views/configuration/RemoteBrowserConfig.vue` | 新增 | 配置管理页 |
| `frontend/src/router/index.js` | 修改 | 新增配置页路由 |
| `frontend/src/views/ui-automation/suites/SuiteList.vue` | 修改 | 执行对话框加远程选项 |
| `frontend/src/views/ui-automation/scheduled-tasks/ScheduledTasks.vue` | 修改 | 表单加远程服务选择 |
| `frontend/src/locales/zh-cn/*.json` / `en/*.json` | 修改 | i18n 翻译 |

## 9. 数据库迁移

一次迁移即可：
1. 创建 `ui_remote_browser_services` 表
2. `ui_test_executions` 加 `remote_browser_service_id` 列（nullable FK）
3. `ui_test_case_executions` 加 `remote_browser_service_id` 列（nullable FK）
4. `ui_scheduled_tasks` 加 `remote_browser_service_id` 列（nullable FK）

## 10. 不在范围内

- 远程浏览器服务的健康监控/心跳检测
- 浏览器资源池/排队机制
- 并发执行限制（由远程服务本身管理）
- AI 智能模式（`ai_base.py`）的远程浏览器支持