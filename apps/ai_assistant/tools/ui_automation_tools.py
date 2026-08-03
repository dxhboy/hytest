from django.db import models as db_models


def list_ui_suites(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出 UI 自动化测试套件。"""
    from apps.ui_automation.models import TestSuite
    limit = min(limit, 50)
    qs = TestSuite.objects.filter(
        db_models.Q(visibility='all') | db_models.Q(created_by=user)
    )
    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    items = list(qs.values('id', 'name', 'description', 'execution_status',
                           'passed_count', 'failed_count')[:limit])
    return {'total': qs.count(), 'items': items}


def get_ui_suite(user, context: dict, suite_id: int):
    """获取 UI 测试套件详情。"""
    from apps.ui_automation.models import TestSuite
    try:
        suite = TestSuite.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=suite_id,
        ).values('id', 'name', 'description', 'execution_status',
                 'passed_count', 'failed_count').get()
        return suite
    except TestSuite.DoesNotExist:
        return {'error': f'套件 {suite_id} 不存在或无访问权限'}


def run_ui_suite(user, context: dict, suite_id: int):
    """触发 UI 套件执行，返回执行 ID。"""
    from apps.ui_automation.models import TestSuite, TestExecution
    try:
        suite = TestSuite.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=suite_id,
        ).get()
    except TestSuite.DoesNotExist:
        return {'error': f'套件 {suite_id} 不存在或无访问权限'}

    execution = TestExecution.objects.create(
        project=suite.project,
        test_suite=suite,
        status='pending',
        executed_by=user,
    )
    return {
        'execution_id': execution.id,
        'suite_name': suite.name,
        'status': 'pending',
        'message': f'UI 套件 "{suite.name}" 已提交执行（执行ID: {execution.id}），请稍后通过 get_ui_execution_result 查询结果。',
    }


def list_ui_elements(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出元素库。"""
    from apps.ui_automation.models import Element
    limit = min(limit, 50)
    # 只返回用户所在项目的元素（通过 project 的成员关系或负责人过滤）
    qs = Element.objects.filter(
        db_models.Q(project__members=user) | db_models.Q(project__owner=user)
    ).distinct()
    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    items = list(qs.values('id', 'name', 'element_type', 'locator_value', 'page')[:limit])
    return {'total': qs.count(), 'items': items}


def get_ui_execution_result(user, context: dict, execution_id: int):
    """查询 UI 自动化执行结果。"""
    from apps.ui_automation.models import TestExecution
    ex = TestExecution.objects.filter(
        db_models.Q(test_suite__created_by=user) | db_models.Q(executed_by=user),
        id=execution_id,
    ).values('id', 'status', 'total_cases', 'passed_cases',
             'failed_cases', 'started_at', 'finished_at', 'error_message').first()
    if not ex:
        return {'error': f'执行记录 {execution_id} 不存在或无访问权限'}
    return ex
