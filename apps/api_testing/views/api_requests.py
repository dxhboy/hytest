"""API请求与请求历史视图"""
import logging

from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import ApiCollection, ApiRequest, Environment, RequestHistory
from ..serializers import ApiRequestSerializer, RequestHistorySerializer
from ..utils import execute_assertions
from ..operation_logger import log_operation
from ..variable_resolver import VariableResolver
from ..services.masking import _mask_sensitive_data
from ..services.request_executor import RequestExecutor
from ..access import visible_request_q
from apps.core.variable_resolver import run_pre_request_script, run_tests_script
from .base import StandardPagination, BaseViewSetMixin

# 获取logger实例
logger = logging.getLogger(__name__)


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

        # 本人创建，或公开且所属项目对当前用户可见（见 access.visible_request_q）
        queryset = ApiRequest.objects.filter(visible_request_q(user)).distinct()

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
            models.Q(executed_by=user) | visible_request_q(user, prefix='request__')
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
