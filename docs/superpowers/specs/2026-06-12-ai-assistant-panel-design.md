# AI Assistant Panel — Design Spec

**Date:** 2026-06-12
**Status:** Approved
**Scope:** 在 TestHub 自动化平台全局添加右下角悬浮 AI 对话助手，支持对 api-testing 和 ui-automation 模块进行读、写、执行操作。

---

## 1. 整体架构

```
┌─────────────────────────────────────────────────────┐
│  Vue 前端                                            │
│                                                      │
│  layout/index.vue                                    │
│    └── <AiAssistantPanel />  (teleport to body)      │
│         ├── 右下角悬浮按钮                            │
│         └── 聊天弹窗 (position: fixed)               │
│              ├── 消息列表                             │
│              └── 输入框 + 发送                        │
│                                                      │
│  Context 注入（自动）：                               │
│    useRoute() → 当前路由/子页面                       │
│    useProjectStore() → 当前项目 ID                   │
└───────────────────┬─────────────────────────────────┘
                    │ POST /api/ai-assistant/chat/
                    ▼
┌─────────────────────────────────────────────────────┐
│  Django 后端：apps/ai_assistant/                     │
│                                                      │
│  ChatView.send_message()                             │
│    ├── 1. 构建 system prompt（注入页面上下文）        │
│    ├── 2. 调用大模型 API（function calling）          │
│    ├── 3. Tool Dispatcher：执行工具函数               │
│    │       ├── api_testing tools                     │
│    │       │     list_interfaces / create_interface  │
│    │       │     run_test_suite / ...                │
│    │       └── ui_automation tools                   │
│    │             list_suites / run_suite / ...       │
│    ├── 4. 多轮 tool call 直到模型返回最终文本         │
│    └── 5. 保存消息记录，返回响应                      │
│                                                      │
│  models: AssistantSession, AssistantMessage          │
│  tools/: api_testing_tools.py, ui_automation_tools.py│
└─────────────────────────────────────────────────────┘
```

**关键设计决策：**
- 前端只发一次请求，多轮 tool call 循环在后端完成（最多 5 轮防止死循环）
- `AiAssistantPanel` 通过 Vue `<Teleport to="body">` 渲染，不受页面 z-index 影响
- 复用现有 `AIModelConfig`（`requirement_analysis` app 已有），使用 `testcase_writer` 角色配置，不新增配置表

---

## 2. 后端数据模型 & API

### Django App

新建 `apps/ai_assistant/`，注册到 `INSTALLED_APPS`，路由前缀 `/api/ai-assistant/`。

### 数据模型

```python
# apps/ai_assistant/models.py

class AssistantSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, default='新会话')
    context_module = models.CharField(max_length=50, blank=True)   # e.g. "api-testing"
    context_page = models.CharField(max_length=100, blank=True)    # e.g. "interface-management"
    context_project_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class AssistantMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant'), ('tool', 'Tool')]
    session = models.ForeignKey(AssistantSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tool_name = models.CharField(max_length=100, blank=True)   # 调用的工具名
    tool_result = models.JSONField(null=True, blank=True)       # 工具返回摘要
    created_at = models.DateTimeField(auto_now_add=True)
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ai-assistant/chat/send_message/` | 发送消息，返回 AI 回复 |
| GET  | `/api/ai-assistant/sessions/` | 获取当前用户会话列表 |
| GET  | `/api/ai-assistant/sessions/{id}/messages/` | 获取会话消息历史 |
| DELETE | `/api/ai-assistant/sessions/{id}/` | 删除会话 |

### 请求/响应格式

**请求体：**
```json
{
  "session_id": 123,
  "message": "帮我列出所有接口",
  "context": {
    "module": "api-testing",
    "page": "interface-management",
    "project_id": 5
  }
}
```

**响应体：**
```json
{
  "session_id": 123,
  "reply": "当前项目共有 12 个接口，以下是列表：...",
  "tools_called": ["list_interfaces"],
  "messages": []
}
```

---

## 3. 工具层（Function Calling Tools）

### 文件结构

```
apps/ai_assistant/
├── __init__.py
├── apps.py
├── models.py
├── serializers.py
├── views.py
├── urls.py
└── tools/
    ├── __init__.py              # 统一导出 TOOLS_REGISTRY, TOOL_DEFINITIONS
    ├── base.py                  # ToolDispatcher，执行分发 + 权限传递
    ├── api_testing_tools.py     # 接口测试工具
    └── ui_automation_tools.py   # UI 自动化工具
```

### api-testing 工具集（第一期）

| 工具名 | 操作类型 | 说明 |
|--------|----------|------|
| `list_interfaces` | 读 | 按项目/关键词列出接口用例 |
| `get_interface` | 读 | 获取单条接口详情 |
| `create_interface` | 写 | 创建接口用例 |
| `run_interface` | 执行 | 执行单条接口并返回结果 |
| `list_test_suites` | 读 | 列出自动化测试套件 |
| `run_test_suite` | 执行 | 触发套件执行 |
| `get_execution_result` | 读 | 查询执行结果 |

### ui-automation 工具集（第一期）

| 工具名 | 操作类型 | 说明 |
|--------|----------|------|
| `list_ui_suites` | 读 | 列出 UI 测试套件 |
| `get_ui_suite` | 读 | 获取套件详情 |
| `run_ui_suite` | 执行 | 触发 UI 套件执行 |
| `list_ui_elements` | 读 | 列出元素库 |
| `get_execution_result` | 读 | 查询执行结果 |

