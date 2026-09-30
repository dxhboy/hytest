"""AI 测试用例生成流水线：生成 → 评审 → 根据评审改进

由 Celery 任务 `requirement_analysis.run_generation` 调用；手动创建（TestCaseGenerationTaskViewSet.generate）
和定时生成（ScheduledGenerationTask）共用同一份实现。
"""
import asyncio
import logging

from asgiref.sync import sync_to_async
from django.utils import timezone

from .models import AIModelService, GenerationConfig, TestCaseGenerationTask

logger = logging.getLogger(__name__)


def enqueue_generation(task):
    """提交生成任务到 Celery；broker 不可用时直接把任务标记为失败，避免前端一直等待"""
    from .tasks import run_generation_task
    try:
        run_generation_task.delay(task.task_id)
    except Exception as e:
        logger.error(f"提交生成任务 {task.task_id} 到任务队列失败: {e}", exc_info=True)
        task.status = 'failed'
        task.error_message = f'提交到任务队列失败，请检查 Redis/Celery 是否启动: {e}'
        task.save(update_fields=['status', 'error_message'])


def _normalized(cases):
    """按用例编号排序并重新编号，使编号连续"""
    return AIModelService.renumber_test_cases(AIModelService.sort_test_cases_by_id(cases))


def _chunk_saver(task, field, threshold, min_chunk):
    """构造流式回调：把 chunk 追加到 task.<field>，按阈值节流写库"""
    def save(content):
        setattr(task, field, content)
        task.save(update_fields=[field])

    async_save = sync_to_async(save)

    async def callback(chunk):
        content = (getattr(task, field) or '') + chunk
        setattr(task, field, content)
        if len(content) % threshold < 20 or len(chunk) > min_chunk:
            try:
                await async_save(content)
            except Exception as save_error:
                logger.warning(f"保存 {field} 失败: {save_error}")

    return callback


def _generate(task, loop):
    task.progress = 30
    if task.output_mode != 'stream':
        task.save()
        return loop.run_until_complete(AIModelService.generate_test_cases(task))

    task.stream_buffer = ''
    task.stream_position = 0
    task.save()

    def save_stream_buffer(content):
        task.stream_buffer = content
        task.stream_position = len(content)
        task.last_stream_update = timezone.now()
        task.save(update_fields=['stream_buffer', 'stream_position', 'last_stream_update'])

    async_save = sync_to_async(save_stream_buffer)

    async def stream_callback(chunk):
        task.stream_buffer += chunk
        task.stream_position = len(task.stream_buffer)
        task.last_stream_update = timezone.now()
        # 每 ~500 字符或 chunk 较大时保存一次
        if task.stream_position % 500 < 20 or len(chunk) > 100:
            try:
                await async_save(task.stream_buffer)
            except Exception as save_error:
                logger.warning(f"保存流式内容失败: {save_error}")

    generated = loop.run_until_complete(
        AIModelService.generate_test_cases_stream(task, callback=stream_callback)
    )
    if task.stream_buffer:
        save_stream_buffer(task.stream_buffer)
    return generated


def _review(task, loop, generated_cases):
    if task.output_mode != 'stream':
        task.review_feedback = loop.run_until_complete(
            AIModelService.review_test_cases(task, generated_cases)
        )
        return

    task.review_feedback = ''
    callback = _chunk_saver(task, 'review_feedback', threshold=100, min_chunk=50)
    loop.run_until_complete(
        AIModelService.review_test_cases_stream(task, generated_cases, callback=callback)
    )
    task.save(update_fields=['review_feedback'])


def _revise(task, loop, generated_cases, review_timeout):
    task.status = 'revising'
    task.progress = 85
    task.final_test_cases = ''  # 清空，准备流式写入
    task.save()

    callback = _chunk_saver(task, 'final_test_cases', threshold=100, min_chunk=50)
    try:
        try:
            revised = loop.run_until_complete(asyncio.wait_for(
                AIModelService.revise_test_cases_based_on_review(
                    task, generated_cases, task.review_feedback, callback=callback
                ),
                timeout=review_timeout,
            ))
        except asyncio.TimeoutError:
            logger.error(f"任务 {task.task_id} 改进阶段超时（{review_timeout}秒），使用原始用例")
            revised = generated_cases

        if revised:
            # 以完整返回值为准（流式回调只是中间状态，可能被截断），修复末条不完整用例后排序编号
            task.final_test_cases = _normalized(AIModelService.fix_incomplete_last_case(revised))
            task.save(update_fields=['final_test_cases'])
            logger.info(f"任务 {task.task_id} 测试用例改进完成 (最终长度: {len(task.final_test_cases)})")
        else:
            logger.warning(f"任务 {task.task_id} 改进返回为空，使用流式回调保存的内容")
    except Exception as revise_error:
        logger.warning(f"任务 {task.task_id} 改进测试用例失败: {revise_error}，使用原始用例")
        task.final_test_cases = _normalized(generated_cases)
        task.save()


