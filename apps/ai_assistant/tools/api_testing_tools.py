from django.db import models as db_models


def list_interfaces(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出用户可见的接口用例（最多 50 条）。"""
    from apps.api_testing.models import ApiRequest
    limit = min(limit, 50)
    qs = ApiRequest.objects.filter(
        db_models.Q(visibility='all') | db_models.Q(created_by=user)
    ).select_related('collection__project')

    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(collection__project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)

    items = list(qs.values('id', 'name', 'method', 'url', 'description')[:limit])
    return {'total': qs.count(), 'items': items}


def get_interface(user, context: dict, interface_id: int):
    """获取单条接口用例的详情。"""
    from apps.api_testing.models import ApiRequest
    try:
        req = ApiRequest.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=interface_id,
        ).values('id', 'name', 'method', 'url', 'description', 'headers',
                 'params', 'body', 'assertions').get()
        return req
    except ApiRequest.DoesNotExist:
        return {'error': f'接口 {interface_id} 不存在或无访问权限'}


def create_interface(user, context: dict, name: str, method: str, url: str,
                     collection_id: int = None, description: str = '',
                     headers: dict = None, params: dict = None, body: dict = None):
    """创建新接口用例。method 可选 GET/POST/PUT/DELETE/PATCH。"""
    from apps.api_testing.models import ApiRequest, ApiCollection
    collection = None
    if collection_id:
        # 只允许操作用户有权访问的集合（属于其项目）
        collection = ApiCollection.objects.filter(
            db_models.Q(project__members=user) | db_models.Q(project__owner=user),
            id=collection_id,
        ).first()
        if not collection:
            return {'error': f'集合 {collection_id} 不存在或无访问权限'}
    req = ApiRequest.objects.create(
        name=name,
        method=method.upper(),
        url=url,
        description=description,
        collection=collection,
        headers=headers or {},
        params=params or {},
        body=body or {},
        created_by=user,
        visibility='private',  # 默认私有，用户可手动改为公开
    )
    return {'id': req.id, 'name': req.name, 'method': req.method, 'url': req.url,
            'message': f'接口 "{req.name}" 创建成功'}


def list_test_suites(user, context: dict, project_id: int = None, keyword: str = None, limit: int = 20):
    """列出 api-testing 自动化测试套件。"""
    from apps.api_testing.models import TestSuite
    limit = min(limit, 50)
    qs = TestSuite.objects.filter(
        db_models.Q(visibility='all') | db_models.Q(created_by=user)
    )
    pid = project_id or (context.get('project_id') if context else None)
    if pid:
        qs = qs.filter(project_id=pid)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    items = list(qs.values('id', 'name', 'description')[:limit])
    return {'total': qs.count(), 'items': items}


def run_test_suite(user, context: dict, suite_id: int):
    """触发 api-testing 套件执行，返回执行 ID。"""
    from apps.api_testing.models import TestSuite, TestExecution
    try:
        suite = TestSuite.objects.filter(
            db_models.Q(visibility='all') | db_models.Q(created_by=user),
            id=suite_id,
        ).get()
    except TestSuite.DoesNotExist:
        return {'error': f'套件 {suite_id} 不存在或无访问权限'}

    execution = TestExecution.objects.create(
        test_suite=suite,
        status='pending',
        executed_by=user,
    )
    return {
        'execution_id': execution.id,
        'suite_name': suite.name,
        'status': 'pending',
        'message': f'套件 "{suite.name}" 已提交执行（执行ID: {execution.id}），请稍后通过 get_execution_result 查询结果。',
    }


def get_execution_result(user, context: dict, execution_id: int, module: str = 'api-testing'):
    """查询执行结果。module 为 api-testing 或 ui-automation。"""
    if module == 'ui-automation':
        from apps.ui_automation.models import TestExecution
    else:
        from apps.api_testing.models import TestExecution

    try:
        ex = TestExecution.objects.filter(
            db_models.Q(test_suite__created_by=user) | db_models.Q(executed_by=user),
            id=execution_id,
        ).values('id', 'status', 'total_requests', 'passed_requests',
                 'failed_requests', 'start_time', 'end_time').first()
        if not ex:
            raise TestExecution.DoesNotExist
        return ex
    except Exception:
        return {'error': f'执行记录 {execution_id} 不存在或无访问权限'}
