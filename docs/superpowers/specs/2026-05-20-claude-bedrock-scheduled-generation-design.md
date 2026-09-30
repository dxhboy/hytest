# Design: AWS Bedrock Claude 接入 + 夜间定时用例生成

**日期**: 2026-05-20  
**状态**: 已审批  
**模块**: `apps/requirement_analysis`

---

## 背景与目标

在现有 AI 用例生成模块（`requirement_analysis`）基础上：

1. 新增 **AWS Bedrock Claude** 作为可选 AI 提供商（通过 `access_key_id` + `secret_access_key` 鉴权）
2. 在需求分析模块内新增**夜间定时任务**功能，支持每天固定时间自动对指定需求文档运行用例生成

---

## 一、AWS Bedrock Claude 适配层

### 1.1 模型配置扩展

`AIModelConfig.model_type` 新增枚举值 `bedrock_claude`。

新增字段存储 Bedrock 鉴权信息（在现有模型上新增列）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `aws_access_key_id` | CharField(255), nullable | AWS Access Key ID |
| `aws_secret_access_key` | CharField(255), nullable | AWS Secret Access Key |
| `aws_region` | CharField(50), default `us-east-1` | AWS 区域 |
| `aws_model_id` | CharField(100), nullable | Bedrock 模型 ID，如 `anthropic.claude-sonnet-4-5` |

非 `bedrock_claude` 类型时这些字段为 null，不影响现有逻辑。

### 1.2 BedrockAdapter

新文件：`apps/requirement_analysis/bedrock_adapter.py`

**职责**：
- 接收与现有 `call_openai_compatible_api` 相同格式的参数（`config`, `messages`）
- 使用 `boto3` 调用 `bedrock-runtime` 的 `converse` / `converse_stream` API
- 将 OpenAI 格式 `messages`（`role: user/assistant/system`）转换为 Bedrock `converse` 格式
- 返回与现有接口一致的响应结构（`content` 字段）

**消息格式转换规则**：
- `role: system` → Bedrock `system` 参数（列表形式）
- `role: user/assistant` → Bedrock `messages` 列表

**流式支持**：
- 非流式：`bedrock_runtime.converse()`
- 流式：`bedrock_runtime.converse_stream()`，逐块 yield，与现有 SSE 回调兼容

**新增依赖**：`boto3`

### 1.3 AIModelService 路由

在 `AIModelService.call_openai_compatible_api()` 和 `call_openai_compatible_api_stream()` 入口处增加分支：

```
if config.model_type == 'bedrock_claude':
    return await BedrockAdapter.call(config, messages)
else:
    # 现有 OpenAI 兼容逻辑不变
```

现有生成、审阅、修订流程零改动。

---

## 二、定时任务模型与后端调度

### 2.1 新增模型 ScheduledGenerationTask

位置：`apps/requirement_analysis/models.py`

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | CharField(100) | 任务名称 |
| `requirement_document` | FK → RequirementDocument | 绑定的需求文档 |
| `ai_model_config` | FK → AIModelConfig | 使用的 AI 配置 |
| `scheduled_time` | TimeField | 每天执行时间（HH:MM） |
| `is_active` | BooleanField, default True | 是否启用 |
| `last_run_at` | DateTimeField, nullable | 最近一次执行时间 |
| `last_run_status` | CharField(20) | `pending` / `running` / `success` / `failed` |
| `last_run_task_id` | FK → TestCaseGenerationTask, nullable | 最近生成任务记录 |
| `created_by` | FK → User | 创建人 |
| `created_at` | DateTimeField, auto | 创建时间 |

### 2.2 调度引擎

使用 `APScheduler`（`pip install apscheduler`）。

在 `apps/requirement_analysis/apps.py` 的 `RequirementAnalysisConfig.ready()` 中启动 `BackgroundScheduler`，注册一个每分钟触发的 job：

