"""P0 安全修复回归测试：认证入口、CSRF、项目级数据隔离"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.executions.models import TestPlan, TestRun, TestRunCase
from apps.projects.models import Project, ProjectMember
from apps.requirement_analysis.models import RequirementDocument, TestCaseGenerationTask
from apps.testcases.models import TestCase as Case

User = get_user_model()


class AuthEndpointTest(TestCase):
    def test_test_register_endpoint_removed(self):
        for prefix in ('/api/auth/', '/api/users/'):
            resp = self.client.post(f'{prefix}test-register/', {'username': 'x', 'password': 'y'})
            self.assertEqual(resp.status_code, 404, prefix)

    def test_register_endpoint_creates_user(self):
        resp = APIClient().post('/api/auth/register/', {
            'username': 'newbie', 'email': 'n@example.com',
            'password': 'Passw0rd!x', 'password_confirm': 'Passw0rd!x',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(User.objects.filter(username='newbie').exists())

    def test_session_auth_requires_csrf(self):
        """Session 认证的写请求必须带 CSRF token，JWT 不受影响"""
        user = User.objects.create_user(username='csrf_user', password='pw12345678')
        client = APIClient(enforce_csrf_checks=True)
        client.login(username='csrf_user', password='pw12345678')
        resp = client.post('/api/projects/', {'name': 'p'}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('CSRF', str(resp.data))

        jwt_client = APIClient(enforce_csrf_checks=True)
        jwt_client.force_authenticate(user=user)
        resp = jwt_client.get('/api/projects/')
        self.assertEqual(resp.status_code, 200)


class ProjectScopingTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pw')
        self.bob = User.objects.create_user(username='bob', password='pw')
        self.viewer = User.objects.create_user(username='viewer', password='pw')
        self.project = Project.objects.create(name='A', owner=self.alice)
        ProjectMember.objects.create(project=self.project, user=self.viewer, role='viewer')

        self.case = Case.objects.create(title='c1', project=self.project, author=self.alice)
        self.plan = TestPlan.objects.create(name='plan', creator=self.alice)
        self.plan.projects.add(self.project)
        self.run = TestRun.objects.create(
            name='run', test_plan=self.plan, project=self.project,
            creator=self.alice, assignee=self.alice,
        )
        self.run_case = TestRunCase.objects.create(test_run=self.run, testcase=self.case)
        self.doc = RequirementDocument.objects.create(
            title='doc', document_type='txt', uploaded_by=self.alice, project=self.project,
        )
        self.gen_task = TestCaseGenerationTask.objects.create(
            task_id='TASK-SCOPE-1', title='t', requirement_text='r',
            project=self.project, created_by=self.alice,
        )

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _ids(self, resp):
        data = resp.data.get('results', resp.data) if isinstance(resp.data, dict) else resp.data
        return {item['id'] for item in data}

    def test_outsider_cannot_see_or_modify_executions(self):
        bob = self.client_for(self.bob)
        self.assertNotIn(self.plan.id, self._ids(bob.get('/api/executions/plans/')))
        self.assertEqual(bob.get(f'/api/executions/plans/{self.plan.id}/').status_code, 404)
        self.assertEqual(bob.get(f'/api/executions/runs/{self.run.id}/').status_code, 404)
        resp = bob.patch(f'/api/executions/run_cases/{self.run_case.id}/update_status/',
                         {'status': 'passed'}, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_member_can_see_executions(self):
        viewer = self.client_for(self.viewer)
        self.assertIn(self.plan.id, self._ids(viewer.get('/api/executions/plans/')))
        self.assertEqual(viewer.get(f'/api/executions/runs/{self.run.id}/').status_code, 200)

    def test_outsider_cannot_modify_project(self):
        bob = self.client_for(self.bob)
        self.assertEqual(bob.patch(f'/api/projects/{self.project.id}/', {'name': 'x'}, format='json').status_code, 404)
        self.assertEqual(bob.delete(f'/api/projects/{self.project.id}/').status_code, 404)
        self.assertNotIn(self.project.id, {p['id'] for p in bob.get('/api/projects/all/').data})

    def test_viewer_member_cannot_modify_project(self):
        viewer = self.client_for(self.viewer)
        self.assertEqual(viewer.get(f'/api/projects/{self.project.id}/').status_code, 200)
        self.assertEqual(viewer.delete(f'/api/projects/{self.project.id}/').status_code, 403)
        self.assertTrue(Project.objects.filter(id=self.project.id).exists())

    def test_reports_only_count_accessible_projects(self):
        bob = self.client_for(self.bob)
        resp = bob.get('/api/reports/reports/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total_cases'], 0)
        self.assertEqual(resp.data['active_plans'], 0)

        alice = self.client_for(self.alice)
        self.assertEqual(alice.get('/api/reports/reports/dashboard/').data['total_cases'], 1)

    def test_requirement_documents_scoped(self):
        bob = self.client_for(self.bob)
        self.assertEqual(bob.get(f'/api/requirement-analysis/documents/{self.doc.id}/').status_code, 404)
        self.assertEqual(
            bob.get(f'/api/requirement-analysis/testcase-generation/{self.gen_task.task_id}/').status_code, 404
        )
        viewer = self.client_for(self.viewer)
        self.assertEqual(viewer.get(f'/api/requirement-analysis/documents/{self.doc.id}/').status_code, 200)

    def test_cannot_create_plan_in_foreign_project(self):
        bob = self.client_for(self.bob)
        resp = bob.post('/api/executions/plans/', {
            'name': 'evil', 'projects': [self.project.id], 'testcases': [self.case.id],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        plan = TestPlan.objects.get(name='evil')
        self.assertEqual(plan.projects.count(), 0)
        self.assertFalse(TestRun.objects.filter(test_plan=plan).exists())


class GlobalConfigPermissionTest(TestCase):
    def test_only_staff_can_write_ai_model_config(self):
        user = User.objects.create_user(username='plain', password='pw')
        staff = User.objects.create_user(username='boss', password='pw', is_staff=True)
        url = '/api/requirement-analysis/ai-models/'

        plain = APIClient()
        plain.force_authenticate(user=user)
        self.assertEqual(plain.get(url).status_code, 200)
        self.assertEqual(plain.post(url, {'name': 'x'}, format='json').status_code, 403)

        admin = APIClient()
        admin.force_authenticate(user=staff)
        # 管理员通过权限校验（这里只验证不是 403，字段校验失败返回 400 也可）
        self.assertNotEqual(admin.post(url, {'name': 'x'}, format='json').status_code, 403)
