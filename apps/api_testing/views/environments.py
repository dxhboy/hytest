"""环境配置视图"""
from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import ApiProject, Environment
from ..serializers import EnvironmentSerializer
from ..operation_logger import log_operation
from .base import BaseViewSetMixin


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
