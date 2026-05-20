"""
Core 应用视图
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from django.db import models as django_models
from .models import UnifiedNotificationConfig
from .serializers import UnifiedNotificationConfigSerializer

import logging
logger = logging.getLogger(__name__)


class UnifiedNotificationConfigViewSet(viewsets.ModelViewSet):
    """统一通知配置视图集"""
    queryset = UnifiedNotificationConfig.objects.all()
    serializer_class = UnifiedNotificationConfigSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['config_type', 'is_default', 'is_active', 'visibility']
    search_fields = ['name']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """仅返回当前用户有权查看的配置：所有人可见 + 自己创建的私有配置"""
        user = self.request.user
        return UnifiedNotificationConfig.objects.filter(
            django_models.Q(visibility='all') | django_models.Q(created_by=user)
        )

    def perform_create(self, serializer):
        """创建通知配置"""
        instance = serializer.save(created_by=self.request.user)
        logger.info(f"创建统一通知配置: {instance.name}")

    def perform_update(self, serializer):
        """更新通知配置（仅创建者可改）"""
        instance = self.get_object()
        if instance.created_by != self.request.user and not self.request.user.is_staff:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('只有创建者才能修改此配置')
        serializer.save()
        logger.info(f"更新统一通知配置: {instance.name}")

    def perform_destroy(self, instance):
        """删除通知配置（仅创建者可删）"""
        if instance.created_by != self.request.user and not self.request.user.is_staff:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('只有创建者才能删除此配置')
        logger.info(f"删除统一通知配置: {instance.name}")
        instance.delete()

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """设置为默认配置"""
        config = self.get_object()
        UnifiedNotificationConfig.objects.filter(is_default=True).update(is_default=False)
        config.is_default = True
        config.save()
        return Response({'message': '已设置为默认配置'})

    @action(detail=False, methods=['get'])
    def active_configs(self, request):
        """获取当前用户可见且启用的配置"""
        configs = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)
