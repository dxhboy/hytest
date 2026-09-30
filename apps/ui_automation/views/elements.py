"""定位策略、元素、元素分组、页面对象相关视图"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from django.utils import timezone
import logging
from ..models import (
    UiProject,
    LocatorStrategy,
    Element,
    ElementGroup,
    PageObject,
    PageObjectElement,
    ScriptElementUsage,
)
from ..serializers import (
    LocatorStrategySerializer,
    ElementSerializer,
    ElementEnhancedSerializer,
    ElementGroupSerializer,
    ElementGroupCreateSerializer,
    PageObjectSerializer,
    PageObjectCreateSerializer,
    PageObjectElementSerializer,
    ScriptElementUsageSerializer,
    ElementValidationSerializer,
    CodeGenerationSerializer,
)
from ..operation_logger import log_operation

logger = logging.getLogger(__name__)


class LocatorStrategyViewSet(viewsets.ModelViewSet):
    queryset = LocatorStrategy.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = LocatorStrategySerializer
    ordering = ['id']


class ElementViewSet(viewsets.ModelViewSet):
    queryset = Element.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'locator_strategy', 'element_type', 'validation_status', 'group']
    search_fields = ['name', 'description', 'page', 'component_name']

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ElementEnhancedSerializer
        return ElementSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的元素
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return Element.objects.filter(project__in=accessible_projects).select_related(
            'project', 'group', 'locator_strategy', 'created_by', 'parent_element'
        ).prefetch_related('script_usages__script').order_by('page', 'name')

    def filter_queryset(self, queryset):
        # 先应用默认的过滤器
        queryset = super().filter_queryset(queryset)

        # 处理页面筛选（使用page_name参数避免与分页page冲突）
        page_name = self.request.query_params.get('page_name', None)
        if page_name:
            queryset = queryset.filter(page=page_name)

        return queryset

    def perform_create(self, serializer):
        # 创建元素时自动设置创建人
        instance = serializer.save(created_by=self.request.user)
        # 记录操作
        log_operation('create', 'element', instance.id, instance.name, self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        # 记录操作
        log_operation('edit', 'element', instance.id, instance.name, self.request.user)

    def perform_destroy(self, instance):
        # 记录操作（在删除前记录）
        log_operation('delete', 'element', instance.id, instance.name, self.request.user)
        instance.delete()

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除元素"""
        try:
            ids = request.data.get('ids', [])
            if not ids:
                return Response({'error': '未提供要删除的元素ID'}, status=status.HTTP_400_BAD_REQUEST)
            if not isinstance(ids, list):
                return Response({'error': 'ids参数格式错误，应为数组'}, status=status.HTTP_400_BAD_REQUEST)

            queryset = self.get_queryset()
            elements_to_delete = queryset.filter(id__in=ids)
            if not elements_to_delete.exists():
                return Response({'error': '未找到可删除的元素或没有权限删除'}, status=status.HTTP_404_NOT_FOUND)

            for elem in elements_to_delete:
                log_operation('delete', 'element', elem.id, elem.name, request.user)

            deletable_ids = list(elements_to_delete.values_list('id', flat=True))
            deleted_count = Element.objects.filter(id__in=deletable_ids).delete()[0]

            return Response({'message': f'成功删除 {deleted_count} 个元素', 'deleted_count': deleted_count})
        except Exception as e:
            logger.error(f"批量删除元素失败: {str(e)}", exc_info=True)
            return Response({'error': f'批量删除失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def validate_locator(self, request, pk=None):
        """验证元素定位器有效性"""
        element = self.get_object()

        # 这里可以集成实际的浏览器验证逻辑
        # 现在只是模拟验证
        validation_result = self._perform_element_validation(element)

        element.validation_status = 'VALID' if validation_result['is_valid'] else 'INVALID'
        element.validation_message = validation_result['validation_message']
        element.last_validated = timezone.now()
        element.save()

        serializer = ElementValidationSerializer(validation_result)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def usages(self, request, pk=None):
        """获取元素在脚本中的使用情况"""
        element = self.get_object()
        usages = ScriptElementUsage.objects.filter(element=element).select_related('script')
        serializer = ScriptElementUsageSerializer(usages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """获取元素树形结构"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'error': '需要指定项目ID'}, status=status.HTTP_400_BAD_REQUEST)

        elements = self.get_queryset().filter(project_id=project_id)
        tree_data = self._build_element_tree(elements)
        return Response(tree_data)

    @action(detail=True, methods=['post'])
    def add_backup_locator(self, request, pk=None):
        """添加备用定位器"""
        element = self.get_object()
        strategy = request.data.get('strategy')
        value = request.data.get('value')

        if not strategy or not value:
            return Response({'error': '策略和值都是必需的'}, status=status.HTTP_400_BAD_REQUEST)

        backup_locators = element.backup_locators or []
        backup_locators.append({'strategy': strategy, 'value': value})
        element.backup_locators = backup_locators
        element.save()

        return Response({'message': '备用定位器添加成功'})

    @action(detail=True, methods=['post'])
    def generate_suggestions(self, request, pk=None):
        """生成元素使用建议"""
        element = self.get_object()
        suggestions = self._generate_element_suggestions(element)
        return Response({'suggestions': suggestions})

    def _perform_element_validation(self, element):
        """执行元素验证（模拟实现）"""
        try:
            # 这里可以集成实际的浏览器自动化工具进行验证
            # 现在只是简单的语法检查
            is_valid = True
            message = "定位器验证通过"
            suggestions = []

            # 简单的语法检查
            if element.locator_strategy.name == 'css':
                if not element.locator_value.strip():
                    is_valid = False
                    message = "CSS选择器不能为空"
            elif element.locator_strategy.name == 'xpath':
                if not element.locator_value.strip():
                    is_valid = False
                    message = "XPath表达式不能为空"

            return {
                'is_valid': is_valid,
                'validation_message': message,
                'suggestions': suggestions
            }
        except Exception as e:
            return {
                'is_valid': False,
                'validation_message': f'验证过程中出现错误: {str(e)}',
                'suggestions': []
            }

    def _build_element_tree(self, elements):
        """构建元素树形结构 - 返回元素列表而不是页面分组，因为前端会自己处理页面关联"""
        element_data_list = []
        for element in elements:
            element_data = {
                'id': element.id,
                'name': element.name,
                'type': 'element',
                'element_type': element.element_type,
                'locator_strategy': element.locator_strategy.name if element.locator_strategy else None,
                'locator_value': element.locator_value,
                'validation_status': element.validation_status,
                'usage_count': element.usage_count,
                'group_id': element.group_id,  # 用于前端关联到页面
                'page': element.page,  # 保留向后兼容
                'children': []
            }
            element_data_list.append(element_data)

        return element_data_list

    def _generate_element_suggestions(self, element):
        """生成元素使用建议"""
        suggestions = []

        # 基于元素类型生成建议
        if element.element_type == 'INPUT':
            suggestions.append("建议为输入框元素添加清空和输入验证操作")
        elif element.element_type == 'BUTTON':
            suggestions.append("建议验证按钮点击后的页面跳转或状态变化")
        elif element.element_type == 'DROPDOWN':
            suggestions.append("建议测试下拉框的所有选项")

        # 基于使用频率生成建议
        if element.usage_count == 0:
            suggestions.append("此元素尚未在任何脚本中使用，考虑是否需要删除")
        elif element.usage_count > 10:
            suggestions.append("此元素使用频率较高，建议添加到页面对象中以提高复用性")

        return suggestions


class ElementGroupViewSet(viewsets.ModelViewSet):
    queryset = ElementGroup.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'parent_group']
    search_fields = ['name', 'description']

    def get_serializer_class(self):
        if self.action == 'create':
            return ElementGroupCreateSerializer
        return ElementGroupSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的元素分组
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return ElementGroup.objects.filter(project__in=accessible_projects).select_related(
            'project__owner', 'project__login_test_case', 'parent_group'
        ).prefetch_related('project__members').annotate(
            # 注解元素数量，ElementGroupSerializer.get_elements_count 直接读取
            elements_total=models.Count('elements', distinct=True)
        ).order_by('order', 'name')

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """获取分组树形结构"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'error': '需要指定项目ID'}, status=status.HTTP_400_BAD_REQUEST)

        groups = self.get_queryset().filter(project_id=project_id, parent_group__isnull=True)
        serializer = ElementGroupSerializer(groups, many=True)
        return Response(serializer.data)


class PageObjectViewSet(viewsets.ModelViewSet):
    queryset = PageObject.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'class_name', 'description']

    def get_serializer_class(self):
        if self.action == 'create':
            return PageObjectCreateSerializer
        return PageObjectSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的项目的页面对象
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return PageObject.objects.filter(project__in=accessible_projects).select_related(
            'project', 'created_by'
        ).prefetch_related('page_object_elements__element').order_by('-created_at')

    @action(detail=True, methods=['post'])
    def generate_code(self, request, pk=None):
        """生成页面对象代码"""
        page_object = self.get_object()
        serializer = CodeGenerationSerializer(data=request.data)

        if serializer.is_valid():
            language = serializer.validated_data['language']
            framework = serializer.validated_data['framework']
            include_comments = serializer.validated_data['include_comments']

            try:
                generated_code = page_object.generate_code(language)

                # 保存生成的代码模板
                page_object.template_code = generated_code
                page_object.save()

                return Response({
                    'code': generated_code,
                    'language': language,
                    'framework': framework
                })
            except Exception as e:
                return Response({
                    'error': f'代码生成失败: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def add_element(self, request, pk=None):
        """向页面对象添加元素"""
        page_object = self.get_object()
        serializer = PageObjectElementSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(page_object=page_object)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def elements(self, request, pk=None):
        """获取页面对象的所有元素"""
        page_object = self.get_object()
        po_elements = page_object.page_object_elements.select_related('element').all()
        serializer = PageObjectElementSerializer(po_elements, many=True)
        return Response(serializer.data)


class PageObjectElementViewSet(viewsets.ModelViewSet):
    queryset = PageObjectElement.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = PageObjectElementSerializer

    def get_queryset(self):
        # 只显示用户有权限访问的页面对象元素
        user = self.request.user
        accessible_projects = UiProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()
        return PageObjectElement.objects.filter(
            page_object__project__in=accessible_projects
        ).select_related('page_object', 'element').order_by('id')
