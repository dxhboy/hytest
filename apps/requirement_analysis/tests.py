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