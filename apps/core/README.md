# 核心功能模块 (Core App)

## 概述

`apps.core` 是一个通用功能模块，用于存放跨模块的管理命令和工具。

## 当前功能

### 1. 统一定时任务调度器

**推荐方式**: `celery -A backend beat`（调度项见 `settings.CELERY_BEAT_SCHEDULE`）

**备用命令**: `python manage.py run_all_scheduled_tasks`——在当前进程内循环执行同一批调度任务，
与 Beat 并存也不会重复执行（各 dispatch 任务通过条件更新抢占到期任务）。

**功能**: 调度 API 测试、UI 自动化、定时用例生成三个模块的定时任务，实际执行都提交给 Celery worker

**支持的模块**:
- API 测试模块 (`apps.api_testing.models.ScheduledTask`)
- UI 自动化模块 (`apps.ui_automation.models.UiScheduledTask`)
- 定时用例生成 (`apps.requirement_analysis.models.ScheduledGenerationTask`)

**调度项**（`settings.CELERY_BEAT_SCHEDULE`，均每 60 秒触发一次）:

| Beat 调度项 | Celery 任务 | 实现位置 |
|------|------|------|
| api-testing-dispatch-due-tasks | `api_testing.dispatch_due_tasks` | `apps/api_testing/tasks.py` |
| ui-automation-dispatch-due-tasks | `ui_automation.dispatch_due_tasks` | `apps/ui_automation/tasks.py` |
| requirement-analysis-dispatch-due-generation-tasks | `requirement_analysis.dispatch_due_generation_tasks` | `apps/requirement_analysis/tasks.py` |

**依赖**: Redis（broker）+ Celery worker。Beat 只负责"发现到期任务并提交"，真正的执行在 worker 中进行，
因此只启动 Beat 而没有 worker 时，任务会停留在队列里不执行。

### 2. 初始化元素定位策略

**命令**: `python manage.py init_locator_strategies`

**功能**: 初始化 UI 自动化测试的元素定位策略

**说明**: 此命令会创建/更新 12 种常用的元素定位策略，包括：
- 通用策略：ID, CSS, XPath, name, class, tag
- Playwright 专用策略：text, placeholder, role, label, title, test-id

### 3. 下载 WebDriver 驱动

**命令**: `python manage.py download_webdrivers`

**功能**: 预下载浏览器 WebDriver 驱动程序

**支持**:
- Chrome (ChromeDriver)
- Firefox (GeckoDriver)
- Edge (EdgeDriver)

**说明**: 首次使用 UI 自动化测试前建议先下载驱动，避免测试时等待下载

## 使用方法

### 1. 启动调度（推荐：Celery Beat）

先启动 Redis，再在项目根目录分别启动 worker 和 Beat：

```bash
# Celery worker - 默认队列（执行定时任务、UI 套件、AI 用例生成）
# Windows 使用 threads 池；Linux/Mac 可去掉 --pool 参数使用默认 prefork
celery -A backend worker -Q celery --pool=threads --concurrency=4 --loglevel=info

# Celery worker - AI 智能模式队列（只能单并发）
celery -A backend worker -Q ai_automation --pool=solo --loglevel=info -n ai@%h

# Celery Beat - 全局只需启动一个
celery -A backend beat --loglevel=info
```

Beat 会在工作目录生成 `celerybeat-schedule*` 状态文件（已加入 `.gitignore`），删除后会自动重建。

### 2. 备用方式：管理命令

不便部署 Beat 时，可用管理命令在当前进程内循环执行同一批调度任务（仍需启动 worker）：

```bash
# 默认每60秒检查一次
python manage.py run_all_scheduled_tasks

# 自定义检查间隔（例如30秒）
python manage.py run_all_scheduled_tasks --interval 30

# 只执行一次检查，不循环（适合调试）
python manage.py run_all_scheduled_tasks --once
```

### 3. 初始化元素定位策略

```bash
# 初始化UI自动化的元素定位策略
python manage.py init_locator_strategies
```

