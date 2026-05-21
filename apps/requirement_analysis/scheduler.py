import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler = None


def check_due_tasks():
    """每分钟调用一次，检查当前时间是否有需要触发的定时生成任务。"""
    from .models import ScheduledGenerationTask
    from .views import run_generation_for_document
    from django.utils import timezone

    now = timezone.localtime(timezone.now())
    current_hm = now.strftime('%H:%M')

    due_tasks = ScheduledGenerationTask.objects.filter(
        is_active=True,
        last_run_status__in=['pending', 'success', 'failed'],
    )

    for task in due_tasks:
        task_hm = task.scheduled_time.strftime('%H:%M')
        if task_hm != current_hm:
            continue
        # 今天已经跑过则跳过
        if task.last_run_at and task.last_run_at.date() == now.date():
            continue

        logger.info(f"触发定时生成任务: id={task.pk}, name={task.name}")
        task.last_run_status = 'running'
        task.last_run_at = timezone.now()
        task.save(update_fields=['last_run_status', 'last_run_at'])

        try:
            gen_task = run_generation_for_document(
                document_id=task.requirement_document_id,
                ai_model_config_id=task.ai_model_config_id,
                created_by_id=task.created_by_id,
            )
            task.last_run_task = gen_task
            task.last_run_status = 'success'
            task.save(update_fields=['last_run_task', 'last_run_status'])
        except Exception as e:
            logger.error(f"定时任务 {task.pk} 执行失败: {e}")
            task.last_run_status = 'failed'
            task.save(update_fields=['last_run_status'])


def start_scheduler():
    """启动 APScheduler，每分钟执行一次 check_due_tasks。"""
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler

    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        check_due_tasks,
        trigger='interval',
        minutes=1,
        id='check_due_generation_tasks',
        replace_existing=True,
        misfire_grace_time=30,
    )
    _scheduler.start()
    logger.info("ScheduledGeneration APScheduler started")
