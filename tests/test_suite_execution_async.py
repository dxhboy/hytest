"""API 测试套件改为 Celery 异步执行：接口立即返回 202，worker 与定时任务共用执行逻辑"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.api_testing import models as api_models
from apps.api_testing.tasks import execute_test_suite_task
from apps.api_testing.utils import execute_test_suite

User = get_user_model()

DELAY = 'apps.api_testing.tasks.execute_test_suite_task.delay'
SESSION_REQUEST = 'requests.Session.request'


def _http_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {'content-type': 'application/json'}
    resp.json.return_value = json_data or {}
    resp.text = '{}'
    resp.cookies = {}
    return resp


class SuiteExecutionAsyncTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='suite_async', password='pw')
        project = api_models.ApiProject.objects.create(name='p', project_type='HTTP', status='IN_PROGRESS', owner=self.user)
        collection = api_models.ApiCollection.objects.create(name='c', project=project)
        self.suite = api_models.TestSuite.objects.create(project=project, name='s', created_by=self.user)
        for i, code in enumerate([200, 500]):
            req = api_models.ApiRequest.objects.create(
                collection=collection, name=f'r{i}', method='GET', url=f'https://svc.example.com/{i}',
                created_by=self.user,
            )
            api_models.TestSuiteRequest.objects.create(
                test_suite=self.suite, request=req, order=i,
                assertions=[{'type': 'status_code', 'name': 'code', 'expected': 200}],
            )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/api-testing/test-suites/{self.suite.id}/execute/'

    @patch(DELAY)
    def test_endpoint_returns_202_with_pending_execution(self, delay):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.data['status'], 'PENDING')
        self.assertEqual(resp.data['total_requests'], 2)
        execution = api_models.TestExecution.objects.get(id=resp.data['id'])
        delay.assert_called_once_with(execution.id, self.user.id)

    @patch(DELAY, side_effect=ConnectionError('redis down'))
    def test_broker_down_marks_execution_failed(self, delay):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.data['status'], 'FAILED')
        execution = api_models.TestExecution.objects.get(id=resp.data['id'])
        self.assertIn('Redis', execution.results[0]['error'])
        self.assertIsNotNone(execution.end_time)

    @patch(SESSION_REQUEST)
    def test_worker_runs_suite_and_updates_execution(self, session_request):
        session_request.side_effect = [_http_response(200), _http_response(500)]
        with patch(DELAY):
            execution_id = self.client.post(self.url).data['id']

        execute_test_suite_task(execution_id, self.user.id)

        execution = api_models.TestExecution.objects.get(id=execution_id)
        self.assertEqual(execution.status, 'FAILED')
        self.assertEqual((execution.passed_requests, execution.failed_requests), (1, 1))
        self.assertIsNotNone(execution.start_time)
        self.assertEqual([r['passed'] for r in execution.results], [True, False])
        self.assertTrue(all(r['history_id'] for r in execution.results))
        self.assertEqual(api_models.RequestHistory.objects.count(), 2)

        # 执行完成后通过既有的执行详情接口即可拿到结果（前端轮询用）
        detail = self.client.get(f'/api/api-testing/test-executions/{execution_id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['status'], 'FAILED')

    @patch(SESSION_REQUEST, return_value=_http_response(200))
    def test_scheduled_execution_shares_engine(self, session_request):
        result = execute_test_suite(self.suite, None, self.user)
        self.assertTrue(result['success'])
        self.assertEqual((result['passed_count'], result['failed_count'], result['total_count']), (2, 0, 2))
        execution = api_models.TestExecution.objects.get(id=result['execution_id'])
        self.assertEqual(execution.status, 'COMPLETED')
        # 与手动执行同一套结果结构
        self.assertIn('history_id', execution.results[0])
