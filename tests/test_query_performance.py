"""查询性能回归测试：列表/统计接口的 SQL 条数不应随数据量增长（N+1）"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.executions import models as exec_models
from apps.projects.models import Project
from apps.testcases.models import TestCase as Case
from apps.ui_automation import models as ui_models
from apps.ui_automation.models import UiProject, ElementGroup

# 以别名引用 Test* 模型，避免 pytest 误当作测试类收集
Plan, Run, RunCase = exec_models.TestPlan, exec_models.TestRun, exec_models.TestRunCase
Suite, Script = ui_models.TestSuite, ui_models.TestScript
SuiteScript, SuiteCase, UiCase = ui_models.TestSuiteScript, ui_models.TestSuiteTestCase, ui_models.TestCase

User = get_user_model()


class _QueryCountMixin:
    def setUp(self):
        self.user = User.objects.create_user(username='perf_owner', password='pw')
        self.project = Project.objects.create(name='P', owner=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self._seq = 0

    def _count_queries(self, url):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        return len(ctx.captured_queries), resp

    def _make_plan_with_run(self, statuses=('passed', 'failed', 'untested'), defects=None):
        """创建一个计划 + 一个执行 + 若干执行用例"""
        self._seq += 1
        plan = Plan.objects.create(name=f'plan{self._seq}', creator=self.user)
        plan.projects.add(self.project)
        run = Run.objects.create(
            name=f'run{self._seq}', test_plan=plan, project=self.project,
            creator=self.user, assignee=self.user,
        )
        for i, st in enumerate(statuses):
            case = Case.objects.create(title=f'c{self._seq}_{i}', project=self.project, author=self.user)
            RunCase.objects.create(
                test_run=run, testcase=case, status=st,
                defects=(defects[i] if defects else []),
            )
        return plan, run


class ProgressStatsBehaviourTest(_QueryCountMixin, TestCase):
    def test_progress_stats_values(self):
        _, run = self._make_plan_with_run(
            statuses=('passed', 'passed', 'failed', 'blocked', 'retest', 'untested', 'untested', 'untested')
        )
        expected = {
            'total': 8, 'untested': 3, 'passed': 2, 'failed': 1, 'blocked': 1, 'retest': 1,
            'tested': 5, 'progress': 62.5,
        }
        # 未注解：单条聚合 SQL
        with self.assertNumQueries(1):
            self.assertEqual(run.progress_stats, expected)
        # 注解后：不再查询
        annotated = Run.with_progress_stats(Run.objects.filter(id=run.id)).get()
        with self.assertNumQueries(0):
            self.assertEqual(annotated.progress_stats, expected)

    def test_progress_stats_empty_run(self):
        _, run = self._make_plan_with_run(statuses=())
        empty = {'total': 0, 'untested': 0, 'passed': 0, 'failed': 0, 'blocked': 0, 'retest': 0, 'progress': 0}
        self.assertEqual(run.progress_stats, empty)
        annotated = Run.with_progress_stats(Run.objects.filter(id=run.id)).get()
        self.assertEqual(annotated.progress_stats, empty)


class ExecutionsQueryCountTest(_QueryCountMixin, TestCase):
    def test_runs_list_constant_queries(self):
        self._make_plan_with_run()
        q1, resp = self._count_queries('/api/executions/runs/')
        for _ in range(4):
            self._make_plan_with_run()
        q5, resp = self._count_queries('/api/executions/runs/')
        self.assertEqual(q1, q5)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]['progress']['total'], 3)
        self.assertEqual(results[0]['progress']['tested'], 2)
        self.assertEqual(results[0]['progress']['progress'], 66.7)

    def test_plans_list_constant_queries(self):
        self._make_plan_with_run()
        q1, _ = self._count_queries('/api/executions/plans/')
        for _ in range(4):
            self._make_plan_with_run()
        q5, _ = self._count_queries('/api/executions/plans/')
        self.assertEqual(q1, q5)

    def test_plan_detail_constant_queries(self):
        plan, _ = self._make_plan_with_run()
        q1, _ = self._count_queries(f'/api/executions/plans/{plan.id}/')
        # 同一计划下再加 4 个执行
        for i in range(4):
            run = Run.objects.create(
                name=f'extra{i}', test_plan=plan, project=self.project,
                creator=self.user, assignee=self.user,
            )
            case = Case.objects.create(title=f'extra{i}', project=self.project, author=self.user)
            RunCase.objects.create(test_run=run, testcase=case, status='passed')
        q5, resp = self._count_queries(f'/api/executions/plans/{plan.id}/')
        self.assertEqual(q1, q5)
        self.assertEqual(len(resp.data['test_runs']), 5)


class ReportsDashboardQueryCountTest(_QueryCountMixin, TestCase):
    def test_dashboard_constant_queries_and_values(self):
        self._make_plan_with_run(statuses=('passed', 'failed'), defects=[['BUG-1', 'BUG-2'], []])
        q1, resp1 = self._count_queries('/api/reports/reports/dashboard/')
        self.assertEqual(resp1.data['total_defects'], 2)

        for _ in range(4):
            self._make_plan_with_run(statuses=('passed', 'untested'), defects=[['BUG-3'], []])
        # 空执行的计划：进度计 0 且不能导致异常
        self._make_plan_with_run(statuses=())
        q6, resp = self._count_queries('/api/reports/reports/dashboard/')
        self.assertEqual(q1, q6)

        data = resp.data
        self.assertEqual(data['active_plans'], 6)
        self.assertEqual(data['total_cases'], 2 + 4 * 2)
        self.assertEqual(data['total_defects'], 2 + 4)
        # 每个计划只有一个执行：plan1=100，其余 4 个=50，空计划=0 → (100+200+0)/6
        self.assertEqual(data['plan_progress'], round((100 + 4 * 50 + 0) / 6, 1))
        # 最近 10 个执行：tested=2+4*1=6, passed=1+4=5
        self.assertEqual(data['pass_rate'], round(5 / 6 * 100, 1))


class UiAutomationQueryCountTest(_QueryCountMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ui_project = UiProject.objects.create(name='UI', base_url='http://x', owner=self.user)
        self.ui_project.members.add(self.user)

    def _make_suite(self):
        self._seq += 1
        suite = Suite.objects.create(project=self.ui_project, name=f's{self._seq}', created_by=self.user)
        script = Script.objects.create(project=self.ui_project, name=f'sc{self._seq}')
        SuiteScript.objects.create(test_suite=suite, test_script=script, order=1)
        for i in range(2):
            case = UiCase.objects.create(project=self.ui_project, name=f'uc{self._seq}_{i}', created_by=self.user)
            SuiteCase.objects.create(test_suite=suite, test_case=case, order=i)
        return suite

    def test_suite_list_constant_queries(self):
        self._make_suite()
        q1, _ = self._count_queries('/api/ui-automation/test-suites/')
        for _ in range(4):
            self._make_suite()
        q5, resp = self._count_queries('/api/ui-automation/test-suites/')
        self.assertEqual(q1, q5)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r['test_case_count'] == 2 and r['script_count'] == 1 for r in results))

    def test_element_group_list_constant_queries(self):
        ElementGroup.objects.create(project=self.ui_project, name='g0')
        q1, _ = self._count_queries('/api/ui-automation/element-groups/')
        for i in range(4):
            ElementGroup.objects.create(project=self.ui_project, name=f'g{i + 1}')
        q5, resp = self._count_queries('/api/ui-automation/element-groups/')
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r['elements_count'] == 0 for r in results))
        self.assertEqual(q1, q5)

    def test_element_group_children_tree(self):
        root = ElementGroup.objects.create(project=self.ui_project, name='root')
        child = ElementGroup.objects.create(project=self.ui_project, name='child', parent_group=root)
        ElementGroup.objects.create(project=self.ui_project, name='leaf', parent_group=child)
        _, resp = self._count_queries(f'/api/ui-automation/element-groups/tree/?project={self.ui_project.id}')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['children'][0]['name'], 'child')
        self.assertEqual(resp.data[0]['children'][0]['children'][0]['name'], 'leaf')
        self.assertEqual(resp.data[0]['children'][0]['children'][0]['children'], [])


class ApiCollectionTreeQueryCountTest(_QueryCountMixin, TestCase):
    def test_collection_children_tree_constant_queries(self):
        from apps.api_testing.models import ApiProject, ApiCollection
        api_project = ApiProject.objects.create(
            name='API', project_type='HTTP', status='IN_PROGRESS', owner=self.user
        )

        def make_branch(i):
            root = ApiCollection.objects.create(name=f'r{i}', project=api_project, order=i)
            child = ApiCollection.objects.create(name=f'c{i}', project=api_project, parent=root)
            ApiCollection.objects.create(name=f'l{i}', project=api_project, parent=child)

        make_branch(0)
        q1, _ = self._count_queries(f'/api/api-testing/collections/?project={api_project.id}&parent__isnull=True')
        for i in range(1, 5):
            make_branch(i)
        q5, resp = self._count_queries(f'/api/api-testing/collections/?project={api_project.id}')
        self.assertEqual(q1, q5)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        roots = [r for r in results if r['parent'] is None]
        self.assertEqual(len(roots), 5)
        self.assertEqual(roots[0]['children'][0]['name'], 'c0')
        self.assertEqual(roots[0]['children'][0]['children'][0]['name'], 'l0')
        self.assertEqual(roots[0]['children'][0]['children'][0]['children'], [])


class RequirementSerializerAuthTest(TestCase):
    def test_anonymous_user_rejected_instead_of_superuser_fallback(self):
        from types import SimpleNamespace
        from django.contrib.auth.models import AnonymousUser
        from rest_framework import serializers as drf_serializers
        from apps.requirement_analysis.serializers import PromptConfigSerializer, _authenticated_user

        User.objects.create_superuser(username='root', password='pw', email='r@example.com')
        ser = PromptConfigSerializer(context={'request': SimpleNamespace(user=AnonymousUser())})
        with self.assertRaises(drf_serializers.ValidationError):
            _authenticated_user(ser)
        user = User.objects.create_user(username='u1', password='pw')
        ser = PromptConfigSerializer(context={'request': SimpleNamespace(user=user)})
        self.assertEqual(_authenticated_user(ser), user)
