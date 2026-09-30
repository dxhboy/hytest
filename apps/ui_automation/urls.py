from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UiProjectViewSet,
    LocatorStrategyViewSet,
    ElementGroupViewSet,
    ElementViewSet,
    TestScriptViewSet,
    PageObjectViewSet,
    ScriptStepViewSet,
    TestSuiteViewSet,
    TestExecutionViewSet,
    TestCaseViewSet,
    TestCaseStepViewSet,
    TestCaseExecutionViewSet,
    UiScheduledTaskViewSet,
    AIExecutionRecordViewSet,
    AICaseViewSet,
    UiNotificationLogViewSet,
    OperationRecordViewSet,
    UiDashboardViewSet,
    RemoteBrowserServiceViewSet,
    UiProjectParameterViewSet,
)
from .views_config import EnvironmentConfigViewSet, AIIntelligentModeConfigViewSet
from .recording_views import (
    start_recording, stop_recording, get_match_results,
    confirm_recording, cancel_recording,
)

router = DefaultRouter()
router.register(r'dashboard', UiDashboardViewSet, basename='dashboard')
router.register(r'projects', UiProjectViewSet)
router.register(r'locator-strategies', LocatorStrategyViewSet)
router.register(r'element-groups', ElementGroupViewSet)
router.register(r'elements', ElementViewSet)
router.register(r'test-scripts', TestScriptViewSet)
router.register(r'page-objects', PageObjectViewSet)
router.register(r'steps', ScriptStepViewSet)
router.register(r'test-suites', TestSuiteViewSet)
router.register(r'test-executions', TestExecutionViewSet)
router.register(r'test-cases', TestCaseViewSet)
router.register(r'test-case-steps', TestCaseStepViewSet)
router.register(r'test-case-executions', TestCaseExecutionViewSet)
router.register(r'scheduled-tasks', UiScheduledTaskViewSet)
router.register(r'ai-execution-records', AIExecutionRecordViewSet)
router.register(r'ai-cases', AICaseViewSet, basename='ai-cases')
router.register(r'ai-case-generation', AICaseViewSet, basename='ai-case-generation')
router.register(r'notification-logs', UiNotificationLogViewSet)
router.register(r'operation-records', OperationRecordViewSet)
router.register(r'remote-browser-services', RemoteBrowserServiceViewSet, basename='remote-browser-services')
router.register(r'project-parameters', UiProjectParameterViewSet, basename='project-parameters')


# Configuration Center APIs
router.register(r'config/environment', EnvironmentConfigViewSet, basename='config-environment')
router.register(r'config/ai-mode', AIIntelligentModeConfigViewSet, basename='config-ai-mode')
router.register(r'ai-models', AIIntelligentModeConfigViewSet, basename='ai-models')

urlpatterns = [
    path('recording/start/', start_recording, name='recording-start'),
    path('recording/<int:session_id>/stop/', stop_recording, name='recording-stop'),
    path('recording/<int:session_id>/match-results/', get_match_results, name='recording-match-results'),
    path('recording/<int:session_id>/confirm/', confirm_recording, name='recording-confirm'),
    path('recording/<int:session_id>/cancel/', cancel_recording, name='recording-cancel'),
    path('', include(router.urls)),
]
# 媒体文件统一由 backend/urls.py 按 SERVE_MEDIA 配置提供