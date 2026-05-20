"""
API测试视图模块
"""
import json
import os
import time
import threading
import logging
from datetime import datetime

import requests
from django.contrib.auth import get_user_model
from django.db import models
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

# 先导入模型
from .models import (
    ApiProject, ApiCollection, ApiRequest, Environment,
    RequestHistory, TestSuite, TestExecution, TestSuiteRequest,
    ScheduledTask, TaskExecutionLog, NotificationLog,
    TaskNotificationSetting, OperationLog, AIServiceConfig,
)

# 然后导入序列化器
from .serializers import (
    ApiProjectSerializer, ApiCollectionSerializer, ApiRequestSerializer,
    EnvironmentSerializer, RequestHistorySerializer, TestSuiteSerializer,
    TestSuiteRequestSerializer, TestExecutionSerializer, UserSerializer,
    ScheduledTaskSerializer, TaskExecutionLogSerializer,
    NotificationLogSerializer, NotificationLogDetailSerializer,
    TaskNotificationSettingSerializer, TaskNotificationSettingDetailSerializer,
    OperationLogSerializer, AIServiceConfigSerializer
)

# 最后导入工具函数
from .utils import execute_assertions
from .operation_logger import log_operation
from .variable_resolver import VariableResolver, parse_and_execute_script, execute_with_response
from apps.core.variable_resolver import run_pre_request_script, run_tests_script

# 获取logger实例
logger = logging.getLogger(__name__)
User = get_user_model()