### 工具执行机制

```
模型返回 tool_call
    ↓
ToolDispatcher.execute(tool_name, args, user, context)
    ↓
工具函数直接调用 Django ORM / 已有 service 层
    ↓
返回结构化结果 → 追加到消息列表 → 继续下一轮模型调用
    ↓
（最多循环 5 轮）模型返回纯文本 → 结束
```

**安全设计：** 每个工具执行时传入 `user` 对象，查询和写入均经过 `get_queryset()` 权限过滤，与正常 API 请求保持一致的权限控制。

---

## 4. 前端组件

### 组件结构

```
frontend/src/components/ai-assistant/
├── AiAssistantPanel.vue       # 主容器：悬浮按钮 + 弹窗外壳
├── AiChatWindow.vue           # 聊天窗口：消息列表 + 输入区
├── AiMessageBubble.vue        # 单条消息气泡（支持 Markdown）
└── AiToolCallIndicator.vue    # 工具调用状态提示（"正在查询接口..."）
```

### 状态管理

新建 `frontend/src/stores/aiAssistant.js`（Pinia）：

```js
{
  isOpen: false,           // 弹窗开关
  currentSessionId: null,  // 当前会话 ID
  messages: [],            // 当前会话消息列表
  loading: false,          // 请求中状态
  toolsInProgress: []      // 正在执行的工具名列表（用于 indicator）
}
```

### 挂载方式

在 `layout/index.vue` 末尾添加：

```vue
<AiAssistantPanel />
```

组件内部使用 `<Teleport to="body">` 渲染到 body 顶层。

### 视觉交互

```
┌─ body ──────────────────────────────────────────┐
│                                                  │
│  [主页面内容]                    ┌────────────┐  │
│                                  │ AI 助手   ×  │
│                                  ├────────────┤  │
│                                  │ 消息列表   │  │
│                                  │            │  │
│                                  ├────────────┤  │
│                                  │ [工具调用] │  │
│                                  ├────────────┤  │
│                                  │ 输入框  ▶  │  │
│                                  └────────────┘  │
│                             [🤖] ← 悬浮触发按钮  │
└──────────────────────────────────────────────────┘
```

- 弹窗：宽 380px，高 600px，`position: fixed`，右下角偏移 20px
- 悬浮按钮：`el-button` 圆形，右下角固定，`bottom: 24px; right: 24px`
- Markdown 渲染：复用 `AssistantView.vue` 的现有渲染逻辑

### 上下文注入

```js
// AiAssistantPanel.vue
const route = useRoute()
const projectStore = useProjectStore()

const context = computed(() => ({
  module: route.meta.module,
  page: route.meta.page,
  project_id: projectStore.currentProjectId
}))
```

路由 meta 改动（每条路由加两个字段，示例）：
```js
{
  path: 'interface-management',
  meta: { module: 'api-testing', page: 'interface-management' }
}
```

---

## 5. 新建文件清单

### 后端

| 文件 | 说明 |
|------|------|
| `apps/ai_assistant/__init__.py` | |
| `apps/ai_assistant/apps.py` | App 注册 |
| `apps/ai_assistant/models.py` | AssistantSession, AssistantMessage |
| `apps/ai_assistant/serializers.py` | 序列化器 |
| `apps/ai_assistant/views.py` | ChatView, SessionViewSet |
| `apps/ai_assistant/urls.py` | 路由 |
| `apps/ai_assistant/tools/__init__.py` | TOOLS_REGISTRY, TOOL_DEFINITIONS |
| `apps/ai_assistant/tools/base.py` | ToolDispatcher |
| `apps/ai_assistant/tools/api_testing_tools.py` | |
| `apps/ai_assistant/tools/ui_automation_tools.py` | |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/components/ai-assistant/AiAssistantPanel.vue` | 主容器 |
| `frontend/src/components/ai-assistant/AiChatWindow.vue` | 聊天窗口 |
| `frontend/src/components/ai-assistant/AiMessageBubble.vue` | 消息气泡 |
| `frontend/src/components/ai-assistant/AiToolCallIndicator.vue` | 工具状态提示 |
| `frontend/src/stores/aiAssistant.js` | Pinia store |
| `frontend/src/api/ai-assistant.js` | API 服务层 |

### 改动已有文件

| 文件 | 改动说明 |
|------|----------|
| `backend/settings.py` | INSTALLED_APPS 加 `apps.ai_assistant` |
| `backend/urls.py` | 注册 `/api/ai-assistant/` 路由 |
| `frontend/src/layout/index.vue` | 引入并挂载 `<AiAssistantPanel />` |
| `frontend/src/router/index.js` | 各路由 meta 加 `module` / `page` 字段 |
| `frontend/src/locales/zh-cn/*.js` | 新增 i18n 词条 |
| `frontend/src/locales/en/*.js` | 新增 i18n 词条 |

---

## 6. 不在本期范围内

- 弹窗拖拽移动
- 流式（SSE）响应
- 工具执行确认弹窗（写操作前二次确认）
- 会话历史面板（弹窗内仅显示当前会话，历史入口可跳转到全屏 assistant 页）
