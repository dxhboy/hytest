"""需求分析模块的 Celery 任务"""
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# 定时生成的触发宽限期：Beat 漏掉一两分钟（重启、阻塞）时仍能补触发，但不会在很久之后才执行
SCHEDULE_GRACE = timedelta(minutes=10)


@shared_task(name='requirement_analysis.run_generation', ignore_result=True,
             soft_time_limit=55 * 60, time_limit=60 * 60)
def run_generation_task(task_id):
    from .generation import run_generation_pipeline
    run_generation_pipeline(task_id)


@shared_task(name='requirement_analysis.dispatch_due_generation_tasks', ignore_result=True)
def dispatch_due_generation_tasks():
    """由 Celery Beat 每分钟触发：找出今天到点且尚未执行的定时生成任务并提交执行"""
    from .models import ScheduledGenerationTask
    from .generation import run_generation_for_document

    now = timezone.localtime(timezone.now())
    dispatched = 0
    for task in ScheduledGenerationTask.objects.filter(is_active=True).exclude(last_run_status='running'):
        scheduled_at = timezone.make_aware(
            datetime.combine(now.date(), task.scheduled_time), now.tzinfo
        )
        if not (scheduled_at <= now < scheduled_at + SCHEDULE_GRACE):
            continue
        if task.last_run_at and timezone.localtime(task.last_run_at).date() == now.date():
            continue

        # 条件更新抢占：多个 Beat/worker 同时检查时只有一个能成功，避免重复触发
        claimed = ScheduledGenerationTask.objects.filter(
            pk=task.pk, last_run_at=task.last_run_at
        ).exclude(last_run_status='running').update(last_run_status='running', last_run_at=timezone.now())
        if not claimed:
            continue

        logger.info(f"触发定时生成任务: id={task.pk}, name={task.name}")
        try:
            gen_task = run_generation_for_document(
                document_id=task.requirement_document_id,
                ai_model_config_id=task.ai_model_config_id,
                created_by_id=task.created_by_id,
            )
            # 生成任务已进入队列；最终结果以关联的 TestCaseGenerationTask 状态为准
            ScheduledGenerationTask.objects.filter(pk=task.pk).update(
                last_run_task=gen_task, last_run_status='success'
            )
            dispatched += 1
        except Exception as e:
            logger.error(f"定时任务 {task.pk} 执行失败: {e}", exc_info=True)
            ScheduledGenerationTask.objects.filter(pk=task.pk).update(last_run_status='failed')
    return dispatched
