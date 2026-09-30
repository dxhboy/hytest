"""定时任务、执行日志与通知相关视图"""
import logging

from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import (
    ApiProject, ScheduledTask, TaskExecutionLog, NotificationLog, TaskNotificationSetting,
)
from ..serializers import (
    ScheduledTaskSerializer, TaskExecutionLogSerializer,
    NotificationLogSerializer, NotificationLogDetailSerializer,
    TaskNotificationSettingSerializer, TaskNotificationSettingDetailSerializer,
)
from ..access import visible_scheduled_task_q

# 获取logger实例
logger = logging.getLogger(__name__)


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
        return ScheduledTask.objects.filter(visible_scheduled_task_q(user)).distinct()

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
            from ..tasks import enqueue_scheduled_task
            execution_log = enqueue_scheduled_task(task, executed_by=request.user)
            logger.info(f"定时任务 {task.id} 已提交到任务队列，执行日志: {execution_log.id}")
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
        ).distinct().select_related('notification_config').prefetch_related('custom_recipients')

    @action(detail=True, methods=['post'], url_path='update-settings')
    def update_notification_settings(self, request, pk=None):
        """更新通知设置"""
        setting = self.get_object()
        serializer = TaskNotificationSettingDetailSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)
