# apps/api_testing/signals.py
"""接口请求断言变更时，自动同步到"原样复制"了这组断言的测试套件步骤

规则：
- 套件步骤断言与请求**修改前**的断言完全一致 → 视为未自定义的副本，同步为新断言
- 套件步骤断言已被单独修改 → 保留，不覆盖
- 套件步骤断言为空 → 执行时本就回退使用请求自身断言（见 utils.run_suite_execution），无需同步
可通过 settings.API_SUITE_ASSERTION_SYNC（环境变量同名）关闭。
注意：QuerySet.update()/bulk_update() 不触发 save 信号，不会同步。
"""
import copy
import logging

from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import ApiRequest, TestSuiteRequest

logger = logging.getLogger(__name__)

_MISSING = object()


def _sync_enabled():
    return getattr(settings, 'API_SUITE_ASSERTION_SYNC', True)


@receiver(pre_save, sender=ApiRequest)
def remember_old_assertions(sender, instance, raw=False, update_fields=None, **kwargs):
    """记录修改前的断言，挂在当前实例上（不用全局状态，线程安全）"""
    instance._old_assertions = _MISSING
    if raw or not instance.pk or not _sync_enabled():
        return
    if update_fields is not None and 'assertions' not in update_fields:
        return
    old = ApiRequest.objects.filter(pk=instance.pk).values_list('assertions', flat=True).first()
    if old is not None:
        instance._old_assertions = old


@receiver(post_save, sender=ApiRequest)
def sync_test_suite_assertions(sender, instance, created=False, raw=False, **kwargs):
    old_assertions = getattr(instance, '_old_assertions', _MISSING)
    instance._old_assertions = _MISSING
    if created or raw or old_assertions is _MISSING or old_assertions == instance.assertions:
        return
    if not old_assertions:
        # 原断言为空时不存在"原样复制"的非空副本
        return

    updated = 0
    for suite_request in TestSuiteRequest.objects.filter(request=instance).exclude(assertions=[]):
        if suite_request.assertions != old_assertions:
            continue  # 已单独自定义，保留
        suite_request.assertions = copy.deepcopy(instance.assertions)
        suite_request.save(update_fields=['assertions'])
        updated += 1
    if updated:
        logger.info(f"请求 {instance.pk} 的断言已变更，同步更新了 {updated} 个测试套件步骤")
