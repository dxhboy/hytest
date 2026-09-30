# CLAUDE.md

This file provides guidance to Claude Code when **developing the TestHub platform itself** (Django backend + Vue 3 frontend).

> 用 TestHub 平台管理其他项目的用例和自动化脚本，请切换到 `workspace/`（项目根目录下）。

## Project Overview

TestHub is an AI-driven test management platform built with Django 4.2 (backend) + Vue 3 (frontend). It provides test case management, API testing, UI automation testing, AI-powered requirement analysis, and test case generation capabilities.

## 路径规范

- 所有文件路径使用**相对路径**（相对于项目根目录），不使用绝对路径，确保项目迁移后无需修改任何配置。

## Skill 路由规则

| 场景 | 必用 Skill |
|------|-----------|
| 新增功能/页面 | `superpowers:brainstorming` → `superpowers:writing-plans` |
| Bug 修复 | `superpowers:systematic-debugging` |
| 实现功能代码 | `superpowers:test-driven-development` |
| 多个独立子任务 | `superpowers:dispatching-parallel-agents` |
| 提交/合并前 | `superpowers:verification-before-completion` |

## Common Commands

```bash
# 激活虚拟环境（Windows，venv 在项目目录下）
source venv/Scripts/activate

# 激活虚拟环境（MacOS）
source .venv/bin/activate
```

### 启动项目（开发环境）

一键启动（先启动 Redis）：`python scripts/dev.py`，可用 `--only` / `--skip` 选择服务（backend/worker/ai/beat/frontend），Ctrl+C 全部停止。

等价于分别启动以下服务：

| # | 服务 | `dev.py` 服务名 | 手动启动命令 | 是否必需 |
|---|------|----------------|-------------|---------|
| 0 | Redis | —（需自行启动） | 例如 `redis-server` | 必需：Celery 任务队列、定时调度、缓存都依赖它 |
| 1 | 后端（HTTP 接口 + WebSocket，脚本录制也在这里） | `backend` | `uvicorn backend.asgi:application --host 0.0.0.0 --port 8001 --reload --loop backend.event_loop:loop_factory` | 必需 |
| 2 | Celery worker（默认队列） | `worker` | `celery -A backend worker -Q celery --pool=threads --concurrency=4 --loglevel=info` | 必需：UI 套件执行、API 套件执行、AI 用例生成、定时任务的执行都走这里 |
| 3 | Celery worker（AI 队列） | `ai` | `celery -A backend worker -Q ai_automation --pool=solo --loglevel=info -n ai@%h` | 使用 UI 自动化 **AI 智能模式**时需要 |
| 4 | Celery Beat | `beat` | `celery -A backend beat --loglevel=info` | 需要**定时任务**自动触发时需要（不启动时手动"立即执行"仍可用） |
| 5 | 前端（Vite） | `frontend` | `cd frontend` 后 `npm run dev` | 必需 |

日常开发最少需要 0、1、2、5；3、4 按需启动（`python scripts/dev.py --skip ai,beat`）。

说明：
- 后端命令中的 `--loop` 必须保留：Windows 上 uvicorn 开启 `--reload` 时默认改用 SelectorEventLoop，脚本录制在后端用 Playwright 启动浏览器会报 `NotImplementedError`（见 `backend/event_loop.py`）
- 后端端口 8001 是前端开发代理（`frontend/vite.config.js`）指向的端口，只需启动一个后端实例
- Windows 不支持 Celery 的 prefork 池，默认队列用 threads 池；Linux/Mac 可去掉 `--pool=threads` 使用默认 prefork
- AI 队列受 GIF 录制文件名限制只能单并发（`--pool=solo`）；Beat 全局只启动一个

### Backend (Django)

```bash
pip install -r requirements-dev.txt   # 开发依赖（含 pytest）
python -m pytest                      # 运行全部后端测试（tests/ + apps/）
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py run_all_scheduled_tasks
python manage.py init_locator_strategies
python manage.py download_webdrivers
```

### Frontend (Vue 3 + Vite)

```bash
cd frontend
npm install
npm run build
npm run lint
```

## Architecture

### Backend Structure (`apps/`)

