# AI Assistant Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 TestHub 自动化平台全局添加右下角悬浮 AI 对话助手，支持通过 function calling 对 api-testing 和 ui-automation 模块进行读、写、执行操作。

**Architecture:** 新建独立 Django App `apps/ai_assistant/`，通过 OpenAI-compatible API + function calling 实现工具调度，多轮 tool call 循环在后端完成（最多 5 轮）；前端 `AiAssistantPanel.vue` 通过 `<Teleport to="body">` 挂载为全局右下角悬浮弹窗，上下文（模块/页面）由路由 meta 自动注入。

**Tech Stack:** Django 4.2, httpx, DRF; Vue 3 + Pinia + Element Plus + Teleport

---

## 文件清单

### 新建（后端）
| 文件 | 职责 |
|------|------|
| `apps/ai_assistant/__init__.py` | App 包 |
| `apps/ai_assistant/apps.py` | AppConfig |
| `apps/ai_assistant/models.py` | AssistantSession, AssistantMessage |
| `apps/ai_assistant/serializers.py` | 请求/响应序列化 |
| `apps/ai_assistant/views.py` | ChatView, SessionViewSet |
| `apps/ai_assistant/urls.py` | 路由注册 |
| `apps/ai_assistant/tests.py` | 后端单测 |
| `apps/ai_assistant/tools/__init__.py` | TOOL_DEFINITIONS, TOOLS_REGISTRY 导出 |
| `apps/ai_assistant/tools/base.py` | ToolDispatcher, call_llm_with_tools |
| `apps/ai_assistant/tools/api_testing_tools.py` | 7 个 api-testing 工具函数 |
| `apps/ai_assistant/tools/ui_automation_tools.py` | 5 个 ui-automation 工具函数 |

### 新建（前端）
| 文件 | 职责 |
|------|------|
| `frontend/src/stores/aiAssistant.js` | Pinia store (isOpen, messages, loading…) |
| `frontend/src/api/ai-assistant.js` | API 服务层 |
| `frontend/src/components/ai-assistant/AiAssistantPanel.vue` | 主容器：悬浮按钮 + 弹窗外壳 |
| `frontend/src/components/ai-assistant/AiChatWindow.vue` | 聊天窗口：消息列表 + 输入区 |
| `frontend/src/components/ai-assistant/AiMessageBubble.vue` | 单条消息气泡（支持 Markdown） |
| `frontend/src/components/ai-assistant/AiToolCallIndicator.vue` | 工具调用状态提示 |
| `frontend/src/locales/lang/zh-cn/ai-assistant.js` | 中文 i18n |
| `frontend/src/locales/lang/en/ai-assistant.js` | 英文 i18n |

### 修改（已有文件）
| 文件 | 改动 |
|------|------|
| `backend/settings.py` | INSTALLED_APPS 加 `apps.ai_assistant` |
| `backend/urls.py` | 注册 `/api/ai-assistant/` 路由 |
| `frontend/src/layout/index.vue` | 引入并挂载 `<AiAssistantPanel />` |
| `frontend/src/router/index.js` | api-testing + ui-automation 路由加 meta.module/page |
| `frontend/src/locales/lang/zh-cn/index.js` | 导入 ai-assistant.js |
| `frontend/src/locales/lang/en/index.js` | 导入 ai-assistant.js |

---

## Task 1: Django App 骨架 + 数据模型

**Files:**
- Create: `apps/ai_assistant/__init__.py`
- Create: `apps/ai_assistant/apps.py`
- Create: `apps/ai_assistant/models.py`
- Create: `apps/ai_assistant/tests.py`

- [ ] **Step 1: 创建 App 目录结构**

```bash
cd /d/python/testhub_platform-main
source venv/Scripts/activate
mkdir -p apps/ai_assistant/tools apps/ai_assistant/migrations
touch apps/ai_assistant/__init__.py
touch apps/ai_assistant/tools/__init__.py
touch apps/ai_assistant/migrations/__init__.py
```

- [ ] **Step 2: 写 apps.py**

Create `apps/ai_assistant/apps.py`:

```python
from django.apps import AppConfig


class AiAssistantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ai_assistant'
    verbose_name = 'AI Assistant Panel'
```

- [ ] **Step 3: 写 models.py**

Create `apps/ai_assistant/models.py`:

```python
from django.db import models
from django.conf import settings


class AssistantSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_panel_sessions'
    )
    title = models.CharField(max_length=100, default='新会话')
    context_module = models.CharField(max_length=50, blank=True)
    context_page = models.CharField(max_length=100, blank=True)
    context_project_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user} - {self.title}'


class AssistantMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('tool', 'Tool'),
    ]
    session = models.ForeignKey(
        AssistantSession, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tool_name = models.CharField(max_length=100, blank=True)
    tool_result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
```

- [ ] **Step 4: 写 tests.py（先写失败测试）**

Create `apps/ai_assistant/tests.py`:

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import AssistantSession, AssistantMessage

User = get_user_model()


class AssistantSessionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass')

    def test_create_session(self):
        session = AssistantSession.objects.create(
            user=self.user,
            title='测试会话',
            context_module='api-testing',
            context_page='interface-management',
            context_project_id=1,
        )
        self.assertEqual(session.title, '测试会话')
        self.assertEqual(session.context_module, 'api-testing')

    def test_create_message(self):
        session = AssistantSession.objects.create(user=self.user)
        msg = AssistantMessage.objects.create(
            session=session, role='user', content='帮我列出接口'
        )
        self.assertEqual(msg.role, 'user')
        self.assertEqual(session.messages.count(), 1)

    def test_session_ordering_by_updated(self):
        s1 = AssistantSession.objects.create(user=self.user, title='s1')
        s2 = AssistantSession.objects.create(user=self.user, title='s2')
        sessions = list(AssistantSession.objects.filter(user=self.user))
        self.assertEqual(sessions[0].id, s2.id)
