# Claude Bedrock + 夜间定时用例生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在需求分析模块新增 AWS Bedrock Claude 作为 AI 提供商，并支持每天定时自动对指定需求文档运行用例生成。

**Architecture:** 新增 `BedrockAdapter` 封装 boto3 调用，`AIModelConfig` 扩展 `bedrock_claude` 类型及 AWS 鉴权字段；新增 `ScheduledGenerationTask` 模型，APScheduler 每分钟轮询并触发到期任务；前端新增定时任务页面和配置中心 Bedrock 配置项。

**Tech Stack:** Python 3.x, Django 4.2, DRF, boto3, APScheduler, Vue 3, Element Plus, Pinia

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `apps/requirement_analysis/bedrock_adapter.py` | 新建 | boto3 Bedrock 调用，转换消息格式 |
| `apps/requirement_analysis/models.py` | 修改 | 新增 `bedrock_claude` 类型字段、AWS 鉴权字段、`ScheduledGenerationTask` 模型 |
| `apps/requirement_analysis/migrations/XXXX_bedrock_scheduled.py` | 新建（自动生成） | 数据库迁移 |
| `apps/requirement_analysis/serializers.py` | 修改 | 新增 `ScheduledGenerationTaskSerializer` |
| `apps/requirement_analysis/views.py` | 修改 | 新增 `ScheduledGenerationTaskViewSet`，抽取 `run_generation_for_document` |
| `apps/requirement_analysis/urls.py` | 修改 | 注册 `scheduled-generation` router |
| `apps/requirement_analysis/apps.py` | 修改 | `ready()` 中启动 APScheduler |
| `apps/requirement_analysis/scheduler.py` | 新建 | APScheduler 调度逻辑 |
| `apps/requirement_analysis/tests.py` | 修改 | 新增测试 |
| `requirements.txt` | 修改 | 新增 `boto3`, `apscheduler` |
| `frontend/src/api/requirement-analysis.js` | 修改 | 新增定时任务 API 函数 |
| `frontend/src/views/requirement-analysis/ScheduledGenerationTasks.vue` | 新建 | 定时任务列表+表单页面 |
| `frontend/src/views/requirement-analysis/AIModelConfig.vue` | 修改 | 新增 Bedrock 配置字段 |
| `frontend/src/router/index.js` | 修改 | 新增 `scheduled-generation` 路由 |
| `frontend/src/layout/index.vue` | 修改 | ai-generation 菜单新增"定时任务"入口 |

---

## Task 1: 安装新依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 在 requirements.txt 末尾新增两行**

```
boto3>=1.34.0
apscheduler>=3.10.4
```

- [ ] **Step 2: 安装依赖**

```bash
pip install boto3>=1.34.0 "apscheduler>=3.10.4"
```

Expected: 安装成功，无报错。

- [ ] **Step 3: 验证可导入**

```bash
python -c "import boto3; import apscheduler; print('OK')"
```

Expected: 输出 `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add boto3 and apscheduler dependencies"
```

---

## Task 2: BedrockAdapter 实现

**Files:**
- Create: `apps/requirement_analysis/bedrock_adapter.py`
- Test: `apps/requirement_analysis/tests.py`

- [ ] **Step 1: 写失败测试（mock boto3）**

在 `apps/requirement_analysis/tests.py` 追加：

```python
from unittest.mock import MagicMock, patch
from django.test import TestCase


class BedrockAdapterTest(TestCase):
    def _make_config(self):
        config = MagicMock()
        config.aws_access_key_id = 'AKIAIOSFODNN7EXAMPLE'
        config.aws_secret_access_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
        config.aws_region = 'us-east-1'
        config.aws_model_id = 'anthropic.claude-sonnet-4-5'
        config.max_tokens = 4096
        config.temperature = 0.7
        config.top_p = 0.9
        return config

    @patch('apps.requirement_analysis.bedrock_adapter.boto3')
    def test_call_non_stream_returns_content(self, mock_boto3):
        from apps.requirement_analysis.bedrock_adapter import BedrockAdapter
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = {
            'output': {'message': {'content': [{'text': 'hello world'}]}}
        }
        messages = [
            {'role': 'system', 'content': 'You are a tester.'},
            {'role': 'user', 'content': 'Write test cases.'},
        ]
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            BedrockAdapter.call(self._make_config(), messages)
        )
        self.assertIn('choices', result)
        self.assertEqual(result['choices'][0]['message']['content'], 'hello world')

    @patch('apps.requirement_analysis.bedrock_adapter.boto3')
    def test_system_message_extracted(self, mock_boto3):
        from apps.requirement_analysis.bedrock_adapter import BedrockAdapter
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = {
            'output': {'message': {'content': [{'text': 'ok'}]}}
        }
        messages = [
            {'role': 'system', 'content': 'system prompt'},
            {'role': 'user', 'content': 'hello'},
        ]
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            BedrockAdapter.call(self._make_config(), messages)
        )
        call_kwargs = mock_client.converse.call_args[1]
        # system messages should be passed as 'system' param
        self.assertIn('system', call_kwargs)
        self.assertEqual(call_kwargs['system'][0]['text'], 'system prompt')
        # user messages should exclude the system message
        self.assertEqual(len(call_kwargs['messages']), 1)
        self.assertEqual(call_kwargs['messages'][0]['role'], 'user')
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test apps.requirement_analysis.tests.BedrockAdapterTest -v 2
```

