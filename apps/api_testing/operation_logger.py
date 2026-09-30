"""
操作记录工具
用于记录用户在API测试模块中的各种操作
"""
import logging

from .models import OperationLog

logger = logging.getLogger(__name__)


def resolve_project_id(resource_type, resource_id, models=None):
    """根据资源类型和 ID 推算所属 ApiProject；无法确定（全局资源、已删除）时返回 None

    models: 可选的模型提供者（数据迁移里传 apps.get_model），默认使用当前模型
    """
    def get_model(name):
        if models is not None:
            return models('api_testing', name)
        from . import models as api_models
        return getattr(api_models, name)

    lookups = {
        'project': ('ApiProject', 'id'),
        'collection': ('ApiCollection', 'project_id'),
        'request': ('ApiRequest', 'collection__project_id'),
        'suite': ('TestSuite', 'project_id'),
        'environment': ('Environment', 'project_id'),
        'execution': ('TestExecution', 'test_suite__project_id'),
    }
    try:
        if resource_type == 'task':
            row = get_model('ScheduledTask').objects.filter(pk=resource_id).values(
                'test_suite__project_id', 'api_request__collection__project_id'
            ).first()
            return (row['test_suite__project_id'] or row['api_request__collection__project_id']) if row else None
        if resource_type not in lookups:
            return None
        model_name, field = lookups[resource_type]
        return get_model(model_name).objects.filter(pk=resource_id).values_list(field, flat=True).first()
    except Exception as e:
        logger.warning(f"推算操作日志所属项目失败: {resource_type}#{resource_id}: {e}")
        return None


def log_operation(operation_type, resource_type, resource_id, resource_name, user, description=None, project_id=None):
    """
    记录用户操作

    Args:
        operation_type: 操作类型 (create, edit, delete, execute, run, save)
        resource_type: 资源类型 (project, collection, request, suite, environment, task, execution)
        resource_id: 资源ID
        resource_name: 资源名称
        user: 操作用户
        description: 操作描述(可选,如果不提供会自动生成)
        project_id: 所属项目(可选,不提供时按资源自动推算；删除操作需在删除前调用)
    """
    if description is None:
        # 自动生成描述
        operation_text = dict(OperationLog.OPERATION_TYPE_CHOICES).get(operation_type, operation_type)
        resource_text = dict(OperationLog.RESOURCE_TYPE_CHOICES).get(resource_type, resource_type)
        description = f"{operation_text}{resource_text}「{resource_name}」"

    try:
        if project_id is None:
            project_id = resolve_project_id(resource_type, resource_id)
        OperationLog.objects.create(
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            description=description,
            user=user,
            project_id=project_id,
        )
    except Exception as e:
        # 记录操作日志失败不应影响主要业务逻辑
        logger.error(f"记录操作日志失败: {e}")
