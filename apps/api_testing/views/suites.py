"""测试套件视图"""
import json
import logging

from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import ApiRequest, TestSuite, TestSuiteRequest
from ..serializers import TestSuiteSerializer, TestSuiteRequestSerializer, TestExecutionSerializer
from ..operation_logger import log_operation
from ..access import visible_suite_q
from .base import BaseViewSetMixin

# 获取logger实例
logger = logging.getLogger(__name__)


class TestSuiteViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """测试套件视图集"""
    queryset = TestSuite.objects.all()
    serializer_class = TestSuiteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['project']

    def get_queryset(self):
        user = self.request.user
        return TestSuite.objects.filter(visible_suite_q(user)).distinct()

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """
        执行测试套件（异步）

        创建执行记录后提交到 Celery（api_testing.execute_test_suite），立即返回 202 与执行记录，
        前端轮询 /api/.../executions/{id}/ 直到状态不为 PENDING/RUNNING。
        执行逻辑与定时任务共用 utils.run_suite_execution。
        """
        test_suite = self.get_object()

        try:
            from ..tasks import enqueue_suite_execution
            execution = enqueue_suite_execution(test_suite, request.user)
        except Exception as e:
            logger.error(f"执行测试套件失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'执行测试套件失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        serializer = TestExecutionSerializer(execution)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

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
        return TestSuiteRequest.objects.filter(visible_suite_q(user, prefix='test_suite__')).distinct()
