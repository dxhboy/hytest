"""
API测试视图模块

按业务域拆分为子模块，此处统一导出，保持 `from apps.api_testing.views import ...` 兼容。
"""
from .base import StandardPagination, BaseViewSetMixin
from .projects import ApiProjectViewSet, ApiCollectionViewSet
from .api_requests import ApiRequestViewSet, RequestHistoryViewSet
from .environments import EnvironmentViewSet
from .suites import TestSuiteViewSet, TestSuiteRequestViewSet
from .executions import TestExecutionViewSet
from .users import UserViewSet
from .scheduled import (
    ScheduledTaskViewSet, TaskExecutionLogViewSet,
    NotificationLogViewSet, TaskNotificationSettingViewSet,
)
from .operation_logs import OperationLogViewSet
from .dashboard import ApiDashboardViewSet
from .ai import AIServiceConfigViewSet

# 兼容旧导入路径：以下对象已迁移到 services 层
from ..services.masking import _mask_sensitive_data
from ..services.request_executor import RequestExecutor
from ..services.notifications import NotificationManager

__all__ = [
    'StandardPagination', 'BaseViewSetMixin',
    'ApiProjectViewSet', 'ApiCollectionViewSet',
    'ApiRequestViewSet', 'RequestHistoryViewSet',
    'EnvironmentViewSet',
    'TestSuiteViewSet', 'TestSuiteRequestViewSet',
    'TestExecutionViewSet',
    'UserViewSet',
    'ScheduledTaskViewSet', 'TaskExecutionLogViewSet',
    'NotificationLogViewSet', 'TaskNotificationSettingViewSet',
    'OperationLogViewSet',
    'ApiDashboardViewSet',
    'AIServiceConfigViewSet',
    '_mask_sensitive_data', 'RequestExecutor', 'NotificationManager',
]