Expected: `ImportError` 或 `ModuleNotFoundError`（bedrock_adapter 不存在）

- [ ] **Step 3: 创建 BedrockAdapter**

新建文件 `apps/requirement_analysis/bedrock_adapter.py`：

```python
import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List

import boto3

logger = logging.getLogger(__name__)


class BedrockAdapter:
    """将 AWS Bedrock converse API 适配为与 AIModelService 一致的接口。"""

    @staticmethod
    def _build_client(config):
        return boto3.client(
            'bedrock-runtime',
            region_name=config.aws_region or 'us-east-1',
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )

    @staticmethod
    def _split_messages(messages: List[Dict[str, str]]):
        """将 OpenAI 格式 messages 拆分为 system 列表和 conversation 列表。"""
        system_parts = []
        conversation = []
        for msg in messages:
            if msg['role'] == 'system':
                system_parts.append({'text': msg['content']})
            else:
                conversation.append({
                    'role': msg['role'],
                    'content': [{'text': msg['content']}],
                })
        return system_parts, conversation

    @staticmethod
    async def call(config, messages: List[Dict[str, str]], max_tokens: int = None) -> Dict[str, Any]:
        """非流式调用，返回与 call_openai_compatible_api 一致的结构。"""
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        system_parts, conversation = BedrockAdapter._split_messages(messages)

        def _invoke():
            client = BedrockAdapter._build_client(config)
            kwargs = dict(
                modelId=config.aws_model_id,
                messages=conversation,
                inferenceConfig={
                    'maxTokens': actual_max_tokens,
                    'temperature': config.temperature,
                    'topP': config.top_p,
                },
            )
            if system_parts:
                kwargs['system'] = system_parts
            logger.info(f"Bedrock converse: model={config.aws_model_id}, region={config.aws_region}")
            return client.converse(**kwargs)

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, _invoke)
        except Exception as e:
            logger.error(f"Bedrock API 调用失败: {repr(e)}")
            raise Exception(f"Bedrock API 调用失败: {str(e) or repr(e)}")

        text = response['output']['message']['content'][0]['text']
        # 返回与 OpenAI 格式一致的结构，让 AIModelService 无缝消费
        return {
            'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}],
            'usage': response.get('usage', {}),
        }

    @staticmethod
    async def call_stream(config, messages: List[Dict[str, str]], callback=None, max_tokens: int = None) -> AsyncIterator[str]:
        """流式调用，逐块 yield 文本；callback 与现有 SSE 回调兼容。"""
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        system_parts, conversation = BedrockAdapter._split_messages(messages)

        def _invoke_stream():
            client = BedrockAdapter._build_client(config)
            kwargs = dict(
                modelId=config.aws_model_id,
                messages=conversation,
                inferenceConfig={
                    'maxTokens': actual_max_tokens,
                    'temperature': config.temperature,
                    'topP': config.top_p,
                },
            )
            if system_parts:
                kwargs['system'] = system_parts
            logger.info(f"Bedrock converse_stream: model={config.aws_model_id}")
            return client.converse_stream(**kwargs)

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, _invoke_stream)
        except Exception as e:
            logger.error(f"Bedrock 流式 API 调用失败: {repr(e)}")
            raise Exception(f"Bedrock 流式 API 调用失败: {str(e) or repr(e)}")

        full_content = ""
        for event in response['stream']:
            if 'contentBlockDelta' in event:
                chunk = event['contentBlockDelta']['delta'].get('text', '')
                if chunk:
                    full_content += chunk
                    if callback:
                        await callback(full_content)
                    yield chunk
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.BedrockAdapterTest -v 2
```

Expected: `OK` 2 tests passed

- [ ] **Step 5: Commit**

```bash
git add apps/requirement_analysis/bedrock_adapter.py apps/requirement_analysis/tests.py
git commit -m "feat: add BedrockAdapter for AWS Bedrock Claude integration"
```

---

## Task 3: AIModelConfig 模型扩展（bedrock_claude 类型 + AWS 字段）

**Files:**
- Modify: `apps/requirement_analysis/models.py:199-246`
- Test: `apps/requirement_analysis/tests.py`

- [ ] **Step 1: 写失败测试**

在 `apps/requirement_analysis/tests.py` 追加：

```python
class AIModelConfigBedrockTest(TestCase):
    def test_bedrock_claude_in_model_choices(self):
        from apps.requirement_analysis.models import AIModelConfig
        choices_keys = [c[0] for c in AIModelConfig.MODEL_CHOICES]
        self.assertIn('bedrock_claude', choices_keys)

    def test_bedrock_fields_exist(self):
        from apps.requirement_analysis.models import AIModelConfig
        field_names = [f.name for f in AIModelConfig._meta.get_fields()]
        for field in ('aws_access_key_id', 'aws_secret_access_key', 'aws_region', 'aws_model_id'):
            self.assertIn(field, field_names, f"Missing field: {field}")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test apps.requirement_analysis.tests.AIModelConfigBedrockTest -v 2
```

Expected: `AssertionError: 'bedrock_claude' not found in ...`

- [ ] **Step 3: 修改 AIModelConfig 模型**

编辑 `apps/requirement_analysis/models.py`，找到 `MODEL_CHOICES`（第 201 行），在 `('other', '其他'),` 之前加入：

