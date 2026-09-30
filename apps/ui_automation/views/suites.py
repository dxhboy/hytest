"""测试套件相关视图"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
import logging
from ..models import TestScript, TestSuite, TestSuiteScript, RemoteBrowserService
from ..serializers import (
    TestSuiteSerializer,
    TestSuiteCreateSerializer,
    TestSuiteUpdateSerializer,
    TestSuiteWithScriptsSerializer,
    TestSuiteScriptSerializer,
    TestSuiteTestCaseSerializer,
)
from ..operation_logger import log_operation

logger = logging.getLogger(__name__)


class TestSuiteViewSet(viewsets.ModelViewSet):
    queryset = TestSuite.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'description']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return TestSuiteCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TestSuiteUpdateSerializer
        elif self.action == 'retrieve':
            return TestSuiteWithScriptsSerializer
        return TestSuiteSerializer

    def get_queryset(self):
        user = self.request.user
        qs = TestSuite.objects.filter(
            models.Q(visibility='all') | models.Q(created_by=user)
        )
        if getattr(self, 'action', None) == 'list':
            # 列表序列化嵌套 project/scripts/suite_scripts/suite_test_cases，统一预取并注解数量，避免 N+1
            script_qs = TestScript.objects.select_related(
                'project__owner', 'project__login_test_case'
            ).prefetch_related('project__members')
            qs = qs.select_related('project__owner', 'project__login_test_case').prefetch_related(
                'project__members',
                models.Prefetch('scripts', queryset=script_qs),
                models.Prefetch('suite_scripts', queryset=TestSuiteScript.objects.prefetch_related(
                    models.Prefetch('test_script', queryset=script_qs))),
                'suite_test_cases__test_case',
                'test_cases',
            ).annotate(
                test_case_total=models.Count('suite_test_cases', distinct=True),
                script_total=models.Count('suite_scripts', distinct=True),
            ).order_by('-created_at')  # annotate(GROUP BY) 后 Meta.ordering 不再生效，显式保持原排序
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('create', 'suite', instance.id, instance.name, self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('edit', 'suite', instance.id, instance.name, self.request.user)

    def perform_destroy(self, instance):
        # 记录操作（在删除前记录）
        log_operation('delete', 'suite', instance.id, instance.name, self.request.user)
        instance.delete()

    @action(detail=True, methods=['get'])
    def scripts(self, request, pk=None):
        """获取测试套件中的所有脚本"""
        test_suite = self.get_object()
        scripts = test_suite.suite_scripts.all()
        serializer = TestSuiteScriptSerializer(scripts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_script(self, request, pk=None):
        """向测试套件添加脚本"""
        test_suite = self.get_object()
        script_id = request.data.get('test_script_id')
        order = request.data.get('order', 0)
        try:
            from ..models import TestSuiteScript
            suite_script = TestSuiteScript.objects.create(
                test_suite=test_suite,
                test_script_id=script_id,
                order=order
            )
            serializer = TestSuiteScriptSerializer(suite_script)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def remove_script(self, request, pk=None):
        """从测试套件移除脚本"""
        test_suite = self.get_object()
        script_id = request.data.get('script_id')
        try:
            suite_script = TestSuiteScript.objects.get(test_suite=test_suite, test_script_id=script_id)
            suite_script.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TestSuiteScript.DoesNotExist:
            return Response({'error': 'Script not found in this suite'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'])
    def test_cases(self, request, pk=None):
        """获取测试套件中的所有测试用例"""
        test_suite = self.get_object()
        test_cases = test_suite.suite_test_cases.all()
        serializer = TestSuiteTestCaseSerializer(test_cases, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_test_case(self, request, pk=None):
        """向测试套件添加测试用例"""
        test_suite = self.get_object()
        test_case_id = request.data.get('test_case_id')
        order = request.data.get('order', 0)

        try:
            from ..models import TestSuiteTestCase
            suite_test_case = TestSuiteTestCase.objects.create(
                test_suite=test_suite,
                test_case_id=test_case_id,
                order=order
            )
            serializer = TestSuiteTestCaseSerializer(suite_test_case)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def remove_test_case(self, request, pk=None):
        """从测试套件移除测试用例"""
        test_suite = self.get_object()
        test_case_id = request.data.get('test_case_id')

        try:
            from ..models import TestSuiteTestCase
            suite_test_case = TestSuiteTestCase.objects.get(
                test_suite=test_suite,
                test_case_id=test_case_id
            )
            suite_test_case.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TestSuiteTestCase.DoesNotExist:
            return Response({'error': '测试用例不存在于该测试套件中'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def update_test_case_order(self, request, pk=None):
        """更新测试套件中测试用例的顺序"""
        test_suite = self.get_object()
        test_case_orders = request.data.get('test_case_orders', [])

        try:
            from ..models import TestSuiteTestCase
            for item in test_case_orders:
                TestSuiteTestCase.objects.filter(
                    test_suite=test_suite,
                    test_case_id=item['test_case_id']
                ).update(order=item['order'])

            return Response({'message': '顺序更新成功'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def run_suite(self, request, pk=None):
        """执行测试套件"""
        test_suite = self.get_object()

        # 传统模式执行（Playwright/Selenium）
        # 检查是否包含测试用例或脚本
        test_case_count = test_suite.suite_test_cases.count()
        script_count = test_suite.suite_scripts.count()
        if test_case_count == 0 and script_count == 0:
            return Response({
                'error': '该测试套件未包含任何测试用例或脚本，无法执行'
            }, status=status.HTTP_400_BAD_REQUEST)

        engine = request.data.get('engine', 'playwright')
        browser = request.data.get('browser', 'chrome')
        headless = request.data.get('headless', False)

        remote_browser_service_id = request.data.get('remote_browser_service_id', None)
        remote_service = None
        if remote_browser_service_id:
            try:
                remote_service = RemoteBrowserService.objects.get(
                    id=remote_browser_service_id, is_active=True
                )
            except RemoteBrowserService.DoesNotExist:
                return Response({'error': '远程浏览器服务不存在或未启用'}, status=400)

        # 更新套件执行状态为运行中
        test_suite.execution_status = 'running'
        test_suite.save()

        # 记录运行操作
        log_operation('run', 'suite', test_suite.id, test_suite.name, request.user)

        # 提交到 Celery 任务队列执行（原来是裸线程 threading.Thread，
        # 没有并发上限；现在交给任务队列，worker 并发数可控、可独立扩容）
        from ..tasks import execute_test_suite_task

        try:
            execute_test_suite_task.delay(
                suite_id=test_suite.id,
                engine=engine,
                browser=browser,
                headless=headless,
                user_id=request.user.id,
                remote_service_id=remote_service.id if remote_service else None,
            )
        except Exception as e:
            # 提交失败（比如 Redis/broker 不可用）：回滚状态，
            # 避免套件永久卡在 "running"，谁都不会再去把它改回来
            test_suite.execution_status = 'failed'
            test_suite.save()
            logger.error(f'提交测试套件执行任务失败: suite_id={test_suite.id}, error={e}')
            return Response({
                'error': f'提交执行任务失败，请检查任务队列服务是否正常: {e}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'message': '测试套件开始执行',
            'suite_id': test_suite.id,
            'test_case_count': test_case_count,
            'engine': engine,
            'browser': browser,
            'headless': headless
        }, status=status.HTTP_200_OK)