**输出示例**:
```
开始初始化定位策略...
  ✓ 创建策略: ID
  ✓ 创建策略: CSS
  ✓ 创建策略: XPath
  - 策略已存在: name
  ...

============================================================
初始化完成！
新创建: 3 个
更新: 0 个
总计: 12 个定位策略
============================================================

当前可用的定位策略：
  - ID: 通过元素的 id 属性定位，最快速可靠
  - CSS: 通过 CSS 选择器定位，灵活强大
  - XPath: 通过 XPath 表达式定位，功能最强大
  ...
```

### 4. 下载 WebDriver 驱动

```bash
# 下载所有浏览器的驱动（默认）
python manage.py download_webdrivers

# 只下载指定浏览器的驱动
python manage.py download_webdrivers --browsers chrome firefox

# 只下载 Chrome 驱动
python manage.py download_webdrivers --browsers chrome
```

**输出示例**:
```
开始下载WebDriver驱动程序...
注意：首次下载可能需要几分钟时间

正在下载 ChromeDriver...
✓ ChromeDriver 下载成功 (耗时: 45.2秒)
  路径: /Users/xxx/.wdm/drivers/chromedriver/mac64/129.0.6668.58/chromedriver

正在下载 GeckoDriver (Firefox)...
✓ GeckoDriver 下载成功 (耗时: 32.1秒)
  路径: /Users/xxx/.wdm/drivers/geckodriver/mac64/v0.35.0/geckodriver

正在下载 EdgeDriver...
✓ EdgeDriver 下载成功 (耗时: 28.5秒)
  路径: /Users/xxx/.wdm/drivers/edgedriver/mac64/129.0.2792.65/edgedriver

============================================================
下载完成！成功: 3个
============================================================
驱动程序已缓存，后续测试执行将会更快！
```

**说明**:
- 首次下载可能需要几分钟，驱动会缓存到本地
- 后续执行测试时会自动使用缓存的驱动，无需重新下载
- 如果不预先下载，测试执行时会自动下载，但会增加测试等待时间

### 5. 生产环境部署建议

生产环境需要常驻以下进程：后端 API（ASGI）、Celery worker（默认队列）、Celery worker（ai_automation 队列，按需）、Celery Beat（全局一个）。

#### 方案1: 使用 systemd (推荐 Linux)

创建 `/etc/systemd/system/testhub-worker.service`:

```ini
[Unit]
Description=TestHub Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=your_user
Group=your_group
WorkingDirectory=/path/to/testhub_platform
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A backend worker -Q celery --concurrency=4 --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

AI 智能模式队列复制一份为 `testhub-worker-ai.service`，`ExecStart` 改为：

```ini
ExecStart=/path/to/venv/bin/celery -A backend worker -Q ai_automation --concurrency=1 --loglevel=info -n ai@%%h
```

创建 `/etc/systemd/system/testhub-beat.service`（`ExecStart` 改为 Beat，其余同上）:

```ini
ExecStart=/path/to/venv/bin/celery -A backend beat --loglevel=info
```

启动服务:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now testhub-worker testhub-worker-ai testhub-beat
sudo systemctl status testhub-worker testhub-beat
```

#### 方案2: 使用 Supervisor

配置文件 `/etc/supervisor/conf.d/testhub-celery.conf`:

```ini
[program:testhub-worker]
command=/path/to/venv/bin/celery -A backend worker -Q celery --concurrency=4 --loglevel=info
directory=/path/to/testhub_platform
user=your_user
autostart=true
autorestart=true
stopwaitsecs=600
redirect_stderr=true
stdout_logfile=/var/log/supervisor/testhub-worker.log

[program:testhub-worker-ai]
command=/path/to/venv/bin/celery -A backend worker -Q ai_automation --concurrency=1 --loglevel=info -n ai@%%h
directory=/path/to/testhub_platform
user=your_user
autostart=true
autorestart=true
stopwaitsecs=600
redirect_stderr=true
stdout_logfile=/var/log/supervisor/testhub-worker-ai.log

[program:testhub-beat]
command=/path/to/venv/bin/celery -A backend beat --loglevel=info
directory=/path/to/testhub_platform
user=your_user
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/testhub-beat.log
```