```python
        ('bedrock_claude', 'AWS Bedrock Claude'),
```

在 `top_p` 字段（第 223 行）之后、`is_active` 字段之前，新增四个字段：

```python
    aws_access_key_id = models.CharField(max_length=255, verbose_name='AWS Access Key ID', blank=True, null=True)
    aws_secret_access_key = models.CharField(max_length=255, verbose_name='AWS Secret Access Key', blank=True, null=True)
    aws_region = models.CharField(max_length=50, verbose_name='AWS Region', default='us-east-1', blank=True, null=True)
    aws_model_id = models.CharField(max_length=100, verbose_name='Bedrock Model ID', blank=True, null=True)
```

同时将 `base_url` 和 `api_key` 字段改为可选（bedrock_claude 不需要这两个字段）——确认它们已经是 `blank=True, null=True`。当前 `api_key` 已是 nullable，但 `base_url` 是 `URLField` 不允许为空，需修改：

```python
    base_url = models.CharField(max_length=500, verbose_name='API Base URL', blank=True, null=True)
```

（从 URLField 改为 CharField 以兼容 Bedrock 不填 base_url 的场景，同时保持现有数据兼容）

- [ ] **Step 4: 生成并运行迁移**

```bash
python manage.py makemigrations requirement_analysis --name bedrock_aimodelconfig
python manage.py migrate
```

Expected: `OK` 无错误

- [ ] **Step 5: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.AIModelConfigBedrockTest -v 2
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add apps/requirement_analysis/models.py apps/requirement_analysis/migrations/ apps/requirement_analysis/tests.py
git commit -m "feat: extend AIModelConfig with bedrock_claude type and AWS credential fields"
```

---

## Task 4: AIModelService 路由到 BedrockAdapter

**Files:**
- Modify: `apps/requirement_analysis/models.py`（AIModelService 的两个 call 方法）
- Test: `apps/requirement_analysis/tests.py`

- [ ] **Step 1: 写失败测试**

在 `apps/requirement_analysis/tests.py` 追加：

```python
class AIModelServiceBedrockRoutingTest(TestCase):
    def _make_bedrock_config(self):
        config = MagicMock()
        config.model_type = 'bedrock_claude'
        config.aws_access_key_id = 'KEY'
        config.aws_secret_access_key = 'SECRET'
        config.aws_region = 'us-east-1'
        config.aws_model_id = 'anthropic.claude-sonnet-4-5'
        config.max_tokens = 4096
        config.temperature = 0.7
        config.top_p = 0.9
        return config

    @patch('apps.requirement_analysis.bedrock_adapter.boto3')
    def test_routes_to_bedrock_adapter(self, mock_boto3):
        from apps.requirement_analysis.models import AIModelService
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.return_value = {
            'output': {'message': {'content': [{'text': 'result'}]}}
        }
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            AIModelService.call_openai_compatible_api(
                self._make_bedrock_config(),
                [{'role': 'user', 'content': 'hello'}]
            )
        )
        self.assertIn('choices', result)
        mock_client.converse.assert_called_once()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test apps.requirement_analysis.tests.AIModelServiceBedrockRoutingTest -v 2
