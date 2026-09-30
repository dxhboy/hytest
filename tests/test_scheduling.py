"""定时任务统一由 Celery Beat 调度：到期任务只被提交一次"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.api_testing.models import ScheduledTask, TaskExecutionLog
from apps.api_testing.tasks import dispatch_due_tasks as dispatch_api
from apps.ui_automation.models import UiProject, UiScheduledTask
from apps.ui_automation.tasks import dispatch_due_tasks as dispatch_ui

User = get_user_model()


class ApiDispatchTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sched', password='pw')

    def make(self, **kwargs):
        defaults = dict(
            name='t', task_type='API_REQUEST', trigger_type='INTERVAL', interval_seconds=3600,
            status='ACTIVE', next_run_time=timezone.now() - timedelta(seconds=5), created_by=self.user,
        )
        defaults.update(kwargs)
        return ScheduledTask.objects.create(**defaults)

    @patch('apps.api_testing.tasks.run_scheduled_task.delay')
    def test_due_task_dispatched_once_and_rescheduled(self, delay):
        task = self.make()
        self.assertEqual(dispatch_api(), 1)
        self.assertEqual(dispatch_api(), 0)  # 下一轮不会重复提交
        delay.assert_called_once()
        task.refresh_from_db()
        self.assertGreater(task.next_run_time, timezone.now())
        self.assertEqual(TaskExecutionLog.objects.filter(task=task, status='PENDING').count(), 1)

    @patch('apps.api_testing.tasks.run_scheduled_task.delay')
    def test_paused_and_future_tasks_skipped(self, delay):
        self.make(status='PAUSED')
        self.make(next_run_time=timezone.now() + timedelta(minutes=5))
        self.assertEqual(dispatch_api(), 0)
        delay.assert_not_called()

    @patch('apps.api_testing.tasks.run_scheduled_task.delay', side_effect=ConnectionError('redis down'))
    def test_broker_failure_marks_log_failed(self, delay):
        task = self.make()
        self.assertEqual(dispatch_api(), 0)
        log = TaskExecutionLog.objects.get(task=task)
        self.assertEqual(log.status, 'FAILED')
        self.assertIn('Redis', log.error_message)


class UiDispatchTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ui_sched', password='pw')
        self.project = UiProject.objects.create(name='p', owner=self.user)

    def make(self, **kwargs):
        defaults = dict(
            name='ui', task_type='TEST_CASE', trigger_type='INTERVAL', interval_seconds=3600,
            status='ACTIVE', next_run_time=timezone.now() - timedelta(seconds=5),
            project=self.project, created_by=self.user, test_cases=[1],
        )
        defaults.update(kwargs)
        return UiScheduledTask.objects.create(**defaults)

    @patch('apps.ui_automation.tasks.run_scheduled_task_now_task.delay')
    def test_due_task_dispatched_once(self, delay):
        task = self.make()
        self.assertEqual(dispatch_ui(), 1)
        self.assertEqual(dispatch_ui(), 0)
        delay.assert_called_once_with(task.id)
        task.refresh_from_db()
        self.assertEqual(task.total_runs, 1)
        self.assertGreater(task.next_run_time, timezone.now())

    @patch('apps.ui_automation.tasks.run_scheduled_task_now_task.delay')
    def test_missing_config_skipped_but_rescheduled(self, delay):
        task = self.make(test_cases=[])
        self.assertEqual(dispatch_ui(), 0)
        delay.assert_not_called()
        task.refresh_from_db()
        self.assertEqual(task.total_runs, 0)
        self.assertGreater(task.next_run_time, timezone.now())
