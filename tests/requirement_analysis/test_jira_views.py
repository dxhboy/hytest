from unittest.mock import patch, MagicMock
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.users.models import UserProfile
from cryptography.fernet import Fernet
from django.conf import settings

User = get_user_model()


class JiraPreviewViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester_jira_view', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        # 写入加密 token
        f = Fernet(settings.JIRA_TOKEN_ENCRYPT_KEY)
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.jira_domain = 'co.atlassian.net'
        profile.jira_email = 'u@co.com'
        profile.jira_api_token = f.encrypt(b'token123').decode()
        profile.save()

    @patch('apps.requirement_analysis.jira_views.JiraClient')
    def test_preview_returns_issue_summary(self, MockClient):
        instance = MockClient.return_value
        instance.get_issue.return_value = {
            'key': 'PROJ-1',
            'fields': {'summary': 'Login', 'description': None,
                       'priority': None, 'labels': [], 'subtasks': []}
        }
        instance.extract_content.return_value = '# Login'
        # 需要 mock issue_key_from_url 静态方法
        with patch('apps.requirement_analysis.jira_views.JiraClient.issue_key_from_url', return_value='PROJ-1'):
            resp = self.client.post('/api/requirement-analysis/jira/preview/', {
                'urls': ['https://co.atlassian.net/browse/PROJ-1'],
                'selected_fields': ['summary'],
            }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)
        self.assertEqual(resp.data['results'][0]['issue_key'], 'PROJ-1')

    def test_preview_returns_400_when_no_jira_config(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.jira_domain = ''
        profile.save()
        resp = self.client.post('/api/requirement-analysis/jira/preview/', {
            'urls': ['https://co.atlassian.net/browse/PROJ-1'],
            'selected_fields': ['summary'],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_validate_endpoint_exists(self):
        """Jira 凭据未配置时，validate 端点返回 400"""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.jira_domain = ''
        profile.save()
        resp = self.client.post('/api/requirement-analysis/jira/validate/')
        self.assertEqual(resp.status_code, 400)