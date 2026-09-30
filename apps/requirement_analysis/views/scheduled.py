"""定时用例生成任务视图"""
import logging

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import ScheduledGenerationTask
from ..serializers import ScheduledGenerationTaskSerializer

logger = logging.getLogger(__name__)

class ScheduledGenerationTaskViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduledGenerationTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ScheduledGenerationTask.objects.filter(
            created_by=self.request.user
        ).select_related('requirement_document', 'ai_model_config', 'last_run_task')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        task = self.get_object()
        task.is_active = not task.is_active
        task.save(update_fields=['is_active'])
        return Response({'is_active': task.is_active})
