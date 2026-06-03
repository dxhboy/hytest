# Jira 需求导入与测试用例生成设计文档

**日期：** 2026-06-03  
**模块：** requirement_analysis + users + versions + executions  
**状态：** 已确认，待实施

---

## 1. 背景与目标

TestHub 的智能用例生成模块目前支持"上传文档"和"手动输入文本"两种需求来源。本设计在此基础上新增第三种来源——**从 Jira Cloud Issue 拉取需求**——并在此之上构建 **Jira Issue ↔ 版本 ↔ 测试用例** 的三向关联体系，最终实现"基于 Jira 需求推荐回归测试用例"的能力。

### 核心目标

1. 用户粘贴 Jira Issue URL（支持单条和批量），系统自动拉取需求内容并调用 AI 生成测试用例。
2. 生成的用例自动与来源 Issue 关联；手工用例也可手动关联任意 Issue。
3. 版本发布时，系统根据版本关联的 Issue 自动推荐回归测试用例，并支持一键加入测试计划。

---

## 2. 认证与凭据管理

### 2.1 支持范围

仅支持 **Jira Cloud（cloud.atlassian.com）**，认证方式为 **邮箱 + API Token**（Basic Auth over HTTPS）。

### 2.2 凭据存储策略

| 配置项 | 存储位置 | 管理方 |
|---|---|---|
| Jira 域名（如 `company.atlassian.net`） | `UserProfile.jira_domain` | 每个用户自行填写 |
| 登录邮箱 | `UserProfile.jira_email` | 每个用户自行填写 |
| API Token | `UserProfile.jira_api_token`（加密） | 每个用户自行填写 |

- API Token 使用 `cryptography.fernet` 对称加密后存入数据库，密钥来自 `settings.SECRET_KEY` 派生。
- 序列化时 API Token 返回 `***` 掩码；更新时留空则不覆盖原值。
- 个人资料页新增 **"Jira 配置" Tab** 供用户填写和测试连接。

---

## 3. 数据模型

### 3.1 UserProfile 扩展（`apps/users/models.py`）

新增三个字段到现有 `UserProfile` 模型：

```python
jira_domain    = CharField(max_length=255, blank=True)  # company.atlassian.net
jira_email     = CharField(max_length=255, blank=True)
jira_api_token = CharField(max_length=512, blank=True)  # 加密存储
```

### 3.2 JiraIssueLink（`apps/requirement_analysis/models.py`）

记录已导入的 Jira Issue 元数据及其与 TestHub 版本的关联。

```python
class JiraIssueLink(models.Model):
    issue_key       = CharField(max_length=64)           # PROJ-123
    issue_url       = URLField()                          # 原始 URL
    issue_summary   = CharField(max_length=500)           # Issue 标题（冗余）
    jira_domain     = CharField(max_length=255)           # 来源域名
    jira_fix_version = CharField(max_length=255, blank=True)  # Jira Fix Version 字段
    version         = ForeignKey('versions.Version', null=True, blank=True, on_delete=SET_NULL)
    project         = ForeignKey('projects.Project', null=True, blank=True, on_delete=SET_NULL)
    created_by      = ForeignKey(User, on_delete=SET_NULL, null=True)
    created_at      = DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('issue_key', 'jira_domain')
```

### 3.3 JiraIssueCaseLink（`apps/requirement_analysis/models.py`）

用例与 Issue 的多对多关联，使用 `GenericForeignKey` 同时支持 AI 生成用例（`GeneratedTestCase`）和手工用例（`testcases.TestCase`）。

