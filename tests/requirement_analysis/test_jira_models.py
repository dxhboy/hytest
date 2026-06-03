from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.requirement_analysis.models import JiraIssueLink, JiraIssueCaseLink

User = get_user_model()

class JiraIssueLinkTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester_jira_model', password='pass')

    def test_create_issue_link(self):
        link = JiraIssueLink.objects.create(
            issue_key='PROJ-123',
            issue_url='https://co.atlassian.net/browse/PROJ-123',
            issue_summary='Login feature',
            jira_domain='co.atlassian.net',
            created_by=self.user,
        )
        self.assertEqual(str(link.issue_key), 'PROJ-123')

    def test_unique_together_issue_key_domain(self):
        JiraIssueLink.objects.create(
            issue_key='PROJ-1', issue_url='https://co.atlassian.net/browse/PROJ-1',
            issue_summary='S', jira_domain='co.atlassian.net', created_by=self.user)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            JiraIssueLink.objects.create(
                issue_key='PROJ-1', issue_url='https://co.atlassian.net/browse/PROJ-1',
                issue_summary='S', jira_domain='co.atlassian.net', created_by=self.user)
