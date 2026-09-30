"""API项目与集合视图（含 Swagger 导入）"""
import json
from datetime import datetime

import requests
from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import ApiProject, ApiCollection, ApiRequest, TestSuiteRequest
from ..serializers import ApiProjectSerializer, ApiCollectionSerializer
from ..operation_logger import log_operation
from ..services.swagger_import import generate_test_cases, parse_swagger_spec
from .base import BaseViewSetMixin


class ApiProjectViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """API项目视图集"""
    queryset = ApiProject.objects.all()
    serializer_class = ApiProjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project_type', 'status', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name', 'start_date']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        return ApiProject.objects.filter(
            models.Q(visibility='all') |
            models.Q(owner=user) |
            models.Q(members=user)
        ).distinct()

    def perform_create(self, serializer):
        """创建项目时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='create',
            resource_type='project',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_update(self, serializer):
        """更新项目时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='edit',
            resource_type='project',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_destroy(self, instance):
        """删除项目时记录日志"""
        log_operation(
            operation_type='delete',
            resource_type='project',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )
        instance.delete()

    @action(detail=False, methods=['post'], url_path='create-sample')
    def create_sample_project(self, request):
        """创建示例项目（宠物店）"""
        if ApiProject.objects.filter(name='宠物店API示例项目').exists():
            return Response({'message': '示例项目已存在'}, status=status.HTTP_400_BAD_REQUEST)

        project = ApiProject.objects.create(
            name='宠物店API示例项目',
            description='参考Apifox宠物店示例，包含用户管理、宠物管理、订单管理等接口',
            project_type='HTTP',
            status='IN_PROGRESS',
            owner=request.user,
            start_date=datetime.now().date()
        )

        self._create_sample_data(project, request.user)

        serializer = self.get_serializer(project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _create_sample_data(self, project, user):
        """创建示例数据"""
        # 用户管理集合
        user_collection = ApiCollection.objects.create(
            project=project,
            name='用户管理',
            description='用户注册、登录、信息管理相关接口',
            order=1
        )

        # 用户注册接口
        ApiRequest.objects.create(
            collection=user_collection,
            name='用户注册',
            description='新用户注册接口',
            method='POST',
            url='{{base_url}}/api/users/register',
            headers={'Content-Type': 'application/json'},
            body={
                'type': 'json',
                'data': {
                    'username': 'testuser',
                    'email': 'test@example.com',
                    'password': 'password123'
                }
            },
            created_by=user,
            order=1
        )

        # 用户登录接口
        ApiRequest.objects.create(
            collection=user_collection,
            name='用户登录',
            description='用户登录获取token',
            method='POST',
            url='{{base_url}}/api/users/login',
            headers={'Content-Type': 'application/json'},
            body={
                'type': 'json',
                'data': {
                    'username': 'testuser',
                    'password': 'password123'
                }
            },
            created_by=user,
            order=2
        )

        # 宠物管理集合
        pet_collection = ApiCollection.objects.create(
            project=project,
            name='宠物管理',
            description='宠物信息增删改查接口',
            order=2
        )

        # 获取宠物列表
        ApiRequest.objects.create(
            collection=pet_collection,
            name='获取宠物列表',
            description='分页获取宠物列表',
            method='GET',
            url='{{base_url}}/api/pets',
            headers={'Authorization': 'Bearer {{token}}'},
            params={'page': '1', 'limit': '10'},
            created_by=user,
            order=1
        )

        # 创建宠物
        ApiRequest.objects.create(
            collection=pet_collection,
            name='创建宠物',
            description='添加新宠物信息',
            method='POST',
            url='{{base_url}}/api/pets',
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer {{token}}'
            },
            body={
                'type': 'json',
                'data': {
                    'name': '小白',
                    'category': 'dog',
                    'age': 2,
                    'price': 1000
                }
            },
            created_by=user,
            order=2
        )


