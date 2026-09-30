"""API测试仪表盘视图"""
from django.db import models
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import ApiProject, ApiRequest, TestSuite, RequestHistory


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
