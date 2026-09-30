"""
UI 自动化视图包。

原 apps/ui_automation/views.py（约 2800 行）按业务域拆分为本包下的多个模块，
这里统一 re-export，保证 `from .views import XxxViewSet`（urls.py 等）继续可用。
配置中心视图（views_config.py）和录制视图（recording_views.py）仍在原位置，不在本包内。
"""
from ..ai_execution_helpers import extract_step_info
from .common import StandardPagination
from .projects import UiProjectViewSet, UiProjectParameterViewSet, RemoteBrowserServiceViewSet
from .elements import (
    LocatorStrategyViewSet, ElementViewSet, ElementGroupViewSet,
    PageObjectViewSet, PageObjectElementViewSet,
)
from .scripts import ScriptStepViewSet, ScriptElementUsageViewSet, TestScriptViewSet
from .suites import TestSuiteViewSet
from .executions import TestExecutionViewSet
from .cases import TestCaseViewSet, TestCaseStepViewSet, TestCaseExecutionViewSet
from .operation_records import OperationRecordViewSet
from .scheduled import UiScheduledTaskViewSet, UiNotificationLogViewSet, UiTaskNotificationSettingViewSet
from .ai import AICaseViewSet, AIExecutionRecordViewSet
from .dashboard import UiDashboardViewSet

__all__ = [
    'extract_step_info', 'StandardPagination',
    'UiProjectViewSet', 'UiProjectParameterViewSet', 'RemoteBrowserServiceViewSet',
    'LocatorStrategyViewSet', 'ElementViewSet', 'ElementGroupViewSet',
    'PageObjectViewSet', 'PageObjectElementViewSet',
    'ScriptStepViewSet', 'ScriptElementUsageViewSet', 'TestScriptViewSet',
    'TestSuiteViewSet', 'TestExecutionViewSet',
    'TestCaseViewSet', 'TestCaseStepViewSet', 'TestCaseExecutionViewSet',
    'OperationRecordViewSet',
    'UiScheduledTaskViewSet', 'UiNotificationLogViewSet', 'UiTaskNotificationSettingViewSet',
    'AICaseViewSet', 'AIExecutionRecordViewSet',
    'UiDashboardViewSet',
]
