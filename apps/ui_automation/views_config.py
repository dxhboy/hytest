from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.core.permissions import IsStaffOrReadOnly
import shutil
import subprocess
import platform
import os
import json
import logging

logger = logging.getLogger(__name__)

class EnvironmentConfigViewSet(viewsets.ViewSet):
    """
    UI自动化环境配置视图集
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def check_environment(self, request):
        """
        检测环境状态 (系统浏览器和Playwright浏览器)
        """
        import sys
        from .browser_paths import find_installed_browser_path

        # 1. 检测系统浏览器 (Selenium常用)
        system_browsers_list = ['chrome', 'firefox', 'edge'] # Safari not on Windows usually
        if platform.system() == 'Darwin':
             system_browsers_list.append('safari')

        system_results = []

        is_windows = platform.system() == 'Windows'
        current_system = platform.system()

        # 各浏览器在找不到时给出的安装建议，按当前系统分平台维护
        # （候选路径本身已经统一到 browser_paths.py，这里只保留"文案"这一份差异）
        install_cmd_map = {
            'chrome': {
                'Windows': "请下载 Chrome 安装包安装",
                'Darwin': "brew install --cask google-chrome",
                'Linux': "sudo dnf install chromium 或 sudo dnf install google-chrome-stable",
            },
            'firefox': {
                'Windows': "请下载 Firefox 安装包安装",
                'Darwin': "brew install --cask firefox",
                'Linux': "sudo dnf install firefox",
            },
            'edge': {
                'Windows': "请下载 Edge 安装包安装",
                'Darwin': "brew install --cask microsoft-edge",
                'Linux': "从微软官网下载 Edge Linux 版本安装包",
            },
            'safari': {
                'Darwin': "系统自带",
            },
        }

        for browser in system_browsers_list:
            installed_path = find_installed_browser_path(browser, system=current_system)
            installed = installed_path is not None
            version = None  # Version check omitted for simplicity/performance
            install_cmd = install_cmd_map.get(browser, {}).get(current_system, "")

            system_results.append({
                'name': browser,
                'installed': installed,
                'version': version,
                'install_cmd': install_cmd
            })

        # 2. 检测Playwright浏览器
        playwright_browsers_list = ['chromium', 'firefox', 'webkit']
        playwright_results = []
        
        # Playwright 缓存路径
        if is_windows:
            playwright_cache_dir = os.path.join(os.environ.get('LOCALAPPDATA'), 'ms-playwright')
        elif platform.system() == 'Darwin':  # macOS
            playwright_cache_dir = os.path.expanduser('~/Library/Caches/ms-playwright')
        else:  # Linux
            playwright_cache_dir = os.path.expanduser('~/.cache/ms-playwright')
        
        # 调试信息：打印缓存路径
        logger.debug(f"Playwright cache dir: {playwright_cache_dir}")

        for browser in playwright_browsers_list:
            installed = False
            version = None
            install_cmd = f"playwright install {browser}"
            
            # 检查缓存目录中是否有对应的浏览器文件夹
            if os.path.exists(playwright_cache_dir):
                for dirname in os.listdir(playwright_cache_dir):
                    # 匹配规则: chromium-123456, firefox-1234, webkit-1234
                    # 注意: 有时候是 chromium-vxxxx
                    if dirname.startswith(browser + '-'):
                        installed = True
                        version = dirname.split('-')[-1]
                        break
            
            playwright_results.append({
                'name': browser,
                'installed': installed,
                'version': version,
                'install_cmd': install_cmd
            })

        return Response({
            'os': platform.system(),
            'system_browsers': system_results,
            'playwright_browsers': playwright_results
        })

    @action(detail=False, methods=['post'])
    def install_driver(self, request):
        """
        安装浏览器驱动
        """
        browser = request.data.get('browser')
        if not browser:
            return Response({'error': 'Browser name is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 使用当前 Python 环境执行模块安装命令
            import sys
            subprocess.run([sys.executable, '-m', 'playwright', 'install', browser], check=True)
            return Response({'message': f'Successfully installed driver for {browser}'})
        except subprocess.CalledProcessError as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from apps.core.llm import LLMClient, LLMError, LLMTimeoutError, resolve_base_url
from apps.requirement_analysis.models import AIModelConfig

# 测试连接只发 1 个 token，60 秒读取超时足够
CONNECTION_TEST_READ_TIMEOUT = 60.0


def _probe_connection(config, log_prefix):
    """
    发送最小 chat/completions 请求测试连通性，返回 DRF Response（响应格式与迁移前一致）
    """
    client = LLMClient(config, read_timeout=CONNECTION_TEST_READ_TIMEOUT, auto_version=False)
    try:
        if not client.config.is_bedrock:
            logger.info(f"{log_prefix} - 发送POST请求到: {client.url}")
        # 不回填 temperature 等采样参数：部分模型（如 Kimi）只接受特定 temperature
        client.chat([{"role": "user", "content": "Hi"}], max_tokens=1, defaults=())
        logger.info(f"{log_prefix} - API连接测试成功")
        return Response({'message': '连接成功'})
    except LLMTimeoutError as e:
        logger.error(f"{log_prefix} - API连接测试超时: {e.message}")
        return Response(
            {'error': '连接测试超时: 请检查网络连接或API地址是否正确'},
            status=status.HTTP_408_REQUEST_TIMEOUT
        )
    except LLMError as e:
        if e.status_code is not None:
            logger.error(f"{log_prefix} - API调用返回错误: Status={e.status_code}, Body={e.body}")
            return Response(
                {'error': f'连接失败: {e.status_code} - {e.body}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        logger.error(f"{log_prefix} - API连接测试异常: {e.message}")
        return Response(
            {'error': f'连接异常: {e.message}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        logger.error(f"{log_prefix} - API连接测试异常: {repr(e)}")
        return Response(
            {'error': f'连接异常: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class AIIntelligentModeConfigViewSet(viewsets.ViewSet):
    """
    AI智能模式配置视图集 (Browser-use) - 使用ModelViewSet支持标准CRUD
    """
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    read_only_actions = ('test_connection',)
    queryset = AIModelConfig.objects.filter(role='browser_use_text')

    def list(self, request):
        """
        获取所有AI智能模式配置列表
        """
        configs = self.queryset.order_by('-created_at')
        serializer_data = [{
            'id': config.id,
            'name': config.name,
            'model_type': config.model_type,
            'model_name': config.model_name,
            'base_url': config.base_url,
            'is_active': config.is_active,
            'api_key_length': len(config.api_key) if config.api_key else 0,  # 返回API Key长度用于生成掩码
            'created_at': config.created_at,
            'updated_at': config.updated_at
        } for config in configs]
        return Response(serializer_data)

    def create(self, request):
        """
        创建新的AI智能模式配置
        """
        data = request.data
        user = request.user

        # 验证必填字段
        required_fields = ['name', 'model_type', 'model_name', 'api_key']
        for field in required_fields:
            if not data.get(field):
                return Response(
                    {'error': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 如果创建时启用，先禁用其他所有配置
        if data.get('is_active', True):
            self.queryset.filter(is_active=True).update(is_active=False)

        # 创建新配置
        config = AIModelConfig.objects.create(
            name=data['name'],
            model_type=data['model_type'],
            role='browser_use_text',
            model_name=data['model_name'],
            api_key=data['api_key'],
            base_url=data.get('base_url', ''),
            is_active=data.get('is_active', True),
            created_by=user
        )

        return Response({
            'id': config.id,
            'name': config.name,
            'model_type': config.model_type,
            'model_name': config.model_name,
            'base_url': config.base_url,
            'is_active': config.is_active,
            'created_at': config.created_at
        }, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        """
        获取单个配置详情
        """
        try:
            config = self.queryset.get(pk=pk)
            return Response({
                'id': config.id,
                'name': config.name,
                'model_type': config.model_type,
                'model_name': config.model_name,
                'base_url': config.base_url,
                'is_active': config.is_active,
                'created_at': config.created_at,
                'updated_at': config.updated_at
            })
        except AIModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    def update(self, request, pk=None):
        """
        更新配置 (PUT)
        """
        try:
            config = self.queryset.get(pk=pk)
            data = request.data

            # 如果启用此配置，先禁用其他所有配置
            new_is_active = data.get('is_active', config.is_active)
            disabled_config_names = []
            if new_is_active:
                # 查找将被禁用的配置
                active_configs = self.queryset.exclude(pk=pk).filter(is_active=True)
                disabled_config_names = [c.name for c in active_configs]
                # 先禁用其他所有配置（不包括当前配置），避免唯一约束冲突
                active_configs.update(is_active=False)

            # 更新字段
            if 'name' in data:
                config.name = data['name']
            if 'model_type' in data:
                config.model_type = data['model_type']
            if 'model_name' in data:
                config.model_name = data['model_name']
            if 'api_key' in data and data['api_key']:
                config.api_key = data['api_key']
            if 'base_url' in data:
                config.base_url = data['base_url']
            if 'is_active' in data:
                config.is_active = data['is_active']

            config.save()

            response_data = {
                'id': config.id,
                'name': config.name,
                'model_type': config.model_type,
                'model_name': config.model_name,
                'base_url': config.base_url,
                'is_active': config.is_active,
                'created_at': config.created_at,
                'updated_at': config.updated_at
            }

            # 如果禁用了其他配置,返回被禁用的配置名称
            if disabled_config_names:
                response_data['disabled_configs'] = disabled_config_names

            return Response(response_data)
        except AIModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def partial_update(self, request, pk=None):
        """
        部分更新配置 (PATCH)
        """
        return self.update(request, pk)

    def destroy(self, request, pk=None):
        """
        删除配置
        """
        try:
            config = self.queryset.get(pk=pk)
            config.delete()
            return Response(
                {'message': 'Config deleted successfully'},
                status=status.HTTP_204_NO_CONTENT
            )
        except AIModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'], url_path='test_connection')
    def test_connection_preview(self, request):
        """
        测试模型连接 (在保存前测试，不保存配置)
        """
        provider = request.data.get('provider')
        base_url = request.data.get('base_url')
        api_key = request.data.get('api_key')
        model_name = request.data.get('model_name')

        if not api_key:
            return Response(
                {'error': 'API Key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 默认Base URL处理（统一由 apps.core.llm 维护各厂商默认地址）
        base_url = resolve_base_url(provider, base_url)

        if not base_url:
             return Response(
                 {'error': 'Base URL is required for this provider'},
                 status=status.HTTP_400_BAD_REQUEST
             )

        probe_config = {
            'provider': provider,
            'base_url': base_url,
            'api_key': api_key,
            'model_name': model_name,
        }
        return _probe_connection(probe_config, 'AI智能模式预览')

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """
        测试已保存配置的连接
        """
        try:
            config = self.queryset.get(pk=pk)
        except AIModelConfig.DoesNotExist:
            return Response(
                {'error': 'Config not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        logger.info(f"=== AI智能模式 - 开始测试模型连接 ===")
        logger.info(f"模型类型: {config.model_type}")
        logger.info(f"模型名称: {config.model_name}")
        logger.info(f"API URL: {config.base_url}")
        logger.info(f"API Key前缀: {config.api_key[:10]}..." if len(config.api_key) > 10 else f"API Key: {config.api_key}")

        # 使用默认Base URL（统一由 apps.core.llm 维护各厂商默认地址）
        if not resolve_base_url(config.model_type, config.base_url):
            return Response(
                {'error': 'Base URL is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return _probe_connection(config, 'AI智能模式')