```

Expected: 测试失败（boto3.client 未被调用，走了 httpx 路径）

- [ ] **Step 3: 在 AIModelService.call_openai_compatible_api 顶部添加 Bedrock 分支**

找到 `apps/requirement_analysis/models.py` 第 422 行 `async def call_openai_compatible_api` 方法，在函数体开头（`headers = {` 之前）插入：

```python
        if config.model_type == 'bedrock_claude':
            from .bedrock_adapter import BedrockAdapter
            return await BedrockAdapter.call(config, messages, max_tokens)
```

- [ ] **Step 4: 在 AIModelService.call_openai_compatible_api_stream 顶部添加 Bedrock 分支**

找到第 533 行 `async def call_openai_compatible_api_stream` 方法，在函数体开头（`headers = {` 之前）插入：

```python
        if config.model_type == 'bedrock_claude':
            from .bedrock_adapter import BedrockAdapter
            async for chunk in BedrockAdapter.call_stream(config, messages, callback, max_tokens):
                yield chunk
            return
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.AIModelServiceBedrockRoutingTest -v 2
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add apps/requirement_analysis/models.py apps/requirement_analysis/tests.py
git commit -m "feat: route bedrock_claude model type to BedrockAdapter in AIModelService"
```

---

## Task 5: ScheduledGenerationTask 模型

**Files:**
- Modify: `apps/requirement_analysis/models.py`（末尾新增模型）
- Test: `apps/requirement_analysis/tests.py`

- [ ] **Step 1: 写失败测试**

在 `apps/requirement_analysis/tests.py` 追加：

```python
from django.contrib.auth import get_user_model

class ScheduledGenerationTaskModelTest(TestCase):
    def setUp(self):
        UserModel = get_user_model()
        self.user = UserModel.objects.create_user(username='testuser', password='pass')

    def test_model_fields_exist(self):
        from apps.requirement_analysis.models import ScheduledGenerationTask
        field_names = [f.name for f in ScheduledGenerationTask._meta.get_fields()]
        for field in ('name', 'requirement_document', 'ai_model_config',
                      'scheduled_time', 'is_active', 'last_run_at',
                      'last_run_status', 'last_run_task', 'created_by', 'created_at'):
            self.assertIn(field, field_names, f"Missing field: {field}")

    def test_default_status_is_pending(self):
        from apps.requirement_analysis.models import ScheduledGenerationTask
        task = ScheduledGenerationTask(last_run_status='')
        # default via field default
        field = ScheduledGenerationTask._meta.get_field('last_run_status')
        self.assertEqual(field.default, 'pending')
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test apps.requirement_analysis.tests.ScheduledGenerationTaskModelTest -v 2
```

Expected: `ImportError` 或 `AttributeError`

- [ ] **Step 3: 在 models.py 末尾添加 ScheduledGenerationTask 模型**

在 `apps/requirement_analysis/models.py` 末尾追加：

```python

class ScheduledGenerationTask(models.Model):
    """定时用例生成任务"""
    STATUS_CHOICES = [
        ('pending', '待执行'),
        ('running', '执行中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]

    name = models.CharField(max_length=100, verbose_name='任务名称')
    requirement_document = models.ForeignKey(
        RequirementDocument, on_delete=models.CASCADE,
        related_name='scheduled_generation_tasks', verbose_name='需求文档'
    )
    ai_model_config = models.ForeignKey(
        AIModelConfig, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_tasks', verbose_name='AI模型配置'
    )
    scheduled_time = models.TimeField(verbose_name='每日执行时间（HH:MM）')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name='最近执行时间')
    last_run_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='最近执行状态'
    )
    last_run_task = models.ForeignKey(
        TestCaseGenerationTask, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_source', verbose_name='最近生成任务'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'scheduled_generation_task'
        verbose_name = '定时用例生成任务'
        verbose_name_plural = '定时用例生成任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} @ {self.scheduled_time}"
```

- [ ] **Step 4: 生成并运行迁移**

```bash
python manage.py makemigrations requirement_analysis --name add_scheduled_generation_task
python manage.py migrate
```

Expected: `OK`

- [ ] **Step 5: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.ScheduledGenerationTaskModelTest -v 2
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add apps/requirement_analysis/models.py apps/requirement_analysis/migrations/ apps/requirement_analysis/tests.py
git commit -m "feat: add ScheduledGenerationTask model"
```

---

## Task 6: 抽取 run_generation_for_document 函数

**Files:**
- Modify: `apps/requirement_analysis/views.py`
- Test: `apps/requirement_analysis/tests.py`

- [ ] **Step 1: 写失败测试**

在 `apps/requirement_analysis/tests.py` 追加：

```python
class RunGenerationForDocumentTest(TestCase):
    def test_function_exists_and_is_callable(self):
        from apps.requirement_analysis.views import run_generation_for_document
        import inspect
        self.assertTrue(callable(run_generation_for_document))
        sig = inspect.signature(run_generation_for_document)
        self.assertIn('document_id', sig.parameters)
        self.assertIn('ai_model_config_id', sig.parameters)
        self.assertIn('created_by_id', sig.parameters)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test apps.requirement_analysis.tests.RunGenerationForDocumentTest -v 2
```

Expected: `ImportError`

- [ ] **Step 3: 在 views.py 顶层（ViewSet 类之外）新增函数**

在 `apps/requirement_analysis/views.py` 中所有 import 之后、第一个 ViewSet 类定义之前，插入：

```python
def run_generation_for_document(document_id: int, ai_model_config_id: int = None, created_by_id: int = None):
    """
    为指定需求文档创建并执行用例生成任务。
    供定时任务和手动触发共用。
    返回 TestCaseGenerationTask 实例。
    """
    import threading
    import asyncio
    from .models import (
        RequirementDocument, AIModelConfig, PromptConfig,
        GenerationConfig, TestCaseGenerationTask, AIModelService
    )
    from django.contrib.auth import get_user_model

    User = get_user_model()

    doc = RequirementDocument.objects.get(pk=document_id)
    requirement_text = doc.extracted_text or doc.title

    writer_config = (
        AIModelConfig.objects.get(pk=ai_model_config_id)
        if ai_model_config_id
        else AIModelConfig.objects.filter(role='writer', is_active=True).first()
    )
    reviewer_config = AIModelConfig.objects.filter(role='reviewer', is_active=True).first()
    writer_prompt = PromptConfig.get_active_config('writer')
    reviewer_prompt = PromptConfig.get_active_config('reviewer')

    gen_config = GenerationConfig.get_active_config()
    output_mode = gen_config.default_output_mode if gen_config else 'stream'

    created_by = User.objects.get(pk=created_by_id) if created_by_id else (
        User.objects.filter(is_superuser=True).first() or User.objects.first()
    )

    task = TestCaseGenerationTask.objects.create(
        title=f"[定时] {doc.title}",
        requirement_text=requirement_text,
        writer_model_config=writer_config,
        reviewer_model_config=reviewer_config,
        writer_prompt_config=writer_prompt,
        reviewer_prompt_config=reviewer_prompt,
        output_mode=output_mode,
        created_by=created_by,
    )

    def execute():
        try:
            task.status = 'generating'
            task.progress = 10
            task.save()

            enable_auto_review = gen_config.enable_auto_review if gen_config else True
            review_timeout = gen_config.review_timeout if gen_config else 120

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if task.output_mode == 'stream':
                    task.stream_buffer = ''
                    task.stream_position = 0
                    task.save()

                    def save_stream_buffer(content):
                        from django.utils import timezone
                        task.stream_buffer = content
                        task.stream_position = len(content)
                        task.last_stream_update = timezone.now()
                        task.save(update_fields=['stream_buffer', 'stream_position', 'last_stream_update'])

                    from asgiref.sync import sync_to_async
                    async_save = sync_to_async(save_stream_buffer)

                    async def stream_cb(chunk):
                        await async_save(chunk)

                    loop.run_until_complete(
                        AIModelService.generate_test_cases_stream(task, stream_cb)
                    )
                else:
                    loop.run_until_complete(AIModelService.generate_test_cases(task))

                task.progress = 30
                task.save()

                if enable_auto_review and reviewer_config and reviewer_prompt:
                    task.status = 'reviewing'
                    task.progress = 60
                    task.save()
                    test_cases = task.generated_test_cases
                    if task.output_mode == 'stream':
                        loop.run_until_complete(
                            AIModelService.review_test_cases_stream(task, test_cases, None)
                        )
                    else:
                        loop.run_until_complete(AIModelService.review_test_cases(task, test_cases))
                    task.progress = 70
                    task.save()

                    task.status = 'revising'
                    task.progress = 85
                    task.save()
                    loop.run_until_complete(
                        AIModelService.revise_test_cases_based_on_review(task)
                    )

                task.status = 'completed'
                task.progress = 100
                from django.utils import timezone
                task.completed_at = timezone.now()
                task.save()
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"定时生成任务 {task.task_id} 失败: {e}")
            task.status = 'failed'
            task.error_message = str(e)
            task.save()

    thread = threading.Thread(target=execute, daemon=True)
    thread.start()
    return task
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.RunGenerationForDocumentTest -v 2
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add apps/requirement_analysis/views.py apps/requirement_analysis/tests.py
git commit -m "feat: extract run_generation_for_document shared function"
```

---

## Task 7: ScheduledGenerationTask API（序列化器 + ViewSet + URL）

**Files:**
- Modify: `apps/requirement_analysis/serializers.py`
- Modify: `apps/requirement_analysis/views.py`
- Modify: `apps/requirement_analysis/urls.py`
- Test: `apps/requirement_analysis/tests.py`

- [ ] **Step 1: 写失败测试**

在 `apps/requirement_analysis/tests.py` 追加：

```python
from rest_framework.test import APIClient

class ScheduledGenerationTaskAPITest(TestCase):
    def setUp(self):
        UserModel = get_user_model()
        self.user = UserModel.objects.create_user(username='apiuser', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_endpoint_returns_200(self):
        response = self.client.get('/api/requirement-analysis/scheduled-generation/')
        self.assertEqual(response.status_code, 200)

    def test_toggle_endpoint_exists(self):
        from apps.requirement_analysis.models import ScheduledGenerationTask, RequirementDocument
        import datetime
        doc = RequirementDocument.objects.create(
            title='Test Doc', document_type='txt',
            uploaded_by=self.user, extracted_text='some text'
        )
        task = ScheduledGenerationTask.objects.create(
            name='Night Task', requirement_document=doc,
            scheduled_time=datetime.time(2, 0), created_by=self.user
        )
        response = self.client.post(f'/api/requirement-analysis/scheduled-generation/{task.pk}/toggle/')
        self.assertIn(response.status_code, [200, 201])
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test apps.requirement_analysis.tests.ScheduledGenerationTaskAPITest -v 2
```

Expected: `404` 或 `ImportError`

- [ ] **Step 3: 在 serializers.py 末尾添加序列化器**

在 `apps/requirement_analysis/serializers.py` 末尾追加：

```python
from .models import ScheduledGenerationTask

class ScheduledGenerationTaskSerializer(serializers.ModelSerializer):
    requirement_document_title = serializers.CharField(
        source='requirement_document.title', read_only=True
    )
    ai_model_config_name = serializers.CharField(
        source='ai_model_config.name', read_only=True
    )
    last_run_task_id = serializers.CharField(
        source='last_run_task.task_id', read_only=True
    )

    class Meta:
        model = ScheduledGenerationTask
        fields = [
            'id', 'name', 'requirement_document', 'requirement_document_title',
            'ai_model_config', 'ai_model_config_name',
            'scheduled_time', 'is_active',
            'last_run_at', 'last_run_status', 'last_run_task_id',
            'created_by', 'created_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'last_run_at', 'last_run_status', 'last_run_task_id']
```

- [ ] **Step 4: 在 views.py 末尾（最后一个 ViewSet 后）添加 ViewSet**

在 `apps/requirement_analysis/views.py` 末尾追加：

```python
from .models import ScheduledGenerationTask
from .serializers import ScheduledGenerationTaskSerializer

class ScheduledGenerationTaskViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduledGenerationTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ScheduledGenerationTask.objects.filter(
            created_by=self.request.user
        ).select_related('requirement_document', 'ai_model_config', 'last_run_task')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        task = self.get_object()
        task.is_active = not task.is_active
        task.save(update_fields=['is_active'])
        return Response({'is_active': task.is_active})
```

- [ ] **Step 5: 在 urls.py 注册路由**

在 `apps/requirement_analysis/urls.py` 中，在 `from .views import (` 的导入列表末尾加入 `ScheduledGenerationTaskViewSet`，然后在 router 注册行末尾添加：

```python
router.register(r'scheduled-generation', ScheduledGenerationTaskViewSet, basename='scheduledgenerationtask')
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.ScheduledGenerationTaskAPITest -v 2
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add apps/requirement_analysis/serializers.py apps/requirement_analysis/views.py apps/requirement_analysis/urls.py apps/requirement_analysis/tests.py
git commit -m "feat: add ScheduledGenerationTask API (serializer, viewset, router)"
```

---

## Task 8: APScheduler 调度引擎

**Files:**
- Create: `apps/requirement_analysis/scheduler.py`
- Modify: `apps/requirement_analysis/apps.py`
- Test: `apps/requirement_analysis/tests.py`

- [ ] **Step 1: 写失败测试**

在 `apps/requirement_analysis/tests.py` 追加：

```python
class SchedulerCheckDueTest(TestCase):
    def test_check_due_tasks_function_exists(self):
        from apps.requirement_analysis.scheduler import check_due_tasks
        self.assertTrue(callable(check_due_tasks))

    def test_check_due_tasks_skips_inactive(self):
        """已禁用的任务不应被触发"""
        from apps.requirement_analysis.models import ScheduledGenerationTask, RequirementDocument
        from apps.requirement_analysis.scheduler import check_due_tasks
        import datetime
        UserModel = get_user_model()
        user = UserModel.objects.create_user(username='scheduser', password='pass')
        doc = RequirementDocument.objects.create(
            title='Doc', document_type='txt',
            uploaded_by=user, extracted_text='text'
        )
        now = datetime.datetime.now()
        ScheduledGenerationTask.objects.create(
            name='Inactive', requirement_document=doc,
            scheduled_time=now.time().replace(second=0, microsecond=0),
            is_active=False, created_by=user
        )
        with patch('apps.requirement_analysis.scheduler.run_generation_for_document') as mock_run:
            check_due_tasks()
            mock_run.assert_not_called()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test apps.requirement_analysis.tests.SchedulerCheckDueTest -v 2
```

Expected: `ImportError`

- [ ] **Step 3: 创建 scheduler.py**

新建 `apps/requirement_analysis/scheduler.py`：

```python
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler = None


def check_due_tasks():
    """每分钟调用一次，检查当前时间是否有需要触发的定时生成任务。"""
    from .models import ScheduledGenerationTask
    from .views import run_generation_for_document
    from django.utils import timezone

    now = timezone.localtime(timezone.now())
    current_hm = now.strftime('%H:%M')

    due_tasks = ScheduledGenerationTask.objects.filter(
        is_active=True,
        last_run_status__in=['pending', 'success', 'failed'],
    )

    for task in due_tasks:
        task_hm = task.scheduled_time.strftime('%H:%M')
        if task_hm != current_hm:
            continue
        # 今天已经跑过则跳过
        if task.last_run_at and task.last_run_at.date() == now.date():
            continue

        logger.info(f"触发定时生成任务: id={task.pk}, name={task.name}")
        task.last_run_status = 'running'
        task.last_run_at = timezone.now()
        task.save(update_fields=['last_run_status', 'last_run_at'])

        try:
            gen_task = run_generation_for_document(
                document_id=task.requirement_document_id,
                ai_model_config_id=task.ai_model_config_id,
                created_by_id=task.created_by_id,
            )
            task.last_run_task = gen_task
            task.last_run_status = 'success'
            task.save(update_fields=['last_run_task', 'last_run_status'])
        except Exception as e:
            logger.error(f"定时任务 {task.pk} 执行失败: {e}")
            task.last_run_status = 'failed'
            task.save(update_fields=['last_run_status'])


def start_scheduler():
    """启动 APScheduler，每分钟执行一次 check_due_tasks。"""
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler

    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        check_due_tasks,
        trigger='interval',
        minutes=1,
        id='check_due_generation_tasks',
        replace_existing=True,
        misfire_grace_time=30,
    )
    _scheduler.start()
    logger.info("ScheduledGeneration APScheduler started")
```

- [ ] **Step 4: 修改 apps.py 在 ready() 中启动调度器**

将 `apps/requirement_analysis/apps.py` 改为：

```python
from django.apps import AppConfig


class RequirementAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.requirement_analysis'
    verbose_name = '需求分析'

    def ready(self):
        import os
        # 避免 Django 开发服务器 auto-reloader 导致 scheduler 启动两次
        if os.environ.get('RUN_MAIN') != 'true' and os.environ.get('DJANGO_SETTINGS_MODULE'):
            return
        try:
            from .scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to start scheduler: {e}")
```

> 注意：`RUN_MAIN` 判断在 `runserver` 下有效；在生产（gunicorn/uwsgi）下去掉该判断或改用进程锁。

- [ ] **Step 5: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.SchedulerCheckDueTest -v 2
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add apps/requirement_analysis/scheduler.py apps/requirement_analysis/apps.py apps/requirement_analysis/tests.py
git commit -m "feat: add APScheduler-based nightly generation scheduler"
```

---

## Task 9: 前端 API 层

**Files:**
- Modify: `frontend/src/api/requirement-analysis.js`

- [ ] **Step 1: 在 requirement-analysis.js 末尾追加定时任务 API 函数**

先确认 `getRequirementDocuments` 是否已导出；若无，在文件末尾定时任务函数之前先补充：

```javascript
// ==================== 需求文档 ====================

export function getRequirementDocuments(params) {
  return request({
    url: '/requirement-analysis/documents/',
    method: 'get',
    params,
  })
}
```

然后追加定时任务函数：

```javascript
// ==================== 定时生成任务 ====================

export function getScheduledGenerationTasks(params) {
  return request({
    url: '/requirement-analysis/scheduled-generation/',
    method: 'get',
    params,
  })
}

export function createScheduledGenerationTask(data) {
  return request({
    url: '/requirement-analysis/scheduled-generation/',
    method: 'post',
    data,
  })
}

export function updateScheduledGenerationTask(id, data) {
  return request({
    url: `/requirement-analysis/scheduled-generation/${id}/`,
    method: 'put',
    data,
  })
}

export function deleteScheduledGenerationTask(id) {
  return request({
    url: `/requirement-analysis/scheduled-generation/${id}/`,
    method: 'delete',
  })
}

export function toggleScheduledGenerationTask(id) {
  return request({
    url: `/requirement-analysis/scheduled-generation/${id}/toggle/`,
    method: 'post',
  })
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/requirement-analysis.js
git commit -m "feat: add scheduled generation task API functions"
```

---

## Task 10: 前端定时任务页面

**Files:**
- Create: `frontend/src/views/requirement-analysis/ScheduledGenerationTasks.vue`

- [ ] **Step 1: 创建页面组件**

新建 `frontend/src/views/requirement-analysis/ScheduledGenerationTasks.vue`：

```vue
<template>
  <div class="scheduled-generation-tasks">
    <div class="page-header">
      <h2>{{ $t('menu.scheduledGenerationTasks') }}</h2>
      <el-button type="primary" @click="openDialog()">
        {{ $t('common.create') }}
      </el-button>
    </div>

    <el-table :data="tasks" v-loading="loading" stripe>
      <el-table-column prop="name" :label="$t('scheduledTask.name')" min-width="140" />
      <el-table-column prop="requirement_document_title" :label="$t('scheduledTask.document')" min-width="160" />
      <el-table-column prop="ai_model_config_name" :label="$t('scheduledTask.aiModel')" min-width="140" />
      <el-table-column prop="scheduled_time" :label="$t('scheduledTask.scheduledTime')" width="100" />
      <el-table-column :label="$t('scheduledTask.status')" width="90">
        <template #default="{ row }">
          <el-switch
            v-model="row.is_active"
            @change="handleToggle(row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="last_run_at" :label="$t('scheduledTask.lastRunAt')" width="160">
        <template #default="{ row }">
          {{ row.last_run_at ? formatDateTime(row.last_run_at) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="last_run_status" :label="$t('scheduledTask.lastRunStatus')" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.last_run_status)" size="small">
            {{ row.last_run_status || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('common.actions')" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">{{ $t('common.edit') }}</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">{{ $t('common.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑 Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingTask ? $t('common.edit') : $t('common.create')"
      width="500px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item :label="$t('scheduledTask.name')" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.document')" prop="requirement_document">
          <el-select v-model="form.requirement_document" filterable style="width:100%">
            <el-option
              v-for="doc in documents"
              :key="doc.id"
              :label="doc.title"
              :value="doc.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.aiModel')">
          <el-select v-model="form.ai_model_config" clearable style="width:100%">
            <el-option
              v-for="cfg in aiConfigs"
              :key="cfg.id"
              :label="cfg.name"
              :value="cfg.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.scheduledTime')" prop="scheduled_time">
          <el-time-picker
            v-model="form.scheduled_time"
            format="HH:mm"
            value-format="HH:mm:ss"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.status')">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getScheduledGenerationTasks,
  createScheduledGenerationTask,
  updateScheduledGenerationTask,
  deleteScheduledGenerationTask,
  toggleScheduledGenerationTask,
} from '@/api/requirement-analysis'
import { getRequirementDocuments } from '@/api/requirement-analysis'
import { getAIModelConfigs } from '@/api/requirement-analysis'

const tasks = ref([])
const loading = ref(false)
const documents = ref([])
const aiConfigs = ref([])
const dialogVisible = ref(false)
const editingTask = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const defaultForm = () => ({
  name: '',
  requirement_document: null,
  ai_model_config: null,
  scheduled_time: '02:00:00',
  is_active: true,
})
const form = ref(defaultForm())

const rules = {
  name: [{ required: true, message: '请填写任务名称', trigger: 'blur' }],
  requirement_document: [{ required: true, message: '请选择需求文档', trigger: 'change' }],
  scheduled_time: [{ required: true, message: '请选择执行时间', trigger: 'change' }],
}

async function fetchTasks() {
  loading.value = true
  try {
    const res = await getScheduledGenerationTasks()
    tasks.value = res.data?.results ?? res.data ?? []
  } finally {
    loading.value = false
  }
}

async function fetchOptions() {
  const [docRes, cfgRes] = await Promise.all([
    getRequirementDocuments(),
    getAIModelConfigs({ role: 'writer' }),
  ])
  documents.value = docRes.data?.results ?? docRes.data ?? []
  aiConfigs.value = cfgRes.data?.results ?? cfgRes.data ?? []
}

function openDialog(task = null) {
  editingTask.value = task
  form.value = task
    ? { ...task }
    : defaultForm()
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    if (editingTask.value) {
      await updateScheduledGenerationTask(editingTask.value.id, form.value)
    } else {
      await createScheduledGenerationTask(form.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    fetchTasks()
  } finally {
    submitting.value = false
  }
}

async function handleToggle(row) {
  try {
    await toggleScheduledGenerationTask(row.id)
  } catch {
    row.is_active = !row.is_active
    ElMessage.error('切换失败')
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm('确认删除该定时任务？', '提示', { type: 'warning' })
  await deleteScheduledGenerationTask(row.id)
  ElMessage.success('已删除')
  fetchTasks()
}

function statusTagType(status) {
  return { success: 'success', failed: 'danger', running: 'warning', pending: 'info' }[status] || 'info'
}

function formatDateTime(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

onMounted(() => {
  fetchTasks()
  fetchOptions()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
</style>
```

> 注意：`getRequirementDocuments` 如果尚未在 `requirement-analysis.js` 中导出，需要先确认接口路径并补充导出函数（`/requirement-analysis/documents/`）。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/requirement-analysis/ScheduledGenerationTasks.vue
git commit -m "feat: add ScheduledGenerationTasks frontend page"
```

---

## Task 11: 前端路由与侧边栏

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layout/index.vue`

- [ ] **Step 1: 在 router/index.js 的 /ai-generation children 中添加路由**

找到 `frontend/src/router/index.js` 第 167-170 行（`task-detail/:taskId` 路由块）之后，插入：

```javascript
      {
        path: 'scheduled-generation',
        name: 'ScheduledGenerationTasks',
        component: () =>
          import('@/views/requirement-analysis/ScheduledGenerationTasks.vue'),
      },
```

- [ ] **Step 2: 在 layout/index.vue 的 ai-generation 菜单块中添加菜单项**

找到 `frontend/src/layout/index.vue` 第 26-29 行（`generated-testcases` 菜单项）之后、`</el-sub-menu>` 之前，插入：

```vue
              <el-menu-item index="/ai-generation/scheduled-generation">{{
                $t("menu.scheduledGenerationTasks")
              }}</el-menu-item>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/router/index.js frontend/src/layout/index.vue
git commit -m "feat: add scheduled-generation route and menu item"
```

---

## Task 12: AIModelConfig 前端扩展（Bedrock 配置字段）

**Files:**
- Modify: `frontend/src/views/requirement-analysis/AIModelConfig.vue`

- [ ] **Step 1: 在模型类型选项中添加 bedrock_claude**

在 `AIModelConfig.vue` 中找到模型类型的 `el-select` 或模型类型选项数组，添加：

```javascript
{ value: 'bedrock_claude', label: 'AWS Bedrock Claude' }
```

- [ ] **Step 2: 在表单中添加 Bedrock 专属字段（条件显示）**

在 AI Key / Base URL 字段的下方（或表单末尾），添加 `v-if="form.model_type === 'bedrock_claude'"` 的条件块：

```vue
<template v-if="form.model_type === 'bedrock_claude'">
  <el-form-item label="Access Key ID" prop="aws_access_key_id">
    <el-input v-model="form.aws_access_key_id" placeholder="AKIAIOSFODNN7EXAMPLE" />
  </el-form-item>
  <el-form-item label="Secret Access Key" prop="aws_secret_access_key">
    <el-input v-model="form.aws_secret_access_key" type="password" show-password />
  </el-form-item>
  <el-form-item label="Region">
    <el-input v-model="form.aws_region" placeholder="us-east-1" />
  </el-form-item>
  <el-form-item label="Model ID">
    <el-select v-model="form.aws_model_id" allow-create filterable style="width:100%">
      <el-option value="anthropic.claude-sonnet-4-5" label="Claude Sonnet 4.5" />
      <el-option value="anthropic.claude-opus-4-7" label="Claude Opus 4.7" />
      <el-option value="anthropic.claude-haiku-4-5-20251001" label="Claude Haiku 4.5" />
    </el-select>
  </el-form-item>
</template>
```

同时确保表单的 `form` 对象初始化时包含这四个字段（默认空字符串），以及提交时这四个字段会被包含在 payload 中（ModelSerializer 已有这四个字段）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/requirement-analysis/AIModelConfig.vue
git commit -m "feat: add Bedrock Claude fields to AI model config form"
```

---

## Task 13: 端到端冒烟测试

- [ ] **Step 1: 启动后端**

```bash
source venv/Scripts/activate
python manage.py runserver
```

- [ ] **Step 2: 启动前端**

```bash
"D:/software/Node/node.exe" frontend/node_modules/vite/bin/vite.js
```

- [ ] **Step 3: 在配置中心验证 Bedrock 模型配置**

访问 http://localhost:3000 → 配置中心 → AI模型配置 → 新建配置，选择 `AWS Bedrock Claude`，确认 Bedrock 专属字段出现。

- [ ] **Step 4: 在 AI 用例生成菜单验证定时任务页面**

访问 http://localhost:3000/ai-generation/scheduled-generation，确认页面加载正常，可新建定时任务。

- [ ] **Step 5: 运行全部后端测试**

```bash
python manage.py test apps.requirement_analysis.tests -v 2
```

Expected: 所有测试通过，无错误。

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: Claude Bedrock integration and nightly scheduled generation complete"
```
