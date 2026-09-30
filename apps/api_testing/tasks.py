"""API 测试模块的 Celery 任务：定时任务调度与执行

原来由 run_all_scheduled_tasks 命令轮询 + ScheduledTaskViewSet._execute_task_async 裸线程执行，
现在统一由 Celery Beat 触发 dispatch_due_api_tasks，执行放到 worker 中。
"""
import logging
import os

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _generate_allure_report(execution_id):
    """为套件执行生成 Allure 报告，确保通知里的报告链接可访问"""
    from .models import TestExecution
    from .services import allure_report

    execution = TestExecution.objects.get(id=execution_id)
    results_dir = os.path.join(settings.MEDIA_ROOT, 'allure-results', f'execution_{execution.id}')
    report_dir = os.path.join(settings.MEDIA_ROOT, 'allure-reports', f'execution_{execution.id}')
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)
    allure_report.generate_test_result_files(execution, results_dir)
    allure_report.generate_allure_report_with_fallback(execution, results_dir, report_dir)
    allure_report.generate_summary_html(execution, report_dir)


def execute_scheduled_task(task_id, execution_log_id):
    """执行一次 API 定时任务并记录日志、统计、通知"""
    from .models import ScheduledTask, TaskExecutionLog
    from .utils import execute_api_request, execute_test_suite
    from .services.notifications import NotificationManager

    task = ScheduledTask.objects.get(id=task_id)
    execution_log = TaskExecutionLog.objects.get(id=execution_log_id)

    success = True
    try:
        execution_log.status = 'RUNNING'
        execution_log.start_time = timezone.now()
        execution_log.save()

        if task.task_type == 'TEST_SUITE':
            result = execute_test_suite(task.test_suite, task.environment, task.created_by)
        elif task.task_type == 'API_REQUEST':
            result = execute_api_request(task.api_request, task.environment, task.created_by)
        else:
            raise ValueError(f"未知的任务类型: {task.task_type}")

        execution_log.status = 'COMPLETED'
        execution_log.end_time = timezone.now()
        execution_log.result = result
        execution_log.save()

        task.update_run_stats(success=True)
        task.last_result = result
        task.save()
    except Exception as e:
        success = False
        logger.error(f"API 定时任务 {task_id} 执行失败: {e}", exc_info=True)
        execution_log.status = 'FAILED'
        execution_log.end_time = timezone.now()
        execution_log.error_message = str(e)
        execution_log.save()

        task.update_run_stats(success=False)
        task.error_message = str(e)
        task.save()

    # 失败时也尝试生成报告（可能有部分结果数据）
    result = execution_log.result or {}
    if task.task_type == 'TEST_SUITE' and result.get('execution_id'):
        try:
            _generate_allure_report(result['execution_id'])
            logger.info(f"自动生成Allure报告成功: execution_{result['execution_id']}")
        except Exception as report_err:
            logger.warning(f"自动生成Allure报告失败（不影响通知发送）: {report_err}")

    NotificationManager().send_notification(task, execution_log, success=success)


@shared_task(name='api_testing.run_scheduled_task', ignore_result=True)
def run_scheduled_task(task_id, execution_log_id):
    execute_scheduled_task(task_id, execution_log_id)


def enqueue_scheduled_task(task, executed_by=None):
    """创建执行日志并提交到任务队列，返回执行日志"""
    from .models import TaskExecutionLog

    execution_log = TaskExecutionLog.objects.create(task=task, status='PENDING', executed_by=executed_by)
    try:
        run_scheduled_task.delay(task.id, execution_log.id)
    except Exception as e:
        execution_log.status = 'FAILED'
        execution_log.error_message = f'提交到任务队列失败，请检查 Redis/Celery 是否启动: {e}'
        execution_log.save(update_fields=['status', 'error_message'])
        raise
    return execution_log


@shared_task(name='api_testing.execute_test_suite', ignore_result=True)
def execute_test_suite_task(execution_id, user_id=None):
    """
    手动执行测试套件（原 TestSuiteViewSet.execute 在 HTTP 请求内同步执行，现放到 worker）
    执行记录由接口预先创建，这里负责执行并更新状态，前端轮询执行详情获取结果。
    """
    from django.contrib.auth import get_user_model
    from .models import TestExecution
    from .operation_logger import log_operation
    from .utils import run_suite_execution

    try:
        execution = TestExecution.objects.select_related('test_suite', 'test_suite__environment').get(id=execution_id)
    except TestExecution.DoesNotExist:
        logger.error(f"[API] 套件执行记录不存在: execution_id={execution_id}")
        return

    user = get_user_model().objects.filter(id=user_id).first() if user_id else None
    test_suite = execution.test_suite

    try:
        run_suite_execution(execution, test_suite.environment, user or execution.executed_by)
    except Exception as e:
        # run_suite_execution 已把执行记录标记为 FAILED
        logger.error(f"[API] 套件执行失败: execution_id={execution_id}, error={e}", exc_info=True)
        return

    if user:
        log_operation(
            operation_type='execute',
            resource_type='suite',
            resource_id=test_suite.id,
            resource_name=test_suite.name,
            user=user
        )


def enqueue_suite_execution(test_suite, user):
    """
    创建套件执行记录（PENDING，worker 开始执行时置为 RUNNING）并提交到 Celery；
    提交失败（如 broker 未启动）时把执行记录标记为 FAILED 并写入明确的错误信息，返回执行记录。
    """
    from .models import TestExecution

    execution = TestExecution.objects.create(
        test_suite=test_suite,
        status='PENDING',
        total_requests=test_suite.testsuiterequest_set.filter(enabled=True).count(),
        executed_by=user
    )
    try:
        execute_test_suite_task.delay(execution.id, user.id if user else None)
    except Exception as e:
        logger.error(f"[API] 提交套件执行任务失败: execution_id={execution.id}, error={e}", exc_info=True)
        message = f'提交到任务队列失败，请检查 Redis/Celery 是否启动: {e}'
        execution.status = 'FAILED'
        execution.end_time = timezone.now()
        execution.results = [{'error': message}]
        execution.save(update_fields=['status', 'end_time', 'results'])
    return execution


@shared_task(name='api_testing.dispatch_due_tasks', ignore_result=True)
def dispatch_due_tasks():
    """由 Celery Beat 每分钟触发：提交所有到期的 API 定时任务"""
    from .models import ScheduledTask

    now = timezone.now()
    dispatched = 0
    for task in ScheduledTask.objects.filter(status='ACTIVE', next_run_time__lte=now):
        # 提交前先把 next_run_time 推到下一周期（条件更新抢占），
        # 执行耗时超过调度间隔或多个调度器并存时都不会重复触发
        claimed = ScheduledTask.objects.filter(
            pk=task.pk, status='ACTIVE', next_run_time=task.next_run_time
        ).update(next_run_time=task.calculate_next_run())
        if not claimed:
            continue
        try:
            enqueue_scheduled_task(task)
            dispatched += 1
            logger.info(f"[API] 定时任务已提交: {task.name}")
        except Exception as e:
            logger.error(f"[API] 提交定时任务 {task.name} 失败: {e}", exc_info=True)
    return dispatched
