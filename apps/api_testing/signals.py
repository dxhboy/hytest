# apps/api_testing/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.signals import request_finished
import json
import logging

from .models import ApiRequest, TestSuiteRequest

logger = logging.getLogger(__name__)


class ApiRequestChangeTracker:
    """跟踪API请求的变更"""
    _instance = None
    _changed_requests = set()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def mark_changed(self, request_id):
        """标记请求已被修改"""
        self._changed_requests.add(request_id)
        logger.info(f"标记请求 {request_id} 为已修改")

    def get_and_clear_changed(self):
        """获取并清空已修改的请求ID集合"""
        changed = self._changed_requests.copy()
        self._changed_requests.clear()
        return changed

    def has_changes(self, request_id):
        """检查请求是否有变更"""
        return request_id in self._changed_requests


tracker = ApiRequestChangeTracker()


@receiver(pre_save, sender=ApiRequest)
def track_api_request_changes(sender, instance, **kwargs):
    """跟踪API请求的变更"""
    if instance.pk:  # 更新操作
        try:
            old_instance = ApiRequest.objects.get(pk=instance.pk)

            # 检查断言是否发生变化
            old_assertions = json.dumps(old_instance.assertions, sort_keys=True)
            new_assertions = json.dumps(instance.assertions, sort_keys=True)

            if old_assertions != new_assertions:
                tracker.mark_changed(instance.pk)
                logger.info(f"请求 {instance.pk} 的断言已修改")
        except ApiRequest.DoesNotExist:
            pass


@receiver(post_save, sender=ApiRequest)
def sync_test_suite_assertions(sender, instance, **kwargs):
    """同步测试套件中的断言"""
    # 检查请求的断言是否被修改
    if tracker.has_changes(instance.pk):
        logger.info(f"开始同步请求 {instance.pk} 的断言到测试套件")

        # 查找所有引用了此请求的测试套件请求
        suite_requests = TestSuiteRequest.objects.filter(
            request=instance,
            assertions__isnull=False  # 只更新那些有自定义断言的
        ).exclude(assertions=[])

        updated_count = 0
        for suite_request in suite_requests:
            try:
                # 获取当前套件请求的断言
                current_assertions = suite_request.assertions or []

                # 检查套件请求是否有自定义断言
                # 如果有，询问是否要更新（这里我们选择保留自定义断言）
                # 如果需要强制更新，可以添加一个配置选项

                # 可选：如果套件请求的断言是直接从原始请求复制的（没有自定义修改）
                # 则自动更新
                if _is_copied_from_original(suite_request, instance):
                    # 深拷贝原始请求的断言
                    suite_request.assertions = json.loads(
                        json.dumps(instance.assertions)
                    )
                    suite_request.save(update_fields=['assertions'])
                    updated_count += 1
                    logger.info(f"更新测试套件请求 {suite_request.id} 的断言")

            except Exception as e:
                logger.error(f"更新测试套件请求 {suite_request.id} 失败: {e}")

        logger.info(f"完成同步，更新了 {updated_count} 个测试套件请求")

        # 清除标记
        tracker.get_and_clear_changed()


def _is_copied_from_original(suite_request, api_request):
    """检查套件请求的断言是否是从原始请求复制的（没有自定义修改）"""
    # 这里实现一个启发式方法来判断是否是原始断言的副本
    # 例如：检查断言是否完全相同，或者检查是否有修改标记

    # 简单实现：如果套件请求的断言与原始请求完全相同，则认为是副本
    return suite_request.assertions == api_request.assertions

# 可选：添加批量同步的action到视图集