class StandardPagination(PageNumberPagination):
    """标准分页类"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000


class BaseViewSetMixin:
    """基础视图集混入类，提供通用方法"""

    def _replace_variables(self, text, variables):
        """替换文本中的变量"""
        if not isinstance(text, str):
            return text

        result = text
        for key, value in (variables or {}).items():
            if isinstance(value, dict):
                replacement = str(value.get('currentValue', '') or value.get('initialValue', ''))
            else:
                replacement = str(value) if value is not None else ''
            result = result.replace(f'{{{{{key}}}}}', replacement)
        return result

    def _replace_variables_in_dict(self, data, variables):
        """递归替换字典中的变量"""
        if isinstance(data, dict):
            return {k: self._replace_variables_in_dict(v, variables) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_variables_in_dict(item, variables) for item in data]
        elif isinstance(data, str):
            return self._replace_variables(data, variables)
        else:
            return data

    def _resolve_variables_in_dict(self, data, resolver):
        """递归解析字典中的动态函数占位符"""
        if isinstance(data, dict):
            return {k: self._resolve_variables_in_dict(v, resolver) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_variables_in_dict(item, resolver) for item in data]
        elif isinstance(data, str):
            return resolver.resolve(data)
        else:
            return data


class ApiProjectViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """API项目视图集"""
    queryset = ApiProject.objects.all()
    serializer_class = ApiProjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project_type', 'status', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name', 'start_date']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return ApiProject.objects.filter(
            models.Q(visibility='all') |
            models.Q(owner=user) |
            models.Q(members=user)
        ).distinct()

    def perform_create(self, serializer):
        """创建项目时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='create',
            resource_type='project',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_update(self, serializer):
        """更新项目时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='edit',
            resource_type='project',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_destroy(self, instance):
        """删除项目时记录日志"""
        log_operation(
            operation_type='delete',
            resource_type='project',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )
        instance.delete()

    @action(detail=False, methods=['post'], url_path='create-sample')
    def create_sample_project(self, request):
        """创建示例项目（宠物店）"""
        if ApiProject.objects.filter(name='宠物店API示例项目').exists():
            return Response({'message': '示例项目已存在'}, status=status.HTTP_400_BAD_REQUEST)

        project = ApiProject.objects.create(
            name='宠物店API示例项目',
            description='参考Apifox宠物店示例，包含用户管理、宠物管理、订单管理等接口',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=request.user,
            start_date=datetime.now().date()
        )

        self._create_sample_data(project, request.user)

        serializer = self.get_serializer(project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _create_sample_data(self, project, user):
        """创建示例数据"""
        # 用户管理集合
        user_collection = ApiCollection.objects.create(
            project=project,
            name='用户管理',
            description='用户注册、登录、信息管理相关接口',
            order=1
        )

        # 用户注册接口
        ApiRequest.objects.create(
            collection=user_collection,
            name='用户注册',
            description='新用户注册接口',
            method='POST',
            url='{{base_url}}/api/users/register',
            headers={'Content-Type': 'application/json'},
            body={
                'type': 'json',
                'data': {
                    'username': 'testuser',
                    'email': 'test@example.com',
                    'password': 'password123'
                }
            },
            created_by=user,
            order=1
        )

        # 用户登录接口
        ApiRequest.objects.create(
            collection=user_collection,
            name='用户登录',
            description='用户登录获取token',
            method='POST',
            url='{{base_url}}/api/users/login',
            headers={'Content-Type': 'application/json'},
            body={
                'type': 'json',
                'data': {
                    'username': 'testuser',
                    'password': 'password123'
                }
            },
            created_by=user,
            order=2
        )

        # 宠物管理集合
        pet_collection = ApiCollection.objects.create(
            project=project,
            name='宠物管理',
            description='宠物信息增删改查接口',
            order=2
        )

        # 获取宠物列表
        ApiRequest.objects.create(
            collection=pet_collection,
            name='获取宠物列表',
            description='分页获取宠物列表',
            method='GET',
            url='{{base_url}}/api/pets',
            headers={'Authorization': 'Bearer {{token}}'},
            params={'page': '1', 'limit': '10'},
            created_by=user,
            order=1
        )

        # 创建宠物
        ApiRequest.objects.create(
            collection=pet_collection,
            name='创建宠物',
            description='添加新宠物信息',
            method='POST',
            url='{{base_url}}/api/pets',
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer {{token}}'
            },
            body={
                'type': 'json',
                'data': {
                    'name': '小白',
                    'category': 'dog',
                    'age': 2,
                    'price': 1000
                }
            },
            created_by=user,
            order=2
        )


_SENSITIVE_KEYS = frozenset([
    'password', 'passwd', 'pwd', 'secret', 'token', 'authorization',
    'auth', 'api_key', 'apikey', 'access_token', 'refresh_token',
    'private_key', 'secret_key', 'client_secret',
])


def _mask_sensitive_data(data):
    """递归地将敏感字段值替换为 '******'"""
    if isinstance(data, dict):
        return {
            k: '******' if k.lower() in _SENSITIVE_KEYS else _mask_sensitive_data(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_sensitive_data(item) for item in data]
    return data


def _resolve_ref(spec, ref):
    """解析 $ref 引用，返回对应的 schema dict"""
    if not ref or not ref.startswith('#/'):
        return {}
    parts = ref.lstrip('#/').split('/')
    node = spec
    for part in parts:
        if not isinstance(node, dict):
            return {}
        node = node.get(part, {})
    return node or {}


def _get_sample_value(schema, spec, depth=0):
    """根据 JSON Schema 生成示例值，depth 防止循环引用"""
    if depth > 4 or not isinstance(schema, dict):
        return None
    if '$ref' in schema:
        schema = _resolve_ref(spec, schema['$ref'])
    if not schema:
        return None

    if 'enum' in schema:
        return schema['enum'][0]

    s_type = schema.get('type', 'string')
    fmt = schema.get('format', '')

    if s_type == 'integer':
        minimum = schema.get('minimum')
        return int(minimum) if minimum is not None else 1
    if s_type == 'number':
        minimum = schema.get('minimum')
        return float(minimum) if minimum is not None else 0.1
    if s_type == 'boolean':
        return True
    if s_type == 'array':
        item_val = _get_sample_value(schema.get('items', {}), spec, depth + 1)
        return [item_val] if item_val is not None else []
    if s_type == 'object':
        props = schema.get('properties', {})
        return {k: _get_sample_value(v, spec, depth + 1) for k, v in list(props.items())[:8]}

    # string
    if fmt == 'date':
        return '2024-01-01'
    if fmt == 'date-time':
        return '2024-01-01T00:00:00Z'
    if fmt == 'email':
        return 'test@example.com'
    if fmt in ('password', 'byte'):
        return 'Test@123456'
    if fmt == 'uuid':
        return '00000000-0000-0000-0000-000000000001'
    min_len = schema.get('minLength', 0)
    base = 'test'
    return base + 'x' * max(0, min_len - len(base))


def _build_body(operation, spec, is_v3, sample=True):
    """提取并构建请求 body，sample=True 时填入示例值"""
    if is_v3:
        rb = operation.get('requestBody', {})
        content = rb.get('content', {})
        if 'application/json' in content:
            body_schema = content['application/json'].get('schema', {})
            if '$ref' in body_schema:
                body_schema = _resolve_ref(spec, body_schema['$ref'])
            data = json.dumps(_get_sample_value(body_schema, spec) or {}, ensure_ascii=False, indent=2) if sample else '{}'
            return {'type': 'raw', 'rawType': 'json', 'data': data}, body_schema
        if 'multipart/form-data' in content:
            return {'type': 'form-data', 'data': []}, {}
        if 'application/x-www-form-urlencoded' in content:
            return {'type': 'x-www-form-urlencoded', 'data': []}, {}
    else:
        for param in operation.get('parameters', []):
            if param.get('in') == 'body':
                body_schema = param.get('schema', {})
                if '$ref' in body_schema:
                    body_schema = _resolve_ref(spec, body_schema['$ref'])
                data = json.dumps(_get_sample_value(body_schema, spec) or {}, ensure_ascii=False, indent=2) if sample else '{}'
                return {'type': 'raw', 'rawType': 'json', 'data': data}, body_schema
    return {}, {}


def _extract_params_meta(operation, path_item, spec, is_v3):
    """提取所有参数元信息（含 schema、是否必填）"""
    meta = []
    seen = set()
    all_params = list(path_item.get('parameters', [])) + list(operation.get('parameters', []))
    for param in all_params:
        if not isinstance(param, dict):
            continue
        if '$ref' in param:
            param = _resolve_ref(spec, param['$ref'])
        p_name = param.get('name', '')
        p_in = param.get('in', '')
        if not p_name or p_in == 'body' or (p_name, p_in) in seen:
            continue
        seen.add((p_name, p_in))
        schema = param.get('schema', {}) if is_v3 else {
            'type': param.get('type', 'string'),
            'format': param.get('format', ''),
            'enum': param.get('enum'),
            'minimum': param.get('minimum'),
            'maximum': param.get('maximum'),
            'minLength': param.get('minLength'),
            'maxLength': param.get('maxLength'),
            'default': param.get('default'),
        }
        if '$ref' in schema:
            schema = _resolve_ref(spec, schema['$ref'])
        meta.append({
            'name': p_name,
            'in': p_in,
            'required': param.get('required', p_in == 'path'),
            'description': param.get('description', ''),
            'schema': schema,
        })
    return meta


def _make_param_dict(params_meta, p_in, override=None, use_invalid_type=False):
    """把 params_meta 中指定 in 类型的参数转成 dict，override 可替换特定 key 的值"""
    result = {}
    override = override or {}
    for p in params_meta:
        if p['in'] != p_in:
            continue
        name = p['name']
        if name in override:
            result[name] = override[name]
        elif use_invalid_type and p['schema'].get('type') in ('integer', 'number'):
            result[name] = 'invalid_string'
        else:
            val = _get_sample_value(p['schema'], {})
            result[name] = str(val) if val is not None else ''
    return result


# 用例标签多语言映射（lang: 'zh' | 'en'）
CASE_LABELS = {
    'zh': {
        'normal': '正常',
        'missing_required': '异常-缺少必填',
        'boundary_exceed_max': '边界-超出最大值',
        'boundary_below_min': '边界-低于最小值',
        'boundary_exceed_maxlen': '边界-超出最大长度',
        'boundary_below_minlen': '边界-低于最小长度',
        'type_error': '异常-类型错误',
        'empty_body': '异常-空Body',
        'assert_ok': '状态码校验',
        'missing_desc': '必填参数置空: {params}',
        'exceed_max_desc': '{param} 超出最大值 {val}',
        'below_min_desc': '{param} 低于最小值 {val}',
        'exceed_maxlen_desc': '{param} 超出最大长度 {val}',
        'below_minlen_desc': '{param} 低于最小长度 {val}',
        'type_error_desc': '数值参数传入非法字符串: {params}',
        'empty_body_desc': '请求体为空',
    },
    'en': {
        'normal': 'Normal',
        'missing_required': 'Error-Missing Required',
        'boundary_exceed_max': 'Boundary-Exceed Max',
        'boundary_below_min': 'Boundary-Below Min',
        'boundary_exceed_maxlen': 'Boundary-Exceed MaxLength',
        'boundary_below_minlen': 'Boundary-Below MinLength',
        'type_error': 'Error-Type Mismatch',
        'empty_body': 'Error-Empty Body',
        'assert_ok': 'Status Code Check',
        'missing_desc': 'Required params set to empty: {params}',
        'exceed_max_desc': '{param} exceeds max {val}',
        'below_min_desc': '{param} below min {val}',
        'exceed_maxlen_desc': '{param} exceeds maxLength {val}',
        'below_minlen_desc': '{param} below minLength {val}',
        'type_error_desc': 'Numeric params passed invalid string: {params}',
        'empty_body_desc': 'Empty request body',
    },
}

# 用例分类与标签前缀的映射（用于 dry_run 中解析 case_category）
_LABEL_TO_CATEGORY = {
    'normal': 'normal',
    'missing_required': 'error',
    'boundary_exceed_max': 'boundary',
    'boundary_below_min': 'boundary',
    'boundary_exceed_maxlen': 'boundary',
    'boundary_below_minlen': 'boundary',
    'type_error': 'error',
    'empty_body': 'error',
}


def generate_test_cases(ep, spec, lang='zh'):
    """为单个 endpoint 生成正常、异常、边界值测试用例列表"""
    lb = CASE_LABELS.get(lang, CASE_LABELS['zh'])
    cases = []
    params_meta = ep['params_meta']
    method = ep['method']
    url = ep['url']
    tag = ep['tag']
    base_name = ep['name']
    desc = ep.get('description', '')
    normal_body = ep['body']
    empty_body = {'type': 'raw', 'rawType': 'json', 'data': '{}'} if normal_body.get('type') == 'raw' else {}

    required_query = [p for p in params_meta if p['in'] == 'query' and p['required']]
    required_header = [p for p in params_meta if p['in'] == 'header' and p['required']]
    numeric_params = [p for p in params_meta if p['schema'].get('type') in ('integer', 'number')]
    boundary_params = [p for p in params_meta if
                       p['schema'].get('maximum') is not None or p['schema'].get('minimum') is not None
                       or p['schema'].get('maxLength') is not None or p['schema'].get('minLength') is not None]

    normal_q = _make_param_dict(params_meta, 'query')
    normal_h = _make_param_dict(params_meta, 'header')

    def _case(label_key, name, description, query, headers, body, assertions):
        return {
            'tag': tag,
            'name': name,
            'description': description,
            'method': method,
            'url': url,
            'headers': headers,
            'params': query,
            'body': body,
            'assertions': assertions,
            'case_category': _LABEL_TO_CATEGORY.get(label_key, 'error'),
        }

    ok_assert = [{'name': lb['assert_ok'], 'type': 'status_code', 'operator': 'eq', 'expected': 200, 'enabled': True}]
    err_assert = [{'name': lb['assert_ok'], 'type': 'status_code', 'operator': 'gte', 'expected': 400, 'enabled': True}]

    # 1. 正常用例
    cases.append(_case('normal', f'[{lb["normal"]}] {base_name}', desc, normal_q, normal_h, normal_body, ok_assert))

    # 2. 缺少必填参数
    if required_query or required_header:
        miss_q = {k: '' for k in normal_q}
        miss_h = {k: '' for k in normal_h}
        req_names = [p['name'] for p in required_query + required_header]
        cases.append(_case(
            'missing_required',
            f'[{lb["missing_required"]}] {base_name}',
            lb['missing_desc'].format(params=', '.join(req_names[:4])),
            miss_q, miss_h, empty_body, err_assert
        ))

    # 3. 边界值（数值超出最大值 / 字符串超出最大长度）
    for p in boundary_params[:2]:
        schema = p['schema']
        p_in = p['in']
        p_name = p['name']
        if schema.get('maximum') is not None:
            over = schema['maximum'] + 1
            ov = {p_name: str(over)} if p_in == 'query' else {}
            oh = {p_name: str(over)} if p_in == 'header' else {}
            cases.append(_case(
                'boundary_exceed_max',
                f'[{lb["boundary_exceed_max"]}] {base_name} ({p_name}={over})',
                lb['exceed_max_desc'].format(param=p_name, val=schema['maximum']),
                {**normal_q, **ov}, {**normal_h, **oh}, normal_body, err_assert
            ))
        elif schema.get('minimum') is not None:
            under = schema['minimum'] - 1
            ov = {p_name: str(under)} if p_in == 'query' else {}
            oh = {p_name: str(under)} if p_in == 'header' else {}
            cases.append(_case(
                'boundary_below_min',
                f'[{lb["boundary_below_min"]}] {base_name} ({p_name}={under})',
                lb['below_min_desc'].format(param=p_name, val=schema['minimum']),
                {**normal_q, **ov}, {**normal_h, **oh}, normal_body, err_assert
            ))
        elif schema.get('maxLength') is not None:
            over_val = 'a' * (schema['maxLength'] + 1)
            ov = {p_name: over_val} if p_in == 'query' else {}
            cases.append(_case(
                'boundary_exceed_maxlen',
                f'[{lb["boundary_exceed_maxlen"]}] {base_name} ({p_name})',
                lb['exceed_maxlen_desc'].format(param=p_name, val=schema['maxLength']),
                {**normal_q, **ov}, normal_h, normal_body, err_assert
            ))
        elif schema.get('minLength') is not None and schema['minLength'] > 0:
            short_val = 'a' * max(0, schema['minLength'] - 1)
            ov = {p_name: short_val} if p_in == 'query' else {}
            cases.append(_case(
                'boundary_below_minlen',
                f'[{lb["boundary_below_minlen"]}] {base_name} ({p_name})',
                lb['below_minlen_desc'].format(param=p_name, val=schema['minLength']),
                {**normal_q, **ov}, normal_h, normal_body, err_assert
            ))

    # 4. 参数类型错误
    if numeric_params:
        type_err_q = _make_param_dict(params_meta, 'query', use_invalid_type=True)
        type_err_h = _make_param_dict(params_meta, 'header', use_invalid_type=True)
        err_names = [p['name'] for p in numeric_params[:3]]
        cases.append(_case(
            'type_error',
            f'[{lb["type_error"]}] {base_name}',
            lb['type_error_desc'].format(params=', '.join(err_names)),
            type_err_q, type_err_h, normal_body, err_assert
        ))

    # 5. 异常 body（有 body 的接口）
    if normal_body.get('type') == 'raw' and method in ('POST', 'PUT', 'PATCH'):
        cases.append(_case(
            'empty_body',
            f'[{lb["empty_body"]}] {base_name}',
            lb['empty_body_desc'],
            normal_q, normal_h, {'type': 'raw', 'rawType': 'json', 'data': '{}'}, err_assert
        ))

    return cases


def parse_swagger_spec(spec):
    """解析 Swagger 2.0 / OpenAPI 3.0 规范，返回 endpoint 元数据列表"""
    version = str(spec.get('openapi', spec.get('swagger', '2.0')))
    is_v3 = version.startswith('3')

    if is_v3:
        servers = spec.get('servers', [])
        base_url = (servers[0].get('url', '') if servers else '').rstrip('/')
    else:
        host = spec.get('host', '')
        base_path = spec.get('basePath', '/').rstrip('/')
        scheme = (spec.get('schemes') or ['http'])[0]
        base_url = f"{scheme}://{host}{base_path}" if host else base_path

    endpoints = []
    paths = spec.get('paths', {})
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue

            tags = operation.get('tags') or ['默认']
            tag = tags[0]
            name = (operation.get('summary') or operation.get('operationId') or
                    f'{method.upper()} {path}')
            description = operation.get('description', '')
            params_meta = _extract_params_meta(operation, path_item, spec, is_v3)
            body, _ = _build_body(operation, spec, is_v3, sample=True)

            endpoints.append({
                'tag': tag,
                'name': name,
                'description': description,
                'method': method.upper(),
                'url': base_url + path,
                'params_meta': params_meta,
                'body': body,
            })

    return endpoints, is_v3


class ApiCollectionViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """API集合视图集"""
    queryset = ApiCollection.objects.all()
    serializer_class = ApiCollectionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['project', 'parent']

    def get_queryset(self):
        user = self.request.user
        return ApiCollection.objects.filter(
            project__in=ApiProject.objects.filter(
                models.Q(visibility='all') |
                models.Q(owner=user) |
                models.Q(members=user)
            )
        ).distinct()

    def perform_create(self, serializer):
        """创建集合时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='create',
            resource_type='collection',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_update(self, serializer):
        """更新集合时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='edit',
            resource_type='collection',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def _collect_request_ids(self, collection):
        """递归收集集合及所有子集合中的接口 ID"""
        ids = list(collection.requests.values_list('id', flat=True))
        for child in collection.children.all():
            ids.extend(self._collect_request_ids(child))
        return ids

    def perform_destroy(self, instance):
        """删除集合前检查接口是否已被测试套件使用"""
        from rest_framework.exceptions import ValidationError
        all_request_ids = self._collect_request_ids(instance)
        if all_request_ids:
            used = TestSuiteRequest.objects.filter(request_id__in=all_request_ids).exists()
            if used:
                raise ValidationError('该集合中的接口已在自动化测试套件中使用，无法删除')
        log_operation(
            operation_type='delete',
            resource_type='collection',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )
        instance.delete()

    @action(detail=False, methods=['post'], url_path='import-swagger')
    def import_swagger(self, request):
        """从 Swagger/OpenAPI 规范导入接口（支持 URL 或 JSON 内容，支持 dry_run 预览，支持按模块筛选）"""
        source_type = request.data.get('source_type', 'url')
        project_id = request.data.get('project_id')
        dry_run = request.data.get('dry_run', False)
        # selected_tags: 空列表表示全部模块
        selected_tags = request.data.get('selected_tags', [])
        # update_mode: True 时更新已有用例的技术字段，False 时纯新增
        update_mode = request.data.get('update_mode', False)
        # lang: 'zh' 或 'en'，用于生成语言化的用例名称和描述
        raw_lang = request.data.get('lang', request.headers.get('Accept-Language', 'zh'))
        lang = 'en' if str(raw_lang).lower().startswith('en') else 'zh'

        if not project_id:
            return Response({'error': '请选择项目'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = ApiProject.objects.get(
                models.Q(id=project_id) &
                (models.Q(owner=request.user) | models.Q(members=request.user))
            )
        except ApiProject.DoesNotExist:
            return Response({'error': '项目不存在或无权限'}, status=status.HTTP_404_NOT_FOUND)

        # 获取 Swagger 规范
        swagger_spec = None
        if source_type == 'url':
            swagger_url = request.data.get('swagger_url', '').strip()
            if not swagger_url:
                return Response({'error': '请输入 Swagger URL'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                req_headers = {}
                token = request.data.get('token', '').strip()
                if token:
                    req_headers['Authorization'] = token if token.lower().startswith('bearer ') else f'Bearer {token}'
                resp = requests.get(swagger_url, headers=req_headers, timeout=15)
                resp.raise_for_status()
                swagger_spec = resp.json()
            except Exception as e:
                return Response({'error': f'获取 Swagger 文档失败：{str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            swagger_json = request.data.get('swagger_json')
            if not swagger_json:
                return Response({'error': '请提供 Swagger JSON 内容'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                swagger_spec = json.loads(swagger_json) if isinstance(swagger_json, str) else swagger_json
            except json.JSONDecodeError as e:
                return Response({'error': f'JSON 解析失败：{str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # 解析规范
        try:
            endpoints, is_v3 = parse_swagger_spec(swagger_spec)
        except Exception as e:
            return Response({'error': f'Swagger 解析失败：{str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        if not endpoints:
            return Response({'error': '未解析到任何接口，请确认 Swagger 文档格式正确'}, status=status.HTTP_400_BAD_REQUEST)

        # 为所有 endpoint 生成测试用例（逐个 try-except 防止单个解析失败影响全局）
        all_cases = []
        for ep in endpoints:
            try:
                all_cases.extend(generate_test_cases(ep, swagger_spec, lang=lang))
            except Exception:
                pass

        if not all_cases:
            return Response({'error': '生成测试用例失败，请检查 Swagger 文档内容'}, status=status.HTTP_400_BAD_REQUEST)

        # 收集全部 tag（供前端模块筛选用）
        all_tags = sorted({c['tag'] for c in all_cases if c.get('tag')})

        # 预览模式：返回用例列表（不入库）
        if dry_run:
            filtered = all_cases
            if selected_tags:
                filtered = [c for c in all_cases if c['tag'] in selected_tags]

            # update_mode 时预查已有请求，标记 new/update
            existing_keys = set()
            if update_mode:
                existing_keys = set(
                    ApiRequest.objects.filter(
                        collection__project=project,
                        collection__parent=None,
                    ).values_list('collection__name', 'method', 'url')
                )

            preview = []
            for c in filtered:
                action = 'update' if (c['tag'], c['method'], c['url']) in existing_keys else 'new'
                preview.append({
                    'tag': c['tag'],
                    'name': c['name'],
                    'method': c['method'],
                    'url': c['url'],
                    'case_type': c['name'].split(']')[0].lstrip('[') if ']' in c['name'] else c['name'],
                    'case_category': c.get('case_category', 'error'),
                    'action': action,
                })
            new_cnt = sum(1 for p in preview if p['action'] == 'new')
            upd_cnt = sum(1 for p in preview if p['action'] == 'update')
            return Response({
                'endpoints': preview,
                'total': len(preview),
                'all_tags': all_tags,
                'new_count': new_cnt,
                'update_count': upd_cnt,
            })

        # 入库前按 selected_tags 过滤（空列表 = 全部）
        if selected_tags:
            all_cases = [c for c in all_cases if c['tag'] in selected_tags]
        if not all_cases:
            return Response({'error': '所选模块下未找到可生成的用例'}, status=status.HTTP_400_BAD_REQUEST)

        # 入库：先批量确定所有集合，再批量创建/更新请求
        collection_map = {}
        new_count = 0
        updated_count = 0
        # 按 tag 分组 cases，保持顺序
        from collections import OrderedDict
        tag_cases = OrderedDict()
        for case in all_cases:
            tag = case['tag'] or '默认'
            tag_cases.setdefault(tag, []).append(case)

        for tag, cases in tag_cases.items():
            collection, _ = ApiCollection.objects.get_or_create(
                project=project,
                name=tag,
                parent=None,
                defaults={'order': ApiCollection.objects.filter(project=project, parent=None).count()}
            )
            collection_map[tag] = collection
            for case in cases:
                try:
                    if update_mode:
                        existing = ApiRequest.objects.filter(
                            collection=collection,
                            method=case['method'],
                            url=case['url'],
                        ).first()
                        if existing:
                            existing.headers = case.get('headers', {})
                            existing.params = case.get('params', {})
                            existing.body = case.get('body', {})
                            existing.assertions = case.get('assertions', [])
                            existing.save(update_fields=['headers', 'params', 'body', 'assertions', 'updated_at'])
                            updated_count += 1
                            continue
                    ApiRequest.objects.create(
                        collection=collection,
                        name=case['name'],
                        description=case.get('description', ''),
                        method=case['method'],
                        url=case['url'],
                        headers=case.get('headers', {}),
                        params=case.get('params', {}),
                        body=case.get('body', {}),
                        assertions=case.get('assertions', []),
                        order=ApiRequest.objects.filter(collection=collection).count(),
                        created_by=request.user,
                        request_type='HTTP',
                    )
                    new_count += 1
                except Exception:
                    pass

        if update_mode:
            message = f'新增 {new_count} 条，更新 {updated_count} 条用例，涉及 {len(collection_map)} 个集合'
        else:
            message = f'成功生成 {new_count} 条用例，涉及 {len(collection_map)} 个集合'
        return Response({
            'message': message,
            'created_requests': new_count,
            'updated_requests': updated_count,
            'created_collections': len(collection_map),
        })


class RequestExecutor:
    """请求执行器 - 封装请求执行逻辑"""

    def __init__(self, resolver=None):
        self.resolver = resolver or VariableResolver()
        self.session = requests.Session()

    def prepare_headers(self, headers, variables):
        """准备请求头"""
        result = {}
        if isinstance(headers, list):
            for header_item in headers:
                if header_item.get('enabled', True) and header_item.get('key'):
                    key = header_item['key']
                    value = self._replace_variables(str(header_item.get('value', '')), variables)
                    value = self.resolver.resolve(value)
                    result[key] = value
        else:
            headers_copy = headers.copy() if headers else {}
            for key, value in headers_copy.items():
                result[key] = self.resolver.resolve(self._replace_variables(str(value), variables))
        return result

    def prepare_params(self, params, variables):
        """准备请求参数"""
        result = {}
        if params:
            for key, value in params.items():
                result[key] = self.resolver.resolve(self._replace_variables(str(value), variables))
        return result

    def prepare_body(self, body, method, variables):
        """准备请求体"""
        logger.info(f"[DEBUG] prepare_body 原始输入: body={body}, method={method}")
        if not body or method not in ['POST', 'PUT', 'PATCH']:
            return None, 'none'

        if not isinstance(body, dict):
            return self.resolver.resolve(self._replace_variables(str(body), variables)), 'raw'

        body_type = body.get('type', 'raw')
        body_data = body.get('data', '')
        logger.info(f"[DEBUG] prepare_body 解析: body_type={body_type}, body_data={body_data}")

        if body_type == 'json':
            if isinstance(body_data, (dict, list)):
                body_data = self._replace_variables_in_dict(body_data, variables)
                body_data = self._resolve_variables_in_dict(body_data, self.resolver)
            else:
                body_str = self.resolver.resolve(self._replace_variables(str(body_data), variables))
                try:
                    body_data = json.loads(body_str)
                except json.JSONDecodeError:
                    body_data = body_str
            return body_data, body_type

        elif body_type in ['x-www-form-urlencoded', 'form-data']:
            return self._prepare_form_data(body_data, body_type, variables), body_type

        else:  # raw
            return self.resolver.resolve(self._replace_variables(str(body_data), variables)), body_type

    def _prepare_form_data(self, body_data, body_type, variables):
        """准备表单数据"""
        if isinstance(body_data, dict):
            result = {}
            for key, value in body_data.items():
                resolved_key = self.resolver.resolve(self._replace_variables(str(key), variables))
                resolved_value = self.resolver.resolve(self._replace_variables(str(value), variables))
                result[resolved_key] = resolved_value
            return result
        elif isinstance(body_data, list):
            result = {}
            for item in body_data:
                if item.get('enabled', True) and item.get('key'):
                    key = self.resolver.resolve(self._replace_variables(str(item['key']), variables))
                    value = self.resolver.resolve(self._replace_variables(str(item.get('value', '')), variables))
                    result[key] = value
            return result
        else:
            return self.resolver.resolve(self._replace_variables(str(body_data), variables))

    def execute(self, method, url, headers=None, params=None, body=None, body_type='none', timeout=30):
        """执行请求"""
        merged_headers = dict(headers or {})

        if body_type == 'json':
            # 强制 Content-Type 为 application/json，避免用户配置的 header 冲突
            merged_headers['Content-Type'] = 'application/json'
        elif body_type == 'x-www-form-urlencoded':
            # 强制 Content-Type 为 application/x-www-form-urlencoded，
            # 防止用户配置了 application/json 导致服务端解析失败（如 OAuth2 token 接口）
            merged_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        elif body_type == 'form-data':
            # multipart/form-data 的 boundary 由 requests 自动生成，不能手动设置
            merged_headers.pop('Content-Type', None)

        request_kwargs = {
            'method': method,
            'url': url,
            'headers': merged_headers,
            'params': params or {},
            'timeout': timeout
        }

        if body_type == 'json':
            request_kwargs['json'] = body
        else:
            request_kwargs['data'] = body

        logger.info(f"[DEBUG] 执行请求: {method} {url} | body_type={body_type} | body={body} | headers={merged_headers}")
        start_time = time.time()
        response = self.session.request(**request_kwargs)
        end_time = time.time()

        return response, (end_time - start_time) * 1000

    # 代理方法，保持与BaseViewSetMixin的兼容
    def _replace_variables(self, text, variables):
        if not isinstance(text, str):
            return text
        result = text
        for key, value in (variables or {}).items():
            if isinstance(value, dict):
                replacement = str(value.get('currentValue', '') or value.get('initialValue', ''))
            else:
                replacement = str(value) if value is not None else ''
            result = result.replace(f'{{{{{key}}}}}', replacement)
        return result

    def _replace_variables_in_dict(self, data, variables):
        if isinstance(data, dict):
            return {k: self._replace_variables_in_dict(v, variables) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_variables_in_dict(item, variables) for item in data]
        elif isinstance(data, str):
            return self._replace_variables(data, variables)
        else:
            return data

    def _resolve_variables_in_dict(self, data, resolver):
        if isinstance(data, dict):
            return {k: self._resolve_variables_in_dict(v, resolver) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_variables_in_dict(item, resolver) for item in data]
        elif isinstance(data, str):
            return resolver.resolve(data)
        else:
            return data


class ApiRequestViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """API请求视图集"""
    queryset = ApiRequest.objects.all()
    serializer_class = ApiRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['collection', 'method', 'request_type']
    search_fields = ['name', 'url']

    def get_queryset(self):
        user = self.request.user

        # visibility='all' 的用例对所有登录用户可见，private 仅自己可见
        queryset = ApiRequest.objects.filter(
            models.Q(visibility='all') | models.Q(created_by=user)
        ).distinct()

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(
                models.Q(collection__project_id=project_id) |
                models.Q(collection__isnull=True, created_by=user)
            ).distinct()

        return queryset

    def perform_create(self, serializer):
        """创建接口时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='create',
            resource_type='request',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_update(self, serializer):
        """更新接口时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='edit',
            resource_type='request',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_destroy(self, instance):
        """删除接口时记录日志"""
        log_operation(
            operation_type='delete',
            resource_type='request',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )
        instance.delete()

    @action(detail=False, methods=['patch'], url_path='batch-move')
    def batch_move(self, request):
        """批量移动接口到指定集合"""
        ids = request.data.get('ids', [])
        collection_id = request.data.get('collection_id')  # None 表示移到根（无集合）

        if not ids:
            return Response({'detail': '请提供要移动的接口 id 列表'}, status=400)

        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return Response({'detail': 'ids 必须为整数列表'}, status=400)

        # 只能操作本人创建的接口
        qs = ApiRequest.objects.filter(
            id__in=ids,
            created_by=request.user
        )

        if collection_id is not None:
            try:
                collection = ApiCollection.objects.get(id=collection_id)
            except ApiCollection.DoesNotExist:
                return Response({'detail': '目标集合不存在'}, status=404)

            # 跨项目校验：已属于某集合的接口必须与目标集合同项目
            cross_project = qs.filter(
                collection__isnull=False
            ).exclude(
                collection__project=collection.project
            ).exists()
            if cross_project:
                return Response({'detail': '不能将接口移动到不同项目的集合'}, status=400)

            moved = qs.update(collection=collection)
        else:
            moved = qs.update(collection=None)

        skipped = len(ids) - moved
        return Response({'moved': moved, 'skipped': skipped})

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除接口"""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'detail': '请提供要删除的接口 id 列表'}, status=400)

        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return Response({'detail': 'ids 必须为整数列表'}, status=400)

        qs = ApiRequest.objects.filter(id__in=ids, created_by=request.user)
        deleted_count, _ = qs.delete()
        skipped = len(ids) - deleted_count
        return Response({'deleted': deleted_count, 'skipped': skipped})

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """执行API请求"""
        api_request = self.get_object()
        environment_id = request.data.get('environment_id')

        try:
            resolver = VariableResolver()
            executor = RequestExecutor(resolver)

            # 解析环境变量
            variables = {}
            if environment_id:
                env = Environment.objects.get(id=environment_id)
                variables.update(env.variables)

            # 获取请求数据
            request_params = request.data.get('params', api_request.params)
            request_headers = request.data.get('headers', api_request.headers)
            request_body = request.data.get('body', api_request.body)
            request_method = request.data.get('method', api_request.method)
            request_url = request.data.get('url', api_request.url)

            pre_console = []
            tests_console = []
            # 执行 pre-request 脚本
            pre_script_result = run_pre_request_script(
                api_request.pre_request_script or '', variables
            )
            variables.update(pre_script_result['variables'])
            pre_console = pre_script_result['console']
            for err in pre_script_result.get('errors', []):
                logger.warning("pre-request script error: %s", err)
                pre_console.append(f'[ERROR] {err}')
            # 将脚本中设置的额外请求头合并进去
            if pre_script_result['extra_headers']:
                if isinstance(request_headers, list):
                    for k, v in pre_script_result['extra_headers'].items():
                        request_headers.append({'key': k, 'value': v, 'enabled': True})
                elif isinstance(request_headers, dict):
                    request_headers.update(pre_script_result['extra_headers'])

            # 替换变量
            url = executor._replace_variables(request_url or '', variables)
            url = resolver.resolve(url)

            headers = executor.prepare_headers(request_headers, variables)

            # skip_auth：前端传递或 model 字段均可触发，删除所有 Authorization 变体
            skip_auth = request.data.get('skip_auth', api_request.skip_auth)
            if skip_auth:
                headers = {k: v for k, v in headers.items() if k.lower() != 'authorization'}

            params = executor.prepare_params(request_params, variables)
            body_data, body_type = executor.prepare_body(request_body, request_method, variables)

            # 执行请求
            response, response_time = executor.execute(
                method=request_method,
                url=url,
                headers=headers,
                params=params,
                body=body_data,
                body_type=body_type
            )

            # 执行 tests 脚本（仅变量赋值 + console 输出，不再提取断言）
            if api_request.post_request_script:
                tests_result = run_tests_script(
                    api_request.post_request_script, variables, response
                )
                variables.update(tests_result['variables'])
                tests_console = tests_result['console']
                for err in tests_result.get('errors', []):
                    logger.warning("tests script error: %s", err)
                    tests_console.append(f'[ERROR] {err}')

            # 执行断言验证（断言完全由 Assertions UI 配置驱动）
            assertions = request.data.get('assertions', api_request.assertions) or []
            for assertion in assertions:
                if assertion.get('type') == 'response_time':
                    assertion['actual_time'] = response_time
            assertions_results = execute_assertions(response, assertions, variables=variables)

            # 保存请求历史
            history = RequestHistory.objects.create(
                request=api_request,
                environment_id=environment_id,
                request_data={
                    'url': url,
                    'method': request_method,
                    'headers': _mask_sensitive_data(headers),
                    'params': _mask_sensitive_data(params),
                    'body': _mask_sensitive_data(body_data)
                },
                response_data={
                    'headers': dict(response.headers),
                    'body': response.text,
                    'json': response.json() if response.headers.get('content-type', '').startswith('application/json') else None
                },
                status_code=response.status_code,
                response_time=response_time,
                executed_by=request.user
            )

            log_operation(
                operation_type='execute',
                resource_type='request',
                resource_id=api_request.id,
                resource_name=api_request.name,
                user=request.user
            )

            history_data = RequestHistorySerializer(history).data
            history_data['assertions_results'] = assertions_results
            history_data['console_output'] = pre_console + tests_console

            return Response(history_data)

        except Exception as e:
            logger.error(f"执行API请求失败: {str(e)}", exc_info=True)
            history = RequestHistory.objects.create(
                request=api_request,
                environment_id=environment_id,
                request_data={
                    'url': api_request.url,
                    'method': api_request.method,
                    'headers': _mask_sensitive_data(api_request.headers),
                    'params': _mask_sensitive_data(api_request.params),
                    'body': _mask_sensitive_data(api_request.body)
                },
                error_message=str(e),
                executed_by=request.user
            )

            return Response(RequestHistorySerializer(history).data, status=status.HTTP_400_BAD_REQUEST)


class EnvironmentViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """环境配置视图集"""
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['scope', 'project', 'is_active']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return Environment.objects.filter(
            models.Q(scope='GLOBAL') |
            models.Q(
                scope='LOCAL',
                project__in=ApiProject.objects.filter(
                    models.Q(visibility='all') |
                    models.Q(owner=user) |
                    models.Q(members=user)
                )
            )
        ).distinct().order_by('-created_at')

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """激活环境"""
        environment = self.get_object()

        if environment.scope == 'LOCAL' and environment.project:
            Environment.objects.filter(
                project=environment.project,
                scope='LOCAL'
            ).update(is_active=False)
        elif environment.scope == 'GLOBAL':
            Environment.objects.filter(scope='GLOBAL').update(is_active=False)

        environment.is_active = True
        environment.save()

        return Response({'message': '环境已激活'})

    def perform_create(self, serializer):
        """创建环境时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='create',
            resource_type='environment',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_update(self, serializer):
        """更新环境时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='edit',
            resource_type='environment',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_destroy(self, instance):
        """删除环境时记录日志"""
        log_operation(
            operation_type='delete',
            resource_type='environment',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )
        instance.delete()


class RequestHistoryViewSet(viewsets.ModelViewSet):
    """请求历史视图集"""
    queryset = RequestHistory.objects.all()
    serializer_class = RequestHistorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['request__request_type', 'status_code']
    ordering = ['-executed_at']
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        return RequestHistory.objects.filter(
            models.Q(request__visibility='all') |
            models.Q(executed_by=user) |
            models.Q(request__created_by=user)
        ).select_related(
            'request', 'environment', 'executed_by',
            'request__created_by', 'environment__created_by', 'environment__project'
        ).distinct()

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除请求历史"""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': '未提供要删除的记录ID'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = self.get_queryset()
        valid_ids = list(queryset.filter(id__in=ids).values_list('id', flat=True))

        deleted_count, _ = RequestHistory.objects.filter(id__in=valid_ids).delete()

        return Response({'message': f'成功删除 {deleted_count} 条记录'})

    @action(detail=False, methods=['delete'], url_path='clear')
    def clear(self, request):
        """清空当前用户的所有请求历史"""
        request_type = request.query_params.get('request_type')
        qs = RequestHistory.objects.filter(executed_by=request.user)
        if request_type:
            qs = qs.filter(request__request_type=request_type)
        deleted_count, _ = qs.delete()
        return Response({'message': f'成功清空 {deleted_count} 条记录', 'deleted': deleted_count})

class TestSuiteViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """测试套件视图集"""
    queryset = TestSuite.objects.all()
    serializer_class = TestSuiteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['project']

    def get_queryset(self):
        user = self.request.user
        return TestSuite.objects.filter(
            models.Q(visibility='all') | models.Q(created_by=user)
        ).distinct()

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """执行测试套件"""
        test_suite = self.get_object()
        execution = None

        try:
            # 创建执行记录
            execution = TestExecution.objects.create(
                test_suite=test_suite,
                status='RUNNING',
                start_time=timezone.now(),
                executed_by=request.user
            )

            # 获取套件中的请求
            suite_requests = TestSuiteRequest.objects.filter(
                test_suite=test_suite,
                enabled=True
            ).order_by('order').select_related('request')

            execution.total_requests = suite_requests.count()
            execution.save()

            results = []
            passed_count = 0
            failed_count = 0

            resolver = VariableResolver()
            executor = RequestExecutor(resolver)
            session = requests.Session()
            executor.session = session

            auth_variables = {}
            token_type = 'Bearer'

            # 执行每个请求
            for suite_request in suite_requests:
                api_request = suite_request.request

                # 准备断言列表
                assertions_to_execute = []

                # 优先使用套件请求关联表中的断言
                if suite_request.assertions:
                    for assertion in suite_request.assertions:
                        if isinstance(assertion, dict):
                            # 深拷贝断言，避免引用问题
                            assertions_to_execute.append(json.loads(json.dumps(assertion)))
                # 如果没有套件请求断言，使用请求本身的断言
                elif api_request.assertions:
                    for assertion in api_request.assertions:
                        if isinstance(assertion, dict):
                            # 深拷贝断言，避免引用问题
                            assertions_to_execute.append(json.loads(json.dumps(assertion)))

                logger.info(f"执行请求 {api_request.name}，断言数量: {len(assertions_to_execute)}")
                logger.debug(f"断言内容: {json.dumps(assertions_to_execute, ensure_ascii=False, indent=2)}")

                result = self._execute_single_request(
                    api_request,
                    test_suite,
                    executor,
                    resolver,
                    auth_variables,
                    token_type,
                    request.user,
                    assertions_to_execute
                )

                results.append(result)
                if result.get('passed', False):
                    passed_count += 1
                else:
                    failed_count += 1

            # 更新执行记录
            execution.end_time = timezone.now()
            execution.passed_requests = passed_count
            execution.failed_requests = failed_count
            execution.status = 'COMPLETED' if failed_count == 0 else 'FAILED'
            execution.results = results  # 确保这里保存了完整的断言结果
            execution.save()

            # 记录操作日志
            log_operation(
                operation_type='execute',
                resource_type='suite',
                resource_id=test_suite.id,
                resource_name=test_suite.name,
                user=request.user
            )

            # 返回执行记录
            serializer = TestExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"执行测试套件失败: {str(e)}", exc_info=True)
            if execution:
                execution.status = 'FAILED'
                execution.end_time = timezone.now()
                execution.results = [{'error': str(e)}]
                execution.save()
            return Response(
                {'error': f'执行测试套件失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _execute_single_request(self, api_request, test_suite, executor, resolver,
                                auth_variables, token_type, user, assertions):
        """执行单个请求 """
        try:
            # 准备变量
            variables = {}
            if test_suite.environment:
                variables.update(test_suite.environment.variables)
            variables.update(auth_variables)

            # 执行预处理脚本
            if api_request.pre_request_script:
                try:
                    script_context = {
                        'variables': variables,
                        'resolver': resolver,
                        'runtime_vars': resolver.runtime_variables
                    }
                    parse_and_execute_script(api_request.pre_request_script, script_context)
                except Exception as e:
                    logger.warning(f"预处理脚本执行失败: {str(e)}")

            # 替换变量
            url = executor._replace_variables(api_request.url, variables)
            url = resolver.resolve(url)

            headers = executor.prepare_headers(api_request.headers, variables)

            if 'token' in auth_variables and 'Authorization' not in headers:
                headers['Authorization'] = f'{token_type} {auth_variables["token"]}'

            params = executor.prepare_params(api_request.params, variables)
            body_data, body_type = executor.prepare_body(api_request.body, api_request.method, variables)

            # 执行请求
            response, response_time = executor.execute(
                method=api_request.method,
                url=url,
                headers=headers,
                params=params,
                body=body_data,
                body_type=body_type
            )

            # 执行后处理脚本，提取 Tests 中的 MongoDB 断言
            script_assertions = []
            if api_request.post_request_script:
                try:
                    script_result = execute_with_response(api_request.post_request_script, response)
                    for _i, _sa in enumerate(script_result.get('assertions', [])):
                        _expected = _sa.get('expected')
                        if _expected is not None and isinstance(_expected, (dict, list)):
                            script_assertions.append({
                                'type': 'mongo_match',
                                'name': f'Tests断言 {_i + 1}',
                                'expected': _expected,
                            })
                except Exception as e:
                    logger.warning(f"后处理脚本执行失败: {str(e)}")

            # 提取认证信息
            self._extract_auth_info(response, auth_variables, token_type, executor.session)

            # 为响应时间断言添加实际时间
            processed_assertions = []
            for assertion in assertions:
                # 确保每个断言都是字典且有正确的结构
                if isinstance(assertion, dict):
                    assertion_copy = assertion.copy()
                    if assertion_copy.get('type') == 'response_time':
                        assertion_copy['actual_time'] = response_time
                    # 确保断言有必要的字段
                    if 'name' not in assertion_copy:
                        assertion_copy['name'] = '未命名断言'
                    if 'type' not in assertion_copy:
                        assertion_copy['type'] = 'unknown'
                    processed_assertions.append(assertion_copy)

            # 合并运行时变量（pre/post script 中赋值的变量，以及前序请求提取的变量）
            variables.update(resolver.runtime_variables)

            # 执行断言
            from .utils import execute_assertions
            assertions_results = execute_assertions(response, processed_assertions + script_assertions, variables=variables)

            # 判断是否通过
            passed = all(r.get('passed', False) for r in assertions_results)

            # 准备响应数据
            response_json = None
            try:
                if response.headers.get('content-type', '').startswith('application/json'):
                    response_json = response.json()
            except:
                pass

            # 保存请求历史 - 确保保存完整的断言结果
            history = RequestHistory.objects.create(
                request=api_request,
                environment=test_suite.environment,
                request_data={
                    'url': url,
                    'method': api_request.method,
                    'headers': _mask_sensitive_data(headers),
                    'params': _mask_sensitive_data(params),
                    'body': _mask_sensitive_data(body_data)
                },
                response_data={
                    'headers': dict(response.headers),
                    'body': response.text,
                    'json': response_json
                },
                status_code=response.status_code,
                response_time=response_time,
                assertions_results=assertions_results,  # 保存完整的断言结果
                executed_by=user
            )

            # 构建结果 - 确保包含完整的断言结果
            result = {
                'request_id': api_request.id,
                'name': api_request.name,
                'method': api_request.method,
                'url': url,
                'status_code': response.status_code,
                'response_time': response_time,
                'passed': passed,
                'error': '',
                'assertions_results': assertions_results,  # 保存完整的断言结果
                'history_id': history.id
            }

            # 添加失败断言信息
            if not passed:
                failed_assertions = [a for a in assertions_results if not a.get('passed', False)]
                result['failed_assertions'] = failed_assertions
                result['error'] = f"有 {len(failed_assertions)} 个断言失败"

            return result

        except Exception as e:
            logger.error(f"执行请求失败 {api_request.name}: {str(e)}", exc_info=True)

            # 记录失败的请求历史
            try:
                history = RequestHistory.objects.create(
                    request=api_request,
                    environment=test_suite.environment,
                    request_data={
                        'url': api_request.url,
                        'method': api_request.method,
                        'headers': _mask_sensitive_data(api_request.headers),
                        'params': _mask_sensitive_data(api_request.params),
                        'body': _mask_sensitive_data(api_request.body)
                    },
                    error_message=str(e),
                    executed_by=user
                )
                history_id = history.id
            except:
                history_id = None

            return {
                'request_id': api_request.id,
                'name': api_request.name,
                'method': api_request.method,
                'url': api_request.url,
                'passed': False,
                'error': str(e),
                'assertions_results': [{
                    'name': '执行错误',
                    'type': 'error',
                    'passed': False,
                    'message': f'请求执行失败: {str(e)}',
                    'expected': None,
                    'actual': None
                }],
                'history_id': history_id
            }

    def _extract_auth_info(self, response, auth_variables, token_type, session):
        """从响应中提取认证信息"""
        try:
            response_json = response.json()

            # 常见的token字段
            token_fields = [
                'access_token', 'token', 'accessToken',
                'jwt', 'auth_token', 'id_token', 'refresh_token'
            ]

            for field in token_fields:
                if field in response_json:
                    auth_variables[field] = response_json[field]

                    # 如果是access_token，也设置为token变量
                    if field == 'access_token' and 'token' not in auth_variables:
                        auth_variables['token'] = response_json[field]

            # 提取token_type
            if 'token_type' in response_json:
                token_type = response_json['token_type']
                auth_variables['token_type'] = token_type

        except (ValueError, AttributeError):
            pass

        # 从响应头提取认证信息
        auth_header = response.headers.get('Authorization')
        if auth_header:
            if auth_header.startswith('Bearer '):
                auth_variables['token'] = auth_header.replace('Bearer ', '')
                auth_variables['token_type'] = 'Bearer'
            elif auth_header.startswith('Token '):
                auth_variables['token'] = auth_header.replace('Token ', '')
                auth_variables['token_type'] = 'Token'

        # 提取cookies
        if session.cookies:
            cookies_dict = session.cookies.get_dict()
            auth_variables.update(cookies_dict)
            if 'sessionid' in cookies_dict:
                auth_variables['session_id'] = cookies_dict['sessionid']

    @action(detail=True, methods=['post'], url_path='add-requests')
    def add_requests(self, request, pk=None):
        """添加请求到测试套件"""
        test_suite = self.get_object()
        request_ids = request.data.get('request_ids', [])

        # 获取是否需要复制原始断言的参数，默认为True
        copy_original_assertions = request.data.get('copy_original_assertions', True)

        try:
            added_count = 0
            for request_id in request_ids:
                api_request = ApiRequest.objects.get(id=request_id)

                # 检查是否已存在
                existing = TestSuiteRequest.objects.filter(
                    test_suite=test_suite,
                    request=api_request
                ).first()

                if existing:
                    continue

                # 创建新的关联记录
                # 根据参数决定是否复制原始断言
                assertions = []
                if copy_original_assertions and api_request.assertions:
                    # 深拷贝断言，避免引用问题
                    assertions = json.loads(json.dumps(api_request.assertions))

                max_order = TestSuiteRequest.objects.filter(
                    test_suite=test_suite
                ).aggregate(models.Max('order'))['order__max']
                next_order = (max_order + 1) if max_order is not None else 0
                TestSuiteRequest.objects.create(
                    test_suite=test_suite,
                    request=api_request,
                    order=next_order,
                    enabled=True,
                    assertions=assertions  # 正确设置断言字段
                )
                added_count += 1

            return Response({
                'message': f'成功添加 {added_count} 个请求到测试套件',
                'added_count': added_count
            })

        except ApiRequest.DoesNotExist:
            return Response(
                {'error': '一个或多个请求不存在'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], url_path='reorder-requests')
    def reorder_requests(self, request, pk=None):
        """重新排序测试套件中的请求"""
        test_suite = self.get_object()
        orders = request.data.get('orders', [])

        try:
            for item in orders:
                TestSuiteRequest.objects.filter(
                    id=item['id'],
                    test_suite=test_suite
                ).update(order=item['order'])
            return Response({'message': '排序已保存'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        """创建测试套件时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='create',
            resource_type='suite',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_update(self, serializer):
        """更新测试套件时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='edit',
            resource_type='suite',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_destroy(self, instance):
        """删除测试套件时记录日志"""
        log_operation(
            operation_type='delete',
            resource_type='suite',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )
        instance.delete()


class TestSuiteRequestViewSet(viewsets.ModelViewSet):
    """测试套件请求关联视图集"""
    queryset = TestSuiteRequest.objects.all()
    serializer_class = TestSuiteRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['test_suite', 'enabled']

    def get_queryset(self):
        user = self.request.user
        return TestSuiteRequest.objects.filter(
            models.Q(test_suite__visibility='all') |
            models.Q(test_suite__created_by=user)
        ).distinct()


class TestExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """测试执行记录视图集"""
    queryset = TestExecution.objects.all()
    serializer_class = TestExecutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'test_suite']
    ordering = ['-created_at']
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        return TestExecution.objects.filter(
            models.Q(test_suite__visibility='all') |
            models.Q(executed_by=user) |
            models.Q(test_suite__created_by=user)
        ).distinct()

    @action(detail=True, methods=['post'], url_path='generate-allure-report')
    def generate_allure_report(self, request, pk=None):
        """生成Allure报告数据"""
        execution = self.get_object()

        try:
            results_dir = os.path.join(settings.MEDIA_ROOT, 'allure-results', f'execution_{execution.id}')
            os.makedirs(results_dir, exist_ok=True)

            self._generate_test_result_files(execution, results_dir)

            report_output_dir = os.path.join(settings.MEDIA_ROOT, 'allure-reports', f'execution_{execution.id}')
            os.makedirs(report_output_dir, exist_ok=True)

            self._generate_allure_report_with_fallback(execution, results_dir, report_output_dir)

            summary_file = self._generate_summary_html(execution, report_output_dir)

            return Response({
                'message': 'Allure报告生成成功',
                'report_url': f'/media/allure-reports/execution_{execution.id}/summary.html'
            })
        except Exception as e:
            logger.error(f"生成Allure报告失败: {str(e)}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _generate_allure_report_with_fallback(self, execution, results_dir, report_output_dir):
        """生成Allure报告，带降级策略"""
        import subprocess
        import shutil
        from pathlib import Path

        base_dir = Path(__file__).resolve().parent.parent.parent
        allure_executable = 'allure.bat' if os.name == 'nt' else 'allure'
        allure_cmd = str(base_dir / 'allure' / 'bin' / allure_executable)

        if not os.path.exists(allure_cmd):
            possible_paths = [
                base_dir / 'allure' / 'bin' / allure_executable,
                Path('/usr/local/bin/allure'),
                Path('/usr/bin/allure'),
            ]
            for path in possible_paths:
                if path.exists():
                    allure_cmd = str(path)
                    break
            else:
                allure_cmd = None

        os.makedirs(results_dir, exist_ok=True)

        if allure_cmd:
            try:
                if os.path.exists(report_output_dir):
                    shutil.rmtree(report_output_dir)

                subprocess.run([
                    allure_cmd, 'generate',
                    results_dir,
                    '--clean',
                    '--output', report_output_dir
                ], check=True, capture_output=True, text=True, timeout=60)
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
                logger.warning(f"Allure命令失败: {str(e)}，使用降级方案")
                self._copy_static_allure_files(report_output_dir)

        self._ensure_report_exists(execution, report_output_dir)

    def _copy_static_allure_files(self, report_output_dir):
        """复制静态Allure文件"""
        import shutil
        static_dir = os.path.join(settings.MEDIA_ROOT, 'allure-static')
        if os.path.exists(static_dir):
            for item in os.listdir(static_dir):
                source = os.path.join(static_dir, item)
                destination = os.path.join(report_output_dir, item)
                if os.path.isdir(source):
                    shutil.copytree(source, destination, dirs_exist_ok=True)
                else:
                    shutil.copy2(source, destination)

    def _ensure_report_exists(self, execution, report_output_dir):
        """确保报告文件存在"""
        if not os.path.exists(os.path.join(report_output_dir, 'index.html')):
            fallback_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>测试报告 - {execution.test_suite.name}</title>
</head>
<body>
    <h1>测试报告</h1>
    <p>测试套件: {execution.test_suite.name}</p>
    <p>状态: {execution.get_status_display()}</p>
    <p>总请求数: {execution.total_requests}</p>
    <p>通过: {execution.passed_requests}</p>
    <p>失败: {execution.failed_requests}</p>
</body>
</html>
"""
            with open(os.path.join(report_output_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(fallback_html)

    def _generate_summary_html(self, execution, report_output_dir):
        """生成摘要HTML - 仪表盘设计"""
        import math

        project_name = execution.test_suite.project.name
        suite_name = execution.test_suite.name
        total = execution.total_requests or 0
        passed = execution.passed_requests or 0
        failed = execution.failed_requests or 0
        skipped = max(0, total - passed - failed)
        pass_rate = round(passed / total * 100, 1) if total > 0 else 0.0
        status_is_ok = execution.status == "COMPLETED"
        status_text = execution.get_status_display()
        exec_time = execution.created_at.strftime('%Y-%m-%d %H:%M:%S') if execution.created_at else 'N/A'

        duration_text = 'N/A'
        if execution.start_time and execution.end_time:
            secs = (execution.end_time - execution.start_time).total_seconds()
            duration_text = f"{secs:.1f} 秒" if secs < 60 else f"{int(secs // 60)} 分 {int(secs % 60)} 秒"

        # SVG donut chart 参数（半径 54, 圆心 60,60）
        r = 60
        circ = round(2 * math.pi * r, 2)
        pass_arc = round(pass_rate / 100 * circ, 2)
        fail_arc = round(circ - pass_arc, 2)

        index_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - 接口测试报告</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a2e; }}

        /* ── Header ── */
        .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #7c3aed 100%); color: #fff; padding: 0; }}
        .header-inner {{ max-width: 1280px; margin: 0 auto; padding: 2rem 2rem 1.8rem; display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; }}
        .header-left h1 {{ font-size: 1.75rem; font-weight: 700; letter-spacing: -0.5px; }}
        .header-left .subtitle {{ margin-top: 0.4rem; opacity: 0.85; font-size: 0.95rem; }}
        .header-left .subtitle span {{ margin-right: 1.2rem; }}
        .header-right {{ display: flex; align-items: center; gap: 0.75rem; flex-shrink: 0; }}
        .badge {{ display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.45rem 1rem; border-radius: 999px; font-weight: 600; font-size: 0.85rem; }}
        .badge-ok  {{ background: #22c55e; color: #fff; }}
        .badge-err {{ background: #ef4444; color: #fff; }}
        .btn-allure {{ display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.5rem 1.1rem; background: rgba(255,255,255,0.15); border: 1.5px solid rgba(255,255,255,0.35); border-radius: 6px; color: #fff; text-decoration: none; font-size: 0.88rem; font-weight: 600; transition: background 0.2s; }}
        .btn-allure:hover {{ background: rgba(255,255,255,0.28); text-decoration: none; }}

        /* ── Main ── */
        .main {{ max-width: 1280px; margin: 0 auto; padding: 2rem; }}

        /* ── Metric cards ── */
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
        .metric-card {{ background: #fff; border-radius: 12px; padding: 1.4rem 1.6rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); border-top: 4px solid transparent; }}
        .metric-card.c-total  {{ border-top-color: #6366f1; }}
        .metric-card.c-passed {{ border-top-color: #22c55e; }}
        .metric-card.c-failed {{ border-top-color: #ef4444; }}
        .metric-card.c-rate   {{ border-top-color: #f59e0b; }}
        .metric-card.c-time   {{ border-top-color: #06b6d4; }}
        .metric-card.c-dur    {{ border-top-color: #8b5cf6; }}
        .metric-val {{ font-size: 2.1rem; font-weight: 800; line-height: 1; }}
        .metric-val.v-total  {{ color: #6366f1; }}
        .metric-val.v-passed {{ color: #22c55e; }}
        .metric-val.v-failed {{ color: #ef4444; }}
        .metric-val.v-rate   {{ color: #f59e0b; }}
        .metric-val.v-time   {{ color: #06b6d4; font-size: 1.25rem; }}
        .metric-val.v-dur    {{ color: #8b5cf6; font-size: 1.35rem; }}
        .metric-label {{ margin-top: 0.4rem; font-size: 0.82rem; color: #6b7280; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }}

        /* ── Dashboard row ── */
        .dashboard {{ display: grid; grid-template-columns: 280px 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }}
        @media (max-width: 768px) {{ .dashboard {{ grid-template-columns: 1fr; }} }}

        .chart-card {{ background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .chart-card h3 {{ font-size: 0.95rem; color: #374151; font-weight: 600; margin-bottom: 1rem; align-self: flex-start; }}
        .donut-wrap {{ position: relative; width: 160px; height: 160px; }}
        .donut-center {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .donut-pct {{ font-size: 1.9rem; font-weight: 800; color: #1a1a2e; line-height: 1; }}
        .donut-sub {{ font-size: 0.72rem; color: #6b7280; margin-top: 0.2rem; }}
        .legend {{ display: flex; gap: 1rem; margin-top: 1rem; flex-wrap: wrap; justify-content: center; }}
        .legend-item {{ display: flex; align-items: center; gap: 0.35rem; font-size: 0.82rem; color: #374151; }}
        .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}

        .bar-card {{ background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }}
        .bar-card h3 {{ font-size: 0.95rem; color: #374151; font-weight: 600; margin-bottom: 1.2rem; }}
        .bar-row {{ display: flex; align-items: center; gap: 0.8rem; margin-bottom: 0.9rem; }}
        .bar-label {{ width: 3.5rem; font-size: 0.82rem; color: #6b7280; text-align: right; flex-shrink: 0; }}
        .bar-track {{ flex: 1; height: 22px; background: #f3f4f6; border-radius: 6px; overflow: hidden; }}
        .bar-fill {{ height: 100%; border-radius: 6px; display: flex; align-items: center; padding-left: 8px; color: #fff; font-size: 0.78rem; font-weight: 700; min-width: 2rem; transition: width 0.6s ease; }}
        .bar-fill.b-pass {{ background: linear-gradient(90deg, #22c55e, #16a34a); }}
        .bar-fill.b-fail {{ background: linear-gradient(90deg, #ef4444, #dc2626); }}
        .bar-fill.b-skip {{ background: linear-gradient(90deg, #9ca3af, #6b7280); }}
        .bar-count {{ width: 2rem; font-size: 0.82rem; font-weight: 700; color: #374151; flex-shrink: 0; }}

        /* ── Test results table ── */
        .results-card {{ background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }}
        .results-card h3 {{ font-size: 0.95rem; color: #374151; font-weight: 600; margin-bottom: 1rem; }}
        .results-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
        .results-table th {{ background: #f9fafb; padding: 0.7rem 0.8rem; text-align: left; font-size: 0.78rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid #e5e7eb; }}
        .results-table td {{ padding: 0.75rem 0.8rem; border-bottom: 1px solid #f3f4f6; vertical-align: top; }}
        .results-table tr:last-child td {{ border-bottom: none; }}
        .results-table tr:hover td {{ background: #fafafa; }}
        .tag-method {{ display: inline-block; padding: 0.18rem 0.55rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; color: #fff; }}
        .m-get    {{ background: #3b82f6; }}
        .m-post   {{ background: #22c55e; }}
        .m-put    {{ background: #f59e0b; }}
        .m-patch  {{ background: #8b5cf6; }}
        .m-delete {{ background: #ef4444; }}
        .m-other  {{ background: #6b7280; }}
        .tag-status {{ display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.2rem 0.65rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }}
        .s-pass {{ background: #dcfce7; color: #15803d; }}
        .s-fail {{ background: #fee2e2; color: #b91c1c; }}
        .cell-url {{ color: #6b7280; word-break: break-all; max-width: 340px; }}
        .assertions-list {{ margin-top: 6px; padding-left: 0; list-style: none; }}
        .assertions-list li {{ font-size: 0.8rem; padding: 3px 0; display: flex; align-items: flex-start; gap: 0.4rem; }}
        .a-ok  {{ color: #15803d; }}
        .a-err {{ color: #b91c1c; }}
        .err-box {{ margin-top: 4px; padding: 0.4rem 0.6rem; background: #fff1f2; border-radius: 4px; font-size: 0.8rem; color: #b91c1c; }}

        /* ── Footer ── */
        .footer {{ text-align: center; padding: 1.5rem; color: #9ca3af; font-size: 0.82rem; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-inner">
            <div class="header-left">
                <h1>{project_name} - 接口测试报告</h1>
                <div class="subtitle">
                    <span>测试套件：{suite_name}</span>
                    <span>执行时间：{exec_time}</span>
                </div>
            </div>
            <div class="header-right">
                <span class="badge {'badge-ok' if status_is_ok else 'badge-err'}">
                    {'✓' if status_is_ok else '✗'} {status_text}
                </span>
                <a href="index.html" target="_blank" class="btn-allure">&#128196; 查看 Allure 详情报告</a>
            </div>
        </div>
    </div>

    <div class="main">
        <!-- 指标卡片 -->
        <div class="metrics">
            <div class="metric-card c-total">
                <div class="metric-val v-total">{total}</div>
                <div class="metric-label">总用例数</div>
            </div>
            <div class="metric-card c-passed">
                <div class="metric-val v-passed">{passed}</div>
                <div class="metric-label">通过</div>
            </div>
            <div class="metric-card c-failed">
                <div class="metric-val v-failed">{failed}</div>
                <div class="metric-label">失败</div>
            </div>
            <div class="metric-card c-rate">
                <div class="metric-val v-rate">{pass_rate}%</div>
                <div class="metric-label">通过率</div>
            </div>
            <div class="metric-card c-time">
                <div class="metric-val v-time">{exec_time}</div>
                <div class="metric-label">执行时间</div>
            </div>
            <div class="metric-card c-dur">
                <div class="metric-val v-dur">{duration_text}</div>
                <div class="metric-label">执行耗时</div>
            </div>
        </div>

        <!-- 仪表盘 -->
        <div class="dashboard">
            <!-- 甜甜圈图 -->
            <div class="chart-card">
                <h3>执行结果分布</h3>
                <div class="donut-wrap">
                    <svg viewBox="0 0 120 120" width="160" height="160">
                        <!-- 背景圆 -->
                        <circle cx="60" cy="60" r="{r}" fill="none" stroke="#f3f4f6" stroke-width="16"/>
                        <!-- 失败弧（先画，在通过弧下面） -->
                        <circle cx="60" cy="60" r="{r}" fill="none" stroke="#ef4444" stroke-width="16"
                            stroke-dasharray="{fail_arc} {circ}"
                            stroke-dashoffset="-{pass_arc}"
                            transform="rotate(-90 60 60)"/>
                        <!-- 通过弧 -->
                        <circle cx="60" cy="60" r="{r}" fill="none" stroke="#22c55e" stroke-width="16"
                            stroke-dasharray="{pass_arc} {circ}"
                            stroke-dashoffset="0"
                            transform="rotate(-90 60 60)"/>
                    </svg>
                    <div class="donut-center">
                        <span class="donut-pct">{pass_rate}%</span>
                        <span class="donut-sub">通过率</span>
                    </div>
                </div>
                <div class="legend">
                    <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>通过 {passed}</div>
                    <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>失败 {failed}</div>
                    {"<div class='legend-item'><div class='legend-dot' style='background:#9ca3af'></div>跳过 " + str(skipped) + "</div>" if skipped > 0 else ""}
                </div>
            </div>

            <!-- 水平进度条 -->
            <div class="bar-card">
                <h3>各类结果统计</h3>
                <div class="bar-row">
                    <span class="bar-label">通过</span>
                    <div class="bar-track">
                        <div class="bar-fill b-pass" style="width:{round(passed/total*100) if total else 0}%">{passed}</div>
                    </div>
                    <span class="bar-count">{passed}</span>
                </div>
                <div class="bar-row">
                    <span class="bar-label">失败</span>
                    <div class="bar-track">
                        <div class="bar-fill b-fail" style="width:{round(failed/total*100) if total else 0}%">{failed}</div>
                    </div>
                    <span class="bar-count">{failed}</span>
                </div>
                {"<div class='bar-row'><span class='bar-label'>跳过</span><div class='bar-track'><div class='bar-fill b-skip' style='width:" + str(round(skipped/total*100) if total else 0) + "%'>" + str(skipped) + "</div></div><span class='bar-count'>" + str(skipped) + "</span></div>" if skipped > 0 else ""}
                <div style="margin-top:1.5rem; padding:1rem; background:#f9fafb; border-radius:8px;">
                    <table style="width:100%; font-size:0.85rem; border-collapse:collapse;">
                        <tr>
                            <td style="color:#6b7280; padding:4px 0;">总用例数</td>
                            <td style="font-weight:700; text-align:right;">{total}</td>
                            <td style="color:#6b7280; padding:4px 0 4px 2rem;">通过率</td>
                            <td style="font-weight:700; text-align:right; color:#f59e0b;">{pass_rate}%</td>
                        </tr>
                        <tr>
                            <td style="color:#6b7280; padding:4px 0;">执行状态</td>
                            <td style="font-weight:700; text-align:right; color:{'#22c55e' if status_is_ok else '#ef4444'};">{status_text}</td>
                            <td style="color:#6b7280; padding:4px 0 4px 2rem;">执行耗时</td>
                            <td style="font-weight:700; text-align:right;">{duration_text}</td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>

        <!-- 测试结果明细 -->
        <div class="results-card">
            <h3>测试结果明细</h3>
            <table class="results-table">
                <thead>
                    <tr>
                        <th style="width:2.5rem;">#</th>
                        <th style="width:5rem;">方法</th>
                        <th>接口名称 / URL</th>
                        <th style="width:5rem;">状态码</th>
                        <th style="width:5rem;">耗时(ms)</th>
                        <th style="width:5rem;">结果</th>
                        <th>断言详情</th>
                    </tr>
                </thead>
                <tbody>
"""

        if execution.results:
            for i, result in enumerate(execution.results):
                is_passed = result.get('passed', False)
                method = result.get('method', 'GET').upper()
                method_cls = f"m-{method.lower()}" if method.lower() in ('get','post','put','patch','delete') else 'm-other'
                name = result.get('name', f'请求 {i+1}')
                url = result.get('url', '')
                sc = result.get('status_code', '-')
                rt = result.get('response_time', None)
                rt_text = f"{rt:.1f}" if rt is not None else '-'
                error = result.get('error', '')
                assertions = result.get('assertions_results', [])

                assertions_html = ''
                if assertions:
                    assertions_html = '<ul class="assertions-list">'
                    for a in assertions:
                        a_ok = a.get('passed', False)
                        icon = '✓' if a_ok else '✗'
                        cls = 'a-ok' if a_ok else 'a-err'
                        msg = a.get('message', a.get('name', '断言'))
                        a_type = a.get('type', '')
                        if a_type == 'status_code':
                            msg = f"状态码: 期望 {a.get('expected','?')}，实际 {a.get('actual','?')}"
                        elif a_type == 'response_time':
                            msg = f"响应时间: 期望 ≤{a.get('expected','?')}ms，实际 {a.get('actual_time', a.get('actual','?'))}ms"
                        elif a_type == 'json_path':
                            msg = f"JSON路径 [{a.get('json_path','')}]: 期望 {a.get('expected','?')}，实际 {a.get('actual','?')}"
                        elif a_type == 'contains':
                            msg = f"包含断言: 关键词 &quot;{a.get('expected','?')}&quot; {'存在' if a_ok else '不存在'}"
                        elif a_type == 'header':
                            msg = f"响应头 [{a.get('header_name','')}]: 期望 {a.get('expected','?')}，实际 {a.get('actual','?')}"
                        assertions_html += f'<li class="{cls}"><span>{icon}</span><span>{msg}</span></li>'
                    assertions_html += '</ul>'

                if error and not assertions:
                    assertions_html = f'<div class="err-box">{error}</div>'

                index_content += f"""
                <tr>
                    <td style="color:#9ca3af;">{i + 1}</td>
                    <td><span class="tag-method {method_cls}">{method}</span></td>
                    <td>
                        <div style="font-weight:600; margin-bottom:3px;">{name}</div>
                        <div class="cell-url">{url}</div>
                    </td>
                    <td style="font-weight:600;">{sc}</td>
                    <td>{rt_text}</td>
                    <td><span class="tag-status {'s-pass' if is_passed else 's-fail'}">{'PASS' if is_passed else 'FAILL'}</span></td>
                    <td>{assertions_html}</td>
                </tr>"""

        index_content += f"""
                </tbody>
            </table>
        </div>

        <div class="footer">报告生成时间：{exec_time} &nbsp;|&nbsp; 测试套件：{suite_name} &nbsp;|&nbsp; 项目：{project_name}</div>
    </div>
</body>
</html>"""

        summary_file = os.path.join(report_output_dir, 'summary.html')
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(index_content)

        return summary_file

    def _generate_test_result_files(self, execution, report_dir):
        """生成测试结果文件（含详细入参、响应及断言比对）"""
        try:
            if not execution.results:
                logger.warning(f"执行记录 {execution.id} 没有结果数据")
                return

            # 批量加载请求历史，避免 N+1 查询
            history_ids = [r.get('history_id') for r in execution.results if r.get('history_id')]
            histories = {}
            if history_ids:
                for h in RequestHistory.objects.filter(id__in=history_ids).values(
                        'id', 'request_data', 'response_data', 'status_code', 'response_time'):
                    histories[h['id']] = h

            container_data = {
                "uuid": str(execution.id),
                "name": execution.test_suite.name,
                "children": [f"{execution.id}-{i}" for i in range(len(execution.results))]
            }

            container_file_path = os.path.join(report_dir, f'{execution.id}-container.json')
            with open(container_file_path, 'w', encoding='utf-8') as f:
                json.dump(container_data, f, ensure_ascii=False, indent=2)

            # 使用执行开始时间作为基准，每个用例间隔 2 秒，确保按先执行在前排序
            import math as _math
            base_ts = int(
                (execution.start_time or execution.created_at).timestamp() * 1000
            ) if (execution.start_time or execution.created_at) else int(time.time() * 1000)

            for i, result in enumerate(execution.results):
                test_start = base_ts + i * 2000
                test_stop = test_start + 1800

                # ── 构建 Parameters（入参，密码字段已掩码） ──────────────────
                parameters = [
                    {"name": "method",        "value": result.get('method', 'GET')},
                    {"name": "url",           "value": result.get('url', '')},
                    {"name": "status_code",   "value": str(result.get('status_code', 'N/A'))},
                    {"name": "response_time", "value": f"{result.get('response_time', 0):.2f}ms"
                     if result.get('response_time') is not None else 'N/A'},
                ]

                history = histories.get(result.get('history_id'))
                req_data = {}
                resp_data = {}
                if history:
                    req_data  = history.get('request_data')  or {}
                    resp_data = history.get('response_data') or {}

                    # 请求头（过滤敏感字段）
                    req_headers = _mask_sensitive_data(req_data.get('headers') or {})
                    if req_headers and isinstance(req_headers, dict):
                        for k, v in req_headers.items():
                            parameters.append({"name": f"header.{k}", "value": str(v)})

                    # 查询参数
                    req_params = _mask_sensitive_data(req_data.get('params') or {})
                    if req_params and isinstance(req_params, dict):
                        for k, v in req_params.items():
                            parameters.append({"name": f"query.{k}", "value": str(v)})
                    elif req_params and isinstance(req_params, str) and req_params:
                        parameters.append({"name": "query_string", "value": req_params})

                    # 请求体（掩码敏感字段，截断超长内容）
                    req_body = _mask_sensitive_data(req_data.get('body'))
                    if req_body is not None:
                        if isinstance(req_body, (dict, list)):
                            body_str = json.dumps(req_body, ensure_ascii=False, indent=2)
                        else:
                            body_str = str(req_body)
                        if len(body_str) > 1000:
                            body_str = body_str[:1000] + '\n...(内容已截断)'
                        parameters.append({"name": "request_body", "value": body_str})

                # ── 构建 Steps（Test Body） ────────────────────────────────

                # Step 1: 发送请求 - 展示请求摘要
                req_summary_lines = [
                    f"{result.get('method', 'GET')}  {result.get('url', '')}",
                ]
                if req_data.get('params'):
                    req_summary_lines.append(f"Query Params: {json.dumps(_mask_sensitive_data(req_data.get('params')), ensure_ascii=False)}")
                if req_data.get('body'):
                    body_preview = _mask_sensitive_data(req_data.get('body'))
                    body_preview_str = json.dumps(body_preview, ensure_ascii=False) if isinstance(body_preview, (dict, list)) else str(body_preview)
                    if len(body_preview_str) > 300:
                        body_preview_str = body_preview_str[:300] + '...'
                    req_summary_lines.append(f"Request Body: {body_preview_str}")

                send_step = {
                    "name": "发送请求",
                    "status": "passed",
                    "stage": "finished",
                    "start": test_start,
                    "stop": test_start + 800,
                    "description": "\n".join(req_summary_lines),
                    "steps": []
                }

                # Step 2: 验证响应 - 展示响应状态 + body
                resp_body_raw = resp_data.get('body', '') or ''
                resp_body_preview = resp_body_raw[:800] + ('...(已截断)' if len(resp_body_raw) > 800 else '')
                resp_status = result.get('status_code', history.get('status_code', '-') if history else '-')
                resp_time = result.get('response_time', history.get('response_time', '-') if history else '-')
                resp_rt_text = f"{resp_time:.2f}ms" if isinstance(resp_time, (int, float)) else str(resp_time)
                resp_summary = (
                    f"HTTP {resp_status}  |  耗时 {resp_rt_text}\n\n"
                    f"Response Body:\n{resp_body_preview}"
                )

                # 断言子步骤
                assertion_steps = []
                for j, assertion in enumerate(result.get('assertions_results', [])):
                    a_ok = assertion.get('passed', False)
                    a_type = assertion.get('type', 'unknown')
                    a_name = assertion.get('name', f'断言 {j+1}')
                    a_msg = assertion.get('message', '')

                    # 构造比对详情
                    if a_type == 'status_code':
                        detail = f"类型: 状态码断言 | 期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                    elif a_type == 'response_time':
                        detail = f"类型: 响应时间断言 | 期望: ≤{assertion.get('expected', '?')}ms | 实际: {assertion.get('actual_time', assertion.get('actual', '?'))}ms"
                    elif a_type == 'json_path':
                        detail = (
                            f"类型: JSON路径断言 | 路径: {assertion.get('json_path', '')} | "
                            f"期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                        )
                    elif a_type == 'contains':
                        detail = f"类型: 包含断言 | 关键词: {assertion.get('expected', '?')} | 结果: {'找到' if a_ok else '未找到'}"
                    elif a_type == 'header':
                        detail = (
                            f"类型: 响应头断言 | 头名称: {assertion.get('header_name', '')} | "
                            f"期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                        )
                    elif a_type == 'equals':
                        detail = f"类型: 相等断言 | 期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                    elif a_type == 'mongo_match':
                        mongo_r = assertion.get('mongo_result', {})
                        total = mongo_r.get('total', 0)
                        passed_c = mongo_r.get('successful_count', 0)
                        failed_c = mongo_r.get('failed_count', 0)
                        detail = f"类型: MongoDB断言 | 总检查点: {total} | 通过: {passed_c} | 失败: {failed_c}"
                    else:
                        detail = f"类型: {a_type} | {a_msg}"

                    # MongoDB 断言：为每个失败的匹配项生成子步骤
                    mongo_sub_steps = []
                    if a_type == 'mongo_match':
                        mongo_r = assertion.get('mongo_result', {})
                        for k, fm in enumerate(mongo_r.get('failed_matches', [])):
                            mongo_sub_steps.append({
                                "name": f"✗ {fm.get('path', '?')} [{fm.get('operator', '?')}] 期望: {fm.get('expected', '?')} | 实际: {fm.get('actual', '?')}",
                                "status": "failed",
                                "stage": "finished",
                                "start": test_start + 900 + j * 10 + k,
                                "stop": test_start + 901 + j * 10 + k,
                                "steps": []
                            })
                        for k, sm in enumerate(mongo_r.get('successful_matches', [])):
                            mongo_sub_steps.append({
                                "name": f"✓ {sm.get('path', '?')} [{sm.get('operator', '?')}] 期望: {sm.get('expected', '?')} | 实际: {sm.get('actual', '?')}",
                                "status": "passed",
                                "stage": "finished",
                                "start": test_start + 900 + j * 10 + len(mongo_r.get('failed_matches', [])) + k,
                                "stop": test_start + 901 + j * 10 + len(mongo_r.get('failed_matches', [])) + k,
                                "steps": []
                            })

                    a_step = {
                        "name": f"{'✓' if a_ok else '✗'} {a_name}: {detail}",
                        "status": "passed" if a_ok else "failed",
                        "stage": "finished",
                        "start": test_start + 900 + j * 10,
                        "stop": test_start + 910 + j * 10,
                        "steps": mongo_sub_steps
                    }
                    if not a_ok and assertion.get('error'):
                        a_step["statusDetails"] = {"message": assertion.get('error'), "trace": ""}
                    assertion_steps.append(a_step)

                verify_step = {
                    "name": "验证响应",
                    "status": "passed" if result.get('passed', False) else "failed",
                    "stage": "finished",
                    "start": test_start + 800,
                    "stop": test_stop,
                    "description": resp_summary,
                    "steps": assertion_steps
                }

                request_result = {
                    "uuid": f"{execution.id}-{i}",
                    "name": result.get('name', f'测试请求 {i+1}'),
                    "status": "passed" if result.get('passed', False) else "failed",
                    "stage": "finished",
                    "start": test_start,
                    "stop": test_stop,
                    "description": f"{result.get('method', 'GET')} {result.get('url', '')}",
                    "historyId": f"{execution.test_suite.id}-{i}",
                    "fullName": f"{execution.test_suite.name} / {result.get('name', f'请求 {i+1}')}",
                    "links": [],
                    "labels": [
                        {"name": "suite",      "value": execution.test_suite.name},
                        {"name": "testClass",  "value": execution.test_suite.name},
                        {"name": "package",    "value": "api_testing"},
                        {"name": "project",    "value": execution.test_suite.project.name}
                    ],
                    "parameters": parameters,
                    "steps": [send_step, verify_step]
                }

                if result.get('error'):
                    request_result["statusDetails"] = {
                        "message": result.get('error'),
                        "trace": resp_body_preview if resp_body_preview else ""
                    }

                request_file_path = os.path.join(report_dir, f'{execution.id}-{i}-result.json')
                with open(request_file_path, 'w', encoding='utf-8') as f:
                    json.dump(request_result, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"生成测试结果文件失败: {str(e)}", exc_info=True)
            raise


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """用户列表接口，用于项目成员选择"""
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']


class NotificationManager:
    """通知管理器 - 处理邮件和Webhook通知"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_notification(self, task, execution_log, success=True):
        """发送通知"""
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            self.logger.info(f"任务: {task}, execution_log: {execution_log}")
            self.logger.info(f"发送通知 - 任务: {task.name}, 状态: {'成功' if success else '失败'}")

            notification_setting = None
            if hasattr(task, 'notification_settings'):
                try:
                    notification_setting = task.notification_settings.first()
                except Exception as e:
                    self.logger.error(f"获取任务通知设置时出错: {e}")
                    return

            if not notification_setting or not notification_setting.is_enabled:
                self.logger.info(f"任务 {task.id} 的通知设置未启用或不存在")
                return

            execution_status = 'success' if success else 'failed'
            if not notification_setting.should_notify(execution_status):
                self.logger.info(f"根据执行状态 {execution_status}，不应该发送通知")
                return

            notification_config = notification_setting.get_notification_config()
            self.logger.info(f"notification_setting: {notification_setting}")
            self.logger.info(f"notification_config: {notification_config}")
            has_config = notification_config is not None
            has_custom_bots = bool(notification_setting.custom_webhook_bots)
            has_custom_recipients = notification_setting.custom_recipients.exists()

            # 当通知类型包含 webhook 时，还需检查是否存在任何激活的统一 Webhook 配置，
            # _send_webhook_notification 会独立查询所有激活配置，不依赖 FK 关联
            has_unified_webhook = False
            if notification_setting.notification_type in ['webhook', 'both']:
                try:
                    from apps.core.models import UnifiedNotificationConfig
                    has_unified_webhook = UnifiedNotificationConfig.objects.filter(
                        config_type__in=['webhook_wechat', 'webhook_feishu', 'webhook_dingtalk'],
                        is_active=True
                    ).exists()
                except Exception as e:
                    self.logger.warning(f"检查统一Webhook配置时出错: {e}")

            if not (has_config or has_custom_bots or has_custom_recipients or has_unified_webhook):
                self.logger.warning("没有找到通知配置且无自定义设置")
                return

            if notification_setting.notification_type in ['email', 'both']:
                self._send_email_notification(task, execution_log, notification_setting, notification_config, success)

            if notification_setting.notification_type in ['webhook', 'both']:
                self._send_webhook_notification(task, execution_log, notification_setting, notification_config, success)

        except Exception as e:
            self.logger.error(f"发送通知失败: {str(e)}", exc_info=True)

    def _send_email_notification(self, task, execution_log, notification_setting, notification_config, success):
        """发送邮件通知"""
        try:
            from django.core.mail import send_mail
            from django.conf import settings

            self.logger.info("开始发送邮件通知")

            subject = f"定时任务执行{'成功' if success else '失败'}: {task.name}"

            summary_info = '无详细信息'
            if execution_log.result:
                result_data = execution_log.result
                summary_fields = {
                    'success': result_data.get('success'),
                    'execution_id': result_data.get('execution_id'),
                    'passed_count': result_data.get('passed_count'),
                    'failed_count': result_data.get('failed_count'),
                    'total_count': result_data.get('total_count')
                }
                summary_info = '\n'.join([f'{k}: {v}' for k, v in summary_fields.items() if v is not None])

            message = f"""
            任务名称: {task.name}
            执行状态: {'成功' if success else '失败'}
            执行时间: {execution_log.created_at.strftime('%Y-%m-%d %H:%M:%S')}
            任务类型: {'测试套件执行' if task.task_type == 'TEST_SUITE' else 'API请求执行'}

            执行概要:
            {summary_info}

            错误信息:
            {execution_log.error_message if execution_log.error_message else '无错误信息'}
            """

            recipients = []
            if notification_setting.custom_recipients.exists():
                recipients = [user.email for user in notification_setting.custom_recipients.all() if user.email]

            if hasattr(task, 'notify_emails') and task.notify_emails:
                if isinstance(task.notify_emails, list):
                    recipients.extend(task.notify_emails)
                else:
                    recipients.append(task.notify_emails)

            recipients = list(set(recipients))

            if not recipients:
                self.logger.warning("没有找到任何邮件收件人")
                return

            from_email = settings.DEFAULT_FROM_EMAIL
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipients,
                fail_silently=False,
            )
            self.logger.info("邮件发送成功")

            from .models import NotificationLog
            NotificationLog.objects.create(
                task=task,
                task_name=task.name,
                task_type=task.task_type,
                notification_type='task_execution',
                sender_name='系统邮件通知',
                sender_email=from_email,
                recipient_info=[{'email': email} for email in recipients],
                notification_content=message,
                status='success',
                sent_at=timezone.now()
            )

        except Exception as e:
            self.logger.error(f"发送邮件通知失败: {str(e)}", exc_info=True)

    def _send_webhook_notification(self, task, execution_log, notification_setting, notification_config, success):
        """发送Webhook通知"""
        try:
            import requests
            import json
            from datetime import datetime

            self.logger.info("开始发送Webhook通知")

            all_webhook_bots = []

            try:
                from apps.core.models import UnifiedNotificationConfig
                all_webhook_configs = UnifiedNotificationConfig.objects.filter(
                    config_type__in=['webhook_wechat', 'webhook_feishu', 'webhook_dingtalk'],
                    is_active=True
                )

                for config in all_webhook_configs:
                    bots = config.get_webhook_bots()
                    for bot in bots:
                        if bot.get('enabled', True) and bot.get('enable_api_testing', True):
                            all_webhook_bots.append(bot)
            except ImportError:
                self.logger.warning("无法导入统一配置，尝试使用API测试模块配置")
                if notification_config:
                    bots = notification_config.get_webhook_bots()
                    all_webhook_bots.extend([b for b in bots if b.get('enabled', True)])
            except Exception as e:
                self.logger.error(f"获取统一配置时出错: {e}")

            if notification_setting.custom_webhook_bots:
                for bot_type, bot_config in notification_setting.custom_webhook_bots.items():
                    bot_data = {
                        'type': bot_type,
                        'name': bot_config.get('name', f'自定义{bot_type}机器人'),
                        'webhook_url': bot_config.get('webhook_url'),
                        'enabled': bot_config.get('enabled', True)
                    }
                    if bot_type == 'dingtalk' and bot_config.get('secret'):
                        bot_data['secret'] = bot_config.get('secret')
                    elif bot_type == 'feishu' and bot_config.get('secret'):
                        bot_data['secret'] = bot_config.get('secret')

                    if bot_data.get('enabled', True) and bot_data.get('webhook_url'):
                        all_webhook_bots.append(bot_data)

            if not all_webhook_bots:
                self.logger.warning("没有找到任何启用的webhook机器人配置")
                return

            status_text = '成功' if success else '失败'

            for bot in all_webhook_bots:
                self._send_single_webhook(bot, task, execution_log, status_text, success)

        except Exception as e:
            self.logger.error(f"发送Webhook通知失败: {str(e)}", exc_info=True)

    def _send_single_webhook(self, bot, task, execution_log, status_text, success):
        """发送单个Webhook通知，兼容有签名和无签名的飞书/钉钉"""
        import requests
        import json
        import time
        import hmac
        import hashlib
        import base64
        import urllib.parse
        from datetime import datetime

        bot_type = bot.get('type', 'unknown')
        webhook_url = bot['webhook_url']

        message_data = self._build_webhook_message(bot_type, task, execution_log, status_text, success)

        # 飞书签名：timestamp(秒) 和 sign 必须放在请求体中，不能加到 URL
        if bot_type in ['feishu', 'lark'] and bot.get('secret'):
            timestamp = str(int(time.time()))
            string_to_sign = f'{timestamp}\n{bot["secret"]}'
            hmac_code = hmac.new(string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
            sign = base64.b64encode(hmac_code).decode('utf-8')
            message_data['timestamp'] = timestamp
            message_data['sign'] = sign
        else:
            # 钉钉等其他类型签名加到 URL
            webhook_url = self._add_signature_to_url(bot_type, bot, webhook_url)

        try:
            response = requests.post(
                webhook_url,
                json=message_data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            # 飞书/钉钉始终返回 HTTP 200，实际成功与否需检查响应体中的业务 code
            resp_text = response.text[:200]
            try:
                resp_json = response.json()
                biz_code = resp_json.get('code', resp_json.get('errcode', 0))
            except Exception:
                resp_json = {}
                biz_code = 0

            notify_status = 'success' if biz_code == 0 else 'failed'
            if notify_status == 'success':
                self.logger.info(f"Webhook通知发送成功 - {bot_type}: {response.status_code}, 响应体: {resp_text}")
            else:
                self.logger.error(f"Webhook通知业务失败 - {bot_type}: code={biz_code}, 响应体: {resp_text}")

            from .models import NotificationLog
            NotificationLog.objects.create(
                task=task,
                task_name=task.name,
                task_type=task.task_type,
                notification_type='task_execution',
                sender_name=f'系统Webhook通知-{bot_type}',
                sender_email='',
                recipient_info=[],
                webhook_bot_info={
                    'bot_type': bot_type,
                    'bot_name': bot.get('name', 'Unknown'),
                    'webhook_url': webhook_url[:50] + '...' if len(webhook_url) > 50 else webhook_url
                },
                notification_content=json.dumps(message_data, ensure_ascii=False),
                status=notify_status,
                error_message='' if notify_status == 'success' else resp_text,
                sent_at=timezone.now(),
                response_info={
                    'status_code': response.status_code,
                    'response_text': response.text[:500]
                }
            )

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Webhook通知发送失败 - {bot_type}: {str(e)}")

            try:
                from .models import NotificationLog
                NotificationLog.objects.create(
                    task=task,
                    task_name=task.name,
                    task_type=task.task_type,
                    notification_type='task_execution',
                    sender_name=f'系统Webhook通知-{bot_type}',
                    sender_email='',
                    recipient_info=[],
                    webhook_bot_info={
                        'bot_type': bot_type,
                        'bot_name': bot.get('name', 'Unknown'),
                        'webhook_url': webhook_url[:50] + '...' if len(webhook_url) > 50 else webhook_url
                    },
                    notification_content=json.dumps(message_data, ensure_ascii=False),
                    status='failed',
                    error_message=str(e),
                    sent_at=timezone.now()
                )
            except:
                pass

    def _add_signature_to_url(self, bot_type, bot, webhook_url):
        """根据机器人类型添加签名参数到URL"""
        import time
        import hmac
        import hashlib
        import base64
        import urllib.parse

        # 如果没有secret，直接返回原URL
        if not bot.get('secret'):
            return webhook_url

        timestamp = str(round(time.time() * 1000))

        # 钉钉签名（飞书签名由 _send_single_webhook 直接写入请求体，不在此处处理）
        if bot_type == 'dingtalk':
            string_to_sign = f'{timestamp}\n{bot["secret"]}'
            string_to_sign_enc = string_to_sign.encode('utf-8')
            secret_enc = bot['secret'].encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode('utf-8'))

            separator = '&' if '?' in webhook_url else '?'
            webhook_url += f'{separator}timestamp={timestamp}&sign={sign}'

        return webhook_url

    def _build_webhook_message(self, bot_type, task, execution_log, status_text, success):
        """构建卡片格式Webhook消息"""
        import socket
        from urllib.parse import urlparse, urlunparse
        from django.conf import settings as django_settings

        exec_time = execution_log.created_at.strftime('%Y-%m-%d %H:%M:%S')
        task_type_text = '接口测试套件' if task.task_type == 'TEST_SUITE' else 'API请求'

        # 获取项目名称
        project_name = ''
        try:
            if task.test_suite:
                project_name = task.test_suite.project.name
            elif task.api_request and task.api_request.collection:
                project_name = task.api_request.collection.project.name
        except Exception:
            pass

        title = f"{'✅' if success else '❌'} {project_name + ' - ' if project_name else ''}{task_type_text}接口测试报告"

        result_data = execution_log.result or {}
        total = result_data.get('total_count', 0) or 0
        passed = result_data.get('passed_count', 0) or 0
        failed = result_data.get('failed_count', 0) or 0
        execution_id = result_data.get('execution_id')
        pass_rate = f"{round(passed / total * 100)}%" if total else 'N/A'

        # 自动将 localhost/127.0.0.1 替换为本机对外 IP，确保外网（飞书/钉钉）可访问
        configured_url = getattr(django_settings, 'SITE_BASE_URL', 'http://localhost:3000')
        parsed = urlparse(configured_url)
        if parsed.hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
            try:
                # 通过 UDP 探测对外路由接口，获取本机局域网/公网 IP
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as _s:
                    _s.settimeout(1)
                    _s.connect(('8.8.8.8', 80))
                    local_ip = _s.getsockname()[0]
            except Exception:
                try:
                    local_ip = socket.gethostbyname(socket.gethostname())
                except Exception:
                    local_ip = parsed.hostname  # 保持原值
            port_part = f":{parsed.port}" if parsed.port else ''
            site_url = f"{parsed.scheme}://{local_ip}{port_part}"
        else:
            site_url = configured_url

        # 链接指向 Allure 摘要报告页，与"生成并查看报告"入口一致
        report_url = (
            f"{site_url}/media/allure-reports/execution_{execution_id}/summary.html"
            if execution_id else site_url
        )

        if bot_type in ['feishu', 'lark']:
            elements = [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务名称**\n{task.name}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行状态**\n{status_text}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行时间**\n{exec_time}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务类型**\n{task_type_text}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**总用例数**\n{total}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**通过 / 失败**\n{passed} / {failed}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**通过率**\n{pass_rate}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**所属项目**\n{project_name or '-'}"}},
                    ]
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看测试报告"},
                            "url": report_url,
                            "type": "primary"
                        }
                    ]
                }
            ]
            if execution_log.error_message:
                elements.insert(1, {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**错误信息**\n{execution_log.error_message[:200]}"}
                })
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "template": "green" if success else "red",
                        "title": {"tag": "plain_text", "content": title}
                    },
                    "elements": elements
                }
            }

        elif bot_type == 'wechat':
            status_color = 'info' if success else 'warning'
            content = (
                f"## {title}\n\n"
                f"> **任务名称**: {task.name}\n"
                f"> **执行状态**: <font color=\"{status_color}\">{status_text}</font>\n"
                f"> **执行时间**: {exec_time}\n"
                f"> **任务类型**: {task_type_text}\n"
                f"> **所属项目**: {project_name or '-'}\n"
                f"> **总用例数**: {total}\n"
                f"> **通过 / 失败**: {passed} / {failed}\n"
                f"> **通过率**: {pass_rate}\n"
            )
            if execution_log.error_message:
                content += f"> **错误信息**: {execution_log.error_message[:200]}\n"
            content += f"\n[查看测试报告]({report_url})"
            return {
                "msgtype": "markdown",
                "markdown": {"content": content}
            }

        elif bot_type == 'dingtalk':
            text = (
                f"### {title}\n\n"
                f"**任务名称**: {task.name}\n\n"
                f"**执行状态**: {status_text}\n\n"
                f"**执行时间**: {exec_time}\n\n"
                f"**任务类型**: {task_type_text}\n\n"
                f"**所属项目**: {project_name or '-'}\n\n"
                f"**总用例数**: {total} | **通过**: {passed} | **失败**: {failed} | **通过率**: {pass_rate}\n\n"
            )
            if execution_log.error_message:
                text += f"**错误信息**: {execution_log.error_message[:200]}\n\n"
            return {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": text,
                    "singleTitle": "查看测试报告",
                    "singleURL": report_url
                }
            }

        else:
            return {
                "text": f"{title}\n任务名称: {task.name}\n执行状态: {status_text}\n执行时间: {exec_time}\n总用例: {total} 通过: {passed} 失败: {failed} 通过率: {pass_rate}"
            }


class ScheduledTaskViewSet(viewsets.ModelViewSet):
    """定时任务视图集"""
    queryset = ScheduledTask.objects.all()
    serializer_class = ScheduledTaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'last_run_time']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return ScheduledTask.objects.filter(
            models.Q(visibility='all') | models.Q(created_by=user)
        )

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """立即执行定时任务"""
        logger.info("=== run_now 方法被调用 ===")

        task = self.get_object()
        if not request.user.is_staff and task.created_by != request.user:
            logger.info("权限检查失败")
            return Response(
                {'error': '无权执行此任务'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            execution_log = TaskExecutionLog.objects.create(
                task=task,
                status='PENDING',
                executed_by=request.user
            )
            logger.info(f"创建执行日志: {execution_log.id}")

            logger.info("调用 _execute_task_async 方法")
            self._execute_task_async(task, execution_log)

            logger.info("任务开始执行")
            return Response(
                {'message': '任务已开始执行', 'execution_id': execution_log.id},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {'error': f'执行任务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """激活定时任务"""
        task = self.get_object()

        if task.status == 'ACTIVE':
            return Response(
                {'error': '任务已经是激活状态'},
                status=status.HTTP_400_BAD_REQUEST
            )

        task.status = 'ACTIVE'
        task.next_run_time = task.calculate_next_run()
        task.save()

        return Response(
            {'message': '任务已激活', 'next_run_time': task.next_run_time},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """暂停定时任务"""
        task = self.get_object()

        if task.status == 'PAUSED':
            return Response(
                {'error': '任务已经是暂停状态'},
                status=status.HTTP_400_BAD_REQUEST
            )

        task.status = 'PAUSED'
        task.next_run_time = None
        task.save()

        return Response(
            {'message': '任务已暂停'},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['get'])
    def execution_logs(self, request, pk=None):
        """获取任务执行日志"""
        task = self.get_object()

        if not request.user.is_staff and task.created_by != request.user:
            return Response(
                {'error': '无权查看此任务的执行日志'},
                status=status.HTTP_403_FORBIDDEN
            )

        logs = TaskExecutionLog.objects.filter(task=task).order_by('-created_at')
        page = self.paginate_queryset(logs)

        if page is not None:
            serializer = TaskExecutionLogSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = TaskExecutionLogSerializer(logs, many=True)
        return Response(serializer.data)

    def _execute_task_async(self, task, execution_log):
        """异步执行任务"""
        task_id = task.id
        execution_log_id = execution_log.id

        def execute():
            from django.db import close_old_connections
            # 关闭请求线程遗留的旧连接，让子线程建立自己的数据库连接
            close_old_connections()

            # 在子线程内重新获取对象，确保使用新鲜的数据库连接，
            # 避免请求结束后连接被回收导致关联查询（通知配置、自定义设置等）失败
            task = ScheduledTask.objects.get(id=task_id)
            execution_log = TaskExecutionLog.objects.get(id=execution_log_id)

            try:
                execution_log.status = 'RUNNING'
                execution_log.start_time = timezone.now()
                execution_log.save()

                if task.task_type == 'TEST_SUITE':
                    result = self._execute_test_suite(task)
                elif task.task_type == 'API_REQUEST':
                    result = self._execute_api_request(task)
                else:
                    raise ValueError(f"未知的任务类型: {task.task_type}")

                execution_log.status = 'COMPLETED'
                execution_log.end_time = timezone.now()
                execution_log.result = result
                execution_log.save()

                task.update_run_stats(success=True)
                task.last_result = result
                task.save()

                # 自动生成 Allure 报告，确保通知链接可访问
                if task.task_type == 'TEST_SUITE' and result.get('execution_id'):
                    try:
                        from .models import TestExecution as _TE
                        _exec_obj = _TE.objects.get(id=result['execution_id'])
                        _evt = TestExecutionViewSet()
                        _results_dir = os.path.join(settings.MEDIA_ROOT, 'allure-results', f'execution_{_exec_obj.id}')
                        os.makedirs(_results_dir, exist_ok=True)
                        _report_dir = os.path.join(settings.MEDIA_ROOT, 'allure-reports', f'execution_{_exec_obj.id}')
                        os.makedirs(_report_dir, exist_ok=True)
                        _evt._generate_test_result_files(_exec_obj, _results_dir)
                        _evt._generate_allure_report_with_fallback(_exec_obj, _results_dir, _report_dir)
                        _evt._generate_summary_html(_exec_obj, _report_dir)
                        logger.info(f"自动生成Allure报告成功: execution_{_exec_obj.id}")
                    except Exception as _report_err:
                        logger.warning(f"自动生成Allure报告失败（不影响通知发送）: {_report_err}")

                # 发送通知
                logger.info("=== 开始检查发送成功通知 ===")
                notification_manager = NotificationManager()
                notification_manager.send_notification(task, execution_log, success=True)
                logger.info("=== 结束检查发送成功通知 ===")

            except Exception as e:
                execution_log.status = 'FAILED'
                execution_log.end_time = timezone.now()
                execution_log.error_message = str(e)
                execution_log.save()

                task.update_run_stats(success=False)
                task.error_message = str(e)
                task.save()

                # 失败时也尝试生成报告（可能有部分结果数据）
                if task.task_type == 'TEST_SUITE' and execution_log.result and execution_log.result.get('execution_id'):
                    try:
                        from .models import TestExecution as _TE
                        _exec_obj = _TE.objects.get(id=execution_log.result['execution_id'])
                        _evt = TestExecutionViewSet()
                        _results_dir = os.path.join(settings.MEDIA_ROOT, 'allure-results', f'execution_{_exec_obj.id}')
                        os.makedirs(_results_dir, exist_ok=True)
                        _report_dir = os.path.join(settings.MEDIA_ROOT, 'allure-reports', f'execution_{_exec_obj.id}')
                        os.makedirs(_report_dir, exist_ok=True)
                        _evt._generate_test_result_files(_exec_obj, _results_dir)
                        _evt._generate_allure_report_with_fallback(_exec_obj, _results_dir, _report_dir)
                        _evt._generate_summary_html(_exec_obj, _report_dir)
                    except Exception as _report_err:
                        logger.warning(f"自动生成失败Allure报告失败: {_report_err}")

                logger.info("=== 开始检查发送失败通知 ===")
                notification_manager = NotificationManager()
                notification_manager.send_notification(task, execution_log, success=False)
                logger.info("=== 结束检查发送失败通知 ===")

        thread = threading.Thread(target=execute)
        thread.daemon = True
        thread.start()

    def _execute_test_suite(self, task):
        """执行测试套件"""
        from .utils import execute_test_suite

        return execute_test_suite(
            task.test_suite,
            task.environment,
            task.created_by
        )

    def _execute_api_request(self, task):
        """执行API请求"""
        from .utils import execute_api_request

        return execute_api_request(
            task.api_request,
            task.environment,
            task.created_by
        )


class TaskExecutionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """任务执行日志视图集"""
    queryset = TaskExecutionLog.objects.all()
    serializer_class = TaskExecutionLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['task', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return TaskExecutionLog.objects.filter(
            task__created_by=user
        ).select_related('task', 'executed_by')


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """通知日志视图集"""
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'notification_type']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return NotificationLog.objects.filter(
            models.Q(
                task__test_suite__project__in=ApiProject.objects.filter(
                    models.Q(visibility='all') |
                    models.Q(owner=user) |
                    models.Q(members=user)
                )
            ) | models.Q(
                task__api_request__collection__project__in=ApiProject.objects.filter(
                    models.Q(visibility='all') |
                    models.Q(owner=user) |
                    models.Q(members=user)
                )
            ) | models.Q(
                task__created_by=user
            )
        ).distinct()

    @action(detail=True, methods=['get'], url_path='detail')
    def get_notification_detail(self, request, pk=None):
        """获取通知详情"""
        notification = self.get_object()
        serializer = NotificationLogDetailSerializer(notification)
        return Response(serializer.data)


class TaskNotificationSettingViewSet(viewsets.ModelViewSet):
    """定时任务通知设置视图集"""
    queryset = TaskNotificationSetting.objects.all()
    serializer_class = TaskNotificationSettingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['task', 'is_enabled']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return TaskNotificationSetting.objects.filter(
            models.Q(
                task__test_suite__project__in=ApiProject.objects.filter(
                    models.Q(visibility='all') |
                    models.Q(owner=user) |
                    models.Q(members=user)
                )
            ) | models.Q(
                task__api_request__collection__project__in=ApiProject.objects.filter(
                    models.Q(visibility='all') |
                    models.Q(owner=user) |
                    models.Q(members=user)
                )
            ) | models.Q(
                task__created_by=user
            )
        ).distinct()

    @action(detail=True, methods=['post'], url_path='update-settings')
    def update_notification_settings(self, request, pk=None):
        """更新通知设置"""
        setting = self.get_object()
        serializer = TaskNotificationSettingDetailSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)


class OperationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """操作日志视图集"""
    queryset = OperationLog.objects.all()
    serializer_class = OperationLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['operation_type', 'resource_type', 'user']
    ordering = ['-created_at']

    def get_queryset(self):
        return OperationLog.objects.all().order_by('-created_at')


class ApiDashboardViewSet(viewsets.ViewSet):
    """API测试仪表盘视图集"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """获取仪表盘统计数据"""
        user = request.user

        accessible_projects = ApiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        project_ids = accessible_projects.values_list('id', flat=True)

        project_count = accessible_projects.count()
        interface_count = ApiRequest.objects.filter(
            collection__project_id__in=project_ids
        ).count()
        suite_count = TestSuite.objects.filter(
            project_id__in=project_ids
        ).count()
        history_count = RequestHistory.objects.filter(
            request__collection__project_id__in=project_ids
        ).count()

        return Response({
            'project_count': project_count,
            'interface_count': interface_count,
            'suite_count': suite_count,
            'history_count': history_count
        })


class AIServiceConfigViewSet(viewsets.ModelViewSet):
    """AI服务配置视图集"""
    queryset = AIServiceConfig.objects.all()
    serializer_class = AIServiceConfigSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['service_type', 'role', 'is_active']
    search_fields = ['name', 'model_name']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return AIServiceConfig.objects.filter(created_by=user)

    @action(detail=False, methods=['post'])
    def test_connection(self, request):
        """测试AI服务连接"""
        config_id = request.data.get('config_id')
        if not config_id:
            return Response({'error': '请提供配置ID'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            config = AIServiceConfig.objects.get(id=config_id, created_by=request.user)
        except AIServiceConfig.DoesNotExist:
            return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)

        try:
            headers = {
                'Authorization': f'Bearer {config.api_key}',
                'Content-Type': 'application/json'
            }

            test_data = {
                'model': config.model_name,
                'messages': [{'role': 'user', 'content': 'Hello'}],
                'max_tokens': 10
            }

            response = requests.post(
                f"{config.base_url}/chat/completions",
                headers=headers,
                json=test_data,
                timeout=10
            )

            if response.status_code == 200:
                return Response({'message': '连接测试成功', 'status': 'success'})
            else:
                return Response({
                    'error': f'连接测试失败: {response.status_code}',
                    'details': response.text
                }, status=status.HTTP_400_BAD_REQUEST)

        except requests.exceptions.Timeout:
            return Response({'error': '连接超时'}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return Response({'error': f'连接失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': f'未知错误: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _call_ai_service(self, config, prompt):
        """调用AI服务"""
        headers = {
            'Authorization': f'Bearer {config.api_key}',
            'Content-Type': 'application/json'
        }

        ai_data = {
            'model': config.model_name,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': config.max_tokens,
            'temperature': config.temperature
        }

        response = requests.post(
            f"{config.base_url}/chat/completions",
            headers=headers,
            json=ai_data,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"AI服务调用失败: {response.status_code} - {response.text}")

        return response.json()

    @action(detail=False, methods=['post'])
    def complete_parameter_descriptions(self, request):
        """使用AI自动补全参数描述"""
        request_id = request.data.get('request_id')
        if not request_id:
            return Response({'error': '请提供请求ID'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            api_request = ApiRequest.objects.get(id=request_id)
        except ApiRequest.DoesNotExist:
            return Response({'error': '请求不存在'}, status=status.HTTP_404_NOT_FOUND)

        try:
            config = AIServiceConfig.objects.filter(
                role='description',
                is_active=True
            ).first()

            if not config:
                return Response({'error': '未找到可用的参数描述补全AI配置'}, status=status.HTTP_400_BAD_REQUEST)

            request_info = {
                'name': api_request.name,
                'description': api_request.description,
                'method': api_request.method,
                'url': api_request.url,
                'headers': api_request.headers,
                'params': api_request.params,
                'body': api_request.body
            }

            prompt = f"""请为以下API请求的参数生成详细的描述说明：

接口名称: {request_info['name']}
接口描述: {request_info['description']}
请求方法: {request_info['method']}
请求URL: {request_info['url']}

请求头参数:
{json.dumps(request_info['headers'], ensure_ascii=False, indent=2)}

URL参数:
{json.dumps(request_info['params'], ensure_ascii=False, indent=2)}

请求体参数:
{json.dumps(request_info['body'], ensure_ascii=False, indent=2)}

请为每个参数生成详细的描述说明，包括：
1. 参数用途
2. 数据类型
3. 是否必填
4. 取值范围或示例值
5. 其他注意事项

请返回JSON格式的结果，格式如下：
{{
  "headers": {{
    "参数名": "参数描述"
  }},
  "params": {{
    "参数名": "参数描述"
  }},
  "body": {{
    "参数名": "参数描述"
  }}
}}"""

            result = self._call_ai_service(config, prompt)
            content = result['choices'][0]['message']['content']

            try:
                descriptions = json.loads(content)
                return Response({'descriptions': descriptions})
            except json.JSONDecodeError:
                return Response({'descriptions': {}, 'raw_content': content})

        except requests.exceptions.Timeout:
            return Response({'error': 'AI服务调用超时'}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return Response({'error': f'AI服务调用失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': f'未知错误: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def generate_mock_data(self, request):
        """使用AI生成模拟数据"""
        schema = request.data.get('schema', {})
        count = request.data.get('count', 1)
        if not schema:
            return Response({'error': '请提供数据结构定义'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            config = AIServiceConfig.objects.filter(
                role='mock_data',
                is_active=True
            ).first()

            if not config:
                return Response({'error': '未找到可用的模拟数据生成AI配置'}, status=status.HTTP_400_BAD_REQUEST)

            prompt = f"""请根据以下数据结构定义，生成{count}条符合该结构的模拟数据：

数据结构定义：
{json.dumps(schema, ensure_ascii=False, indent=2)}

要求：
1. 数据必须符合给定的结构定义
2. 字符串字段生成有意义的中文内容
3. 数值字段生成合理的数值
4. 日期字段生成有效的日期时间
5. 布尔字段随机生成true/false
6. 数组字段生成适当数量的元素

请返回JSON数组格式的结果。"""

            result = self._call_ai_service(config, prompt)
            content = result['choices'][0]['message']['content']

            try:
                mock_data = json.loads(content)
                return Response({'data': mock_data})
            except json.JSONDecodeError:
                return Response({'data': [], 'raw_content': content})

        except requests.exceptions.Timeout:
            return Response({'error': 'AI服务调用超时'}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return Response({'error': f'AI服务调用失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': f'未知错误: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def normalize_parameter_names(self, request):
        """使用AI规范化参数名称"""
        parameters = request.data.get('parameters', [])
        if not parameters:
            return Response({'error': '请提供参数列表'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            config = AIServiceConfig.objects.filter(
                role='naming',
                is_active=True
            ).first()

            if not config:
                return Response({'error': '未找到可用的参数命名规范化AI配置'}, status=status.HTTP_400_BAD_REQUEST)

            params_info = '\n'.join([f"- {param.get('key', '')}: {param.get('value', '')}" for param in parameters])

            prompt = f"""请对以下API参数名称进行规范化处理，使其符合RESTful API命名规范：

{params_info}

请返回JSON格式的结果，包含：
1. 原始参数名
2. 建议的规范化参数名（使用小写字母、下划线分隔、语义清晰）
3. 修改原因

返回格式示例：
[
  {{
    "original": "userName",
    "suggested": "user_name",
    "reason": "使用下划线分隔单词，符合Python命名规范"
  }}
]"""

            result = self._call_ai_service(config, prompt)
            content = result['choices'][0]['message']['content']

            try:
                suggestions = json.loads(content)
                return Response({'suggestions': suggestions})
            except json.JSONDecodeError:
                return Response({'suggestions': [], 'raw_content': content})

        except requests.exceptions.Timeout:
            return Response({'error': 'AI服务调用超时'}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return Response({'error': f'AI服务调用失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': f'未知错误: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def extract_documentation(self, request):
        """使用AI提取API文档"""
        request_id = request.data.get('request_id')
        if not request_id:
            return Response({'error': '请提供请求ID'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            api_request = ApiRequest.objects.get(id=request_id)
        except ApiRequest.DoesNotExist:
            return Response({'error': '请求不存在'}, status=status.HTTP_404_NOT_FOUND)

        try:
            config = AIServiceConfig.objects.filter(
                role='doc_extractor',
                is_active=True
            ).first()

            if not config:
                return Response({'error': '未找到可用的API文档提取AI配置'}, status=status.HTTP_400_BAD_REQUEST)

            request_data = {
                'method': api_request.method,
                'url': api_request.url,
                'headers': api_request.headers,
                'params': api_request.params,
                'body': api_request.body,
                'description': api_request.description
            }

            prompt = f"""请根据以下API请求信息，生成详细的API文档：

请求方法: {request_data['method']}
请求URL: {request_data['url']}
请求头: {json.dumps(request_data['headers'], ensure_ascii=False)}
URL参数: {json.dumps(request_data['params'], ensure_ascii=False)}
请求体: {json.dumps(request_data['body'], ensure_ascii=False)}
描述: {request_data['description']}

请生成包含以下内容的API文档：
1. 接口概述
2. 请求参数说明（包括路径参数、查询参数、请求头、请求体）
3. 响应示例
4. 错误码说明

请以Markdown格式返回文档内容。"""

            result = self._call_ai_service(config, prompt)
            documentation = result['choices'][0]['message']['content']

            return Response({'documentation': documentation})

        except requests.exceptions.Timeout:
            return Response({'error': 'AI服务调用超时'}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return Response({'error': f'AI服务调用失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': f'未知错误: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