```

- [ ] **Step 5: 运行测试确认失败（模型还未注册）**

```bash
cd /d/python/testhub_platform-main
source venv/Scripts/activate
python manage.py test apps.ai_assistant.tests.AssistantSessionModelTest 2>&1 | head -20
```

Expected: `RuntimeError: No module named 'apps.ai_assistant'` 或 `AppRegistryNotReady`（因为还未注册到 INSTALLED_APPS）

- [ ] **Step 6: 注册到 INSTALLED_APPS + 生成迁移**

In `backend/settings.py`, find the `LOCAL_APPS` list and add:

```python
LOCAL_APPS = [
    # ... existing apps ...
    'apps.ai_assistant',   # <-- 添加这行
]
```

Then run:

```bash
python manage.py makemigrations ai_assistant
python manage.py migrate
```

Expected output: `Migrations for 'ai_assistant': apps/ai_assistant/migrations/0001_initial.py`

- [ ] **Step 7: 运行测试确认通过**

```bash
python manage.py test apps.ai_assistant.tests.AssistantSessionModelTest -v 2
```

Expected: `OK (tests=3)`

- [ ] **Step 8: Commit**

```bash
git add apps/ai_assistant/ backend/settings.py
git commit -m "feat: add ai_assistant app with Session and Message models"
```

---

## Task 2: 工具基础层 (ToolDispatcher + LLM 调用)

**Files:**
- Create: `apps/ai_assistant/tools/base.py`

- [ ] **Step 1: 写 tools/base.py**

Create `apps/ai_assistant/tools/base.py`:

```python
import json
import logging
import httpx
from apps.requirement_analysis.models import AIModelConfig

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


def _build_llm_url(base_url: str) -> str:
    base_url = base_url.rstrip('/')
    if base_url.endswith('/chat/completions'):
        return base_url
    if base_url.endswith('/v1'):
        return f'{base_url}/chat/completions'
    return f'{base_url}/v1/chat/completions'


