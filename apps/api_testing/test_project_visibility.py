from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.api_testing.models import ApiProject

User = get_user_model()


class ApiProjectVisibilityTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='api_owner', password='testpass123', email='api_owner@test.com'
        )
        self.other = User.objects.create_user(
            username='api_other', password='testpass123', email='api_other@test.com'
        )
        self.public_project = ApiProject.objects.create(
            name='Public Project',
            project_type='HTTP',
            status='NOT_STARTED',
            owner=self.owner,
            visibility='all',
        )
        self.private_project = ApiProject.objects.create(
            name='Private Project',
            project_type='HTTP',
            status='NOT_STARTED',
            owner=self.owner,
            visibility='private',
        )

    def test_public_project_visible_to_non_member(self):
        """visibility='all' 的项目对非成员可见"""
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/api-testing/projects/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        results = data['results']
        project_ids = [p['id'] for p in results]
        self.assertIn(self.public_project.id, project_ids)

    def test_private_project_hidden_from_non_member(self):
        """visibility='private' 的项目对非成员不可见"""
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/api-testing/projects/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        results = data['results']
        project_ids = [p['id'] for p in results]
        self.assertNotIn(self.private_project.id, project_ids)

    def test_owner_sees_own_private_project(self):
        """owner 能看到自己的 private 项目"""
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.get('/api/api-testing/projects/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        results = data['results']
        project_ids = [p['id'] for p in results]
        self.assertIn(self.private_project.id, project_ids)

    def test_member_sees_private_project(self):
        """成员能看到被加入的 private 项目"""
        member = User.objects.create_user(
            username='api_member', password='testpass123', email='api_member@test.com'
        )
        self.private_project.members.add(member)
        client = APIClient()
        client.force_authenticate(user=member)
        response = client.get('/api/api-testing/projects/')
        self.assertEqual(response.status_code, 200)
        project_ids = [p['id'] for p in response.json()['results']]
        self.assertIn(self.private_project.id, project_ids)

    def test_visibility_field_in_response(self):
        """响应中应包含 visibility 字段"""
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.get(f'/api/api-testing/projects/{self.public_project.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('visibility', response.json())
        self.assertEqual(response.json()['visibility'], 'all')
