"""apps.core.notifications 通知传输层 + 各模块接入（HTTP 全部 mock）"""
import base64
import hashlib
import hmac
import urllib.parse
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.core import notifications
from apps.core.models import UnifiedNotificationConfig

User = get_user_model()

POST = 'apps.core.notifications.requests.post'


def _response(status_code=200, json_data=None, text=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text if text is not None else str(json_data or {})
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status.side_effect = (
        None if status_code < 400 else requests.exceptions.HTTPError(f'{status_code} Error')
    )
    return resp


class SigningTest(SimpleTestCase):
    def test_feishu_sign_matches_official_algorithm(self):
        ts, sign = notifications.feishu_sign('sec', timestamp='1700000000')
        expected = base64.b64encode(
            hmac.new(b'1700000000\nsec', digestmod=hashlib.sha256).digest()
        ).decode()
        self.assertEqual((ts, sign), ('1700000000', expected))

    def test_dingtalk_signed_url(self):
        url = notifications.dingtalk_signed_url('https://oapi.dingtalk.com/robot/send?access_token=x', 'sec',
                                                timestamp='1700000000000')
        digest = hmac.new(b'sec', b'1700000000000\nsec', digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest).decode())
        self.assertEqual(url, f'https://oapi.dingtalk.com/robot/send?access_token=x&timestamp=1700000000000&sign={sign}')
        self.assertIn('?timestamp=', notifications.dingtalk_signed_url('https://h/send', 'sec'))

    def test_prepare_request_per_bot_type(self):
        payload = {'msg_type': 'text'}
        url, body = notifications.prepare_webhook_request(
            {'type': 'feishu', 'webhook_url': 'https://f', 'secret': 's'}, payload)
        self.assertEqual(url, 'https://f')
        self.assertIn('sign', body)
        self.assertIn('timestamp', body)
        self.assertNotIn('sign', payload)  # 不修改调用方传入的 payload

        url, body = notifications.prepare_webhook_request(
            {'type': 'dingtalk', 'webhook_url': 'https://d?access_token=1', 'secret': 's'}, payload)
        self.assertIn('&sign=', url)
        self.assertEqual(body, payload)

        url, body = notifications.prepare_webhook_request({'type': 'wechat', 'webhook_url': 'https://w'}, payload)
        self.assertEqual((url, body), ('https://w', payload))


class PostWebhookTest(SimpleTestCase):
    @patch(POST)
    def test_success_and_biz_code(self, post):
        post.return_value = _response(200, {'code': 0})
        result = notifications.post_webhook({'type': 'wechat', 'webhook_url': 'https://w'}, {'a': 1})
        self.assertTrue(result.delivered)
        post.assert_called_once_with('https://w', json={'a': 1},
                                     headers={'Content-Type': 'application/json'}, timeout=10)

        post.return_value = _response(200, {'code': 19021, 'msg': 'sign match fail'})
        result = notifications.post_webhook({'type': 'feishu', 'webhook_url': 'https://f'}, {})
        self.assertEqual(result.biz_code, 19021)
        self.assertFalse(result.delivered)

    @patch(POST, side_effect=requests.exceptions.ConnectionError('down'))
    def test_network_error_captured(self, post):
        result = notifications.post_webhook({'type': 'wechat', 'webhook_url': 'https://w'}, {})
        self.assertIsInstance(result.error, requests.exceptions.ConnectionError)
        self.assertIsNone(result.status_code)
        self.assertFalse(result.delivered)


class RecipientsAndEmailTest(TestCase):
    def test_resolve_recipients_dedupes_in_order(self):
        users = [SimpleNamespace(email='a@x.com'), SimpleNamespace(email=''), SimpleNamespace(email='b@x.com')]
        self.assertEqual(notifications.resolve_recipients(users, ['b@x.com', 'c@x.com']),
                         ['a@x.com', 'b@x.com', 'c@x.com'])
        self.assertEqual(notifications.resolve_recipients(emails='d@x.com'), ['d@x.com'])
        self.assertEqual(notifications.resolve_recipients(), [])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                       DEFAULT_FROM_EMAIL='noreply@x.com')
    def test_send_email(self):
        self.assertEqual(notifications.send_email('s', 'body', ['a@x.com']), 'noreply@x.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['a@x.com'])


class CollectBotsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='notify', password='pw')

    def test_filters_by_module_flag_and_active(self):
        UnifiedNotificationConfig.objects.create(
            name='all', config_type='webhook_wechat', created_by=self.user,
            webhook_bots={'webhook_url': 'https://w', 'enable_api_testing': False},
        )
        UnifiedNotificationConfig.objects.create(
            name='inactive', config_type='webhook_feishu', created_by=self.user, is_active=False,
            webhook_bots={'webhook_url': 'https://f'},
        )
        self.assertTrue(notifications.has_active_webhook_config())
        self.assertEqual(notifications.collect_unified_webhook_bots(notifications.MODULE_API_TESTING), [])
        bots = notifications.collect_unified_webhook_bots(notifications.MODULE_UI_AUTOMATION)
        self.assertEqual([b['webhook_url'] for b in bots], ['https://w'])


