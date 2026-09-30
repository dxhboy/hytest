"""通用 DRF 权限类"""
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsStaffOrReadOnly(BasePermission):
    """全局配置类资源：登录用户可读，写操作仅限管理员（is_staff）

    视图可通过 `read_only_actions` 声明不修改数据的 POST 动作（如用已保存配置测试连接），
    这些动作对普通用户开放。
    """
    message = '仅管理员可以修改全局配置'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if getattr(view, 'action', None) in getattr(view, 'read_only_actions', ()):
            return True
        return bool(request.user and request.user.is_staff)