class ApiCollectionViewSet(BaseViewSetMixin, viewsets.ModelViewSet):
    """API集合视图集"""
    queryset = ApiCollection.objects.all()
    serializer_class = ApiCollectionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['project', 'parent']

    def get_queryset(self):
        user = self.request.user
        return ApiCollection.objects.filter(
            project__in=ApiProject.objects.filter(
                models.Q(visibility='all') |
                models.Q(owner=user) |
                models.Q(members=user)
            )
        ).distinct()

    def perform_create(self, serializer):
        """创建集合时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='create',
            resource_type='collection',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def perform_update(self, serializer):
        """更新集合时记录日志"""
        instance = serializer.save()
        log_operation(
            operation_type='edit',
            resource_type='collection',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )

    def _collect_request_ids(self, collection):
        """递归收集集合及所有子集合中的接口 ID"""
        ids = list(collection.requests.values_list('id', flat=True))
        for child in collection.children.all():
            ids.extend(self._collect_request_ids(child))
        return ids

    def perform_destroy(self, instance):
        """删除集合前检查接口是否已被测试套件使用"""
        from rest_framework.exceptions import ValidationError
        all_request_ids = self._collect_request_ids(instance)
        if all_request_ids:
            used = TestSuiteRequest.objects.filter(request_id__in=all_request_ids).exists()
            if used:
                raise ValidationError('该集合中的接口已在自动化测试套件中使用，无法删除')
        log_operation(
            operation_type='delete',
            resource_type='collection',
            resource_id=instance.id,
            resource_name=instance.name,
            user=self.request.user
        )
        instance.delete()

    @action(detail=False, methods=['post'], url_path='import-swagger')
    def import_swagger(self, request):
        """从 Swagger/OpenAPI 规范导入接口（支持 URL 或 JSON 内容，支持 dry_run 预览，支持按模块筛选）"""
        source_type = request.data.get('source_type', 'url')
        project_id = request.data.get('project_id')
        dry_run = request.data.get('dry_run', False)
        # selected_tags: 空列表表示全部模块
        selected_tags = request.data.get('selected_tags', [])
        # update_mode: True 时更新已有用例的技术字段，False 时纯新增
        update_mode = request.data.get('update_mode', False)
        # lang: 'zh' 或 'en'，用于生成语言化的用例名称和描述
        raw_lang = request.data.get('lang', request.headers.get('Accept-Language', 'zh'))
        lang = 'en' if str(raw_lang).lower().startswith('en') else 'zh'

        if not project_id:
            return Response({'error': '请选择项目'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = ApiProject.objects.get(
                models.Q(id=project_id) &
                (models.Q(owner=request.user) | models.Q(members=request.user))
            )
        except ApiProject.DoesNotExist:
            return Response({'error': '项目不存在或无权限'}, status=status.HTTP_404_NOT_FOUND)

        # 获取 Swagger 规范
        swagger_spec = None
        if source_type == 'url':
            swagger_url = request.data.get('swagger_url', '').strip()
            if not swagger_url:
                return Response({'error': '请输入 Swagger URL'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                req_headers = {}
                token = request.data.get('token', '').strip()
                if token:
                    req_headers['Authorization'] = token if token.lower().startswith('bearer ') else f'Bearer {token}'
                resp = requests.get(swagger_url, headers=req_headers, timeout=15)
                resp.raise_for_status()
                swagger_spec = resp.json()
            except Exception as e:
                return Response({'error': f'获取 Swagger 文档失败：{str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            swagger_json = request.data.get('swagger_json')
            if not swagger_json:
                return Response({'error': '请提供 Swagger JSON 内容'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                swagger_spec = json.loads(swagger_json) if isinstance(swagger_json, str) else swagger_json
            except json.JSONDecodeError as e:
                return Response({'error': f'JSON 解析失败：{str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # 解析规范
        try:
            endpoints, is_v3 = parse_swagger_spec(swagger_spec)
        except Exception as e:
            return Response({'error': f'Swagger 解析失败：{str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        if not endpoints:
            return Response({'error': '未解析到任何接口，请确认 Swagger 文档格式正确'}, status=status.HTTP_400_BAD_REQUEST)

        # 为所有 endpoint 生成测试用例（逐个 try-except 防止单个解析失败影响全局）
        all_cases = []
        for ep in endpoints:
            try:
                all_cases.extend(generate_test_cases(ep, swagger_spec, lang=lang))
            except Exception:
                pass

        if not all_cases:
            return Response({'error': '生成测试用例失败，请检查 Swagger 文档内容'}, status=status.HTTP_400_BAD_REQUEST)

        # 收集全部 tag（供前端模块筛选用）
        all_tags = sorted({c['tag'] for c in all_cases if c.get('tag')})

        # 预览模式：返回用例列表（不入库）
        if dry_run:
            filtered = all_cases
            if selected_tags:
                filtered = [c for c in all_cases if c['tag'] in selected_tags]

            # update_mode 时预查已有请求，标记 new/update
            existing_keys = set()
            if update_mode:
                existing_keys = set(
                    ApiRequest.objects.filter(
                        collection__project=project,
                        collection__parent=None,
                    ).values_list('collection__name', 'method', 'url')
                )

            preview = []
            for c in filtered:
                action = 'update' if (c['tag'], c['method'], c['url']) in existing_keys else 'new'
                preview.append({
                    'tag': c['tag'],
                    'name': c['name'],
                    'method': c['method'],
                    'url': c['url'],
                    'case_type': c['name'].split(']')[0].lstrip('[') if ']' in c['name'] else c['name'],
                    'case_category': c.get('case_category', 'error'),
                    'action': action,
                })
            new_cnt = sum(1 for p in preview if p['action'] == 'new')
            upd_cnt = sum(1 for p in preview if p['action'] == 'update')
            return Response({
                'endpoints': preview,
                'total': len(preview),
                'all_tags': all_tags,
                'new_count': new_cnt,
                'update_count': upd_cnt,
            })

        # 入库前按 selected_tags 过滤（空列表 = 全部）
        if selected_tags:
            all_cases = [c for c in all_cases if c['tag'] in selected_tags]
        if not all_cases:
            return Response({'error': '所选模块下未找到可生成的用例'}, status=status.HTTP_400_BAD_REQUEST)

        # 入库：先批量确定所有集合，再批量创建/更新请求
        collection_map = {}
        new_count = 0
        updated_count = 0
        # 按 tag 分组 cases，保持顺序
        from collections import OrderedDict
        tag_cases = OrderedDict()
        for case in all_cases:
            tag = case['tag'] or '默认'
            tag_cases.setdefault(tag, []).append(case)

        for tag, cases in tag_cases.items():
            collection, _ = ApiCollection.objects.get_or_create(
                project=project,
                name=tag,
                parent=None,
                defaults={'order': ApiCollection.objects.filter(project=project, parent=None).count()}
            )
            collection_map[tag] = collection
            for case in cases:
                try:
                    if update_mode:
                        existing = ApiRequest.objects.filter(
                            collection=collection,
                            method=case['method'],
                            url=case['url'],
                        ).first()
                        if existing:
                            existing.headers = case.get('headers', {})
                            existing.params = case.get('params', {})
                            existing.body = case.get('body', {})
                            existing.assertions = case.get('assertions', [])
                            existing.save(update_fields=['headers', 'params', 'body', 'assertions', 'updated_at'])
                            updated_count += 1
                            continue
                    ApiRequest.objects.create(
                        collection=collection,
                        name=case['name'],
                        description=case.get('description', ''),
                        method=case['method'],
                        url=case['url'],
                        headers=case.get('headers', {}),
                        params=case.get('params', {}),
                        body=case.get('body', {}),
                        assertions=case.get('assertions', []),
                        order=ApiRequest.objects.filter(collection=collection).count(),
                        created_by=request.user,
                        request_type='HTTP',
                    )
                    new_count += 1
                except Exception:
                    pass

        if update_mode:
            message = f'新增 {new_count} 条，更新 {updated_count} 条用例，涉及 {len(collection_map)} 个集合'
        else:
            message = f'成功生成 {new_count} 条用例，涉及 {len(collection_map)} 个集合'
        return Response({
            'message': message,
            'created_requests': new_count,
            'updated_requests': updated_count,
            'created_collections': len(collection_map),
        })
