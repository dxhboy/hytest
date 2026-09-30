"""API 测试模块的数据可见性规则

项目可见：项目公开（visibility='all'），或本人是负责人/成员。
项目下的资源（接口、套件、定时任务…）可见：本人创建，或资源公开 **且** 所属项目可见。
只看资源自身的 visibility 会让私有项目里标为"公开"的资源泄露给所有人。
"""
from django.db.models import Q

from .models import ApiProject


def visible_api_project_ids(user):
    return ApiProject.objects.filter(
        Q(visibility='all') | Q(owner=user) | Q(members=user)
    ).values('id')


def _p(prefix, field):
    return f'{prefix}{field}'


def visible_request_q(user, prefix=''):
    """ApiRequest；未归属集合的接口没有项目，仅按自身可见性判断"""
    return Q(**{_p(prefix, 'created_by'): user}) | (
        Q(**{_p(prefix, 'visibility'): 'all'}) & (
            Q(**{_p(prefix, 'collection__project_id__in'): visible_api_project_ids(user)})
            | Q(**{_p(prefix, 'collection__isnull'): True})
        )
    )


def visible_suite_q(user, prefix=''):
    """TestSuite"""
    return Q(**{_p(prefix, 'created_by'): user}) | (
        Q(**{_p(prefix, 'visibility'): 'all'})
        & Q(**{_p(prefix, 'project_id__in'): visible_api_project_ids(user)})
    )


def visible_scheduled_task_q(user):
    """ScheduledTask：所属项目取自关联的套件或接口"""
    pids = visible_api_project_ids(user)
    return Q(created_by=user) | (
        Q(visibility='all') & (
            Q(test_suite__project_id__in=pids)
            | Q(api_request__collection__project_id__in=pids)
            | Q(test_suite__isnull=True, api_request__collection__isnull=True)
        )
    )
