from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from .models import TestCaseReview, ReviewAssignment, TestCaseReviewComment, ReviewTemplate
from .serializers import (
    TestCaseReviewSerializer, TestCaseReviewCreateSerializer,
    ReviewAssignmentSerializer, TestCaseReviewCommentSerializer, 
    TestCaseReviewCommentCreateSerializer,
    ReviewTemplateSerializer, ReviewTemplateCreateSerializer
)
from apps.testcases.models import TestCase
from apps.users.models import User
from apps.projects.access import accessible_project_ids, ensure_project_access


def accessible_reviews(user):
    """用户可见的评审：本人创建、被指派评审，或属于可访问的项目"""
    return TestCaseReview.objects.filter(
        Q(creator=user) | Q(reviewers=user) | Q(projects__in=accessible_project_ids(user))
    ).distinct()


def _ensure_projects_access(user, projects):
    for project in projects or []:
        ensure_project_access(user, project)


def _ensure_review_payload_access(user, validated_data):
    """评审关联的项目和用例都必须属于用户可访问的项目"""
    _ensure_projects_access(user, validated_data.get('projects'))
    testcase_ids = validated_data.get('testcases') or []
    if testcase_ids and TestCase.objects.filter(id__in=testcase_ids).exclude(
        project_id__in=accessible_project_ids(user)
    ).exists():
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied('无权限评审部分测试用例')


class TestCaseReviewViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return TestCaseReviewCreateSerializer
        return TestCaseReviewSerializer
    
    def get_queryset(self):
        queryset = accessible_reviews(self.request.user).select_related('creator').prefetch_related(
            'projects', 'testcases', 'reviewers', 'comments', 'reviewassignment_set__reviewer'
        )
        
        # 过滤参数
        project_id = self.request.query_params.get('project', None)
        status_param = self.request.query_params.get('status', None)
        reviewer_id = self.request.query_params.get('reviewer', None)
        
        if project_id:
            queryset = queryset.filter(projects__id=project_id)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if reviewer_id:
            queryset = queryset.filter(reviewers__id=reviewer_id)
            
        return queryset
    
    def perform_create(self, serializer):
        _ensure_review_payload_access(self.request.user, serializer.validated_data)
        serializer.save(creator=self.request.user)

    def perform_update(self, serializer):
        _ensure_review_payload_access(self.request.user, serializer.validated_data)
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def assign_reviewers(self, request, pk=None):
        """分配评审人员"""
        review = self.get_object()
        reviewer_ids = request.data.get('reviewer_ids', [])
        
        for reviewer_id in reviewer_ids:
            try:
                reviewer = User.objects.get(id=reviewer_id)
                ReviewAssignment.objects.get_or_create(
                    review=review,
                    reviewer=reviewer,
                    defaults={'assigned_at': timezone.now()}
                )
            except User.DoesNotExist:
                continue
                
        return Response({'message': '评审人员分配成功'})
    
    @action(detail=True, methods=['post'])
    def submit_review(self, request, pk=None):
        """提交评审结果"""
        review = self.get_object()
        try:
            assignment = ReviewAssignment.objects.get(
                review=review, 
                reviewer=request.user
            )
            assignment.status = request.data.get('status', 'approved')
            assignment.comment = request.data.get('comment', '')
            assignment.checklist_results = request.data.get('checklist_results', {})
            assignment.reviewed_at = timezone.now()
            assignment.save()
            
            # 检查是否所有评审人都已完成评审
            pending_count = ReviewAssignment.objects.filter(
                review=review, 
                status='pending'
            ).count()
            
            if pending_count == 0:
                # 检查评审结果，如果所有人都通过则设为已通过
                approved_count = ReviewAssignment.objects.filter(
                    review=review, 
                    status='approved'
                ).count()
                total_count = ReviewAssignment.objects.filter(review=review).count()
                
                if approved_count == total_count:
                    review.status = 'approved'
                else:
                    review.status = 'rejected'
                    
                review.completed_at = timezone.now()
                review.save()
                
            return Response({'message': '评审提交成功'})
            
        except ReviewAssignment.DoesNotExist:
            return Response(
                {'error': '您未被分配为此评审的评审人'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    @action(detail=False, methods=['get'])
    def my_reviews(self, request):
        """获取我的评审任务"""
        reviews = TestCaseReview.objects.filter(
            reviewers=request.user
        ).select_related('creator').prefetch_related('projects')
        
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)


class TestCaseReviewCommentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return TestCaseReviewCommentCreateSerializer
        return TestCaseReviewCommentSerializer
    
    def get_queryset(self):
        review_id = self.request.query_params.get('review', None)
        testcase_id = self.request.query_params.get('testcase', None)
        
        queryset = TestCaseReviewComment.objects.filter(
            review__in=accessible_reviews(self.request.user)
        ).select_related('author', 'testcase', 'review')
        
        if review_id:
            queryset = queryset.filter(review_id=review_id)
        if testcase_id:
            queryset = queryset.filter(testcase_id=testcase_id)
            
        return queryset
    
    def perform_create(self, serializer):
        review = serializer.validated_data.get('review')
        if review is not None and not accessible_reviews(self.request.user).filter(pk=review.pk).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('无权限评论该评审')
        serializer.save(author=self.request.user)


class ReviewTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ReviewTemplateCreateSerializer
        return ReviewTemplateSerializer
    
    def get_queryset(self):
        project_id = self.request.query_params.get('project', None)
        user = self.request.user
        queryset = ReviewTemplate.objects.filter(
            Q(creator=user) | Q(project__in=accessible_project_ids(user))
        ).distinct().select_related('creator').prefetch_related('project', 'default_reviewers')
        
        if project_id:
            queryset = queryset.filter(project__id=project_id)
            
        return queryset.filter(is_active=True)
    
    def perform_create(self, serializer):
        _ensure_projects_access(self.request.user, serializer.validated_data.get('project'))
        serializer.save(creator=self.request.user)

    def perform_update(self, serializer):
        _ensure_projects_access(self.request.user, serializer.validated_data.get('project'))
        serializer.save()