"""AI 生成测试用例的查看与评审视图"""
import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from apps.projects.access import project_or_owner_q

from ..models import GeneratedTestCase
from ..serializers import GeneratedTestCaseSerializer, TestCaseReviewRequestSerializer

logger = logging.getLogger(__name__)

class GeneratedTestCasePagination(PageNumberPagination):
    """生成测试用例分页器"""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class GeneratedTestCaseViewSet(viewsets.ModelViewSet):
    """生成的测试用例视图集"""
    queryset = GeneratedTestCase.objects.all()  # 仅用于路由 basename，实际数据由 get_queryset 按权限过滤
    serializer_class = GeneratedTestCaseSerializer
    pagination_class = GeneratedTestCasePagination
    http_method_names = ['get', 'patch']  # 只允许GET和PATCH方法

    def get_queryset(self):
        queryset = GeneratedTestCase.objects.filter(project_or_owner_q(
            self.request.user,
            'requirement__analysis__document__project',
            'requirement__analysis__document__uploaded_by',
        ))

        # 按需求ID过滤
        requirement_id = self.request.query_params.get('requirement_id')
        if requirement_id:
            queryset = queryset.filter(requirement_id=requirement_id)

        # 按状态过滤
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        # 按优先级过滤
        priority_param = self.request.query_params.get('priority')
        if priority_param:
            queryset = queryset.filter(priority=priority_param)

        return queryset

    @action(detail=False, methods=['post'])
    def review_test_cases(self, request):
        """评审测试用例"""
        serializer = TestCaseReviewRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            test_case_ids = serializer.validated_data['test_case_ids']
            review_criteria = serializer.validated_data['review_criteria']

            # 同步执行评审
            def run_review():
                try:
                    # 获取测试用例
                    test_cases = GeneratedTestCase.objects.filter(id__in=test_case_ids)

                    passed_count = 0
                    reviewed_cases = []

                    for test_case in test_cases:
                        # 模拟评审逻辑
                        is_passed = len(test_case.title) > 10 and len(test_case.test_steps) > 20

                        if is_passed:
                            passed_count += 1
                            test_case.status = 'approved'
                            test_case.review_comments = '测试用例设计合理，满足评审标准'
                        else:
                            test_case.status = 'rejected'
                            test_case.review_comments = '测试用例需要完善，请补充详细的测试步骤'

                        test_case.reviewed_by_ai = 'AI-Reviewer-v1.0'
                        test_case.save()

                        reviewed_cases.append({
                            'id': test_case.id,
                            'case_id': test_case.case_id,
                            'title': test_case.title,
                            'status': test_case.status,
                            'review_comments': test_case.review_comments
                        })

                    total_count = len(test_cases)
                    pass_rate = (passed_count / total_count * 100) if total_count > 0 else 0

                    return {
                        'total_count': total_count,
                        'passed_count': passed_count,
                        'pass_rate': pass_rate,
                        'reviewed_cases': reviewed_cases
                    }

                except Exception as e:
                    logger.error(f"评审测试用例失败: {e}")
                    raise e

            review_result = run_review()

            return Response({
                'message': f'评审完成，通过率: {review_result["pass_rate"]:.2f}%',
                'review_result': review_result
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"评审测试用例时出错: {e}")
            return Response(
                {'error': f'评审失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
