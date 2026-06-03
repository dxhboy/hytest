from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.requirement_analysis.jira_client import JiraClient, JiraClientError


class JiraClientTest(TestCase):
    def setUp(self):
        self.client = JiraClient(
            domain='co.atlassian.net',
            email='user@co.com',
            api_token='token123'
        )

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_get_issue_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'key': 'PROJ-1',
            'fields': {
                'summary': 'Login page',
                'description': {'content': [{'content': [{'text': 'User can login'}]}]},
                'priority': {'name': 'High'},
                'labels': ['auth'],
                'subtasks': [],
            }
        }
        mock_get.return_value = mock_resp
        issue = self.client.get_issue('PROJ-1', fields=['summary', 'description'])
        self.assertEqual(issue['key'], 'PROJ-1')
        self.assertEqual(issue['fields']['summary'], 'Login page')

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_get_issue_404_raises_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        with self.assertRaises(JiraClientError):
            self.client.get_issue('PROJ-999', fields=['summary'])

    def test_extract_content_summary_only(self):
        issue = {
            'key': 'PROJ-1',
            'fields': {
                'summary': 'Login feature',
                'description': None,
                'priority': {'name': 'Medium'},
                'labels': [],
                'subtasks': [],
            }
        }
        text = self.client.extract_content(issue, selected_fields=['summary'])
        self.assertIn('Login feature', text)

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_validate_connection_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        self.assertTrue(self.client.validate_connection())

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_validate_connection_fail(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp
        self.assertFalse(self.client.validate_connection())

    def test_issue_key_from_url(self):
        url = 'https://co.atlassian.net/browse/PROJ-123'
        key = JiraClient.issue_key_from_url(url)
        self.assertEqual(key, 'PROJ-123')

    def test_issue_key_from_key_directly(self):
        key = JiraClient.issue_key_from_url('PROJ-456')
        self.assertEqual(key, 'PROJ-456')

    def test_issue_key_from_invalid_url(self):
        key = JiraClient.issue_key_from_url('https://example.com/not-a-jira-url')
        self.assertIsNone(key)