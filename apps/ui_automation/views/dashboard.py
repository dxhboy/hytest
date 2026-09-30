"""UI 自动化仪表盘统计视图"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import models
from ..models import UiProject, TestSuite, TestExecution, TestCase, TestCaseExecution


class UiDashboardViewSet(viewsets.ViewSet):
    """UI自动化仪表盘视图集"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """获取仪表盘统计数据"""
        user = request.user

        # 获取用户可访问的项目ID列表
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        project_ids = accessible_projects.values_list('id', flat=True)

        # 统计数据
        project_count = accessible_projects.count()

        # 测试用例数量
        test_case_count = TestCase.objects.filter(project_id__in=project_ids).count()

        # 测试套件数量（包含用例总数）
        suite_count = TestSuite.objects.filter(project_id__in=project_ids).count()

        from ..models import TestSuiteTestCase
        suite_test_case_count = TestSuiteTestCase.objects.filter(
            test_suite__project_id__in=project_ids
        ).count()

        # 测试执行数量（传统+新版）
        execution_count = TestExecution.objects.filter(project_id__in=project_ids).count()
        test_case_execution_count = TestCaseExecution.objects.filter(project_id__in=project_ids).count()
        total_execution_count = execution_count + test_case_execution_count

        return Response({
            'project_count': project_count,
            'test_case_count': test_case_count,
            'suite_count': suite_test_case_count,
            'execution_count': total_execution_count
        })