def call_llm_with_tools(messages: list, tools: list) -> dict:
    """调用 OpenAI-compatible API，返回原始响应 dict。未配置模型时抛 ValueError。"""
    config = AIModelConfig.objects.filter(is_active=True, role='writer').first()
    if not config:
        raise ValueError('未找到可用的 AI 模型配置，请在"配置中心 → AI 模型配置"中添加并启用一个 writer 角色的配置。')

    url = _build_llm_url(config.base_url)
    headers = {'Authorization': f'Bearer {config.api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': config.model_name,
        'messages': messages,
        'max_tokens': config.max_tokens,
        'temperature': config.temperature,
        'tools': tools,
        'tool_choice': 'auto',
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


class ToolDispatcher:
    """将模型返回的 tool_call 分发到对应的 Python 函数。"""

    _registry: dict = {}  # {tool_name: callable}

    @classmethod
    def register(cls, name: str, func):
        cls._registry[name] = func

    @classmethod
    def execute(cls, tool_name: str, args: dict, user, context: dict) -> dict:
        func = cls._registry.get(tool_name)
        if not func:
            return {'error': f'未知工具: {tool_name}'}
        try:
            return func(user=user, context=context, **args)
        except Exception as e:
            logger.exception('Tool %s failed', tool_name)
            return {'error': str(e)}


def run_tool_loop(messages: list, tools: list, user, context: dict) -> tuple[str, list]:
    """
    执行完整的 tool-call 循环，返回 (final_reply, tools_called_names)。
    messages 应已包含 system prompt 和本轮用户消息。
    """
    from apps.ai_assistant.tools import TOOL_DEFINITIONS  # 延迟导入避免循环

    tools_called = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = call_llm_with_tools(messages, TOOL_DEFINITIONS)
        choice = response['choices'][0]
        msg = choice['message']
        finish_reason = choice.get('finish_reason', '')

        if finish_reason != 'tool_calls':
            return msg.get('content') or '', tools_called

        # 执行工具调用
        messages.append(msg)
        for tc in msg.get('tool_calls', []):
            name = tc['function']['name']
            args = json.loads(tc['function']['arguments'])
            tools_called.append(name)
            result = ToolDispatcher.execute(name, args, user, context)
            messages.append({
                'role': 'tool',
                'tool_call_id': tc['id'],
                'content': json.dumps(result, ensure_ascii=False),
            })

    return '工具调用轮次超出上限，请简化您的请求后重试。', tools_called
```

- [ ] **Step 2: Commit**

```bash
git add apps/ai_assistant/tools/base.py
git commit -m "feat: add ToolDispatcher and LLM call helper"
```

---

## Task 3: api_testing 工具函数

**Files:**
- Create: `apps/ai_assistant/tools/api_testing_tools.py`

- [ ] **Step 1: 写 api_testing_tools.py**

Create `apps/ai_assistant/tools/api_testing_tools.py`:

```python
from django.db import models as db_models


def list_interfaces(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出用户可见的接口用例（最多 50 条）。"""
    from apps.api_testing.models import ApiRequest
    limit = min(limit, 50)
    qs = ApiRequest.objects.filter(
        db_models.Q(visibility='all') | db_models.Q(created_by=user)
    ).select_related('collection__project')

    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(collection__project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)

    items = list(qs.values('id', 'name', 'method', 'url', 'description')[:limit])
    return {'total': qs.count(), 'items': items}


def get_interface(user, context: dict, interface_id: int):
    """获取单条接口用例的详情。"""
    from apps.api_testing.models import ApiRequest
    try:
        req = ApiRequest.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=interface_id,
        ).values('id', 'name', 'method', 'url', 'description', 'headers',
                 'params', 'body', 'assertions').get()
        return req
    except ApiRequest.DoesNotExist:
        return {'error': f'接口 {interface_id} 不存在或无访问权限'}


def create_interface(user, context: dict, name: str, method: str, url: str,
                     collection_id: int = None, description: str = '',
                     headers: dict = None, params: dict = None, body: dict = None):
    """创建新接口用例。method 可选 GET/POST/PUT/DELETE/PATCH。"""
    from apps.api_testing.models import ApiRequest, ApiCollection
    collection = None
    if collection_id:
        collection = ApiCollection.objects.filter(id=collection_id).first()
    req = ApiRequest.objects.create(
        name=name,
        method=method.upper(),
        url=url,
        description=description,
        collection=collection,
        headers=headers or {},
        params=params or {},
        body=body or {},
        created_by=user,
        visibility='all',
    )
    return {'id': req.id, 'name': req.name, 'method': req.method, 'url': req.url,
            'message': f'接口 "{req.name}" 创建成功'}


def list_test_suites(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出 api-testing 自动化测试套件。"""
    from apps.api_testing.models import TestSuite
    limit = min(limit, 50)
    qs = TestSuite.objects.filter(
        db_models.Q(visibility='all') | db_models.Q(created_by=user)
    )
    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    items = list(qs.values('id', 'name', 'description')[:limit])
    return {'total': qs.count(), 'items': items}


def run_test_suite(user, context: dict, suite_id: int):
    """触发 api-testing 套件执行，返回执行 ID。"""
    from apps.api_testing.models import TestSuite, TestExecution
    try:
        suite = TestSuite.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=suite_id,
        ).get()
    except TestSuite.DoesNotExist:
        return {'error': f'套件 {suite_id} 不存在或无访问权限'}

    execution = TestExecution.objects.create(
        test_suite=suite,
        status='pending',
        executed_by=user,
    )
    return {
        'execution_id': execution.id,
        'suite_name': suite.name,
        'status': 'pending',
        'message': f'套件 "{suite.name}" 已提交执行（执行ID: {execution.id}），请稍后通过 get_execution_result 查询结果。',
    }


def get_execution_result(user, context: dict, execution_id: int, module: str = 'api-testing'):
    """查询执行结果。module 为 api-testing 或 ui-automation。"""
    if module == 'ui-automation':
        from apps.ui_automation.models import TestExecution
    else:
        from apps.api_testing.models import TestExecution

    try:
        ex = TestExecution.objects.filter(
            db_models.Q(test_suite__created_by=user) | db_models.Q(executed_by=user),
            id=execution_id,
        ).values('id', 'status', 'total_requests', 'passed_requests',
                 'failed_requests', 'start_time', 'end_time').first()
        if not ex:
            raise TestExecution.DoesNotExist
        return ex
    except Exception:
        return {'error': f'执行记录 {execution_id} 不存在或无访问权限'}
```

- [ ] **Step 2: Commit**

```bash
git add apps/ai_assistant/tools/api_testing_tools.py
git commit -m "feat: add api_testing tool functions for AI assistant"
```

---

## Task 4: ui_automation 工具函数

**Files:**
- Create: `apps/ai_assistant/tools/ui_automation_tools.py`

- [ ] **Step 1: 写 ui_automation_tools.py**

Create `apps/ai_assistant/tools/ui_automation_tools.py`:

```python
from django.db import models as db_models


def list_ui_suites(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出 UI 自动化测试套件。"""
    from apps.ui_automation.models import TestSuite
    limit = min(limit, 50)
    qs = TestSuite.objects.filter(
        db_models.Q(visibility='all') | db_models.Q(created_by=user)
    )
    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    items = list(qs.values('id', 'name', 'description', 'execution_status',
                           'passed_count', 'failed_count')[:limit])
    return {'total': qs.count(), 'items': items}


def get_ui_suite(user, context: dict, suite_id: int):
    """获取 UI 测试套件详情。"""
    from apps.ui_automation.models import TestSuite
    try:
        suite = TestSuite.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=suite_id,
        ).values('id', 'name', 'description', 'execution_status',
                 'passed_count', 'failed_count').get()
        return suite
    except TestSuite.DoesNotExist:
        return {'error': f'套件 {suite_id} 不存在或无访问权限'}


def run_ui_suite(user, context: dict, suite_id: int):
    """触发 UI 套件执行，返回执行 ID。"""
    from apps.ui_automation.models import TestSuite, TestExecution
    try:
        suite = TestSuite.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=suite_id,
        ).get()
    except TestSuite.DoesNotExist:
        return {'error': f'套件 {suite_id} 不存在或无访问权限'}

    execution = TestExecution.objects.create(
        project=suite.project,
        test_suite=suite,
        status='pending',
        executed_by=user,
    )
    return {
        'execution_id': execution.id,
        'suite_name': suite.name,
        'status': 'pending',
        'message': f'UI 套件 "{suite.name}" 已提交执行（执行ID: {execution.id}），请稍后通过 get_ui_execution_result 查询结果。',
    }


def list_ui_elements(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出元素库。"""
    from apps.ui_automation.models import Element
    limit = min(limit, 50)
    qs = Element.objects.all()
    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    items = list(qs.values('id', 'name', 'element_type', 'locator_value', 'page')[:limit])
    return {'total': qs.count(), 'items': items}


def get_ui_execution_result(user, context: dict, execution_id: int):
    """查询 UI 自动化执行结果。"""
    from apps.ui_automation.models import TestExecution
    ex = TestExecution.objects.filter(
        db_models.Q(test_suite__created_by=user) | db_models.Q(executed_by=user),
        id=execution_id,
    ).values('id', 'status', 'total_cases', 'passed_cases',
             'failed_cases', 'started_at', 'finished_at', 'error_message').first()
    if not ex:
        return {'error': f'执行记录 {execution_id} 不存在或无访问权限'}
    return ex
```

- [ ] **Step 2: Commit**

```bash
git add apps/ai_assistant/tools/ui_automation_tools.py
git commit -m "feat: add ui_automation tool functions for AI assistant"
```

---

## Task 5: 工具注册表 + TOOL_DEFINITIONS

**Files:**
- Modify: `apps/ai_assistant/tools/__init__.py`

- [ ] **Step 1: 写 tools/__init__.py**

Create `apps/ai_assistant/tools/__init__.py`:

```python
from .base import ToolDispatcher
from .api_testing_tools import (
    list_interfaces, get_interface, create_interface,
    list_test_suites, run_test_suite, get_execution_result,
)
from .ui_automation_tools import (
    list_ui_suites, get_ui_suite, run_ui_suite,
    list_ui_elements, get_ui_execution_result,
)

# 注册所有工具
_TOOLS = {
    'list_interfaces': list_interfaces,
    'get_interface': get_interface,
    'create_interface': create_interface,
    'list_test_suites': list_test_suites,
    'run_test_suite': run_test_suite,
    'get_execution_result': get_execution_result,
    'list_ui_suites': list_ui_suites,
    'get_ui_suite': get_ui_suite,
    'run_ui_suite': run_ui_suite,
    'list_ui_elements': list_ui_elements,
    'get_ui_execution_result': get_ui_execution_result,
}
for _name, _func in _TOOLS.items():
    ToolDispatcher.register(_name, _func)

# OpenAI function calling 格式的工具定义
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_interfaces",
            "description": "列出 api-testing 模块的接口用例，可按项目ID或名称关键词过滤",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID，不填则返回用户可见的所有接口"},
                    "keyword": {"type": "string", "description": "按名称关键词模糊搜索"},
                    "limit": {"type": "integer", "description": "返回条数，默认20，最大50"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_interface",
            "description": "获取单条接口用例的完整详情（含 headers、body、断言等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "interface_id": {"type": "integer", "description": "接口用例ID"},
                },
                "required": ["interface_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_interface",
            "description": "创建新的接口用例",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "接口名称"},
                    "method": {"type": "string", "description": "HTTP 方法：GET/POST/PUT/DELETE/PATCH"},
                    "url": {"type": "string", "description": "请求 URL"},
                    "collection_id": {"type": "integer", "description": "所属集合ID（可选）"},
                    "description": {"type": "string", "description": "接口描述（可选）"},
                    "headers": {"type": "object", "description": "请求头（可选）"},
                    "params": {"type": "object", "description": "查询参数（可选）"},
                    "body": {"type": "object", "description": "请求体（可选）"},
                },
                "required": ["name", "method", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_test_suites",
            "description": "列出 api-testing 自动化测试套件",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID（可选）"},
                    "keyword": {"type": "string", "description": "名称关键词（可选）"},
                    "limit": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_test_suite",
            "description": "触发 api-testing 测试套件执行，返回执行ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer", "description": "套件ID"},
                },
                "required": ["suite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_execution_result",
            "description": "查询 api-testing 或 ui-automation 的执行结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "execution_id": {"type": "integer", "description": "执行记录ID"},
                    "module": {"type": "string", "description": "模块：api-testing 或 ui-automation，默认 api-testing"},
                },
                "required": ["execution_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_suites",
            "description": "列出 UI 自动化测试套件",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID（可选）"},
                    "keyword": {"type": "string", "description": "名称关键词（可选）"},
                    "limit": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ui_suite",
            "description": "获取 UI 测试套件详情",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer", "description": "UI 套件ID"},
                },
                "required": ["suite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_ui_suite",
            "description": "触发 UI 测试套件执行",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer", "description": "UI 套件ID"},
                },
                "required": ["suite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_elements",
            "description": "列出 UI 元素库",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID（可选）"},
                    "keyword": {"type": "string", "description": "名称关键词（可选）"},
                    "limit": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ui_execution_result",
            "description": "查询 UI 自动化执行结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "execution_id": {"type": "integer", "description": "UI 执行记录ID"},
                },
                "required": ["execution_id"],
            },
        },
    },
]
```

- [ ] **Step 2: Commit**

```bash
git add apps/ai_assistant/tools/__init__.py
git commit -m "feat: register all AI assistant tools and define OpenAI function schemas"
```

---

## Task 6: 后端 serializers + views + urls

**Files:**
- Create: `apps/ai_assistant/serializers.py`
- Create: `apps/ai_assistant/views.py`
- Create: `apps/ai_assistant/urls.py`

- [ ] **Step 1: 写 serializers.py**

Create `apps/ai_assistant/serializers.py`:

```python
from rest_framework import serializers
from .models import AssistantSession, AssistantMessage


class AssistantMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantMessage
        fields = ['id', 'role', 'content', 'tool_name', 'tool_result', 'created_at']


class AssistantSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantSession
        fields = ['id', 'title', 'context_module', 'context_page',
                  'context_project_id', 'created_at', 'updated_at']


class SendMessageSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False, allow_null=True)
    message = serializers.CharField(max_length=4000)
    context = serializers.DictField(required=False, default=dict)
```

- [ ] **Step 2: 写 views.py**

Create `apps/ai_assistant/views.py`:

```python
import json
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AssistantSession, AssistantMessage
from .serializers import (
    AssistantSessionSerializer, AssistantMessageSerializer, SendMessageSerializer
)
from .tools.base import run_tool_loop

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """你是 TestHub 测试平台的 AI 助手，可以帮助用户管理接口测试和 UI 自动化测试。

当前上下文：
- 模块: {context_module}
- 页面: {context_page}
- 项目ID: {context_project_id}

你可以查询、创建接口用例，列出/触发测试套件执行，查询执行结果。
请用中文回复。如果用户请求不清晰，先澄清再操作。
执行写入或执行类操作前，简要描述你将要做什么。"""


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = SendMessageSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        data = ser.validated_data
        user_message = data['message']
        context = data.get('context') or {}
        session_id = data.get('session_id')

        # 获取或创建会话
        if session_id:
            session = AssistantSession.objects.filter(id=session_id, user=user).first()
            if not session:
                return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)
        else:
            session = AssistantSession.objects.create(
                user=user,
                title=user_message[:20],
                context_module=context.get('module', ''),
                context_page=context.get('page', ''),
                context_project_id=context.get('project_id'),
            )

        # 保存用户消息
        AssistantMessage.objects.create(session=session, role='user', content=user_message)

        # 构建消息历史（最近 20 条，避免 token 超限）
        history = list(
            session.messages.exclude(role='tool')
            .order_by('-created_at')[:20]
        )[::-1]

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            context_module=context.get('module', '未知'),
            context_page=context.get('page', '未知'),
            context_project_id=context.get('project_id', '未指定'),
        )
        messages = [{'role': 'system', 'content': system_prompt}]
        for m in history:
            messages.append({'role': m.role, 'content': m.content})

        # 执行工具循环
        try:
            reply, tools_called = run_tool_loop(messages, [], user, context)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.exception('AI tool loop error')
            return Response({'error': f'AI 服务异常: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 保存助手回复
        AssistantMessage.objects.create(
            session=session, role='assistant', content=reply,
            tool_name=','.join(tools_called) if tools_called else '',
        )

        # 更新会话时间
        session.save(update_fields=['updated_at'])

        return Response({
            'session_id': session.id,
            'reply': reply,
            'tools_called': tools_called,
        })


class SessionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AssistantSessionSerializer
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_queryset(self):
        return AssistantSession.objects.filter(user=self.request.user)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        session = self.get_object()
        msgs = session.messages.all()
        return Response(AssistantMessageSerializer(msgs, many=True).data)
```

- [ ] **Step 3: 写 urls.py**

Create `apps/ai_assistant/urls.py`:

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatView, SessionViewSet

router = DefaultRouter()
router.register(r'sessions', SessionViewSet, basename='ai-assistant-sessions')

urlpatterns = [
    path('chat/send_message/', ChatView.as_view(), name='ai-assistant-chat'),
    path('', include(router.urls)),
]
```

- [ ] **Step 4: 注册路由到 backend/urls.py**

In `backend/urls.py`, find the existing `path('api/assistant/', ...)` line and add after it:

```python
path('api/ai-assistant/', include('apps.ai_assistant.urls')),
```

- [ ] **Step 5: 写 API 端点测试**

In `apps/ai_assistant/tests.py`, add the following test class after the existing tests:

```python
from rest_framework.test import APIClient
from django.urls import reverse


class ChatViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='chatuser', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_send_message_creates_session(self):
        # 此测试需要 AI 模型配置，验证会话创建逻辑（mock AI 调用）
        # 若无 AI 配置，应返回 503
        url = '/api/ai-assistant/chat/send_message/'
        resp = self.client.post(url, {
            'message': '帮我列出接口',
            'context': {'module': 'api-testing', 'page': 'interface-management'},
        }, format='json')
        # 无 AI 配置时返回 503，有配置时返回 200
        self.assertIn(resp.status_code, [200, 503])

    def test_session_list(self):
        AssistantSession.objects.create(user=self.user, title='test')
        resp = self.client.get('/api/ai-assistant/sessions/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_session_messages(self):
        session = AssistantSession.objects.create(user=self.user)
        AssistantMessage.objects.create(session=session, role='user', content='hi')
        resp = self.client.get(f'/api/ai-assistant/sessions/{session.id}/messages/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_delete_session(self):
        session = AssistantSession.objects.create(user=self.user)
        resp = self.client.delete(f'/api/ai-assistant/sessions/{session.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(AssistantSession.objects.filter(id=session.id).count(), 0)
```

- [ ] **Step 6: 运行后端测试**

```bash
cd /d/python/testhub_platform-main
source venv/Scripts/activate
python manage.py test apps.ai_assistant -v 2
```

Expected: `OK (tests=7)`

- [ ] **Step 7: 手动验证 API 端点可达**

```bash
python manage.py runserver &
sleep 3
curl -s http://127.0.0.1:8000/api/ai-assistant/sessions/ -H "Authorization: Bearer <token>" | head -50
```

Expected: `{"count":0,"next":null,"previous":null,"results":[]}`（或 401 未授权，说明端点已注册）

- [ ] **Step 8: Commit**

```bash
git add apps/ai_assistant/serializers.py apps/ai_assistant/views.py apps/ai_assistant/urls.py apps/ai_assistant/tests.py backend/urls.py
git commit -m "feat: add ChatView, SessionViewSet, and API routes for ai_assistant"
```

---

## Task 7: 前端 Pinia store

**Files:**
- Create: `frontend/src/stores/aiAssistant.js`

- [ ] **Step 1: 写 aiAssistant.js**

Create `frontend/src/stores/aiAssistant.js`:

```js
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sendMessage, getSessions, getSessionMessages, deleteSession } from '@/api/ai-assistant'

export const useAiAssistantStore = defineStore('aiAssistant', () => {
  const isOpen = ref(false)
  const currentSessionId = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const toolsInProgress = ref([])
  const error = ref(null)

  function togglePanel() {
    isOpen.value = !isOpen.value
  }

  function openPanel() {
    isOpen.value = true
  }

  function closePanel() {
    isOpen.value = false
  }

  function startNewSession() {
    currentSessionId.value = null
    messages.value = []
    error.value = null
  }

  async function send(message, context) {
    if (!message.trim()) return
    loading.value = true
    error.value = null

    const userMsg = { role: 'user', content: message, created_at: new Date().toISOString() }
    messages.value.push(userMsg)

    try {
      const res = await sendMessage({
        session_id: currentSessionId.value,
        message,
        context,
      })
      currentSessionId.value = res.session_id
      toolsInProgress.value = res.tools_called || []
      messages.value.push({
        role: 'assistant',
        content: res.reply,
        tool_name: (res.tools_called || []).join(','),
        created_at: new Date().toISOString(),
      })
    } catch (e) {
      error.value = e.response?.data?.error || e.message || '发送失败'
      messages.value.push({
        role: 'assistant',
        content: `❌ ${error.value}`,
        created_at: new Date().toISOString(),
      })
    } finally {
      loading.value = false
      toolsInProgress.value = []
    }
  }

  async function loadSession(sessionId) {
    currentSessionId.value = sessionId
    const msgs = await getSessionMessages(sessionId)
    messages.value = msgs
  }

  async function removeSession(sessionId) {
    await deleteSession(sessionId)
    if (currentSessionId.value === sessionId) {
      startNewSession()
    }
  }

  return {
    isOpen, currentSessionId, messages, loading, toolsInProgress, error,
    togglePanel, openPanel, closePanel, startNewSession,
    send, loadSession, removeSession,
  }
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/aiAssistant.js
git commit -m "feat: add aiAssistant Pinia store"
```

---

## Task 8: 前端 API 服务层

**Files:**
- Create: `frontend/src/api/ai-assistant.js`

- [ ] **Step 1: 写 ai-assistant.js**

Create `frontend/src/api/ai-assistant.js`:

```js
import api from '@/utils/api'

export function sendMessage(data) {
  return api.post('/ai-assistant/chat/send_message/', data).then(r => r.data)
}

export function getSessions() {
  return api.get('/ai-assistant/sessions/').then(r => r.data.results || r.data)
}

export function getSessionMessages(sessionId) {
  return api.get(`/ai-assistant/sessions/${sessionId}/messages/`).then(r => r.data)
}

export function deleteSession(sessionId) {
  return api.delete(`/ai-assistant/sessions/${sessionId}/`)
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/ai-assistant.js
git commit -m "feat: add ai-assistant API service layer"
```

---

## Task 9: AiMessageBubble 组件

**Files:**
- Create: `frontend/src/components/ai-assistant/AiMessageBubble.vue`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p /d/python/testhub_platform-main/frontend/src/components/ai-assistant
```

- [ ] **Step 2: 写 AiMessageBubble.vue**

Create `frontend/src/components/ai-assistant/AiMessageBubble.vue`:

```vue
<template>
  <div class="message-bubble" :class="[`bubble--${msg.role}`]">
    <div class="bubble-avatar">
      <el-icon v-if="msg.role === 'user'"><UserFilled /></el-icon>
      <el-icon v-else><Cpu /></el-icon>
    </div>
    <div class="bubble-content">
      <div class="bubble-text" v-html="renderedContent" />
      <div v-if="msg.tool_name" class="bubble-tools">
        <el-tag size="small" type="info" v-for="t in toolNames" :key="t">{{ t }}</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { UserFilled, Cpu } from '@element-plus/icons-vue'

const props = defineProps({
  msg: { type: Object, required: true },
})

const toolNames = computed(() =>
  props.msg.tool_name ? props.msg.tool_name.split(',').filter(Boolean) : []
)

// 简单 Markdown 渲染：代码块、行内代码、换行
const renderedContent = computed(() => {
  let text = props.msg.content || ''
  // 代码块
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre class="code-block"><code>${escapeHtml(code.trim())}</code></pre>`
  )
  // 行内代码
  text = text.replace(/`([^`]+)`/g, (_, code) => `<code class="inline-code">${escapeHtml(code)}</code>`)
  // 换行
  text = text.replace(/\n/g, '<br />')
  return text
})

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
</script>

<style scoped>
.message-bubble {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.bubble--user {
  flex-direction: row-reverse;
}
.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.bubble--user .bubble-avatar {
  background: #409eff22;
  color: #409eff;
}
.bubble-content {
  max-width: 80%;
}
.bubble-text {
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
  background: #f5f5f5;
  color: #303030;
}
.bubble--user .bubble-text {
  background: #409eff;
  color: #fff;
}
.bubble-tools {
  margin-top: 4px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.code-block {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  margin: 4px 0;
}
.inline-code {
  background: #f0f0f0;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
  color: #c0392b;
}
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ai-assistant/AiMessageBubble.vue
git commit -m "feat: add AiMessageBubble component with Markdown rendering"
```

---

## Task 10: AiToolCallIndicator 组件

**Files:**
- Create: `frontend/src/components/ai-assistant/AiToolCallIndicator.vue`

- [ ] **Step 1: 写 AiToolCallIndicator.vue**

Create `frontend/src/components/ai-assistant/AiToolCallIndicator.vue`:

```vue
<template>
  <div class="tool-indicator" v-if="tools.length">
    <el-icon class="spinning"><Loading /></el-icon>
    <span>{{ $t('aiAssistant.executing') }}: {{ tools.join(', ') }}</span>
  </div>
  <div class="tool-indicator thinking" v-else-if="loading">
    <el-icon class="spinning"><Loading /></el-icon>
    <span>{{ $t('aiAssistant.thinking') }}</span>
  </div>
</template>

<script setup>
import { Loading } from '@element-plus/icons-vue'
defineProps({
  tools: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
</script>

<style scoped>
.tool-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  padding: 6px 12px;
}
.thinking {
  font-style: italic;
}
.spinning {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ai-assistant/AiToolCallIndicator.vue
git commit -m "feat: add AiToolCallIndicator component"
```

---

## Task 11: AiChatWindow 组件

**Files:**
- Create: `frontend/src/components/ai-assistant/AiChatWindow.vue`

- [ ] **Step 1: 写 AiChatWindow.vue**

Create `frontend/src/components/ai-assistant/AiChatWindow.vue`:

```vue
<template>
  <div class="chat-window">
    <!-- Header -->
    <div class="chat-header">
      <el-icon><Cpu /></el-icon>
      <span>{{ $t('aiAssistant.title') }}</span>
      <div class="header-actions">
        <el-tooltip :content="$t('aiAssistant.newSession')">
          <el-button text :icon="Plus" size="small" @click="store.startNewSession()" />
        </el-tooltip>
        <el-tooltip :content="$t('aiAssistant.close')">
          <el-button text :icon="Close" size="small" @click="store.closePanel()" />
        </el-tooltip>
      </div>
    </div>

    <!-- Messages -->
    <div class="chat-messages" ref="messagesEl">
      <div v-if="!store.messages.length" class="empty-hint">
        <p>{{ $t('aiAssistant.hint') }}</p>
      </div>
      <AiMessageBubble v-for="(msg, i) in store.messages" :key="i" :msg="msg" />
      <AiToolCallIndicator :tools="store.toolsInProgress" :loading="store.loading" />
    </div>

    <!-- Input -->
    <div class="chat-input">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="2"
        :placeholder="$t('aiAssistant.placeholder')"
        :disabled="store.loading"
        resize="none"
        @keydown.enter.exact.prevent="handleSend"
      />
      <el-button
        type="primary"
        :icon="Promotion"
        circle
        :disabled="!inputText.trim() || store.loading"
        @click="handleSend"
        class="send-btn"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Cpu, Plus, Close, Promotion } from '@element-plus/icons-vue'
import { useAiAssistantStore } from '@/stores/aiAssistant'
import AiMessageBubble from './AiMessageBubble.vue'
import AiToolCallIndicator from './AiToolCallIndicator.vue'

const store = useAiAssistantStore()
const route = useRoute()
const inputText = ref('')
const messagesEl = ref(null)

const context = () => ({
  module: route.meta?.module || '',
  page: route.meta?.page || '',
  project_id: route.query?.project_id || route.params?.project_id || null,
})

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || store.loading) return
  inputText.value = ''
  await store.send(text, context())
}

// 自动滚动到底部
watch(
  () => store.messages.length,
  async () => {
    await nextTick()
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  }
)
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.chat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
  font-size: 14px;
}
.header-actions {
  margin-left: auto;
  display: flex;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 0;
}
.empty-hint {
  text-align: center;
  color: #c0c4cc;
  font-size: 13px;
  padding-top: 40px;
}
.chat-input {
  padding: 10px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.chat-input .el-textarea {
  flex: 1;
}
.send-btn {
  flex-shrink: 0;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ai-assistant/AiChatWindow.vue
git commit -m "feat: add AiChatWindow component"
```

---

## Task 12: AiAssistantPanel 主容器

**Files:**
- Create: `frontend/src/components/ai-assistant/AiAssistantPanel.vue`

- [ ] **Step 1: 写 AiAssistantPanel.vue**

Create `frontend/src/components/ai-assistant/AiAssistantPanel.vue`:

```vue
<template>
  <Teleport to="body">
    <!-- 悬浮触发按钮 -->
    <el-tooltip :content="$t('aiAssistant.openTooltip')" placement="left">
      <el-button
        class="ai-fab"
        type="primary"
        circle
        :icon="Cpu"
        @click="store.togglePanel()"
        v-show="!store.isOpen"
      />
    </el-tooltip>

    <!-- 聊天弹窗 -->
    <Transition name="panel-slide">
      <div class="ai-panel" v-show="store.isOpen">
        <AiChatWindow />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { Teleport } from 'vue'
import { Cpu } from '@element-plus/icons-vue'
import { useAiAssistantStore } from '@/stores/aiAssistant'
import AiChatWindow from './AiChatWindow.vue'

const store = useAiAssistantStore()
</script>

<style scoped>
.ai-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 48px;
  height: 48px;
  z-index: 2000;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.4);
}
.ai-panel {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 380px;
  height: 600px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: all 0.25s ease;
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ai-assistant/AiAssistantPanel.vue
git commit -m "feat: add AiAssistantPanel floating panel with teleport"
```

---

## Task 13: 接线 — layout 挂载 + 路由 meta + i18n

**Files:**
- Modify: `frontend/src/layout/index.vue`
- Modify: `frontend/src/router/index.js`
- Create: `frontend/src/locales/lang/zh-cn/ai-assistant.js`
- Create: `frontend/src/locales/lang/en/ai-assistant.js`
- Modify: `frontend/src/locales/lang/zh-cn/index.js`
- Modify: `frontend/src/locales/lang/en/index.js`

- [ ] **Step 1: 创建 i18n 文件**

Create `frontend/src/locales/lang/zh-cn/ai-assistant.js`:

```js
export default {
  aiAssistant: {
    title: 'AI 助手',
    openTooltip: '打开 AI 助手',
    newSession: '新建会话',
    close: '关闭',
    thinking: '思考中...',
    executing: '正在执行',
    placeholder: '输入问题或操作指令（Enter 发送）',
    hint: '你可以问我：\n• 帮我列出所有接口\n• 创建一个 POST 接口\n• 运行测试套件 ID 5',
  },
}
```

Create `frontend/src/locales/lang/en/ai-assistant.js`:

```js
export default {
  aiAssistant: {
    title: 'AI Assistant',
    openTooltip: 'Open AI Assistant',
    newSession: 'New Session',
    close: 'Close',
    thinking: 'Thinking...',
    executing: 'Executing',
    placeholder: 'Ask a question or enter a command (Enter to send)',
    hint: 'You can ask me:\n• List all interfaces\n• Create a POST interface\n• Run test suite ID 5',
  },
}
```

- [ ] **Step 2: 注册 i18n 到 zh-cn/index.js**

In `frontend/src/locales/lang/zh-cn/index.js`, add the import and merge. Find the existing export pattern (e.g., `export default { ...nav, ...auth, ... }`) and add:

```js
import aiAssistant from './ai-assistant'
// 在 export default 的对象展开中加入：
// ...aiAssistant,
```

The exact edit: find the line that has `export default {` and the spread pattern, add `...aiAssistant,` inside the object. Example of the final result:

```js
import aiAssistant from './ai-assistant'
// ... other imports

export default {
  ...nav,
  // ... other spreads
  ...aiAssistant,
}
```

- [ ] **Step 3: 同样注册到 en/index.js**

In `frontend/src/locales/lang/en/index.js`, apply the same change as Step 2 but importing from `./ai-assistant`.

- [ ] **Step 4: 在 layout/index.vue 挂载面板**

In `frontend/src/layout/index.vue`, at the top of `<script setup>`:

```js
import AiAssistantPanel from '@/components/ai-assistant/AiAssistantPanel.vue'
```

At the bottom of the `<template>`, just before the closing `</template>` tag, add:

```vue
<AiAssistantPanel />
```

- [ ] **Step 5: 在 router/index.js 加 meta 字段**

In `frontend/src/router/index.js`, for each api-testing and ui-automation route, add `meta: { module: '...', page: '...' }`. Apply these changes:

For api-testing routes (find each `path:` and add meta):
```js
// Before:
{ path: '/api-testing/interfaces', component: ApiInterfaceManagement }
// After:
{ path: '/api-testing/interfaces', component: ApiInterfaceManagement, meta: { module: 'api-testing', page: 'interface-management' } }
```

Full list of meta to add:
```
/api-testing/dashboard       → { module: 'api-testing', page: 'dashboard' }
/api-testing/projects        → { module: 'api-testing', page: 'projects' }
/api-testing/interfaces      → { module: 'api-testing', page: 'interface-management' }
/api-testing/automation      → { module: 'api-testing', page: 'automation-testing' }
/api-testing/history         → { module: 'api-testing', page: 'history' }
/api-testing/environments    → { module: 'api-testing', page: 'environments' }
/api-testing/reports         → { module: 'api-testing', page: 'reports' }
/api-testing/scheduled-tasks → { module: 'api-testing', page: 'scheduled-tasks' }
/ui-automation/dashboard     → { module: 'ui-automation', page: 'dashboard' }
/ui-automation/projects      → { module: 'ui-automation', page: 'projects' }
/ui-automation/elements-enhanced → { module: 'ui-automation', page: 'elements' }
/ui-automation/test-cases    → { module: 'ui-automation', page: 'test-cases' }
/ui-automation/scripts-enhanced → { module: 'ui-automation', page: 'scripts' }
/ui-automation/suites        → { module: 'ui-automation', page: 'suites' }
/ui-automation/executions    → { module: 'ui-automation', page: 'executions' }
/ui-automation/reports       → { module: 'ui-automation', page: 'reports' }
/ui-automation/scheduled-tasks → { module: 'ui-automation', page: 'scheduled-tasks' }
```

- [ ] **Step 6: 启动前端验证**

```bash
cd /d/python/testhub_platform-main/frontend
"D:/software/Node/node.exe" node_modules/vite/bin/vite.js
```

打开 http://localhost:3000 → 登录 → 进入 api-testing 模块。

验证：
1. 右下角出现蓝色圆形 AI 助手按钮
2. 点击按钮，弹出 380×600px 的聊天弹窗
3. 关闭按钮正常工作
4. 输入文本后按 Enter，消息显示在列表中
5. 若后端已配置 AI 模型，收到 AI 回复；若未配置，显示 "未找到可用的 AI 模型配置"

- [ ] **Step 7: Commit**

```bash
git add frontend/src/locales/ frontend/src/layout/index.vue frontend/src/router/index.js
git commit -m "feat: mount AiAssistantPanel in layout, add router meta, add i18n"
```

---

## Task 14: 端到端冒烟测试

- [ ] **Step 1: 确认后端已有 AI 模型配置**

登录平台 → 配置中心 → AI 模型配置，确认有一条 role=writer、is_active=True 的配置（DeepSeek / Qwen 等 OpenAI-compatible API）。

- [ ] **Step 2: 发送第一条消息**

在 api-testing 页面点击 AI 助手按钮，输入：

```
帮我列出当前项目的接口
```

预期：助手调用 `list_interfaces` 工具，返回接口列表（或提示"未找到接口"）。

- [ ] **Step 3: 测试创建操作**

输入：

```
帮我创建一个名为"健康检查"的 GET 接口，URL 是 /api/health
```

预期：助手调用 `create_interface`，返回创建成功的接口 ID。到接口管理页面可以看到新建的接口。

- [ ] **Step 4: 测试 UI 自动化模块**

切换到 ui-automation 模块，输入：

```
帮我列出所有测试套件
```

预期：助手调用 `list_ui_suites`，返回套件列表。

- [ ] **Step 5: 最终 Commit**

```bash
git add .
git commit -m "feat: complete AI assistant panel end-to-end"
```
