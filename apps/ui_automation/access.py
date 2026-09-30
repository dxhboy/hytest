"""UI 自动化项目级数据访问控制：用户只能访问自己负责或参与的 UiProject 下的数据"""
from django.db.models import Q


def accessible_ui_project_ids(user):
    """用于 `project_id__in=` 子查询"""
    from .models import UiProject

    if not user or not user.is_authenticated:
        return UiProject.objects.none().values('id')
    return UiProject.objects.filter(Q(owner=user) | Q(members=user)).values('id')


def ensure_ui_project_access(user, project):
    """写入前校验项目归属；project 可为 UiProject 实例或主键"""
    from rest_framework.exceptions import PermissionDenied
    from .models import UiProject

    project_id = getattr(project, 'pk', project)
    if not UiProject.objects.filter(pk=project_id, pk__in=accessible_ui_project_ids(user)).exists():
        raise PermissionDenied('无权限访问该项目')