启动:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl status
```

#### 方案3: 使用 nohup (简单方式)

```bash
nohup celery -A backend worker -Q celery --concurrency=4 --loglevel=info > logs/celery-worker.log 2>&1 &
nohup celery -A backend worker -Q ai_automation --concurrency=1 --loglevel=info -n ai@%h > logs/celery-worker-ai.log 2>&1 &
nohup celery -A backend beat --loglevel=info > logs/celery-beat.log 2>&1 &
```

查看日志:
```bash
tail -f logs/celery-worker.log logs/celery-beat.log
```

> 注意：Beat 全局只能运行一个实例；worker 可以按需多开（ai_automation 队列除外）。
> 即使误启动了多个 Beat 或同时运行了 `run_all_scheduled_tasks`，调度任务的条件更新抢占也能保证同一到期任务只执行一次。

## 调度器输出示例

`python manage.py run_all_scheduled_tasks` 的输出：

```
启动统一定时任务调度器，检查间隔 60 秒
调度任务: api_testing.dispatch_due_tasks, ui_automation.dispatch_due_tasks, requirement_analysis.dispatch_due_generation_tasks

[2026-01-10 23:30:00] 开始检查任务...
  ✓ api_testing.dispatch_due_tasks: 提交了 1 个任务
  ✓ ui_automation.dispatch_due_tasks: 提交了 1 个任务
```

使用 Beat 时，可在 worker 日志中看到 `[API] 定时任务已提交: xxx`、`[UI] 定时任务已提交: xxx`、`触发定时生成任务: ...` 等记录。

## 与原有命令的对比

### 统一定时任务调度器

**旧命令（已弃用）**:
```bash
# 只能调度 API 测试任务
python manage.py run_scheduled_tasks
```

**新方式（推荐）**:
```bash
# Celery Beat 统一调度 API 测试、UI 自动化、定时用例生成（需配合 Celery worker）
celery -A backend beat --loglevel=info

# 备用：管理命令
python manage.py run_all_scheduled_tasks
```

> 定时用例生成原来由 `requirement_analysis` 在每个 Django 进程启动时各自启动 APScheduler，
> 多进程部署时会重复触发，现已移除，统一由 Beat 调度。

### 初始化元素定位策略

**旧命令位置**:
```bash
# 位于 apps/ui_automation/management/commands/
python manage.py init_locator_strategies
```

**新命令位置**:
```bash
# 位于 apps/core/management/commands/
python manage.py init_locator_strategies
```

**说明**: 命令功能完全相同，只是位置移到了 core 模块统一管理。

### 下载 WebDriver 驱动

**旧命令位置**:
```bash
# 位于 apps/ui_automation/management/commands/
python manage.py download_webdrivers
```

**新命令位置**:
```bash
# 位于 apps/core/management/commands/
python manage.py download_webdrivers
```

**说明**: 命令功能完全相同，只是位置移到了 core 模块统一管理。

## 注意事项

1. **不要同时运行多个调度器**: 确保同一时间只有一个调度器实例在运行，否则可能导致任务重复执行

2. **权限要求**: 调度器需要访问数据库和执行测试的权限，确保运行用户有足够的权限

3. **日志管理**: 建议将调度器输出重定向到日志文件，便于排查问题

4. **定时任务配置**: 定时任务需要在 Web 界面中配置，调度器只负责执行已配置的任务

5. **元素定位策略初始化**: 首次使用 UI 自动化测试功能前，建议先运行 `init_locator_strategies` 命令初始化定位策略

6. **WebDriver 预下载**: 首次使用 UI 自动化测试前，建议运行 `download_webdrivers` 命令预下载浏览器驱动，避免测试时等待下载

## 扩展说明

为其他模块添加定时任务调度：

1. 在该模块的 `tasks.py` 中实现一个 `@shared_task` 调度任务（参考 `apps/api_testing/tasks.py` 的 `dispatch_due_tasks`），
   用条件更新抢占到期任务后再 `.delay()` 提交执行
2. 在 `settings.CELERY_BEAT_SCHEDULE` 中注册该任务，`run_all_scheduled_tasks` 命令会自动一并执行
