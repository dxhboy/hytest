from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RequirementDocumentViewSet,
    RequirementAnalysisViewSet,
    BusinessRequirementViewSet,
    GeneratedTestCaseViewSet,
    AnalysisTaskViewSet,
    AIModelConfigViewSet,
    PromptConfigViewSet,
    GenerationConfigViewSet,
    TestCaseGenerationTaskViewSet,
    ConfigStatusViewSet,
    ScheduledGenerationTaskViewSet,
    upload_and_analyze,
    analyze_text
)
from . import jira_views

# 创建DRF路由器
router = DefaultRouter()
router.register(r'documents', RequirementDocumentViewSet, basename='requirementdocument')
router.register(r'analyses', RequirementAnalysisViewSet, basename='requirementanalysis')
router.register(r'requirements', BusinessRequirementViewSet, basename='businessrequirement')
router.register(r'test-cases', GeneratedTestCaseViewSet, basename='generatedtestcase')
router.register(r'tasks', AnalysisTaskViewSet, basename='analysistask')
router.register(r'ai-models', AIModelConfigViewSet, basename='aimodelconfig')
router.register(r'prompts', PromptConfigViewSet, basename='promptconfig')
router.register(r'generation-config', GenerationConfigViewSet, basename='generationconfig')
router.register(r'testcase-generation', TestCaseGenerationTaskViewSet, basename='testcasegenerationtask')
router.register(r'config', ConfigStatusViewSet, basename='configstatus')
router.register(r'scheduled-generation', ScheduledGenerationTaskViewSet, basename='scheduledgenerationtask')

app_name = 'requirement_analysis'

urlpatterns = [
    # DRF路由
    path('', include(router.urls)),

    # 特殊API端点
    path('upload-and-analyze/', upload_and_analyze, name='upload-and-analyze'),
    path('analyze-text/', analyze_text, name='analyze-text'),

    # Jira 集成端点
    path('jira/validate/', jira_views.jira_validate_connection, name='jira-validate'),
    path('jira/preview/', jira_views.jira_preview, name='jira-preview'),
    path('jira/import/', jira_views.jira_import, name='jira-import'),
    path('jira/issues/', jira_views.jira_issues_list, name='jira-issues-list'),
    path('jira/issues/<int:issue_id>/link-cases/', jira_views.jira_link_cases, name='jira-link-cases'),
    path('jira/issues/<int:issue_id>/unlink-cases/', jira_views.jira_unlink_cases, name='jira-unlink-cases'),
    path('jira/issues/<int:issue_id>/cases/', jira_views.jira_issue_cases, name='jira-issue-cases'),
    path('jira/recommend/', jira_views.jira_recommend, name='jira-recommend'),
]