def _review_and_revise(task, loop, generated_cases, review_timeout):
    task.status = 'reviewing'
    task.progress = 70
    task.save()
    logger.info(f"开始评审任务 {task.task_id} (output_mode={task.output_mode})")
    try:
        _review(task, loop, generated_cases)
        logger.info(f"任务 {task.task_id} 评审完成")
    except Exception as review_error:
        logger.warning(f"任务 {task.task_id} 评审过程异常: {review_error}")
        task.review_feedback = f"评审过程出现异常: {review_error}\n\n建议：测试用例结构完整，可以使用。"
        task.final_test_cases = _normalized(generated_cases)
        task.save()
        return
    _revise(task, loop, generated_cases, review_timeout)


def run_generation_pipeline(task_id):
    """执行一个 TestCaseGenerationTask 的完整生成流程（同步阻塞，需在 worker 中调用）"""
    task = TestCaseGenerationTask.objects.get(task_id=task_id)
    if task.status in ('completed', 'cancelled'):
        logger.info(f"任务 {task_id} 状态为 {task.status}，跳过执行")
        return

    try:
        previous_loop = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        previous_loop = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        task.status = 'generating'
        task.progress = 10
        task.save()

        gen_config = GenerationConfig.get_active_config()
        enable_auto_review = gen_config.enable_auto_review if gen_config else True
        review_timeout = gen_config.review_timeout if gen_config else 120
        logger.info(f"任务 {task_id} 使用生成配置: auto_review={enable_auto_review}, review_timeout={review_timeout}s")

        generated_cases = _generate(task, loop)
        task.generated_test_cases = generated_cases
        task.progress = 60
        task.save()

        if enable_auto_review and task.reviewer_model_config and task.reviewer_prompt_config:
            _review_and_revise(task, loop, generated_cases, review_timeout)
        else:
            task.final_test_cases = _normalized(generated_cases)
            task.save()
            logger.info(f"任务 {task_id} 跳过评审，直接使用生成的测试用例")

        # 只更新状态字段，避免覆盖流式回调写入的内容
        task.refresh_from_db()
        if task.status == 'cancelled':
            logger.info(f"任务 {task_id} 已被取消，保留取消状态")
            return
        task.status = 'completed'
        task.progress = 100
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'progress', 'completed_at'])
        logger.info(f"任务 {task_id} 已完成")
    except Exception as e:
        logger.error(f"生成任务 {task_id} 执行失败: {e}", exc_info=True)
        task.status = 'failed'
        task.error_message = str(e)
        task.save(update_fields=['status', 'error_message'])
        raise
    finally:
        try:
            # 清理异步生成器，防止 "Task was destroyed but it is pending" 警告
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            logger.warning(f"Error shutting down asyncgens: {e}")
        finally:
            loop.close()
            # 恢复调用线程原有的事件循环，避免影响同线程后续代码
            asyncio.set_event_loop(previous_loop)


def run_generation_for_document(document_id: int, ai_model_config_id: int = None, created_by_id: int = None):
    """
    为指定需求文档创建用例生成任务并提交到任务队列。
    供定时任务和手动触发共用，实际执行见 run_generation_pipeline。
    返回 TestCaseGenerationTask 实例。
    """
    from .models import RequirementDocument, AIModelConfig, PromptConfig
    from django.contrib.auth import get_user_model

    User = get_user_model()

    doc = RequirementDocument.objects.get(pk=document_id)
    requirement_text = doc.extracted_text or doc.title

    writer_config = (
        AIModelConfig.objects.get(pk=ai_model_config_id)
        if ai_model_config_id
        else AIModelConfig.objects.filter(role='writer', is_active=True).first()
    )
    reviewer_config = AIModelConfig.objects.filter(role='reviewer', is_active=True).first()
    project_id = doc.project_id
    writer_prompt = PromptConfig.get_active_config('writer', project_id=project_id)
    reviewer_prompt = PromptConfig.get_active_config('reviewer', project_id=project_id)

    gen_config = GenerationConfig.get_active_config()
    output_mode = gen_config.default_output_mode if gen_config else 'stream'

    created_by = User.objects.get(pk=created_by_id) if created_by_id else doc.uploaded_by

    task = TestCaseGenerationTask.objects.create(
        title=f"[定时] {doc.title}",
        requirement_text=requirement_text,
        project_id=project_id,
        writer_model_config=writer_config,
        reviewer_model_config=reviewer_config,
        writer_prompt_config=writer_prompt,
        reviewer_prompt_config=reviewer_prompt,
        output_mode=output_mode,
        created_by=created_by,
    )
    enqueue_generation(task)
    return task
