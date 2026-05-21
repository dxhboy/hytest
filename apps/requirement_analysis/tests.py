from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.projects.models import Project
from .models import RequirementDocument, RequirementAnalysis, BusinessRequirement, GeneratedTestCase

User = get_user_model()


class RequirementAnalysisTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.project = Project.objects.create(
            name='Test Project',
            description='A test project'
        )

    def test_requirement_document_creation(self):
        """测试需求文档创建"""
        doc = RequirementDocument.objects.create(
            title='Test Document',
            document_type='txt',
            uploaded_by=self.user,
            project=self.project
        )
        self.assertEqual(doc.title, 'Test Document')
        self.assertEqual(doc.status, 'uploaded')

    def test_requirement_analysis_creation(self):
        """测试需求分析创建"""
        doc = RequirementDocument.objects.create(
            title='Test Document',
            document_type='txt',
            uploaded_by=self.user,
            project=self.project
        )
        analysis = RequirementAnalysis.objects.create(
            document=doc,
            analysis_report='Test analysis report',
            requirements_count=5
        )
        self.assertEqual(analysis.requirements_count, 5)
        self.assertEqual(analysis.document, doc)

    def test_business_requirement_creation(self):
        """测试业务需求创建"""
        doc = RequirementDocument.objects.create(
            title='Test Document',
            document_type='txt',
            uploaded_by=self.user,
            project=self.project
        )
        analysis = RequirementAnalysis.objects.create(
            document=doc,
            analysis_report='Test analysis report'
        )
        requirement = BusinessRequirement.objects.create(
            analysis=analysis,
            requirement_id='REQ-001',
            requirement_name='Test Requirement',
            requirement_type='functional',
            module='Test Module',
            requirement_level='high',
            description='Test description',
            acceptance_criteria='Test criteria'
        )
        self.assertEqual(requirement.requirement_id, 'REQ-001')
        self.assertEqual(requirement.requirement_type, 'functional')

    def test_generated_test_case_creation(self):
        """测试生成测试用例创建"""
        doc = RequirementDocument.objects.create(
            title='Test Document',
            document_type='txt',
            uploaded_by=self.user,
            project=self.project
        )
        analysis = RequirementAnalysis.objects.create(
            document=doc,
            analysis_report='Test analysis report'
        )
        requirement = BusinessRequirement.objects.create(
            analysis=analysis,
            requirement_id='REQ-001',
            requirement_name='Test Requirement',
            requirement_type='functional',
            module='Test Module',
            requirement_level='high',
            description='Test description',
            acceptance_criteria='Test criteria'
        )
        test_case = GeneratedTestCase.objects.create(
            requirement=requirement,
            case_id='TC-001',
            title='Test Case Title',
            priority='P1',
            precondition='Test precondition',
            test_steps='Test steps',
            expected_result='Test result'
        )
        self.assertEqual(test_case.case_id, 'TC-001')
        self.assertEqual(test_case.status, 'generated')


from unittest.mock import MagicMock, patch


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

    @patch('apps.requirement_analysis.bedrock_adapter.boto3')
    def test_call_stream_yields_chunks(self, mock_boto3):
        from apps.requirement_analysis.bedrock_adapter import BedrockAdapter
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse_stream.return_value = {
            'stream': [
                {'contentBlockDelta': {'delta': {'text': 'hello'}}},
                {'contentBlockDelta': {'delta': {'text': ' world'}}},
            ]
        }
        messages = [{'role': 'user', 'content': 'test'}]

        async def collect():
            chunks = []
            async for chunk in BedrockAdapter.call_stream(self._make_config(), messages):
                chunks.append(chunk)
            return chunks

        import asyncio
        chunks = asyncio.get_event_loop().run_until_complete(collect())
        self.assertEqual(chunks, ['hello', ' world'])


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


class ScheduledGenerationTaskModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass')

    def test_model_fields_exist(self):
        from apps.requirement_analysis.models import ScheduledGenerationTask
        field_names = [f.name for f in ScheduledGenerationTask._meta.get_fields()]
        for field in ('name', 'requirement_document', 'ai_model_config',
                      'scheduled_time', 'is_active', 'last_run_at',
                      'last_run_status', 'last_run_task', 'created_by', 'created_at'):
            self.assertIn(field, field_names, f"Missing field: {field}")

    def test_default_status_is_pending(self):
        from apps.requirement_analysis.models import ScheduledGenerationTask
        field = ScheduledGenerationTask._meta.get_field('last_run_status')
        self.assertEqual(field.default, 'pending')


class RunGenerationForDocumentTest(TestCase):
    def test_function_exists_and_is_callable(self):
        from apps.requirement_analysis.views import run_generation_for_document
        import inspect
        self.assertTrue(callable(run_generation_for_document))
        sig = inspect.signature(run_generation_for_document)
        self.assertIn('document_id', sig.parameters)
        self.assertIn('ai_model_config_id', sig.parameters)
        self.assertIn('created_by_id', sig.parameters)


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
        with patch('apps.requirement_analysis.views.run_generation_for_document') as mock_run:
            check_due_tasks()
            mock_run.assert_not_called()