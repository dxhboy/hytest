from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.users.models import UserProfile

User = get_user_model()

class UserProfileJiraFieldsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester_jira', password='pass')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)

    def test_jira_fields_default_blank(self):
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.jira_domain, '')
        self.assertEqual(profile.jira_email, '')
        self.assertEqual(profile.jira_api_token, '')

    def test_jira_fields_can_be_set(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.jira_domain = 'company.atlassian.net'
        profile.jira_email = 'user@company.com'
        profile.jira_api_token = 'encrypted_token_here'
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.jira_domain, 'company.atlassian.net')
