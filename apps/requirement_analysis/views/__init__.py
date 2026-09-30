"""
需求分析模块视图包。

按领域拆分：
- documents: 需求文档、需求分析、业务需求、分析任务、上传/文本分析
- generated_cases: AI 生成测试用例
- configs: AI 模型 / 提示词 / 生成行为配置及配置状态检查
- generation_tasks: 测试用例生成任务（含 SSE 进度流）
- scheduled: 定时用例生成任务

此处统一再导出，保持 `from apps.requirement_analysis.views import ...` 的既有用法可用。
"""
from .documents import (
    RequirementDocumentViewSet,
    RequirementAnalysisViewSet,
    BusinessRequirementViewSet,
    AnalysisTaskViewSet,
    upload_and_analyze,
    analyze_text,
)
from .generated_cases import GeneratedTestCasePagination, GeneratedTestCaseViewSet
from .configs import (
    AIModelConfigViewSet,
    PromptConfigViewSet,
    GenerationConfigViewSet,
    ConfigStatusViewSet,
)
from .generation_tasks import (
    PassThroughRenderer,
    TestCaseGenerationTaskPagination,
    TestCaseGenerationTaskViewSet,
)
from .scheduled import ScheduledGenerationTaskViewSet
# 兼容旧导入路径：服务函数已迁移至 generation 模块
from ..generation import run_generation_for_document

__all__ = [
    'RequirementDocumentViewSet',
    'RequirementAnalysisViewSet',
    'BusinessRequirementViewSet',
    'AnalysisTaskViewSet',
    'upload_and_analyze',
    'analyze_text',
    'GeneratedTestCasePagination',
    'GeneratedTestCaseViewSet',
    'AIModelConfigViewSet',
    'PromptConfigViewSet',
    'GenerationConfigViewSet',
    'ConfigStatusViewSet',
    'PassThroughRenderer',
    'TestCaseGenerationTaskPagination',
    'TestCaseGenerationTaskViewSet',
    'ScheduledGenerationTaskViewSet',
    'run_generation_for_document',
]
