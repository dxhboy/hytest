"""AI 用例生成流水线（Celery 任务中执行）"""
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.requirement_analysis.generation import enqueue_generation, run_generation_pipeline
from apps.requirement_analysis.models import AIModelConfig, PromptConfig, TestCaseGenerationTask

User = get_user_model()
SERVICE = 'apps.requirement_analysis.generation.AIModelService'


class GenerationPipelineTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='gen', password='pw')
        self.reviewer = AIModelConfig.objects.create(name='r', model_type='deepseek', role='reviewer', created_by=user)
        self.reviewer_prompt = PromptConfig.objects.create(name='rp', prompt_type='reviewer', content='x', created_by=user)
        self.task = TestCaseGenerationTask.objects.create(
            task_id='TASK-PIPE-1', title='t', requirement_text='r', created_by=user, output_mode='complete',
            reviewer_model_config=self.reviewer, reviewer_prompt_config=self.reviewer_prompt,
        )

    def _patch_service(self, revised='REVISED'):
        async def revise(task, cases, feedback, callback=None):
            # 模拟流式回调只收到部分内容（被截断），完整内容通过返回值给出
            await callback('REV')
            return revised

        return patch.multiple(
            SERVICE,
            generate_test_cases=AsyncMock(return_value='GENERATED'),
            review_test_cases=AsyncMock(return_value='FEEDBACK'),
            revise_test_cases_based_on_review=revise,
            fix_incomplete_last_case=lambda c: c,
            sort_test_cases_by_id=lambda c: c,
            renumber_test_cases=lambda c: f'[{c}]',
        )

    def test_complete_mode_saves_full_revised_result(self):
        with self._patch_service():
            run_generation_pipeline(self.task.task_id)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'completed')
        self.assertEqual(self.task.progress, 100)
        self.assertEqual(self.task.review_feedback, 'FEEDBACK')
        # 以返回的完整内容为准，而不是流式回调写入的截断内容
        self.assertEqual(self.task.final_test_cases, '[REVISED]')

    def test_skip_review_without_reviewer(self):
        self.task.reviewer_model_config = None
        self.task.save()
        with self._patch_service():
            run_generation_pipeline(self.task.task_id)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'completed')
        self.assertEqual(self.task.final_test_cases, '[GENERATED]')

    def test_generation_failure_marks_task_failed(self):
        with patch(f'{SERVICE}.generate_test_cases', AsyncMock(side_effect=RuntimeError('llm down'))):
            with self.assertRaises(RuntimeError):
                run_generation_pipeline(self.task.task_id)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'failed')
        self.assertIn('llm down', self.task.error_message)

    def test_enqueue_failure_marks_task_failed(self):
        with patch('apps.requirement_analysis.tasks.run_generation_task.delay', side_effect=ConnectionError('x')):
            enqueue_generation(self.task)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'failed')
        self.assertIn('Redis', self.task.error_message)
