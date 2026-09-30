"""测试执行记录视图（含 Allure 报告生成入口）"""
import os
import logging

from django.conf import settings
from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import TestExecution
from ..serializers import TestExecutionSerializer
from ..services import allure_report
from ..access import visible_suite_q
from .base import StandardPagination

# 获取logger实例
logger = logging.getLogger(__name__)


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
            models.Q(executed_by=user) | visible_suite_q(user, prefix='test_suite__')
        ).distinct()

    @action(detail=True, methods=['post'], url_path='generate-allure-report')
    def generate_allure_report(self, request, pk=None):
        """生成Allure报告数据"""
        execution = self.get_object()

        try:
            results_dir = os.path.join(settings.MEDIA_ROOT, 'allure-results', f'execution_{execution.id}')
            os.makedirs(results_dir, exist_ok=True)

            allure_report.generate_test_result_files(execution, results_dir)

            report_output_dir = os.path.join(settings.MEDIA_ROOT, 'allure-reports', f'execution_{execution.id}')
            os.makedirs(report_output_dir, exist_ok=True)

            allure_report.generate_allure_report_with_fallback(execution, results_dir, report_output_dir)

            summary_file = allure_report.generate_summary_html(execution, report_output_dir)

            return Response({
                'message': 'Allure报告生成成功',
                'report_url': f'/media/allure-reports/execution_{execution.id}/summary.html'
            })
        except Exception as e:
            logger.error(f"生成Allure报告失败: {str(e)}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