class ApiNotificationManagerTest(TestCase):
    """api_testing.NotificationManager 通过 core 发送，NotificationLog 写入口径不变"""

    def setUp(self):
        from apps.api_testing.models import ScheduledTask
        self.user = User.objects.create_user(username='api_n', password='pw')
        self.task = ScheduledTask.objects.create(
            name='nightly', task_type='API_REQUEST', trigger_type='INTERVAL', interval_seconds=3600,
            status='ACTIVE', next_run_time=timezone.now() + timedelta(hours=1), created_by=self.user,
        )
        self.log = SimpleNamespace(created_at=timezone.now(), error_message='',
                                   result={'total_count': 2, 'passed_count': 2, 'failed_count': 0})

    @override_settings(SITE_BASE_URL='https://testhub.example.com')
    @patch(POST)
    def test_feishu_signed_in_body_and_biz_failure_logged(self, post):
        from apps.api_testing.models import NotificationLog
        from apps.api_testing.services.notifications import NotificationManager

        post.return_value = _response(200, {'code': 19021})
        bot = {'type': 'feishu', 'name': 'fs', 'webhook_url': 'https://open.feishu.cn/hook/x', 'secret': 's'}
        NotificationManager()._send_single_webhook(bot, self.task, self.log, '成功', True)

        sent_body = post.call_args.kwargs['json']
        self.assertEqual(sent_body['msg_type'], 'interactive')
        self.assertIn('sign', sent_body)
        self.assertEqual(post.call_args.args[0], 'https://open.feishu.cn/hook/x')
        log = NotificationLog.objects.get(task=self.task)
        self.assertEqual(log.status, 'failed')
        self.assertIn('"sign"', log.notification_content)

    @override_settings(SITE_BASE_URL='https://testhub.example.com')
    @patch(POST, side_effect=requests.exceptions.Timeout('slow'))
    def test_network_error_logged_as_failed(self, post):
        from apps.api_testing.models import NotificationLog
        from apps.api_testing.services.notifications import NotificationManager

        bot = {'type': 'dingtalk', 'name': 'dd', 'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=1',
               'secret': 's'}
        NotificationManager()._send_single_webhook(bot, self.task, self.log, '成功', True)
        self.assertIn('&sign=', post.call_args.args[0])
        log = NotificationLog.objects.get(task=self.task)
        self.assertEqual((log.status, log.error_message), ('failed', 'slow'))


class UiTaskNotificationTest(TestCase):
    """ui_automation 定时任务通知不再借用 ViewSet 实例，改走 tasks.send_task_notification"""

    def setUp(self):
        from apps.ui_automation.models import UiProject, UiScheduledTask
        self.user = User.objects.create_user(username='ui_n', password='pw')
        project = UiProject.objects.create(name='p', owner=self.user)
        self.task = UiScheduledTask.objects.create(
            name='ui-nightly', task_type='TEST_CASE', trigger_type='INTERVAL', interval_seconds=3600,
            status='ACTIVE', next_run_time=timezone.now() + timedelta(hours=1), project=project,
            created_by=self.user, test_cases=[1], notify_on_success=True, notification_type='both',
            notify_emails=['qa@x.com', 'qa@x.com'], last_run_time=timezone.now(),
            last_result={'success_count': 1, 'failed_count': 0},
        )
        UnifiedNotificationConfig.objects.create(
            name='dd', config_type='webhook_dingtalk', created_by=self.user,
            webhook_bots={'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=1', 'secret': 's'},
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    @patch(POST)
    def test_webhook_and_email_sent_and_logged(self, post):
        from apps.ui_automation.models import UiNotificationLog
        from apps.ui_automation.tasks import send_task_notification

        post.return_value = _response(200, {'errcode': 0}, text='{"errcode":0}')
        send_task_notification(self.task, success=True)

        self.assertEqual(post.call_count, 1)
        self.assertIn('&sign=', post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs['json']['msgtype'], 'actionCard')
        logs = UiNotificationLog.objects.filter(task=self.task).order_by('id')
        self.assertEqual([(l.sender_name, l.status) for l in logs],
                         [('系统Webhook通知', 'success'), ('系统邮件通知', 'success')])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['qa@x.com'])

    @patch(POST)
    def test_skipped_when_success_notification_disabled(self, post):
        from apps.ui_automation.tasks import send_task_notification

        self.task.notify_on_success = False
        send_task_notification(self.task, success=True)
        post.assert_not_called()

    @patch(POST, return_value=_response(500, text='oops'))
    def test_http_error_logged_failed(self, post):
        from apps.ui_automation.models import UiNotificationLog
        from apps.ui_automation.tasks import send_task_notification

        self.task.notification_type = 'webhook'
        send_task_notification(self.task, success=True)
        log = UiNotificationLog.objects.get(task=self.task)
        self.assertEqual((log.status, log.error_message), ('failed', 'HTTP 500: oops'))

    def test_viewset_method_delegates(self):
        from apps.ui_automation.views import UiScheduledTaskViewSet

        with patch('apps.ui_automation.tasks.send_task_notification') as send:
            UiScheduledTaskViewSet()._send_task_notification(self.task, False)
        send.assert_called_once_with(self.task, False)