- **users**: User authentication and profile management (custom User model)
- **projects**: Project and team management
- **testcases**: Manual test case management with steps, attachments, comments
- **testsuites**: Test suite organization
- **executions**: Test plan execution and result tracking
- **reports**: Test report generation
- **reviews**: Test case review workflow with templates and assignments
- **versions**: Version/release management
- **requirement_analysis**: AI-powered requirement document parsing (PDF/Word/TXT) and test case generation
- **assistant**: Dify AI chatbot integration
- **api_testing**: API testing module (HTTP/WebSocket, environments, scheduled tasks, Allure reports)
- **ui_automation**: UI automation with Selenium/Playwright, element management, page objects, AI intelligent mode
- **core**: Shared logic, variable resolution, `llm/`（统一的 OpenAI 兼容 LLM 客户端，含 Bedrock 路由）、`notifications.py`（Webhook/邮件发送）、`permissions.py`
- **data_factory**: Test data generation

### 分层约定

- 大模块（api_testing / ui_automation / requirement_analysis）的视图是 `views/` 包，按领域拆分，`views/__init__.py` 统一导出；业务逻辑放在 `services/`（或 `generation.py` 等模块），**services 不得反向 import views**
- 后台执行一律走 Celery 任务（各 app 的 `tasks.py`），不要在视图里起线程；定时调度由 Celery Beat 触发各 app 的 `dispatch_*` 任务（`settings.CELERY_BEAT_SCHEDULE`）
- 按项目归属的数据必须用 `apps/projects/access.py`（`accessible_project_ids` / `ensure_project_access` / `project_or_owner_q`）过滤；全局配置写操作用 `apps.core.permissions.IsStaffOrReadOnly`
- 调用大模型统一用 `apps.core.llm.LLMClient`，不要再直接写 requests/httpx 调用

### Frontend Structure (`frontend/src/`)

- **views/**: Page components organized by feature module
- **api/**: API service layer
- **stores/**: Pinia state management
- **router/**: Vue Router configuration
- **components/**: Shared components
- **layout/**: Layout components

### Key Configuration Files

- `backend/settings.py`: Django settings (database, REST framework, CORS, Celery, email)
- `frontend/vite.config.js`: Vite build configuration
- `.env`: Environment variables (DB credentials, API keys, email config)

## API Structure

All API endpoints are prefixed with `/api/`:
- `/api/auth/` and `/api/users/`: User authentication
- `/api/projects/`: Project management
- `/api/testcases/`: Test case CRUD
- `/api/testsuites/`: Test suite management
- `/api/executions/`: Test execution
- `/api/reports/`: Report generation
- `/api/reviews/`: Review workflow
- `/api/versions/`: Version management
- `/api/assistant/`: AI assistant chat
- `/api/requirement-analysis/`: AI requirement analysis
- `/api/` (api_testing): API testing endpoints
- `/api/ui-automation/`: UI automation endpoints

API documentation: `/api/docs/` (Swagger), `/api/redoc/` (ReDoc)

## Database

MySQL 8.0+ with `utf8mb4` charset. Configuration via environment variables:
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

## AI Integration

Multiple AI providers configured in `requirement_analysis.AIModelConfig`:
- DeepSeek, Qwen (通义千问), SiliconFlow (硅基流动), OpenAI-compatible APIs
- AI roles: `testcase_writer`, `testcase_reviewer`, `browser_use_text`, `browser_use_vision`

UI automation AI mode uses `browser-use` library with LangChain (`apps/ui_automation/ai_agent.py`).

## Testing Prompt Templates

- `tester.md`: Test case writer persona and output format
- `tester_pro.md`: Test case reviewer persona

## Key Dependencies

Backend: Django REST Framework, drf-spectacular, django-filter, celery, httpx, selenium, playwright, browser-use, langchain-openai

Frontend: Vue 3, Element Plus, Pinia, Vue Router, Axios, ECharts, Monaco Editor, xlsx

## Commit 规范

- 默认不自动提交代码
- 多个相关修改应合并为一个 commit
- commit message 格式：`<type>: <简短描述>`
- 提交前必须运行 lint 和测试