```python
class JiraIssueCaseLink(models.Model):
    LINK_TYPE_AUTO   = 'auto'
    LINK_TYPE_MANUAL = 'manual'
    LINK_TYPE_CHOICES = [(LINK_TYPE_AUTO, '自动'), (LINK_TYPE_MANUAL, '手动')]

    jira_issue   = ForeignKey(JiraIssueLink, on_delete=CASCADE, related_name='case_links')
    content_type = ForeignKey(ContentType, on_delete=CASCADE)
    object_id    = PositiveIntegerField()
    case         = GenericForeignKey('content_type', 'object_id')
    link_type    = CharField(max_length=16, choices=LINK_TYPE_CHOICES, default=LINK_TYPE_MANUAL)
    created_by   = ForeignKey(User, on_delete=SET_NULL, null=True)
    created_at   = DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('jira_issue', 'content_type', 'object_id')
```

---

## 4. 后端架构

### 4.1 Jira 客户端（`apps/requirement_analysis/jira_client.py`）

封装 Jira REST API v3，不依赖第三方 Jira SDK（使用项目已有的 `httpx`）。

```python
class JiraClient:
    def __init__(self, domain: str, email: str, api_token: str): ...

    def get_issue(self, issue_key: str, fields: list[str]) -> dict:
        """拉取单条 Issue 指定字段"""

    def get_epic_children(self, epic_key: str, fields: list[str]) -> list[dict]:
        """拉取 Epic 下所有子 Issue（JQL 查询）"""

    def extract_content(self, issue: dict, selected_fields: list[str]) -> str:
        """将 Issue 数据组装成需求文本，供 AI 生成用例使用"""

    def validate_connection(self) -> bool:
        """验证凭据是否有效（GET /rest/api/3/myself）"""
```

**支持的可选字段：**

| 字段 key | 说明 |
|---|---|
| `summary` | Issue 标题（必选，不可取消）|
| `description` | 描述（ADF 格式自动转纯文本）|
| `acceptance_criteria` | 验收标准（自定义字段，按名称模糊匹配）|
| `subtasks` | 子任务列表（标题汇总）|
| `labels` | 标签 |
| `priority` | 优先级 |

### 4.2 新增 API 端点

全部加入 `apps/requirement_analysis/urls.py`，路径前缀 `/api/requirement-analysis/jira/`。

| 端点 | 方法 | 说明 |
|---|---|---|
| `jira/preview/` | POST | 传入 URL(s) + 字段配置，返回拉取内容摘要，不触发 AI 生成 |
| `jira/import/` | POST | 拉取内容 → 组装文本 → 创建 `TestCaseGenerationTask` → 自动建立关联，返回 task_id |
| `jira/issues/` | GET | 查询当前项目下所有 JiraIssueLink |
| `jira/issues/<id>/link-cases/` | POST | 手动关联用例（批量，支持两种用例类型）|
| `jira/issues/<id>/unlink-cases/` | POST | 解除关联 |
| `jira/issues/<id>/cases/` | GET | 查询某 Issue 关联的所有用例 |
| `jira/recommend/` | POST | 传入 version_id，返回去重后的推荐回归用例列表 |

### 4.3 导入流程

```
POST /jira/import/
  │
  ├─ 1. 读取当前用户 UserProfile.jira_* 凭据并解密
  ├─ 2. JiraClient.get_issue() / get_epic_children() 拉取 Issue
  ├─ 3. extract_content() 按选择字段组装 requirement_text
  ├─ 4. 创建 TestCaseGenerationTask（复用现有逻辑）
  ├─ 5. 为每条 Issue 创建或更新 JiraIssueLink
  │      （记录 jira_fix_version 和 version 关联）
  └─ 6. 任务完成后（信号/回调）自动创建 JiraIssueCaseLink（link_type=auto）
         返回 task_id → 前端跳转任务详情页
```

步骤 6 通过 `post_save` 信号监听 `TestCaseGenerationTask.status` 变为 `completed` 时触发，避免阻塞导入请求。

---

## 5. 前端页面

### 5.1 个人资料页 — Jira 配置 Tab

文件：`frontend/src/views/profile/UserProfile.vue`

在现有"基本信息 | 修改密码"两个 Tab 后增加第三个 Tab：**Jira 配置**。

