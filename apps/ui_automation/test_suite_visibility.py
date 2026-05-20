from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.ui_automation.models import UiProject, TestSuite

User = get_user_model()


class TestSuiteVisibilityTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='ui_owner', password='testpass123', email='ui_owner@test.com'
        )
        self.other = User.objects.create_user(
            username='ui_other', password='testpass123', email='ui_other@test.com'
        )
        self.project = UiProject.objects.create(
            name='Test UI Project',
            owner=self.owner,
            base_url='http://localhost',
        )
        self.suite = TestSuite.objects.create(
            name='Public Suite',
            project=self.project,
            created_by=self.owner,
            visibility='all',
        )

    def test_public_suite_visible_to_non_member(self):
        """visibility='all' 的套件对非项目成员应可见"""
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/ui-automation/test-suites/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        results = data['results']
        suite_ids = [s['id'] for s in results]
        self.assertIn(self.suite.id, suite_ids)

    def test_private_suite_hidden_from_non_creator(self):
        """visibility='private' 的套件对非创建者不可见"""
        private_suite = TestSuite.objects.create(
            name='Private Suite',
            project=self.project,
            created_by=self.owner,
            visibility='private',
        )
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/ui-automation/test-suites/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        results = data['results']
        suite_ids = [s['id'] for s in results]
        self.assertNotIn(private_suite.id, suite_ids)

    def test_creator_sees_own_private_suite(self):
        """创建者能看到自己的 private 套件"""
        private_suite = TestSuite.objects.create(
            name='My Private Suite',
            project=self.project,
            created_by=self.owner,
            visibility='private',
        )
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.get('/api/ui-automation/test-suites/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        results = data['results']
        suite_ids = [s['id'] for s in results]
        self.assertIn(private_suite.id, suite_ids)
