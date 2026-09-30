"""操作日志视图"""
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated

from ..models import ApiProject, OperationLog
from ..serializers import OperationLogSerializer


class OperationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """操作日志视图集：只返回本人负责/参与的项目内的日志，以及本人自己的操作"""
    queryset = OperationLog.objects.all()
    serializer_class = OperationLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['operation_type', 'resource_type', 'user', 'project']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        # 注意这里只按"负责人/成员"判断，公开（visibility='all'）但未加入的项目不算"本项目"
        member_project_ids = ApiProject.objects.filter(Q(owner=user) | Q(members=user)).values('id')
        return OperationLog.objects.filter(
            Q(project_id__in=member_project_ids) | Q(user=user)
        ).select_related('user').order_by('-created_at')
