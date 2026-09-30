"""项目级数据访问控制

所有按项目归属的数据都应通过这里的函数过滤，保证用户只能访问自己负责或参与的项目。
"""
from django.db.models import Q

from .models import Project

# 可修改项目本身（名称、成员、环境等）的成员角色
PROJECT_MANAGER_ROLES = ('owner', 'admin')


def accessible_projects(user):
    """用户负责或参与的项目"""
    if not user or not user.is_authenticated:
        return Project.objects.none()
    return Project.objects.filter(Q(owner=user) | Q(members=user)).distinct()


def accessible_project_ids(user):
    """用于 `xxx__in=` 子查询，避免 JOIN members 后产生重复行"""
    return accessible_projects(user).values('id')


def can_manage_project(user, project):
    """项目负责人或 owner/admin 角色成员可管理项目"""
    if not user or not user.is_authenticated:
        return False
    if project.owner_id == user.id:
        return True
    return project.projectmember_set.filter(user=user, role__in=PROJECT_MANAGER_ROLES).exists()


def can_access_project(user, project_id):
    return accessible_projects(user).filter(id=project_id).exists()


def ensure_project_access(user, project):
    """写入数据前校验项目归属；project 可为 None / Project 实例 / 主键"""
    if project in (None, ''):
        return
    project_id = getattr(project, 'pk', project)
    if not can_access_project(user, project_id):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied('无权限访问该项目')


def project_or_owner_q(user, project_field, owner_field):
    """可选项目的数据：属于可访问项目，或未关联项目但由本人创建"""
    return Q(**{f'{project_field}__in': accessible_project_ids(user)}) | Q(
        **{f'{project_field}__isnull': True, owner_field: user}
    )
