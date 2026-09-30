"""UI 自动化项目、项目参数、远程浏览器服务相关视图"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from django.utils import timezone
from datetime import timedelta
from ..models import (
    UiProject,
    RemoteBrowserService,
    UiProjectParameter,
)
from ..serializers import (
    UiProjectSerializer,
    UiProjectCreateSerializer,
    UiProjectUpdateSerializer,
    RemoteBrowserServiceSerializer,
    RemoteBrowserServiceCreateSerializer,
    UiProjectParameterSerializer,
)
from ..access import accessible_ui_project_ids, ensure_ui_project_access
from ..operation_logger import log_operation


class UiProjectViewSet(viewsets.ModelViewSet):
    queryset = UiProject.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'owner', 'members']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return UiProjectCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UiProjectUpdateSerializer
        return UiProjectSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目
        user = self.request.user
        return UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

    def perform_create(self, serializer):
        # 创建项目时，当前用户自动成为负责人
        instance = serializer.save(owner=self.request.user)
        # 记录操作
        log_operation('create', 'project', instance.id, instance.name, self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('edit', 'project', instance.id, instance.name, self.request.user)

    def perform_destroy(self, instance):
        # 记录操作（在删除前记录）
        log_operation('delete', 'project', instance.id, instance.name, self.request.user)
        instance.delete()


class UiProjectParameterViewSet(viewsets.ModelViewSet):
    """项目参数 CRUD

    参数按项目管理，测试步骤的输入值/断言值、项目的 base_url 里填 "{{参数名}}"
    引用，执行时由 apps/ui_automation/parameter_resolver.py 现查这张表替换成真实值。
    """
    serializer_class = UiProjectParameterSerializer
    filterset_fields = ['project']

    def get_queryset(self):
        # 参数值常含测试账号/令牌，只能访问自己负责或参与的项目的参数
        return UiProjectParameter.objects.filter(
            project_id__in=accessible_ui_project_ids(self.request.user)
        )

    def perform_create(self, serializer):
        ensure_ui_project_access(self.request.user, serializer.validated_data['project'])
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        if 'project' in serializer.validated_data:
            ensure_ui_project_access(self.request.user, serializer.validated_data['project'])
        serializer.save()


class RemoteBrowserServiceViewSet(viewsets.ModelViewSet):
    """远程浏览器服务配置 CRUD"""
    serializer_class = RemoteBrowserServiceSerializer
    filterset_fields = ['project', 'service_type']

    def get_queryset(self):
        queryset = RemoteBrowserService.objects.filter(
            project_id__in=accessible_ui_project_ids(self.request.user)
        )

        # is_active 从 filterset_fields 里挪出来手动处理：前端传的是 JS 布尔值
        # true/false，交给 DjangoFilterBackend 自动生成的 BooleanFilter 解析查询字符串
        # 里的 "true"/"false" 时，不同版本/配置下有过解析不稳定的情况，导致执行页面
        # 的"远程服务"下拉框传了 is_active=true 却仍然把已停用（is_active=false）的
        # 服务也返回回去。这里直接读原始查询参数自己判断，不依赖 filterset 那套自动
        # 推断逻辑，保证"只要传了 is_active"就一定按这个值严格过滤。
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            queryset = queryset.filter(is_active=is_active_param.strip().lower() in ('true', '1', 'yes'))

        # online=true：只要真的还在按心跳周期上报的服务（last_heartbeat 落在阈值窗口
        # 内），is_active=True 但客户端早就异常退出的"僵尸记录"不会被返回。跟 is_active
        # 一样直接读原始查询参数，不走 filterset（is_online 是 @property，不是真实列，
        # DjangoFilterBackend 也过滤不了它）。
        online_param = self.request.query_params.get('online')
        if online_param is not None and online_param.strip().lower() in ('true', '1', 'yes'):
            threshold = timezone.now() - timedelta(seconds=RemoteBrowserService.HEARTBEAT_ONLINE_THRESHOLD_SECONDS)
            queryset = queryset.filter(last_heartbeat__gte=threshold)

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return RemoteBrowserServiceCreateSerializer
        return RemoteBrowserServiceSerializer

    def perform_create(self, serializer):
        ensure_ui_project_access(self.request.user, serializer.validated_data['project'])
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        if 'project' in serializer.validated_data:
            ensure_ui_project_access(self.request.user, serializer.validated_data['project'])
        serializer.save()

    @action(detail=False, methods=['post'])
    def register(self, request):
        """远程浏览器客户端自注册接口

        供部署在远程机器（如机器B）上的客户端脚本调用：客户端启动时携带自己的
        project/name/service_type/url 等信息 POST 到这个接口，后端按 (project, name)
        做 upsert —— 已存在同名记录就更新连接信息，不存在就新建，避免客户端每次
        重启都在配置中心里堆出重复记录。客户端优雅退出时也可以再调一次、把
        is_active 设为 false，主动标记自己下线。
        """
        project_id = request.data.get('project')
        name = request.data.get('name')
        service_type = request.data.get('service_type')
        url = request.data.get('url')

        missing = [f for f in ('project', 'name', 'service_type', 'url') if not request.data.get(f)]
        if missing:
            return Response(
                {'error': f"缺少必填字段: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_types = dict(RemoteBrowserService.SERVICE_TYPE_CHOICES)
        if service_type not in valid_types:
            return Response(
                {'error': f"不支持的 service_type: {service_type}，可选值: {list(valid_types)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 客户端所用账号必须是该项目的负责人或成员
            project = UiProject.objects.get(id=project_id, id__in=accessible_ui_project_ids(request.user))
        except UiProject.DoesNotExist:
            return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)
        except (TypeError, ValueError):
            return Response({'error': 'project 参数不合法'}, status=status.HTTP_400_BAD_REQUEST)

        # upsert 的定位键是 (project, name, service_type) 而不是只有 (project, name)：
        # 同一个客户端进程常见会同时启用 Playwright 和 Selenium 两种服务类型，如果
        # 两边配的是同一个 service_name（比如都用默认的"主机名(IP)"，不带任何类型
        # 后缀——前端下拉框本来就会在展示时额外拼上服务类型，名字里不需要再重复），
        # 只按 (project, name) 定位会导致后注册的那个把先注册的直接覆盖掉，数据库里
        # 只剩一条记录，另一个服务类型的连接信息就丢了。加上 service_type 就能让
        # 两条记录并存，互不干扰。
        service = RemoteBrowserService.objects.filter(
            project=project, name=name, service_type=service_type,
        ).first()
        created = service is None
        if created:
            service = RemoteBrowserService(project=project, name=name, created_by=request.user)

        service.service_type = service_type
        service.url = url
        if 'capabilities' in request.data:
            service.capabilities = request.data.get('capabilities') or {}
        if 'auth_config' in request.data:
            service.auth_config = request.data.get('auth_config') or {}
        service.is_active = request.data.get('is_active', True)
        # 注册本身就是一次"我还活着"的信号，顺带算一次心跳，不用等客户端下一次定时
        # 上报——否则刚注册完的服务要等最多一个心跳周期才会被认成在线。客户端主动
        # 标记自己下线（is_active=False）时不算心跳，避免"已经下线"却又被认成在线。
        if service.is_active:
            service.last_heartbeat = timezone.now()
        service.save()

        serializer = RemoteBrowserServiceSerializer(service)
        return Response(
            {'created': created, 'service': serializer.data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'])
    def heartbeat(self, request):
        """远程客户端心跳接口：客户端常驻运行期间按固定间隔调用，只更新 last_heartbeat。

        跟 register 分开是因为心跳需要频繁调用（默认 30 秒一次），只更新一个时间戳，
        不用像 register 那样每次都带上完整的 url/capabilities/auth_config——payload
        更小，调用更频繁也没什么开销。

        按 (project, name) 定位记录，跟 register 用的是同一套身份（客户端配置里的
        project_id + service_name），不需要客户端记住数据库自增 id。
        """
        project = request.data.get('project')
        name = request.data.get('name')
        if not project or not name:
            return Response(
                {'error': '缺少必填字段: project, name'}, status=status.HTTP_400_BAD_REQUEST,
            )

        updated = RemoteBrowserService.objects.filter(
            project=project, name=name, project_id__in=accessible_ui_project_ids(request.user),
        ).update(
            last_heartbeat=timezone.now(),
        )
        if not updated:
            return Response(
                {'error': '未找到匹配的远程浏览器服务，请先调用 /register/ 完成注册'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({'status': 'ok'})

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """测试远程浏览器服务连接"""
        service = self.get_object()
        try:
            if service.service_type in ('selenium_grid', 'browserstack', 'saucelabs'):
                from ..browser_factory import BrowserConnectionFactory
                driver = BrowserConnectionFactory.create_selenium_driver(
                    browser_type='chrome', headless=True, remote_service=service,
                )
                driver.quit()
            elif service.service_type == 'playwright_remote':
                import asyncio
                from playwright.async_api import async_playwright
                async def _test():
                    pw = await async_playwright().start()
                    browser = await pw.chromium.connect(ws_endpoint=service.url)
                    await browser.close()
                    await pw.stop()
                asyncio.run(_test())
            elif service.service_type == 'playwright_cdp':
                # service.url 现在是远程客户端的"控制接口"地址，不是一个已经在跑的
                # CDP 端点——不能再直接 connect_over_cdp(service.url)。跟真实执行走
                # 同一条路径：BrowserConnectionFactory 会先 POST /launch 让远程客户端
                # 现开一个浏览器，拿到这次专属的 CDP 地址再连上去，测完用
                # close_playwright_browser 通知远程客户端 /close 把它关掉。
                # 这样"测试连接"顺带也验证了远程客户端按需启动这条链路本身是通的，
                # 比之前只是连一下已经常驻的浏览器更能反映真实情况。
                import asyncio
                from playwright.async_api import async_playwright
                from ..browser_factory import BrowserConnectionFactory, close_playwright_browser

                async def _test():
                    pw = await async_playwright().start()
                    try:
                        browser = await BrowserConnectionFactory.create_playwright_browser(
                            playwright_instance=pw,
                            browser_type='chromium',
                            headless=True,
                            remote_service=service,
                        )
                        await close_playwright_browser(browser)
                    finally:
                        await pw.stop()
                asyncio.run(_test())
            return Response({'status': 'success', 'message': '连接成功'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)


# 注：ScreenshotViewSet（对应下面已删除的 Screenshot 模型）已删除——全代码库
# 没有任何地方调用过 Screenshot.objects.create()，实际截图走的是
# TestCaseExecution.screenshots / AIExecutionRecord.screenshots_sequence 这两个
# JSONField，Screenshot 模型是从未被使用过的死代码。见对应的迁移文件。
