from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.projects.models import Project
from apps.testcases.models import TestCase
from apps.versions.models import Version

class TestPlan(models.Model):
    """测试计划"""
    name = models.CharField(max_length=200, verbose_name='计划名称')
    description = models.TextField(blank=True, verbose_name='计划描述')
    projects = models.ManyToManyField(Project, blank=True, related_name='test_plans', verbose_name='关联项目')
    version = models.ForeignKey(Version, on_delete=models.CASCADE, null=True, blank=True, related_name='test_plans', verbose_name='关联版本')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_plans', verbose_name='创建者')
    assignees = models.ManyToManyField(User, blank=True, related_name='assigned_plans', verbose_name='指派给')
    is_active = models.BooleanField(default=True, verbose_name='是否激活')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'test_plans'
        verbose_name = '测试计划'
        verbose_name_plural = '测试计划'
        ordering = ['-created_at']

class TestRun(models.Model):
    """测试执行"""
    STATUS_CHOICES = [
        ('untested', '未测试'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('blocked', '阻塞'),
    ]
    
    name = models.CharField(max_length=200, verbose_name='执行名称')
    description = models.TextField(blank=True, verbose_name='执行描述')
    test_plan = models.ForeignKey(TestPlan, on_delete=models.CASCADE, related_name='test_runs', verbose_name='测试计划')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='test_runs', verbose_name='关联项目')
    version = models.ForeignKey(Version, on_delete=models.CASCADE, null=True, blank=True, related_name='test_runs', verbose_name='关联版本')
    testcases = models.ManyToManyField(TestCase, through='TestRunCase', related_name='test_runs', verbose_name='测试用例')
    assignee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_runs', verbose_name='执行人')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_runs', verbose_name='创建者')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='untested', verbose_name='状态')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    due_date = models.DateTimeField(null=True, blank=True, verbose_name='截止日期')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'test_runs'
        verbose_name = '测试执行'
        verbose_name_plural = '测试执行'
        ordering = ['-created_at']
    
    # 执行进度统计涉及的用例状态
    STAT_STATUSES = ('untested', 'passed', 'failed', 'blocked', 'retest')

    @classmethod
    def stats_annotations(cls, prefix='run_cases'):
        """返回用于 annotate/aggregate 的统计表达式，一条 SQL 即可得到全部状态计数。

        viewset 在列表查询上 annotate 这些字段后，progress_stats 直接读取，避免 N+1。
        """
        from django.db.models import Count, Q
        annotations = {'_stat_total': Count(prefix, distinct=True)}
        for s in cls.STAT_STATUSES:
            annotations[f'_stat_{s}'] = Count(
                prefix, filter=Q(**{f'{prefix}__status': s}), distinct=True
            )
        return annotations

    @classmethod
    def with_progress_stats(cls, queryset):
        """为 TestRun 查询集附加进度统计注解

        注意：带聚合的查询不会再应用 Meta.ordering，调用方需要时请显式 order_by。
        """
        return queryset.annotate(**cls.stats_annotations())

    @staticmethod
    def build_progress_stats(counts):
        """根据状态计数字典（total/untested/passed/...）构造进度统计结果"""
        total = counts.get('total') or 0
        if total == 0:
            return {'total': 0, 'untested': 0, 'passed': 0, 'failed': 0, 'blocked': 0, 'retest': 0, 'progress': 0}

        stats = {'total': total}
        for s in TestRun.STAT_STATUSES:
            stats[s] = counts.get(s) or 0
        stats['tested'] = stats['passed'] + stats['failed'] + stats['blocked'] + stats['retest']
        stats['progress'] = round((stats['tested'] / total) * 100, 1) if total > 0 else 0
        return stats

    @property
    def progress_stats(self):
        """执行进度统计

        优先使用查询集上的注解（见 with_progress_stats），否则用一条聚合 SQL 计算。
        """
        if hasattr(self, '_stat_total'):
            counts = {'total': self._stat_total}
            for s in self.STAT_STATUSES:
                counts[s] = getattr(self, f'_stat_{s}', 0)
        else:
            from django.db.models import Count, Q
            agg = {'total': Count('id')}
            for s in self.STAT_STATUSES:
                agg[s] = Count('id', filter=Q(status=s))
            counts = self.run_cases.aggregate(**agg)
        return self.build_progress_stats(counts)

class TestRunCase(models.Model):
    """测试执行用例"""
    STATUS_CHOICES = [
        ('untested', '未测试'),
        ('passed', '通过'),
        ('failed', '失败'),
        ('blocked', '阻塞'),
        ('retest', '重测'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', '低'),
        ('medium', '中'),
        ('high', '高'),
        ('critical', '紧急'),
    ]
    
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='run_cases', verbose_name='测试执行')
    testcase = models.ForeignKey(TestCase, on_delete=models.CASCADE, verbose_name='测试用例')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='untested', verbose_name='执行状态')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', verbose_name='优先级')
    actual_result = models.TextField(blank=True, verbose_name='实际结果')
    comments = models.TextField(blank=True, verbose_name='备注')
    defects = models.JSONField(default=list, verbose_name='关联缺陷')  # 存储缺陷ID列表
    elapsed_time = models.DurationField(null=True, blank=True, verbose_name='执行耗时')
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name='执行者')
    executed_at = models.DateTimeField(null=True, blank=True, verbose_name='执行时间')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'test_run_cases'
        unique_together = ['test_run', 'testcase']
        verbose_name = '测试执行用例'
        verbose_name_plural = '测试执行用例'
        ordering = ['testcase__id']

class TestRunCaseHistory(models.Model):
    """测试执行历史"""
    run_case = models.ForeignKey(TestRunCase, on_delete=models.CASCADE, related_name='history', verbose_name='执行用例')
    status = models.CharField(max_length=20, choices=TestRunCase.STATUS_CHOICES, verbose_name='执行状态')
    actual_result = models.TextField(blank=True, verbose_name='实际结果')
    comments = models.TextField(blank=True, verbose_name='备注')
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='执行者')
    executed_at = models.DateTimeField(default=timezone.now, verbose_name='执行时间')
    
    class Meta:
        db_table = 'test_run_case_history'
        verbose_name = '测试执行历史'
        verbose_name_plural = '测试执行历史'
        ordering = ['-executed_at']