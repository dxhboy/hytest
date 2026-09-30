"""AI 智能模式用例与执行记录相关视图"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from django.utils import timezone
import logging
from ..models import UiProject, AICase, AIExecutionRecord
from ..serializers import AICaseSerializer, AIExecutionRecordSerializer

logger = logging.getLogger(__name__)


class AICaseViewSet(viewsets.ModelViewSet):
    queryset = AICase.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = AICaseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'description', 'task_description']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        # 返回用户有权限的项目下的AI用例，以及没有关联项目的AI用例
        return AICase.objects.filter(
            models.Q(project__in=accessible_projects) | models.Q(project__isnull=True)
        ).distinct()

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """执行 AI 用例"""
        ai_case = self.get_object()

        # 创建执行记录
        execution_record = AIExecutionRecord.objects.create(
            project=ai_case.project,
            ai_case=ai_case,
            case_name=ai_case.name,
            task_description=ai_case.task_description,
            status='running',
            executed_by=request.user,
            logs="正在分析任务...\n"
        )

        # 提交到 Celery 的 ai_automation 队列执行（原来是裸线程；单独的队列是为了
        # AI 任务的资源隔离，端口冲突问题已经在 ai_base.py 里修复，见 tasks.py 顶部说明。
        # 停止信号改成了纯数据库状态，见 stop_task 和 tasks.run_ai_case_task）
        from ..tasks import run_ai_case_task
        try:
            run_ai_case_task.delay(execution_record.id, ai_case.id)
        except Exception as e:
            # 提交失败时把记录标记为失败，避免永久卡在 "running"
            execution_record.status = 'failed'
            execution_record.logs += f"\n[System] 提交执行任务失败: {e}"
            execution_record.save()
            logger.error(f'提交 AI 用例执行任务失败: execution_id={execution_record.id}, error={e}')
            return Response({
                'error': f'提交执行任务失败，请检查任务队列服务是否正常: {e}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'message': 'AI 用例开始执行',
            'execution_id': execution_record.id
        })

    # 注：_process_gif_recording / _auto_mark_completed_tasks 已挪到
    # apps/ui_automation/ai_execution_helpers.py 作为模块级函数（这两个方法
    # 原本就不依赖 self.request/self.queryset，只是被误放进了 ViewSet 里，
    # 之前 AICaseViewSet 和 AIExecutionRecordViewSet 各自维护了一份逐字节相同
    # 的拷贝）。Celery 任务里直接 import 调用，不再需要"裸实例化 ViewSet"。


class AIExecutionRecordViewSet(viewsets.ModelViewSet):
    """AI执行记录视图集"""
    queryset = AIExecutionRecord.objects.all()
    serializer_class = AIExecutionRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['project', 'ai_case', 'status']
    ordering = ['-start_time']

    def get_queryset(self):
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        # 返回用户有权限的项目下的执行记录，以及没有关联项目的执行记录
        return AIExecutionRecord.objects.filter(
            models.Q(project__in=accessible_projects) | models.Q(project__isnull=True)
        ).distinct()

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=False, methods=['post'])
    def batch_delete(self, request):
        """批量删除AI执行记录"""
        try:
            ids = request.data.get('ids', [])

            # 验证ids参数
            if not ids:
                return Response({'error': '请选择要删除的记录'}, status=status.HTTP_400_BAD_REQUEST)

            # 确保ids是列表
            if not isinstance(ids, list):
                return Response({'error': 'ids参数格式错误，应为数组'}, status=status.HTTP_400_BAD_REQUEST)

            # 只能删除自己有权限的项目下的记录
            queryset = self.get_queryset()
            records_to_delete = queryset.filter(id__in=ids)

            # 检查是否有权限删除这些记录
            if not records_to_delete.exists():
                return Response({'error': '未找到可删除的记录或没有权限删除'}, status=status.HTTP_404_NOT_FOUND)

            # 获取可删除记录的ID列表，避免对distinct()后的queryset调用delete()
            deletable_ids = list(records_to_delete.values_list('id', flat=True))

            # 使用ID列表直接删除，避免distinct()的问题
            deleted_count = AIExecutionRecord.objects.filter(id__in=deletable_ids).delete()[0]

            return Response({'message': f'成功删除 {deleted_count} 条记录', 'deleted_count': deleted_count})
        except Exception as e:
            logger.error(f"批量删除AI执行记录失败: {str(e)}", exc_info=True)
            return Response({'error': f'批量删除失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='run_adhoc')
    def run_adhoc(self, request):
        """执行临时 AI 任务"""
        project_id = request.data.get('project_id')
        task_description = request.data.get('task_description')
        execution_mode = request.data.get('execution_mode', 'text')  # 默认文本模式
        enable_gif = request.data.get('enable_gif', True)  # GIF录制开关，默认开启

        if not task_description:
            return Response({'error': '缺少任务描述参数'}, status=status.HTTP_400_BAD_REQUEST)

        # 获取项目对象（如果提供了project_id）
        project = None
        if project_id:
            try:
                project = UiProject.objects.get(id=project_id)
            except UiProject.DoesNotExist:
                return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 创建执行记录
        execution_record = AIExecutionRecord.objects.create(
            project=project,
            case_name="Adhoc Task",
            task_description=task_description,
            execution_mode=execution_mode,
            status='running',
            executed_by=request.user,
            logs="正在分析任务...\n"
        )

        # 提交到 Celery 的 ai_automation 队列执行（原来是裸线程；停止信号改成
        # 纯数据库状态判断，见 stop_task 和 tasks.run_ai_adhoc_task）
        from ..tasks import run_ai_adhoc_task
        try:
            run_ai_adhoc_task.delay(execution_record.id, task_description, execution_mode, enable_gif)
        except Exception as e:
            # 提交失败时把记录标记为失败，避免永久卡在 "running"
            execution_record.status = 'failed'
            execution_record.logs += f"\n[System] 提交执行任务失败: {e}"
            execution_record.save()
            logger.error(f'提交 AI 临时任务执行失败: execution_id={execution_record.id}, error={e}')
            return Response({
                'error': f'提交执行任务失败，请检查任务队列服务是否正常: {e}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'message': 'AI 任务开始执行',
            'execution_id': execution_record.id
        })

    @action(detail=True, methods=['post'], url_path='stop')
    def stop_task(self, request, pk=None):
        """停止正在执行的任务

        停止信号直接写数据库状态，而不是进程内存字典（原来的 STOP_SIGNALS）。
        因为实际执行现在跑在 Celery worker 进程里，跟发起这个请求的 Django
        Web 进程不是同一个进程，进程内存字典在两边看到的是两份不同的数据，
        worker 永远看不到 Web 进程设置的停止信号。数据库是两边共享的状态，
        run_ai_case_task / run_ai_adhoc_task 里的 should_stop 会定期
        refresh_from_db() 读取这个状态。
        """
        try:
            record = self.get_object()
            if record.status == 'running':
                record.status = 'stopped'
                record.end_time = timezone.now()
                record.logs += "\n[System] 任务已由用户停止。"
                record.save()
                return Response({'message': '已发送停止信号'})
            return Response({'message': '任务不在运行中'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 注：_process_gif_recording / _auto_mark_completed_tasks 已挪到
    # apps/ui_automation/ai_execution_helpers.py 作为模块级函数（这两个方法
    # 原本就不依赖 self.request/self.queryset，只是被误放进了 ViewSet 里，
    # 之前 AICaseViewSet 和 AIExecutionRecordViewSet 各自维护了一份逐字节相同
    # 的拷贝）。Celery 任务里直接 import 调用，不再需要"裸实例化 ViewSet"。

    @action(detail=True, methods=['get'], url_path='report')
    def generate_report(self, request, pk=None):
        """
        生成AI执行报告

        Query Parameters:
            report_type: 报告类型 (summary/detailed/performance)，默认为 summary

        Returns:
            执行报告数据
        """
        try:
            record = self.get_object()
            report_type = request.query_params.get('report_type', 'summary')

            # 导入报告生成器
            from ..reports import AIExecutionReportGenerator

            # 生成报告
            generator = AIExecutionReportGenerator(record)

            if report_type == 'detailed':
                report = generator.generate_detailed_report()
            elif report_type == 'performance':
                report = generator.generate_performance_report()
            else:  # summary
                report = generator.generate_summary_report()

            return Response({
                'success': True,
                'data': report,
                'report_type': report_type
            })

        except Exception as e:
            logger.error(f"生成AI执行报告失败: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='export-pdf')
    def export_pdf(self, request, pk=None):
        """
        导出AI执行报告为PDF

        Query Parameters:
            report_type: 报告类型 (summary/detailed/performance)，默认为 summary

        Returns:
            PDF文件下载
        """
        try:
            record = self.get_object()
            report_type = request.query_params.get('report_type', 'summary')

            # 导入报告生成器
            from ..reports import AIExecutionReportGenerator
            from ..pdf_generator import AIReportPDFGenerator

            # 生成报告数据
            generator = AIExecutionReportGenerator(record)

            if report_type == 'detailed':
                report_data = generator.generate_detailed_report()
            elif report_type == 'performance':
                report_data = generator.generate_performance_report()
            else:  # summary
                report_data = generator.generate_summary_report()

            # 生成PDF
            pdf_generator = AIReportPDFGenerator(report_data, report_type)
            pdf_buffer = pdf_generator.generate()

            # 生成文件名
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            safe_case_name = "".join([c if c.isalnum() or c in (' ', '_', '-') else '_' for c in record.case_name])
            filename = f"AI_Report_{safe_case_name}_{timestamp}.pdf"

            # 返回PDF文件
            response = HttpResponse(
                pdf_buffer.getvalue(),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = len(pdf_buffer.getvalue())

            return response

        except ImportError as e:
            logger.error(f"PDF生成库未安装: {e}")
            return Response({
                'success': False,
                'error': 'PDF生成功能需要安装 reportlab 库，请运行: pip install reportlab'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"导出PDF失败: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
