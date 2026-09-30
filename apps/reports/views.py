from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
from .models import TestReport, ReportTemplate
from apps.executions.models import TestPlan, TestRun, TestRunCase
from apps.testcases.models import TestCase
from apps.requirement_analysis.models import RequirementAnalysis, GeneratedTestCase, BusinessRequirement
from apps.projects.access import accessible_project_ids

class TestReportViewSet(viewsets.ModelViewSet):
    """测试报告视图集"""
    queryset = TestReport.objects.all()  # 仅用于路由 basename，实际数据由 get_queryset 按权限过滤
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TestReport.objects.filter(project_id__in=self._pids())

    def _pids(self):
        """当前用户可访问的项目 ID 子查询，所有统计都限定在这些项目内"""
        return accessible_project_ids(self.request.user)
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """获取概览数据"""
        project_id = request.query_params.get('project')
        
        # 基础查询集
        plans_qs = TestPlan.objects.filter(is_active=True, projects__in=self._pids()).distinct()
        cases_qs = TestCase.objects.filter(project_id__in=self._pids())
        
        if project_id:
            plans_qs = plans_qs.filter(projects__id=project_id)
            cases_qs = cases_qs.filter(project_id=project_id)
            
        # 统计数据
        total_plans = plans_qs.count()
        total_cases = cases_qs.count()
        
        # 计算测试计划总进度
        # 所有活跃计划下 TestRun 的进度：一条带注解的查询取回每个 Run 的状态计数，内存中按计划分组求平均
        runs_qs = TestRun.with_progress_stats(TestRun.objects.filter(test_plan__in=plans_qs))
        stat_fields = ['_stat_total'] + [f'_stat_{s}' for s in TestRun.STAT_STATUSES]

        def _row_stats(row):
            counts = {'total': row['_stat_total']}
            for s in TestRun.STAT_STATUSES:
                counts[s] = row[f'_stat_{s}']
            return TestRun.build_progress_stats(counts)

        plan_run_progresses = {}
        for row in runs_qs.values('test_plan_id', *stat_fields):
            plan_run_progresses.setdefault(row['test_plan_id'], []).append(_row_stats(row)['progress'])

        # 仅统计有 Run 的计划：先求计划内 Run 平均进度，再对计划求平均
        plan_progresses = [sum(p) / len(p) for p in plan_run_progresses.values()]
        avg_plan_progress = round(sum(plan_progresses) / len(plan_progresses), 1) if plan_progresses else 0

        # 计算整体通过率（最近 10 个 Run）
        recent_rows = runs_qs.order_by('-created_at').values(*stat_fields)[:10]
        total_executed = 0
        total_passed = 0

        for row in recent_rows:
            stats = _row_stats(row)
            total_executed += stats.get('tested', 0)
            total_passed += stats['passed']

        pass_rate = round((total_passed / total_executed * 100), 1) if total_executed > 0 else 0

        # 统计缺陷总数 (基于 TestRunCase 的 defects 字段)，一次取回非空 defects 列
        defects_count = 0
        defects_values = TestRunCase.objects.filter(
            test_run__test_plan__in=plans_qs
        ).exclude(defects=[]).values_list('defects', flat=True)
        for defects in defects_values:
            if isinstance(defects, list):
                defects_count += len(defects)

        return Response({
            'active_plans': total_plans,
            'plan_progress': avg_plan_progress,
            'total_cases': total_cases,
            'total_defects': defects_count,
            'pass_rate': pass_rate
        })

    @action(detail=False, methods=['get'])
    def status_distribution(self, request):
        """获取执行状态分布"""
        project_id = request.query_params.get('project')
        version_id = request.query_params.get('version')
        
        runs_qs = TestRun.objects.filter(project_id__in=self._pids())
        if project_id:
            runs_qs = runs_qs.filter(project_id=project_id)
        if version_id:
            runs_qs = runs_qs.filter(version_id=version_id)
            
        distribution = TestRunCase.objects.filter(test_run__in=runs_qs).values('status').annotate(
            count=Count('id')
        )
        
        result = {item['status']: item['count'] for item in distribution}
        for status, _ in TestRunCase.STATUS_CHOICES:
            if status not in result:
                result[status] = 0
                
        return Response(result)

    @action(detail=False, methods=['get'])
    def defect_distribution(self, request):
        """获取缺陷分布 (按优先级)"""
        project_id = request.query_params.get('project')
        qs = TestRunCase.objects.filter(status='failed', test_run__project_id__in=self._pids())
        
        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        distribution = qs.values('priority').annotate(count=Count('id'))
        
        # 映射优先级显示
        priority_map = dict(TestRunCase.PRIORITY_CHOICES)
        result = []
        for item in distribution:
            result.append({
                'name': priority_map.get(item['priority'], item['priority']),
                'value': item['count']
            })
            
        return Response(result)

    @action(detail=False, methods=['get'])
    def failed_cases_top(self, request):
        """获取失败用例TOP榜"""
        project_id = request.query_params.get('project')
        
        qs = TestRunCase.objects.filter(status='failed', test_run__project_id__in=self._pids())
        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        # 按 testcase 分组统计失败次数
        top_failed = qs.values(
            'testcase__id', 'testcase__title'
        ).annotate(
            fail_count=Count('id')
        ).order_by('-fail_count')[:10]
        
        return Response(top_failed)

    @action(detail=False, methods=['get'])
    def execution_trend(self, request):
        """获取每日执行趋势"""
        project_id = request.query_params.get('project')
        days = int(request.query_params.get('days', 7))
        
        # 获取当前时区的今天开始时间
        current_tz = timezone.get_current_timezone()
        local_now = timezone.localtime(timezone.now())
        today = local_now.date()
        
        # 计算起始日期
        start_date = today - timedelta(days=days - 1)
        
        # 构造起始时间的 datetime 对象 (00:00:00)
        start_datetime = datetime.combine(start_date, datetime.min.time())
        start_datetime = timezone.make_aware(start_datetime, current_tz)
        
        qs = TestRunCase.objects.filter(
            executed_at__gte=start_datetime,
            status__in=['passed', 'failed', 'blocked', 'retest'],
            test_run__project_id__in=self._pids(),
        )
        
        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        # 由于数据库聚合(TruncDate)在某些环境下返回None，改为Python内存聚合
        # 获取所有符合条件的记录的执行时间
        executions = qs.values_list('executed_at', flat=True)
        
        # 初始化日期映射
        date_map = {}
        
        for executed_at in executions:
            if executed_at:
                # 转换为本地时间
                local_time = executed_at.astimezone(current_tz)
                date_str = local_time.date().strftime('%Y-%m-%d')
                date_map[date_str] = date_map.get(date_str, 0) + 1
        
        # 补全日期
        result = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            result.append({
                'date': date_str,
                'count': date_map.get(date_str, 0)
            })
            
        return Response(result)

    @action(detail=False, methods=['get'])
    def ai_efficiency(self, request):
        """获取AI效能分析"""
        project_id = request.query_params.get('project')
        
        cases_qs = TestCase.objects.filter(project_id__in=self._pids())
        generated_qs = GeneratedTestCase.objects.filter(requirement__analysis__document__project_id__in=self._pids())
        requirements_qs = BusinessRequirement.objects.filter(analysis__document__project_id__in=self._pids())
        
        if project_id:
            cases_qs = cases_qs.filter(project_id=project_id)
            generated_qs = generated_qs.filter(requirement__analysis__document__project_id=project_id)
            requirements_qs = requirements_qs.filter(analysis__document__project_id=project_id)
            
        # 1. AI生成 vs 人工创建
        ai_count = generated_qs.count()
        adopted_ai_count = generated_qs.filter(status='adopted').count()
        total_cases = cases_qs.count()
        manual_count = max(0, total_cases - adopted_ai_count)
        
        # 2. 生成采纳率
        adoption_rate = round((adopted_ai_count / ai_count * 100), 1) if ai_count > 0 else 0
        
        # 3. 需求覆盖率
        total_reqs = requirements_qs.count()
        covered_reqs = generated_qs.filter(status='adopted').values('requirement').distinct().count()
        coverage_rate = round((covered_reqs / total_reqs * 100), 1) if total_reqs > 0 else 0
        
        # 4. 节省时间估算
        saved_hours = round(ai_count * 15 / 60, 1)
        
        return Response({
            'ai_vs_manual': {
                'ai': ai_count,
                'manual': manual_count
            },
            'adoption_rate': adoption_rate,
            'requirement_coverage': coverage_rate,
            'saved_hours': saved_hours
        })

    @action(detail=False, methods=['get'])
    def team_workload(self, request):
        """获取团队工作量"""
        project_id = request.query_params.get('project')
        
        qs = TestRunCase.objects.filter(
            status__in=['passed', 'failed', 'blocked', 'retest'],
            executed_by__isnull=False,
            test_run__project_id__in=self._pids(),
        )
        
        if project_id:
            qs = qs.filter(test_run__project_id=project_id)
            
        # 统计执行数量
        execution_stats = qs.values(
            'executed_by__username'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # 统计发现缺陷数量
        defect_stats = {}
        defect_qs = qs.filter(status__in=['failed', 'blocked'])
        defect_data = defect_qs.values('executed_by__username').annotate(count=Count('id'))
        for item in defect_data:
            defect_stats[item['executed_by__username']] = item['count']
            
        result = []
        for item in execution_stats:
            username = item['executed_by__username']
            result.append({
                'username': username,
                'execution_count': item['count'],
                'defect_count': defect_stats.get(username, 0)
            })
            
        return Response(result)