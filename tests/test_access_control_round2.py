"""第二轮权限补漏：UI 项目参数 / 远程浏览器服务、AI 生成 SSE、API 测试资源的项目可见性"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.api_testing.models import ApiCollection, ApiProject, ApiRequest, ScheduledTask, TestSuite
from apps.requirement_analysis.models import TestCaseGenerationTask
from apps.ui_automation.models import RemoteBrowserService, UiProject, UiProjectParameter

User = get_user_model()


def results(resp):
    data = resp.data
    return data['results'] if isinstance(data, dict) and 'results' in data else data


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class UiProjectParameterScopingTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='ui_alice', password='pw')
        self.bob = User.objects.create_user(username='ui_bob', password='pw')
        self.project = UiProject.objects.create(name='UI', base_url='http://x', owner=self.alice)
        self.param = UiProjectParameter.objects.create(
            project=self.project, name='password', value='s3cret', created_by=self.alice,
        )

    def test_outsider_cannot_read_or_modify_parameters(self):
        bob = client_for(self.bob)
        self.assertEqual(results(bob.get('/api/ui-automation/project-parameters/')), [])
        self.assertEqual(bob.get(f'/api/ui-automation/project-parameters/{self.param.id}/').status_code, 404)
        resp = bob.post('/api/ui-automation/project-parameters/', {
            'project': self.project.id, 'name': 'x', 'value': 'y',
        }, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_owner_and_member_can_read(self):
        member = User.objects.create_user(username='ui_member', password='pw')
        self.project.members.add(member)
        for user in (self.alice, member):
            names = [p['name'] for p in results(client_for(user).get('/api/ui-automation/project-parameters/'))]
            self.assertEqual(names, ['password'])

    def test_remote_browser_register_requires_membership(self):
        payload = {'project': self.project.id, 'name': 'node', 'service_type': 'playwright_cdp', 'url': 'ws://x'}
        self.assertEqual(
            client_for(self.bob).post('/api/ui-automation/remote-browser-services/register/', payload, format='json').status_code,
            404,
        )
        resp = client_for(self.alice).post('/api/ui-automation/remote-browser-services/register/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(results(client_for(self.bob).get('/api/ui-automation/remote-browser-services/')), [])
        self.assertEqual(
            client_for(self.bob).post('/api/ui-automation/remote-browser-services/heartbeat/',
                                      {'project': self.project.id, 'name': 'node'}, format='json').status_code,
            404,
        )
        self.assertTrue(RemoteBrowserService.objects.filter(name='node').exists())


class GenerationStreamAuthTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='sse_alice', password='pw')
        self.task = TestCaseGenerationTask.objects.create(
            task_id='TASK_SSE0001', title='t', requirement_text='r', created_by=self.alice, status='completed',
        )
        self.url = f'/api/requirement-analysis/testcase-generation/{self.task.task_id}/stream_progress/'

    def test_anonymous_rejected(self):
        self.assertEqual(APIClient().get(self.url).status_code, 401)

    def test_other_user_gets_404(self):
        bob = User.objects.create_user(username='sse_bob', password='pw')
        self.assertEqual(client_for(bob).get(self.url).status_code, 404)

    def test_owner_can_subscribe_via_session(self):
        client = APIClient()
        client.login(username='sse_alice', password='pw')  # EventSource 走 session cookie
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/event-stream', resp['Content-Type'])
        resp.close()


class ApiResourceProjectVisibilityTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='api_alice', password='pw')
        self.bob = User.objects.create_user(username='api_bob', password='pw')
        # 私有项目里被标记为"公开"的资源，不应泄露给非成员
        self.private = ApiProject.objects.create(
            name='priv', project_type='HTTP', status='IN_PROGRESS', owner=self.alice, visibility='private',
        )
        self.public = ApiProject.objects.create(
            name='pub', project_type='HTTP', status='IN_PROGRESS', owner=self.alice, visibility='all',
        )
        self.req_private = self._request(self.private, 'hidden')
        self.req_public = self._request(self.public, 'shown')
        self.suite_private = TestSuite.objects.create(
            name='hidden-suite', project=self.private, created_by=self.alice, visibility='all',
        )
        self.task_private = ScheduledTask.objects.create(
            name='hidden-task', task_type='TEST_SUITE', trigger_type='INTERVAL', interval_seconds=60,
            test_suite=self.suite_private, created_by=self.alice, visibility='all',
        )

    def _request(self, project, name):
        collection = ApiCollection.objects.create(name=f'{name}-c', project=project)
        return ApiRequest.objects.create(
            name=name, url='http://x', collection=collection, created_by=self.alice, visibility='all',
        )

    def test_outsider_sees_only_public_project_resources(self):
        bob = client_for(self.bob)
        names = {r['name'] for r in results(bob.get('/api/api-testing/requests/'))}
        self.assertIn('shown', names)
        self.assertNotIn('hidden', names)
        self.assertEqual(bob.get(f'/api/api-testing/requests/{self.req_private.id}/').status_code, 404)
        self.assertNotIn('hidden-suite', {s['name'] for s in results(bob.get('/api/api-testing/test-suites/'))})
        self.assertNotIn('hidden-task', {t['name'] for t in results(bob.get('/api/api-testing/scheduled-tasks/'))})

    def test_member_and_owner_still_see_everything(self):
        self.private.members.add(self.bob)
        bob = client_for(self.bob)
        self.assertIn('hidden', {r['name'] for r in results(bob.get('/api/api-testing/requests/'))})
        self.assertIn('hidden-suite', {s['name'] for s in results(bob.get('/api/api-testing/test-suites/'))})
        alice = client_for(self.alice)
        self.assertEqual(alice.get(f'/api/api-testing/requests/{self.req_private.id}/').status_code, 200)


class OperationLogScopingTest(TestCase):
    def setUp(self):
        from apps.api_testing.models import Environment
        self.alice = User.objects.create_user(username='log_alice', password='pw')
        self.bob = User.objects.create_user(username='log_bob', password='pw')
        # 公开项目：bob 能看到项目本身，但不是成员，不应看到其中的操作日志
        self.project = ApiProject.objects.create(
            name='p', project_type='HTTP', status='IN_PROGRESS', owner=self.alice, visibility='all',
        )
        self.collection = ApiCollection.objects.create(name='c', project=self.project)
        self.request = ApiRequest.objects.create(
            name='r', url='http://x', collection=self.collection, created_by=self.alice,
        )
        self.env_model = Environment

    def _logs(self, user):
        return results(client_for(user).get('/api/api-testing/operation-logs/'))

    def test_project_resolved_automatically(self):
        from apps.api_testing.models import OperationLog
        from apps.api_testing.operation_logger import log_operation
        log_operation('edit', 'request', self.request.id, 'r', self.alice)
        log_operation('edit', 'collection', self.collection.id, 'c', self.alice)
        self.assertEqual(
            set(OperationLog.objects.values_list('project_id', flat=True)), {self.project.id}
        )

    def test_only_members_see_project_logs(self):
        from apps.api_testing.operation_logger import log_operation
        log_operation('edit', 'request', self.request.id, 'r', self.alice)
        self.assertEqual(len(self._logs(self.alice)), 1)
        self.assertEqual(self._logs(self.bob), [])

        self.project.members.add(self.bob)
        self.assertEqual(len(self._logs(self.bob)), 1)

    def test_logs_without_project_visible_to_operator_only(self):
        from apps.api_testing.operation_logger import log_operation
        env = self.env_model.objects.create(name='g', scope='GLOBAL', created_by=self.bob)
        log_operation('create', 'environment', env.id, 'g', self.bob)
        self.assertEqual(len(self._logs(self.bob)), 1)
        self.assertEqual(self._logs(self.alice), [])

    def test_migration_backfills_history(self):
        import importlib
        from django.apps import apps as global_apps
        from apps.api_testing.models import OperationLog
        migration = importlib.import_module('apps.api_testing.migrations.0007_operationlog_project')
        old_log = OperationLog.objects.create(
            operation_type='edit', resource_type='request', resource_id=self.request.id,
            resource_name='r', description='d', user=self.alice,
        )
        orphan = OperationLog.objects.create(
            operation_type='delete', resource_type='suite', resource_id=999999,
            resource_name='gone', description='d', user=self.alice,
        )
        migration.backfill_project(global_apps, None)
        old_log.refresh_from_db()
        orphan.refresh_from_db()
        self.assertEqual(old_log.project_id, self.project.id)
        self.assertIsNone(orphan.project_id)