**检查逻辑**（每分钟执行）：
1. 查询所有 `is_active=True` 的 `ScheduledGenerationTask`
2. 对比当前时间（精确到分钟）与 `scheduled_time`
3. 若匹配，且 `last_run_at` 不在今天，则触发执行
4. 执行时设置 `last_run_status = running`，完成后更新状态

**防重复执行**：通过数据库原子更新 `last_run_status` 实现幂等，避免多进程重复触发。

### 2.3 执行逻辑抽取

从现有 `TestCaseGenerationTaskViewSet.generate()` 中抽取核心流程为独立函数：

```python
def run_generation_for_document(document_id, ai_config_id, created_by_id=None) -> TestCaseGenerationTask
```

- 手动触发（Web 端点击）和定时触发共用此函数
- 返回创建的 `TestCaseGenerationTask` 实例，供状态追踪

### 2.4 API 端点

新增到现有 DRF router（`apps/requirement_analysis/urls.py`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/requirement-analysis/scheduled-tasks/` | 列表 |
| POST | `/requirement-analysis/scheduled-tasks/` | 新建 |
| GET | `/requirement-analysis/scheduled-tasks/{id}/` | 详情 |
| PUT | `/requirement-analysis/scheduled-tasks/{id}/` | 编辑 |
| DELETE | `/requirement-analysis/scheduled-tasks/{id}/` | 删除 |
| POST | `/requirement-analysis/scheduled-tasks/{id}/toggle/` | 启用/禁用 |

---

## 三、前端页面

### 3.1 新增页面：ScheduledTasks.vue

路径：`frontend/src/views/requirement-analysis/ScheduledTasks.vue`

**布局**（参考 `api-testing/ScheduledTasks.vue` 风格）：

- 顶部："新建定时任务" 按钮
- 列表表格：任务名 | 需求文档 | AI 模型配置 | 执行时间 | 状态开关 | 最近执行时间 | 最近执行结果 | 操作（编辑/删除）
- 新建/编辑 Dialog 表单：
  - 任务名称（文本输入）
  - 需求文档（下拉，调用现有文档列表接口）
  - AI 模型配置（下拉，含 Claude 配置）
  - 每天执行时间（`el-time-picker`，格式 HH:mm）
  - 启用开关

### 3.2 AI 模型配置页面扩展

文件：`frontend/src/views/requirement-analysis/AIModelConfig.vue`

- 模型类型下拉新增 `AWS Bedrock Claude` 选项
- 选择后动态显示专属字段：
  - Access Key ID（文本输入）
  - Secret Access Key（密码输入框，默认隐藏）
  - Region（文本输入，默认 `us-east-1`）
  - Model ID（下拉，预设常用值：`anthropic.claude-sonnet-4-5`、`anthropic.claude-opus-4-7`、`anthropic.claude-haiku-4-5-20251001`，支持自定义输入）

### 3.3 路由与导航

- `router/index.js`：需求分析模块下新增 `/requirement-analysis/scheduled-tasks`
- `layout/index.vue`（或侧边栏配置）：需求分析菜单下新增"定时任务"入口

---

## 依赖变更

| 包 | 用途 | 操作 |
|----|------|------|
| `boto3` | AWS Bedrock API 调用 | 新增到 `requirements.txt` |
| `apscheduler` | 后台定时调度 | 新增到 `requirements.txt` |

---

## 数据库变更

1. `requirement_analysis_aimodelconfig` 表：新增 4 列（`aws_access_key_id`, `aws_secret_access_key`, `aws_region`, `aws_model_id`）
2. 新增表 `requirement_analysis_scheduledgenerationtask`

执行：`python manage.py makemigrations requirement_analysis && python manage.py migrate`

---

## 不在范围内

- 修改 `api_testing` 模块
- 支持除每日固定时间以外的调度模式（cron 表达式、间隔触发）
- Celery Beat 集成
- Bedrock 以外的 Claude 接入方式（如直接 Anthropic API）
