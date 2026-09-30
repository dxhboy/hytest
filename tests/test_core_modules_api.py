"""此前没有测试覆盖的模块（testcases / versions / reviews / core）的基础接口与权限隔离测试"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import UnifiedNotificationConfig
from apps.projects.models import Project
from apps.reviews.models import ReviewTemplate, TestCaseReview
from apps.testcases.models import TestCase as Case
from apps.versions.models import Version

User = get_user_model()


def results(resp):
    data = resp.data
    return data['results'] if isinstance(data, dict) and 'results' in data else data


class ScopedApiTestCase(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice_m', password='pw')
        self.bob = User.objects.create_user(username='bob_m', password='pw')
        self.project = Project.objects.create(name='P', owner=self.alice)
        self.bob_project = Project.objects.create(name='B', owner=self.bob)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class TestCaseApiTest(ScopedApiTestCase):
    def test_create_list_and_isolation(self):
        alice = self.client_for(self.alice)
        resp = alice.post('/api/testcases/', {
            'title': '登录成功', 'project_id': self.project.id, 'priority': 'high', 'test_type': 'functional',
            'expected_result': '进入首页',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        case = Case.objects.get(title='登录成功')
        self.assertEqual(case.project_id, self.project.id)
        self.assertEqual(case.author_id, self.alice.id)

        self.assertEqual([c['id'] for c in results(alice.get('/api/testcases/'))], [case.id])

        bob = self.client_for(self.bob)
        self.assertEqual(results(bob.get('/api/testcases/')), [])
        self.assertEqual(bob.get(f'/api/testcases/{case.id}/').status_code, 404)
        self.assertEqual(bob.delete(f'/api/testcases/{case.id}/').status_code, 404)

    def test_cannot_create_in_foreign_project(self):
        bob = self.client_for(self.bob)
        resp = bob.post('/api/testcases/', {'title': 'x', 'project_id': self.project.id, 'expected_result': 'ok'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        # 指定无权限的项目时落到自己可访问的项目，而不是目标项目
        self.assertNotEqual(Case.objects.get(title='x').project_id, self.project.id)


class VersionApiTest(ScopedApiTestCase):
    def test_create_and_isolation(self):
        alice = self.client_for(self.alice)
        resp = alice.post('/api/versions/', {'name': 'v1.0', 'project_ids': [self.project.id]}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        version = Version.objects.get(name='v1.0')

        self.assertEqual(alice.get(f'/api/versions/projects/{self.project.id}/versions/').status_code, 200)

        bob = self.client_for(self.bob)
        self.assertEqual(bob.get(f'/api/versions/{version.id}/').status_code, 404)
        self.assertEqual(bob.get(f'/api/versions/projects/{self.project.id}/versions/').status_code, 403)
        resp = bob.post('/api/versions/', {'name': 'evil', 'project_ids': [self.project.id]}, format='json')
        self.assertIn(resp.status_code, (400, 403))
        self.assertFalse(Version.objects.filter(name='evil').exists())


class ReviewApiTest(ScopedApiTestCase):
    def setUp(self):
        super().setUp()
        self.case = Case.objects.create(title='c', project=self.project, author=self.alice)

    def test_create_review_and_isolation(self):
        alice = self.client_for(self.alice)
        resp = alice.post('/api/reviews/reviews/', {
            'title': 'R1', 'projects': [self.project.id], 'testcases': [self.case.id], 'reviewers': [self.alice.id],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        review = TestCaseReview.objects.get(title='R1')

        bob = self.client_for(self.bob)
        self.assertEqual(results(bob.get('/api/reviews/reviews/')), [])
        self.assertEqual(bob.get(f'/api/reviews/reviews/{review.id}/').status_code, 404)
        resp = bob.post('/api/reviews/review-comments/', {'review': review.id, 'content': 'x'}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_reviewer_submits_and_review_completes(self):
        alice = self.client_for(self.alice)
        alice.post('/api/reviews/reviews/', {
            'title': 'R2', 'projects': [self.project.id], 'testcases': [self.case.id], 'reviewers': [self.alice.id],
        }, format='json')
        review = TestCaseReview.objects.get(title='R2')
        resp = alice.post(f'/api/reviews/reviews/{review.id}/submit_review/', {'status': 'approved'}, format='json')
        self.assertEqual(resp.status_code, 200)
        review.refresh_from_db()
        self.assertEqual(review.status, 'approved')

    def test_cannot_attach_foreign_project_or_cases(self):
        bob = self.client_for(self.bob)
        resp = bob.post('/api/reviews/reviews/', {
            'title': 'evil', 'projects': [self.project.id], 'testcases': [], 'reviewers': [],
        }, format='json')
        self.assertEqual(resp.status_code, 403)
        resp = bob.post('/api/reviews/reviews/', {
            'title': 'evil2', 'projects': [self.bob_project.id], 'testcases': [self.case.id], 'reviewers': [],
        }, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(TestCaseReview.objects.filter(title__startswith='evil').exists())

    def test_templates_scoped(self):
        template = ReviewTemplate.objects.create(name='T', creator=self.alice)
        template.project.add(self.project)
        self.assertEqual(len(results(self.client_for(self.alice).get('/api/reviews/review-templates/'))), 1)
        self.assertEqual(results(self.client_for(self.bob).get('/api/reviews/review-templates/')), [])


class NotificationConfigApiTest(ScopedApiTestCase):
    def test_private_config_hidden_and_only_creator_can_edit(self):
        shared = UnifiedNotificationConfig.objects.create(name='shared', created_by=self.alice, visibility='all')
        private = UnifiedNotificationConfig.objects.create(name='mine', created_by=self.alice, visibility='private')

        bob = self.client_for(self.bob)
        names = {c['name'] for c in results(bob.get('/api/core/notification-configs/'))}
        self.assertIn('shared', names)
        self.assertNotIn('mine', names)
        self.assertEqual(bob.get(f'/api/core/notification-configs/{private.id}/').status_code, 404)
        self.assertEqual(
            bob.patch(f'/api/core/notification-configs/{shared.id}/', {'name': 'hacked'}, format='json').status_code,
            403,
        )
        shared.refresh_from_db()
        self.assertEqual(shared.name, 'shared')
