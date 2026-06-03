from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()

class JiraProfileAPITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester_jira_api', password='pass123')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_save_and_retrieve_jira_config(self):
        url = reverse('profile')  # /api/users/profile/
        data = {
            'jira_domain': 'myco.atlassian.net',
            'jira_email': 'me@myco.com',
            'jira_api_token_input': 'mytoken123',
        }
        resp = self.client.patch(url, data, format='json')
        self.assertEqual(resp.status_code, 200)

        # 重新读取，token 应被脱敏
        resp2 = self.client.get(url)
        self.assertEqual(resp2.data['jira_domain'], 'myco.atlassian.net')
        self.assertEqual(resp2.data['jira_email'], 'me@myco.com')
        self.assertEqual(resp2.data['jira_api_token'], '***')

    def test_empty_token_does_not_overwrite(self):
        url = reverse('profile')
        # 先保存 token
        self.client.patch(url, {'jira_api_token_input': 'original_token'}, format='json')
        # 再用空 token 更新其他字段
        self.client.patch(url, {'jira_domain': 'other.atlassian.net', 'jira_api_token_input': ''}, format='json')
        from apps.users.models import UserProfile
        from cryptography.fernet import Fernet
        from django.conf import settings
        profile = UserProfile.objects.get(user=self.user)
        f = Fernet(settings.JIRA_TOKEN_ENCRYPT_KEY)
        decrypted = f.decrypt(profile.jira_api_token.encode()).decode()
        self.assertEqual(decrypted, 'original_token')