表单字段：
- Jira 域名（placeholder: `yourcompany.atlassian.net`）
- 邮箱
- API Token（password 类型，已保存时显示 `***`，留空提交则不覆盖）
- "测试连接"按钮 → 调用后端凭据验证接口
- "保存"按钮

### 5.2 侧边栏新增"Jira 需求导入"页面

文件：`frontend/src/views/requirement-analysis/JiraImport.vue`  
路由：`/requirement-analysis/jira-import`  
侧边栏位置：需求分析模块菜单中，紧跟主页面之后

**三步式交互流程：**

**Step 1 — 输入**
- 单条模式：单行输入框，粘贴一个 Issue URL
- 批量模式：多行文本域，每行一个 URL；或输入 Epic URL 勾选"展开子任务"
- 关联 TestHub 版本（可选下拉，来自 `/api/versions/`）

**Step 2 — 字段选择 + 预览**
- 字段复选框：Summary（置灰必选）/ Description / Acceptance Criteria / Subtasks / Labels / Priority
- "预览"按钮 → 调用 `/jira/preview/`
- 展示每条 Issue 的预览卡片：Issue Key、标题、正文前 150 字、状态标记（成功/失败）

**Step 3 — 生成**
- 选择 AI 模型配置（复用现有 `<AIModelSelector>` 组件）
- "开始生成"按钮 → 调用 `/jira/import/`
- 成功后自动跳转 `/requirement-analysis/task-detail/:taskId`

### 5.3 用例详情页 — 手动关联 Jira Issue

涉及页面：
- `frontend/src/views/requirement-analysis/GeneratedTestCaseList.vue`
- `frontend/src/views/testcases/TestCaseDetail.vue`（手工用例）

每条用例新增"关联 Jira Issue"入口（操作列小图标），点击弹窗：
- 输入 Issue URL 或从已导入的 `JiraIssueLink` 下拉选择
- 支持查看和解除当前已关联的 Issue

### 5.4 版本详情页 — 关联需求 Tab 与回归推荐

涉及页面：`frontend/src/views/versions/VersionList.vue` 或版本详情页

新增"关联需求"Tab：
- 展示该版本下所有 `JiraIssueLink`：Issue Key、标题、状态、关联用例数
- "推荐回归用例"按钮 → 调用 `/jira/recommend/?version_id=xxx`
- 结果列表：去重的用例列表，含用例类型（AI/手工）、优先级、来源 Issue
- "加入测试计划"按钮（批量选择后操作）

### 5.5 测试计划创建页 — 自动推荐

涉及页面：`frontend/src/views/executions/ExecutionList.vue` 或执行计划创建弹窗

选择版本后，自动调用 `/jira/recommend/`，在用例选择区上方展示"基于 Jira 需求推荐（N 条）"折叠提示，用户可展开后批量勾选加入计划。

---

## 6. 错误处理

| 场景 | 处理方式 |
|---|---|
| 用户未配置 Jira 凭据 | 返回 400，前端引导跳转个人资料页 Jira 配置 Tab |
| 凭据无效（401）| 返回明确错误提示，引导重新填写 API Token |
| Issue 不存在或无权限（404/403）| 在预览卡片上标红该 Issue，不阻断其他 Issue 处理 |
| Jira API 超时 | 单条超时 10s，批量导入跳过该条并记录错误，返回部分成功结果 |
| Acceptance Criteria 字段不存在 | 静默跳过，不报错 |
| Epic 子任务超过 50 条 | 提示用户并截断，最多导入前 50 条 |

---

## 7. 国际化

所有新增文本在 `frontend/src/locales/lang/zh-cn/requirement.js` 和 `en/requirement.js` 中补充对应 key，命名空间 `requirement.jira.*`。

---

## 8. 不在本期范围内

- Jira Server / Data Center 支持
- Jira Webhook 自动同步（Issue 更新时触发重新生成）
- 双向同步（将 TestHub 用例状态写回 Jira）
- Jira OAuth 2.0 认证
- 超过 50 条子任务的 Epic 分页导入