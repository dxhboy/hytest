"""
UI自动化测试执行服务
支持 Playwright 和 Selenium 测试引擎

重构说明（2026-08）：
批量套件执行不再各自维护一套"点击/输入/断言..."的动作分支，而是直接复用
selenium_engine.SeleniumTestEngine 和 playwright_engine.PlaywrightTestEngine
的 execute_step()，与单用例调试执行走同一套实现。原来的
execute_step_playwright/execute_step_selenium（按 action_type 手写分支）已删除。

Playwright 分支由同步 API 切换为异步 API（通过 asyncio.run 驱动），
这样才能直接调用 PlaywrightTestEngine 的异步 execute_step()，
不需要再单独维护一套同步版本的动作实现。
"""
import asyncio
import time
import json
from datetime import datetime
from django.utils import timezone
from django.db import connection
from selenium.webdriver.support.ui import WebDriverWait

from .models import (
    TestSuite, TestExecution, TestCase, TestCaseStep,
    TestCaseExecution, Element
)
from .variable_resolver import resolve_variables
from .parameter_resolver import resolve_project_parameters
from .selenium_engine import SeleniumTestEngine
from .playwright_engine import PlaywrightTestEngine
from .base_engine import TestEngineProtocol


class _StepAttrView:
    """
    把预取的 step_data 字典包装成属性访问对象。

    SeleniumTestEngine / PlaywrightTestEngine 的 execute_step() 期望传入一个
    有 .action_type / .input_value / .wait_time / .assert_type / .assert_value
    属性的对象（通常是 TestCaseStep 模型实例）。批量执行为了避免在浏览器驱动的
    循环里反复访问 ORM，预先把步骤数据整理成了字典，这里做一层轻量适配，
    这样批量执行可以直接复用引擎的 execute_step()，不用再维护第二套实现。
    """

    def __init__(self, step_data):
        self.action_type = step_data.get('action_type')
        self.input_value = step_data.get('input_value')
        self.wait_time = step_data.get('wait_time')
        self.assert_type = step_data.get('assert_type')
        self.assert_value = step_data.get('assert_value')
        self.step_parameters = step_data.get('step_parameters') or {}


def _build_step_result(step_data, success, log, screenshot_base64=None):
    """把引擎 execute_step() 返回的 (success, log, screenshot_base64) 适配成
    批量执行历史上一直使用的 step_result 字典格式，尽量保持字段兼容。"""
    step_result = {
        'step_number': step_data['step_number'],
        'action_type': step_data['action_type'],
        'description': step_data['description'],
        'success': success,
        'error': None if success else log,
        'log': log,
    }
    if screenshot_base64:
        step_result['screenshot'] = screenshot_base64
    return step_result


class TestExecutor:
    """测试执行器基类"""

    def __init__(self, test_suite, engine='playwright', browser='chrome', headless=False, executed_by=None, remote_service=None):
        self.test_suite = test_suite
        self.engine = engine
        self.browser = browser
        self.headless = headless
        self.executed_by = executed_by
        self.remote_service = remote_service
        self.execution = None
        self.test_cases = []
        self.results = []
        self.scripts = []
        self.script_results = []

    def create_execution_record(self):
        """创建测试执行记录"""
        self.execution = TestExecution.objects.create(
            project=self.test_suite.project,
            test_suite=self.test_suite,
            status='RUNNING',
            engine=self.engine,
            browser=self.browser,
            headless=self.headless,
            executed_by=self.executed_by,
            started_at=timezone.now(),
            remote_browser_service=self.remote_service
        )
        return self.execution

    def update_execution_result(self, status, passed=0, failed=0, skipped=0, duration=0, error_msg=''):
        """更新执行结果"""
        self.execution.status = status
        self.execution.passed_cases = passed
        self.execution.failed_cases = failed
        self.execution.skipped_cases = skipped
        self.execution.total_cases = passed + failed + skipped
        self.execution.duration = duration
        self.execution.finished_at = timezone.now()
        self.execution.error_message = error_msg
        self.execution.result_data = {
            'test_cases': self.results,
            'scripts': self.script_results,
            'summary': {
                'total': self.execution.total_cases,
                'passed': passed,
                'failed': failed,
                'skipped': skipped,
                'pass_rate': round((passed / self.execution.total_cases * 100) if self.execution.total_cases > 0 else 0,
                                   2)
            }
        }
        self.execution.save()

        # 更新套件统计
        self.test_suite.passed_count = passed
        self.test_suite.failed_count = failed
        self.test_suite.execution_status = 'passed' if failed == 0 and passed > 0 else 'failed'
        self.test_suite.save()

    def get_test_cases(self):
        """获取测试套件中的所有测试用例"""
        suite_test_cases = self.test_suite.suite_test_cases.select_related('test_case').order_by('order')
        self.test_cases = [stc.test_case for stc in suite_test_cases]
        print(f"从套件 '{self.test_suite.name}' 获取到 {len(self.test_cases)} 个测试用例")
        for i, tc in enumerate(self.test_cases, 1):
            print(f"  {i}. {tc.name} (ID: {tc.id})")
        return self.test_cases

    def get_scripts(self):
        """获取测试套件中的所有脚本"""
        suite_scripts = self.test_suite.suite_scripts.select_related('test_script').order_by('order')
        self.scripts = [ss.test_script for ss in suite_scripts]
        if self.scripts:
            print(f"从套件 '{self.test_suite.name}' 获取到 {len(self.scripts)} 个脚本")
            for i, s in enumerate(self.scripts, 1):
                print(f"  {i}. {s.name} (ID: {s.id})")
        return self.scripts

    def get_execution_items(self):
        """获取测试用例和脚本的统一执行队列，按 order 混合排序"""
        items = []
        suite_test_cases = self.test_suite.suite_test_cases.select_related('test_case').order_by('order')
        for stc in suite_test_cases:
            items.append({'type': 'case', 'order': stc.order, 'data': stc.test_case})
        self.test_cases = [item['data'] for item in items if item['type'] == 'case']

        suite_scripts = self.test_suite.suite_scripts.select_related('test_script').order_by('order')
        for ss in suite_scripts:
            items.append({'type': 'script', 'order': ss.order, 'data': ss.test_script})
        self.scripts = [item['data'] for item in items if item['type'] == 'script']

        items.sort(key=lambda x: x['order'])

        print(f"从套件 '{self.test_suite.name}' 获取到 {len(self.test_cases)} 个用例, {len(self.scripts)} 个脚本")
        for i, item in enumerate(items, 1):
            tag = '用例' if item['type'] == 'case' else '脚本'
            print(f"  {i}. [{tag}] {item['data'].name} (order={item['order']})")
        return items

    def run_scripts(self):
        """Execute standalone scripts via subprocess"""
        import subprocess
        import tempfile
        import os

        for script in self.scripts:
            start_time = time.time()
            script_result = {
                'script_id': script.id,
                'script_name': script.name,
                'framework': script.framework,
                'language': script.language,
                'success': False,
                'output': '',
                'error': '',
                'duration': 0,
            }

            try:
                # Write script to temp file
                suffix = '.py' if script.language == 'python' else '.js'
                with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
                    f.write(script.content)
                    temp_path = f.name

                try:
                    result = subprocess.run(
                        ['python', temp_path],
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minute timeout
                        cwd=tempfile.gettempdir(),
                    )

                    script_result['output'] = result.stdout
                    script_result['error'] = result.stderr
                    script_result['success'] = result.returncode == 0
                finally:
                    os.unlink(temp_path)

            except subprocess.TimeoutExpired:
                script_result['error'] = 'Script execution timed out (300s)'
            except Exception as e:
                script_result['error'] = str(e)

            script_result['duration'] = round(time.time() - start_time, 2)
            self.script_results.append(script_result)

            print(f"  Script '{script.name}': {'PASS' if script_result['success'] else 'FAIL'}")

    # ------------------------------------------------------------------
    # 自动登录相关
    # ------------------------------------------------------------------

    def _build_case_data(self, test_case):
        """将一个 TestCase 模型实例转换为预取的 case_data 字典（供引擎执行）"""
        case_data = {
            'id': test_case.id,
            'name': test_case.name,
            'project_id': self.test_suite.project_id,
            'case_parameters': test_case.case_parameters,
            'steps': [],
        }
        steps = test_case.steps.select_related('element', 'element__locator_strategy').order_by('step_number')
        for step in steps:
            step_data = {
                'id': step.id,
                'step_number': step.step_number,
                'action_type': step.action_type,
                'description': step.description,
                'input_value': step.input_value,
                'wait_time': step.wait_time,
                'assert_type': step.assert_type,
                'assert_value': step.assert_value,
                'step_parameters': step.step_parameters,
                'element': None,
            }
            if step.element:
                step_data['element'] = {
                    'id': step.element.id,
                    'name': step.element.name,
                    'locator_value': step.element.locator_value,
                    'locator_strategy': step.element.locator_strategy.name if step.element.locator_strategy else 'css',
                    'wait_timeout': step.element.wait_timeout,
                    'force_action': step.element.force_action,
                }
            case_data['steps'].append(step_data)
        return case_data

    def _get_login_case_data(self, suite_case_ids):
        """如果项目配置了前置登录用例且套件中不包含该用例，返回登录用例的 case_data；否则返回 None"""
        login_tc = getattr(self.test_suite.project, 'login_test_case', None)
        if not login_tc:
            return None
        if login_tc.id in suite_case_ids:
            print(f"ℹ️  套件已包含登录用例「{login_tc.name}」，跳过自动登录")
            return None
        print(f"🔐 项目配置了前置登录用例「{login_tc.name}」(ID:{login_tc.id})，将自动执行")
        return self._build_case_data(login_tc)

    def run(self):
        """执行测试套件"""
        print(f"[TestExecutor] 初始化执行器...")
        try:
            # 设置环境变量，允许在后台线程/Celery worker 中使用同步 ORM
            import os
            os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

            # 关闭当前线程的数据库连接，避免线程间共享
            connection.close()
            print(f"[TestExecutor] 数据库连接已重置")

            # 创建执行记录
            print(f"[TestExecutor] 创建执行记录...")
            self.create_execution_record()
            print(f"[TestExecutor] 执行记录已创建: ID={self.execution.id}")

            # 获取统一执行队列（用例和脚本按 order 混合排序）
            print(f"[TestExecutor] 获取执行队列...")
            execution_items = self.get_execution_items()
            print(f"[TestExecutor] 执行队列共 {len(execution_items)} 项")

            if not execution_items:
                self.update_execution_result('FAILED', error_msg='No test cases or scripts to execute')
            else:
                # 根据引擎选择执行方式
                print(f"[TestExecutor] 使用引擎: {self.engine}")
                if self.engine == 'playwright':
                    print(f"[TestExecutor] 启动 Playwright 执行...")
                    self.run_with_playwright(execution_items)
                else:
                    print(f"[TestExecutor] 启动 Selenium 执行...")
                    self.run_with_selenium(execution_items)

            print(f"[TestExecutor] 执行完成")

        except Exception as e:
            print(f"[TestExecutor] 测试执行失败: {str(e)}")
            import traceback
            error_detail = traceback.format_exc()
            traceback.print_exc()
            try:
                if self.execution:
                    print(f"[TestExecutor] 更新执行结果为失败...")
                    self.update_execution_result(
                        status='FAILED',
                        error_msg=f"执行失败: {str(e)}\n\n{error_detail}"
                    )
                else:
                    # 执行记录（TestExecution）本身还没创建成功就出错了
                    # （比如 create_execution_record() 失败），update_execution_result
                    # 依赖 self.execution 无法调用，这里直接兜底把套件状态改回失败，
                    # 否则 run_suite 一开始设置的 execution_status='running' 永远没人
                    # 改回来，前端就会一直显示"执行中"
                    print(f"[TestExecutor] 执行记录未创建，直接重置套件状态为失败")
                    self.test_suite.execution_status = 'failed'
                    self.test_suite.save()
            except Exception as update_error:
                # 兜底逻辑本身也可能失败（比如数据库连接异常），至少打印出来方便排查，
                # 不再往上抛出以免线程崩溃后什么都没记录
                print(f"[TestExecutor] 更新套件状态失败: {update_error}")
        finally:
            # 确保关闭数据库连接
            print(f"[TestExecutor] 关闭数据库连接...")
            connection.close()
            print(f"[TestExecutor] 执行器已退出")

    # ------------------------------------------------------------------
    # Playwright 执行（异步 API，通过 asyncio.run 驱动；动作分支交给 PlaywrightTestEngine）
    # ------------------------------------------------------------------

    def run_with_playwright(self, execution_items=None):
        """使用 Playwright 执行测试套件（同步入口，内部用 asyncio.run 驱动异步引擎）"""
        import sys
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(self._run_with_playwright_async(execution_items))

    async def _run_with_playwright_async(self, execution_items=None):
        from playwright.async_api import async_playwright
        from .browser_factory import BrowserConnectionFactory, close_playwright_browser
        import subprocess as _subprocess
        import tempfile
        import os

        start_time = time.time()
        passed = 0
        failed = 0
        skipped = 0

        # 分离出用例项用于预处理
        case_items = [item for item in execution_items if item['type'] == 'case']
        has_cases = len(case_items) > 0

        # 检查 Playwright 是否可用（仅当有用例时需要）
        if has_cases:
            try:
                from playwright.async_api import async_playwright as test_import
            except ImportError as e:
                error_msg = (
                    "Playwright 模块未正确安装或 Django 服务器未在虚拟环境中运行。\n\n"
                    "请确保：\n"
                    "1. 已在虚拟环境中安装: pip install playwright\n"
                    "2. 已安装浏览器: playwright install\n"
                    "3. Django 服务器在虚拟环境中运行\n\n"
                    f"详细错误: {str(e)}"
                )
                print(f"❌ {error_msg}")

                if self.execution:
                    self.update_execution_result(
                        status='FAILED',
                        failed=len(execution_items),
                        error_msg=error_msg
                    )

                for test_case in self.test_cases:
                    TestCaseExecution.objects.filter(
                        test_case=test_case,
                        test_suite=self.test_suite,
                        status='pending'
                    ).update(
                        status='failed',
                        error_message=error_msg,
                        finished_at=timezone.now()
                    )

                return

        # 预先获取所有测试用例的步骤数据
        test_cases_data = {}
        for test_case in self.test_cases:
            case_data = {
                'id': test_case.id,
                'name': test_case.name,
                'project_id': self.test_suite.project.id,
                'case_parameters': test_case.case_parameters,
                'steps': []
            }

            steps = test_case.steps.select_related('element', 'element__locator_strategy').order_by('step_number')
            for step in steps:
                step_data = {
                    'id': step.id,
                    'step_number': step.step_number,
                    'action_type': step.action_type,
                    'description': step.description,
                    'input_value': step.input_value,
                    'wait_time': step.wait_time,
                    'assert_type': step.assert_type,
                    'assert_value': step.assert_value,
                    'step_parameters': step.step_parameters,
                    'element': None
                }

                if step.element:
                    step_data['element'] = {
                        'id': step.element.id,
                        'name': step.element.name,
                        'locator_value': step.element.locator_value,
                        'locator_strategy': step.element.locator_strategy.name if step.element.locator_strategy else 'css',
                        'wait_timeout': step.element.wait_timeout,
                        'force_action': step.element.force_action,
                        'default_value': step.element.default_value or '',
                    }

                case_data['steps'].append(step_data)

            test_cases_data[test_case.id] = case_data

        # 预先创建所有测试用例执行记录
        case_executions = {}
        for case_id, case_data in test_cases_data.items():
            case_execution = TestCaseExecution.objects.create(
                test_case_id=case_data['id'],
                project_id=case_data['project_id'],
                test_suite=self.test_suite,
                execution_source='suite',
                status='pending',
                engine=self.engine,
                browser=self.browser,
                headless=self.headless,
                created_by=self.executed_by
            )
            case_executions[case_data['id']] = case_execution

        # 自动登录：检查是否需要在用例执行前自动跑登录用例
        suite_case_ids = set(test_cases_data.keys())
        login_case_data = self._get_login_case_data(suite_case_ids) if has_cases else None

        total_items = len(execution_items)
        print(f"准备执行 {total_items} 个项目（{len(self.test_cases)} 用例 + {len(self.scripts)} 脚本，混合排序）")

        browser_type_map = {'chrome': 'chromium', 'firefox': 'firefox', 'safari': 'webkit', 'edge': 'chromium'}
        pw_browser_type = browser_type_map.get(self.browser, 'chromium')

        reuse_browser = getattr(self.test_suite, 'reuse_browser', False)
        if has_cases:
            if reuse_browser:
                print(f"🔄 浏览器复用模式：用例间共享同一浏览器实例")
            else:
                print(f"🆕 独立浏览器模式：每个用例使用独立浏览器")

        # 内联脚本执行辅助函数
        async def _execute_script_inline(script):
            """在混合队列中执行单个脚本"""
            script_start = time.time()
            script_result = {
                'script_id': script.id,
                'script_name': script.name,
                'framework': script.framework,
                'language': script.language,
                'success': False,
                'output': '',
                'error': '',
                'duration': 0,
            }
            try:
                suffix = '.py' if script.language == 'python' else '.js'
                with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
                    f.write(script.content)
                    temp_path = f.name
                try:
                    result = await asyncio.to_thread(
                        _subprocess.run,
                        ['python', temp_path],
                        capture_output=True, text=True, timeout=300
                    )
                    script_result['output'] = result.stdout
                    script_result['error'] = result.stderr
                    script_result['success'] = result.returncode == 0
                except _subprocess.TimeoutExpired:
                    script_result['error'] = 'Script execution timed out (300s)'
                except Exception as e:
                    script_result['error'] = str(e)
                finally:
                    os.unlink(temp_path)
            except Exception as e:
                script_result['error'] = f'Failed to prepare script: {str(e)}'
            script_result['duration'] = time.time() - script_start
            return script_result

        # 如果没有用例，不需要启动 Playwright，直接执行脚本
        if not has_cases:
            for i, item in enumerate(execution_items, 1):
                script = item['data']
                print(f"\n{'=' * 60}")
                print(f"正在执行第 {i}/{total_items} 项: [脚本] {script.name}")
                print(f"{'=' * 60}")
                sr = await _execute_script_inline(script)
                self.script_results.append(sr)
                status_text = '成功' if sr['success'] else '失败'
                print(f"{'✓' if sr['success'] else '✗'} 脚本执行{status_text}，耗时: {sr['duration']:.2f}秒")
                if sr['success']:
                    passed += 1
                else:
                    failed += 1
            duration = time.time() - start_time
            status = 'SUCCESS' if failed == 0 and passed > 0 else 'FAILED'
            self.update_execution_result(status, passed, failed, skipped, duration)
            return

        async with async_playwright() as p:
            # 复用模式：在循环外创建浏览器
            shared_browser = None
            shared_context = None
            shared_page = None
            shared_engine = None

            if reuse_browser:
                try:
                    shared_browser = await BrowserConnectionFactory.create_playwright_browser(
                        playwright_instance=p,
                        browser_type=pw_browser_type,
                        headless=self.headless,
                        remote_service=self.remote_service,
                    )
                    shared_context, shared_page = await BrowserConnectionFactory.create_playwright_context_and_page(
                        shared_browser,
                        remote_service=self.remote_service,
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
                    )
                    shared_engine = PlaywrightTestEngine.attach(shared_page, context=shared_context, browser=shared_browser, browser_type=pw_browser_type, project_id=self.test_suite.project_id)
                    assert isinstance(shared_engine, TestEngineProtocol), f"Engine {type(shared_engine)} does not conform to TestEngineProtocol"
                    print(f"✓ 共享浏览器已启动")

                    # 复用模式：只在第一次导航到基础 URL
                    if self.test_suite.project.base_url:
                        print(f"正在导航到: {self.test_suite.project.base_url}")
                        nav_success, nav_log = await shared_engine.navigate(self.test_suite.project.base_url)
                        print(nav_log)
                        if not nav_success:
                            raise Exception(nav_log)

                    # 复用模式：导航后自动执行一次登录用例
                    if login_case_data:
                        print(f"🔐 正在执行前置登录用例: {login_case_data['name']}")
                        login_result = await self.execute_test_case_playwright_no_db(shared_engine, login_case_data)
                        if login_result['status'] != 'passed':
                            raise Exception(f"前置登录用例执行失败: {login_result.get('error', '未知错误')}")
                        print(f"✓ 前置登录完成")

                except Exception as e:
                    print(f"✗ 共享浏览器启动/导航失败: {str(e)}")
                    for case_id, case_data in test_cases_data.items():
                        self.results.append({
                            'test_case_id': case_data['id'], 'test_case_name': case_data['name'],
                            'status': 'failed', 'steps': [], 'error': f"浏览器启动失败: {str(e)}",
                            'start_time': datetime.now().isoformat(), 'end_time': datetime.now().isoformat(), 'screenshots': []
                        })
                        failed += 1
                        ce = case_executions[case_data['id']]
                        ce.status = 'failed'; ce.finished_at = timezone.now(); ce.error_message = str(e); ce.save()
                    if shared_browser:
                        await close_playwright_browser(shared_browser)
                    duration = time.time() - start_time
                    self.update_execution_result('FAILED', 0, len(execution_items), 0, duration)
                    return

            for i, item in enumerate(execution_items, 1):
                # === 脚本项：通过 subprocess 执行 ===
                if item['type'] == 'script':
                    script = item['data']
                    print(f"\n{'=' * 60}")
                    print(f"正在执行第 {i}/{total_items} 项: [脚本] {script.name}")
                    print(f"{'=' * 60}")
                    sr = await _execute_script_inline(script)
                    self.script_results.append(sr)
                    status_text = '成功' if sr['success'] else '失败'
                    print(f"{'✓' if sr['success'] else '✗'} 脚本执行{status_text}，耗时: {sr['duration']:.2f}秒")
                    if sr['success']:
                        passed += 1
                    else:
                        failed += 1
                    continue

                # === 用例项：通过 Playwright 引擎执行 ===
                test_case = item['data']
                case_data = test_cases_data[test_case.id]
                print(f"\n{'=' * 60}")
                print(f"正在执行第 {i}/{total_items} 项: [用例] {case_data['name']}")
                print(f"{'=' * 60}")

                case_execution = case_executions[case_data['id']]
                case_execution.started_at = timezone.now()
                case_execution.status = 'running'
                case_execution.save()

                browser = shared_browser
                engine = shared_engine
                try:
                    # 复用模式：如果共享浏览器已被关闭（上个用例失败），重新创建并登录
                    if reuse_browser and shared_browser is None:
                        print(f"🔄 正在重启共享浏览器...")
                        shared_browser = await BrowserConnectionFactory.create_playwright_browser(
                            playwright_instance=p,
                            browser_type=pw_browser_type,
                            headless=self.headless,
                            remote_service=self.remote_service,
                        )
                        shared_context, shared_page = await BrowserConnectionFactory.create_playwright_context_and_page(
                            shared_browser,
                            remote_service=self.remote_service,
                            viewport={'width': 1920, 'height': 1080},
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
                        )
                        shared_engine = PlaywrightTestEngine.attach(shared_page, context=shared_context, browser=shared_browser, browser_type=pw_browser_type, project_id=self.test_suite.project_id)
                        assert isinstance(shared_engine, TestEngineProtocol), f"Engine {type(shared_engine)} does not conform to TestEngineProtocol"
                        print(f"✓ 共享浏览器已重启")

                        if self.test_suite.project.base_url:
                            print(f"正在导航到: {self.test_suite.project.base_url}")
                            nav_success, nav_log = await shared_engine.navigate(self.test_suite.project.base_url)
                            print(nav_log)
                            if not nav_success:
                                raise Exception(nav_log)

                        if login_case_data:
                            print(f"🔐 正在重新执行前置登录用例: {login_case_data['name']}")
                            login_result = await self.execute_test_case_playwright_no_db(shared_engine, login_case_data)
                            if login_result['status'] != 'passed':
                                raise Exception(f"前置登录用例执行失败: {login_result.get('error', '未知错误')}")
                            print(f"✓ 前置登录完成")

                        browser = shared_browser
                        engine = shared_engine

                    if not reuse_browser:
                        # 独立模式：每个用例创建新浏览器
                        browser = await BrowserConnectionFactory.create_playwright_browser(
                            playwright_instance=p,
                            browser_type=pw_browser_type,
                            headless=self.headless,
                            remote_service=self.remote_service,
                        )
                        print(f"✓ 浏览器已启动")

                        context, page = await BrowserConnectionFactory.create_playwright_context_and_page(
                            browser,
                            remote_service=self.remote_service,
                            viewport={'width': 1920, 'height': 1080},
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
                        )
                        engine = PlaywrightTestEngine.attach(page, context=context, browser=browser, browser_type=pw_browser_type, project_id=self.test_suite.project_id, case_parameters=case_data.get('case_parameters'))
                        assert isinstance(engine, TestEngineProtocol), f"Engine {type(engine)} does not conform to TestEngineProtocol"

                    if not reuse_browser and self.test_suite.project.base_url:
                        try:
                            print(f"正在导航到: {self.test_suite.project.base_url}")
                            success, nav_log = await engine.navigate(self.test_suite.project.base_url)
                            print(nav_log)
                            if not success:
                                raise Exception(nav_log)
                        except Exception as e:
                            print(f"✗ 导航失败: {str(e)}")
                            self.results.append({
                                'test_case_id': case_data['id'],
                                'test_case_name': case_data['name'],
                                'status': 'failed',
                                'steps': [],
                                'error': f"导航到基础URL失败: {str(e)}",
                                'start_time': datetime.now().isoformat(),
                                'end_time': datetime.now().isoformat(),
                                'screenshots': []
                            })
                            failed += 1
                            if not reuse_browser:
                                await close_playwright_browser(browser)
                                print(f"✓ 浏览器已关闭")
                            continue

                    # 独立模式：每个用例执行前自动登录
                    if not reuse_browser and login_case_data:
                        print(f"🔐 正在执行前置登录用例: {login_case_data['name']}")
                        login_result = await self.execute_test_case_playwright_no_db(engine, login_case_data)
                        if login_result['status'] != 'passed':
                            print(f"⚠️  前置登录失败: {login_result.get('error', '')}")

                    case_result = await self.execute_test_case_playwright_no_db(engine, case_data)
                    self.results.append(case_result)
                    print(f"✓ 用例执行完成，状态: {case_result['status']}")

                    case_execution = case_executions[case_data['id']]
                    case_execution.status = case_result['status']
                    case_execution.finished_at = timezone.now()
                    case_execution.execution_time = (
                                case_execution.finished_at - case_execution.started_at).total_seconds()
                    case_execution.execution_logs = json.dumps(case_result['steps'], ensure_ascii=False)
                    if case_result['error']:
                        case_execution.error_message = case_result['error']
                    if case_result.get('screenshots'):
                        case_execution.screenshots = case_result['screenshots']
                    case_execution.save()

                    print(f"⏱️  执行时长: {case_execution.execution_time:.2f}秒")

                    if case_result['status'] == 'passed':
                        passed += 1
                    elif case_result['status'] == 'failed':
                        failed += 1
                        # 复用模式下用例失败：关闭浏览器，后续用例执行前会重新打开
                        if reuse_browser:
                            print(f"⚠️  复用模式下用例失败，将重启浏览器以保证后续用例正常执行")
                            try:
                                await close_playwright_browser(shared_browser)
                            except Exception:
                                pass
                            shared_browser = None
                            shared_context = None
                            shared_page = None
                            shared_engine = None
                    else:
                        skipped += 1

                except Exception as e:
                    print(f"✗ 用例执行出现异常: {str(e)}")
                    self.results.append({
                        'test_case_id': case_data['id'],
                        'test_case_name': case_data['name'],
                        'status': 'failed',
                        'steps': [],
                        'error': f"用例执行异常: {str(e)}",
                        'start_time': datetime.now().isoformat(),
                        'end_time': datetime.now().isoformat(),
                        'screenshots': []
                    })
                    failed += 1

                    case_execution = case_executions[case_data['id']]
                    case_execution.status = 'failed'
                    case_execution.finished_at = timezone.now()
                    case_execution.execution_time = (
                                case_execution.finished_at - case_execution.started_at).total_seconds()
                    case_execution.error_message = f"用例执行异常: {str(e)}"
                    case_execution.save()

                    # 复用模式下异常：关闭浏览器，后续用例执行前会重新打开
                    if reuse_browser and shared_browser:
                        print(f"⚠️  复用模式下用例异常，将重启浏览器以保证后续用例正常执行")
                        try:
                            await close_playwright_browser(shared_browser)
                        except Exception:
                            pass
                        shared_browser = None
                        shared_context = None
                        shared_page = None
                        shared_engine = None

                finally:
                    if not reuse_browser and browser:
                        await close_playwright_browser(browser)
                        print(f"✓ 浏览器已关闭\n")

            # 复用模式：循环结束后关闭共享浏览器
            if reuse_browser and shared_browser:
                await close_playwright_browser(shared_browser)
                print(f"\n✓ 共享浏览器已关闭")

        duration = time.time() - start_time
        status = 'SUCCESS' if failed == 0 and passed > 0 else 'FAILED'
        self.update_execution_result(status, passed, failed, skipped, duration)

    async def execute_test_case_playwright_no_db(self, engine, case_data):
        """使用 PlaywrightTestEngine 执行单个测试用例的所有步骤（不直接访问数据库）

        Args:
            engine: 已经绑定好 page 的 PlaywrightTestEngine 实例（PlaywrightTestEngine.attach()）
            case_data: 预先准备的用例数据字典，包含id, name, project_id, steps等

        Note:
            步骤级别的具体动作（点击/输入/断言...）全部委托给 engine.execute_step()，
            与单用例调试执行使用同一套实现。switchTab 会更新 engine.page，
            后续步骤/截图都通过 engine.page 读取，天然拿到切换后的页面。
        """
        result = {
            'test_case_id': case_data['id'],
            'test_case_name': case_data['name'],
            'status': 'passed',
            'steps': [],
            'error': None,
            'start_time': datetime.now().isoformat(),
            'screenshots': []
        }

        # 共享引擎（复用浏览器模式）会跨用例复用同一个 engine 实例，这里每次执行
        # 用例前都刷新一遍 case_parameters，避免用上一个用例的参数覆盖当前用例
        engine.case_parameters = case_data.get('case_parameters') or {}

        try:
            for step_data in case_data['steps']:
                element_data = step_data['element'] or {}
                success, log, screenshot_b64 = await engine.execute_step(_StepAttrView(step_data), element_data)
                step_result = _build_step_result(step_data, success, log, screenshot_b64)
                print(f"📄 步骤 {step_data['step_number']} 执行完成: {'成功' if success else '失败'}")
                result['steps'].append(step_result)

                # 步骤执行完后添加短暂延迟，确保页面状态稳定（点击后可能触发动画/下拉框展开）
                if success and step_data['action_type'] in ('click', 'fill', 'hover'):
                    await engine.page.wait_for_timeout(800 if step_data['action_type'] == 'click' else 300)

                if not success:
                    result['status'] = 'failed'
                    result['error'] = step_result.get('error') or f"步骤 {step_data['step_number']} 执行失败"

                    if screenshot_b64:
                        result['screenshots'].append({
                            'url': screenshot_b64,
                            'description': f'步骤 {step_data["step_number"]} 失败截图: {step_data.get("description", "")}',
                            'step_number': step_data['step_number'],
                            'timestamp': datetime.now().isoformat()
                        })
                    else:
                        # engine.execute_step 在多数失败分支已经尝试截图；如果没拿到，这里再补一次
                        try:
                            extra_shot = await engine.capture_screenshot()
                        except Exception:
                            extra_shot = None
                        if extra_shot:
                            result['screenshots'].append({
                                'url': extra_shot,
                                'description': f'步骤 {step_data["step_number"]} 失败截图: {step_data.get("description", "")}',
                                'step_number': step_data['step_number'],
                                'timestamp': datetime.now().isoformat()
                            })
                    break

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            try:
                screenshot_b64 = await engine.capture_screenshot()
            except Exception:
                screenshot_b64 = None
            result['screenshots'].append({
                'url': screenshot_b64,
                'description': f'异常截图: {str(e)}',
                'step_number': None,
                'timestamp': datetime.now().isoformat()
            })

        result['end_time'] = datetime.now().isoformat()
        return result

    # ------------------------------------------------------------------
    # Selenium 执行（同步 API；动作分支交给 SeleniumTestEngine）
    # ------------------------------------------------------------------

    def run_with_selenium(self, execution_items=None):
        """使用 Selenium 执行测试"""
        import subprocess as _subprocess
        import tempfile
        import os as _os

        start_time = time.time()
        passed = 0
        failed = 0
        skipped = 0

        # 分离出用例项用于预处理
        case_items = [item for item in execution_items if item['type'] == 'case']
        has_cases = len(case_items) > 0

        # 预先获取所有测试用例的步骤数据，避免在Selenium上下文中访问ORM
        test_cases_data = {}
        for test_case in self.test_cases:
            case_data = {
                'id': test_case.id,
                'name': test_case.name,
                'project_id': self.test_suite.project.id,
                'case_parameters': test_case.case_parameters,
                'steps': []
            }

            steps = test_case.steps.select_related('element', 'element__locator_strategy').order_by('step_number')
            for step in steps:
                step_data = {
                    'id': step.id,
                    'step_number': step.step_number,
                    'action_type': step.action_type,
                    'description': step.description,
                    'input_value': step.input_value,
                    'wait_time': step.wait_time,
                    'assert_type': step.assert_type,
                    'assert_value': step.assert_value,
                    'step_parameters': step.step_parameters,
                    'element': None
                }

                if step.element:
                    step_data['element'] = {
                        'id': step.element.id,
                        'name': step.element.name,
                        'locator_value': step.element.locator_value,
                        'locator_strategy': step.element.locator_strategy.name if step.element.locator_strategy else 'css',
                        'wait_timeout': step.element.wait_timeout,
                        'force_action': step.element.force_action,
                        'default_value': step.element.default_value or '',
                    }

                case_data['steps'].append(step_data)

            test_cases_data[test_case.id] = case_data

        # 预先创建所有测试用例执行记录
        case_executions = {}
        for case_id, case_data in test_cases_data.items():
            case_execution = TestCaseExecution.objects.create(
                test_case_id=case_data['id'],
                project_id=case_data['project_id'],
                test_suite=self.test_suite,
                execution_source='suite',
                status='pending',
                engine=self.engine,
                browser=self.browser,
                headless=self.headless,
                created_by=self.executed_by
            )
            case_executions[case_data['id']] = case_execution

        # 自动登录
        suite_case_ids = set(test_cases_data.keys())
        login_case_data = self._get_login_case_data(suite_case_ids) if has_cases else None

        reuse_browser = getattr(self.test_suite, 'reuse_browser', False)
        total_items = len(execution_items)
        print(f"准备执行 {total_items} 个项目（{len(self.test_cases)} 用例 + {len(self.scripts)} 脚本，混合排序）")
        if has_cases:
            if reuse_browser:
                print(f"🔄 浏览器复用模式：用例间共享浏览器状态，不重新打开/登录")
            else:
                print(f"🆕 独立模式：每个用例清理浏览器状态并重新导航到基础URL")

        use_browser_reuse = self.browser != 'safari'

        # 内联脚本执行辅助函数
        def _execute_script_inline(script):
            script_start = time.time()
            script_result = {
                'script_id': script.id,
                'script_name': script.name,
                'framework': script.framework,
                'language': script.language,
                'success': False,
                'output': '',
                'error': '',
                'duration': 0,
            }
            try:
                suffix = '.py' if script.language == 'python' else '.js'
                with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
                    f.write(script.content)
                    temp_path = f.name
                try:
                    result = _subprocess.run(
                        ['python', temp_path],
                        capture_output=True, text=True, timeout=300
                    )
                    script_result['output'] = result.stdout
                    script_result['error'] = result.stderr
                    script_result['success'] = result.returncode == 0
                except _subprocess.TimeoutExpired:
                    script_result['error'] = 'Script execution timed out (300s)'
                except Exception as e:
                    script_result['error'] = str(e)
                finally:
                    _os.unlink(temp_path)
            except Exception as e:
                script_result['error'] = f'Failed to prepare script: {str(e)}'
            script_result['duration'] = time.time() - script_start
            return script_result

        # 启动浏览器（仅当有用例时）
        driver = None
        if has_cases:
            if use_browser_reuse:
                try:
                    driver = self.create_selenium_driver()
                    print(f"✓ 浏览器已启动（将复用于所有用例）\n")
                except Exception as e:
                    print(f"✗ 浏览器启动失败: {str(e)}")
                    for case_id, case_data in test_cases_data.items():
                        self.results.append({
                            'test_case_id': case_data['id'],
                            'test_case_name': case_data['name'],
                            'status': 'failed',
                            'steps': [],
                            'error': f"浏览器启动失败: {str(e)}",
                            'start_time': datetime.now().isoformat(),
                            'end_time': datetime.now().isoformat(),
                            'screenshots': []
                        })
                        failed += 1
                    for case_id in test_cases_data:
                        ce = case_executions[case_id]
                        ce.status = 'failed'
                        ce.finished_at = timezone.now()
                        ce.execution_time = 0
                        ce.error_message = f"浏览器启动失败: {str(e)}"
                        ce.save()
                    duration = time.time() - start_time
                    self.update_execution_result('FAILED', 0, len(execution_items), 0, duration)
                    return
            else:
                print(f"ℹ️  Safari 浏览器将为每个用例独立启动（Safari 不支持浏览器复用）\n")

        case_index = 0
        for i, item in enumerate(execution_items, 1):
            # === 脚本项 ===
            if item['type'] == 'script':
                script = item['data']
                print(f"\n{'=' * 60}")
                print(f"正在执行第 {i}/{total_items} 项: [脚本] {script.name}")
                print(f"{'=' * 60}")
                sr = _execute_script_inline(script)
                self.script_results.append(sr)
                status_text = '成功' if sr['success'] else '失败'
                print(f"{'✓' if sr['success'] else '✗'} 脚本执行{status_text}，耗时: {sr['duration']:.2f}秒")
                if sr['success']:
                    passed += 1
                else:
                    failed += 1
                continue

            # === 用例项 ===
            test_case = item['data']
            case_data = test_cases_data[test_case.id]
            case_index += 1
            print(f"\n{'=' * 60}")
            print(f"正在执行第 {i}/{total_items} 项: [用例] {case_data['name']}")
            print(f"{'=' * 60}")

            case_execution = case_executions[case_data['id']]
            case_execution.started_at = timezone.now()
            case_execution.status = 'running'
            case_execution.save()

            # Safari：为每个用例启动新的浏览器
            if not use_browser_reuse:
                try:
                    driver = self.create_selenium_driver()
                    print(f"✓ Safari 浏览器已启动")
                except Exception as e:
                    print(f"✗ Safari 浏览器启动失败: {str(e)}")
                    self.results.append({
                        'test_case_id': case_data['id'],
                        'test_case_name': case_data['name'],
                        'status': 'failed',
                        'steps': [],
                        'error': f"浏览器启动失败: {str(e)}",
                        'start_time': datetime.now().isoformat(),
                        'end_time': datetime.now().isoformat(),
                        'screenshots': []
                    })
                    failed += 1
                    case_execution.status = 'failed'
                    case_execution.finished_at = timezone.now()
                    case_execution.execution_time = (
                                case_execution.finished_at - case_execution.started_at).total_seconds()
                    case_execution.error_message = f"浏览器启动失败: {str(e)}"
                    case_execution.save()
                    continue

            try:
                # 复用模式：如果浏览器已被关闭（上个用例失败），重新创建并登录
                if use_browser_reuse and reuse_browser and driver is None:
                    print(f"🔄 正在重启浏览器...")
                    try:
                        driver = self.create_selenium_driver()
                        print(f"✓ 浏览器已重启")
                    except Exception as restart_err:
                        print(f"✗ 浏览器重启失败: {str(restart_err)}")
                        self.results.append({
                            'test_case_id': case_data['id'],
                            'test_case_name': case_data['name'],
                            'status': 'failed',
                            'steps': [],
                            'error': f"浏览器重启失败: {str(restart_err)}",
                            'start_time': datetime.now().isoformat(),
                            'end_time': datetime.now().isoformat(),
                            'screenshots': []
                        })
                        failed += 1
                        case_execution.status = 'failed'
                        case_execution.finished_at = timezone.now()
                        case_execution.execution_time = (case_execution.finished_at - case_execution.started_at).total_seconds()
                        case_execution.error_message = f"浏览器重启失败: {str(restart_err)}"
                        case_execution.save()
                        continue

                    if self.test_suite.project.base_url:
                        resolved_base_url = resolve_project_parameters(
                            self.test_suite.project.base_url, self.test_suite.project_id
                        )
                        print(f"正在导航到: {resolved_base_url}")
                        driver.get(resolved_base_url)
                        try:
                            WebDriverWait(driver, 10).until(
                                lambda d: d.execute_script("return document.readyState") == "complete"
                            )
                        except:
                            pass
                        time.sleep(2)
                        print(f"✓ 导航完成")

                    if login_case_data:
                        print(f"🔐 正在重新执行前置登录用例: {login_case_data['name']}")
                        login_result = self.execute_test_case_selenium_no_db(driver, login_case_data)
                        if login_result['status'] != 'passed':
                            print(f"⚠️  前置登录失败: {login_result.get('error', '')}")
                        else:
                            print(f"✓ 前置登录完成")

                # 在每个用例开始前清理浏览器状态（仅对非复用模式，且跳过第1个用例）
                # reuse_browser=True 时跳过清理，保持上个用例的登录态和页面状态
                if use_browser_reuse and not reuse_browser and case_index > 1:
                    try:
                        print(f"🧹 清理浏览器状态...")
                        driver.delete_all_cookies()
                        driver.execute_script("window.localStorage.clear();")
                        driver.execute_script("window.sessionStorage.clear();")
                        print(f"✓ 浏览器状态已清理")
                    except Exception as clean_error:
                        print(f"⚠️  清理浏览器状态失败: {str(clean_error)}，继续执行...")

                # 导航到项目基础URL（复用模式下只在第1个用例导航，后续用例保持当前页面）
                should_navigate = self.test_suite.project.base_url and (not reuse_browser or case_index == 1)
                if should_navigate:
                    try:
                        # base_url 可能包含 "{{参数名}}" 项目参数引用，导航前先解析成真实值
                        resolved_base_url = resolve_project_parameters(
                            self.test_suite.project.base_url, self.test_suite.project_id
                        )
                        if resolved_base_url != self.test_suite.project.base_url:
                            print(f"正在导航到: {resolved_base_url} (原始: {self.test_suite.project.base_url})")
                        else:
                            print(f"正在导航到: {resolved_base_url}")

                        # 检测是否在Linux服务器环境
                        import platform
                        is_linux = platform.system() == 'Linux'

                        # 导航到URL
                        driver.get(resolved_base_url)

                        # 等待页面基本加载完成
                        # 在服务器环境（特别是无头模式）需要更长的等待时间
                        try:
                            WebDriverWait(driver, 15 if is_linux else 10).until(
                                lambda d: d.execute_script("return document.readyState") == "complete"
                            )
                        except:
                            pass  # 即使超时也继续执行

                        # 额外等待，确保动态内容加载（Vue/React等SPA应用）
                        extra_wait = 3 if is_linux else 2
                        time.sleep(extra_wait)

                        print(
                            f"✓ 成功导航到: {resolved_base_url} (已等待页面加载完成，额外{extra_wait}秒)")
                    except Exception as e:
                        print(f"✗ 导航失败: {str(e)}")
                        # 导航失败，记录错误并继续下一个用例
                        self.results.append({
                            'test_case_id': case_data['id'],
                            'test_case_name': case_data['name'],
                            'status': 'failed',
                            'steps': [],
                            'error': f"导航到基础URL失败: {str(e)}",
                            'start_time': datetime.now().isoformat(),
                            'end_time': datetime.now().isoformat(),
                            'screenshots': []
                        })
                        failed += 1
                        continue

                # 自动登录：复用模式仅第1个用例登录，独立模式每个用例都登录
                should_login = login_case_data and (
                    (reuse_browser and case_index == 1) or (not reuse_browser)
                )
                if should_login:
                    print(f"🔐 正在执行前置登录用例: {login_case_data['name']}")
                    engine_for_login = SeleniumTestEngine(driver, project_id=self.test_suite.project_id)
                    login_result = self.execute_test_case_selenium_no_db(driver, login_case_data)
                    if login_result['status'] != 'passed':
                        print(f"⚠️  前置登录失败: {login_result.get('error', '')}")
                    else:
                        print(f"✓ 前置登录完成")

                # 执行测试用例
                case_result = self.execute_test_case_selenium_no_db(driver, case_data)
                self.results.append(case_result)
                print(f"✓ 用例执行完成，状态: {case_result['status']}")

                # 立即更新该用例的执行记录（包含准确的执行时间）
                case_execution = case_executions[case_data['id']]
                case_execution.status = case_result['status']
                case_execution.finished_at = timezone.now()
                case_execution.execution_time = (case_execution.finished_at - case_execution.started_at).total_seconds()
                case_execution.execution_logs = json.dumps(case_result['steps'], ensure_ascii=False)
                if case_result['error']:
                    case_execution.error_message = case_result['error']
                if case_result.get('screenshots'):
                    case_execution.screenshots = case_result['screenshots']
                case_execution.save()

                print(f"⏱️  执行时长: {case_execution.execution_time:.2f}秒")

                if case_result['status'] == 'passed':
                    passed += 1
                elif case_result['status'] == 'failed':
                    failed += 1
                    # 复用模式下用例失败：关闭浏览器，后续用例执行前会重新打开
                    if use_browser_reuse and reuse_browser and driver:
                        print(f"⚠️  复用模式下用例失败，将重启浏览器以保证后续用例正常执行")
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = None
                else:
                    skipped += 1

            except Exception as e:
                print(f"✗ 用例执行出现异常: {str(e)}")
                # 记录异常
                self.results.append({
                    'test_case_id': case_data['id'],
                    'test_case_name': case_data['name'],
                    'status': 'failed',
                    'steps': [],
                    'error': f"用例执行异常: {str(e)}",
                    'start_time': datetime.now().isoformat(),
                    'end_time': datetime.now().isoformat(),
                    'screenshots': []
                })
                failed += 1

                # 更新执行记录
                case_execution = case_executions[case_data['id']]
                case_execution.status = 'failed'
                case_execution.finished_at = timezone.now()
                case_execution.execution_time = (case_execution.finished_at - case_execution.started_at).total_seconds()
                case_execution.error_message = f"用例执行异常: {str(e)}"
                case_execution.save()

                # 复用模式下异常：关闭浏览器，后续用例执行前会重新打开
                if use_browser_reuse and reuse_browser and driver:
                    print(f"⚠️  复用模式下用例异常，将重启浏览器以保证后续用例正常执行")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None

            finally:
                # Safari：每个用例执行完都关闭浏览器
                if not use_browser_reuse and driver:
                    try:
                        driver.quit()
                        print(f"✓ Safari 浏览器已关闭\n")
                    except Exception as e:
                        print(f"✗ 关闭 Safari 浏览器时出错: {str(e)}\n")
                    driver = None

        # 所有用例执行完毕后，关闭浏览器（仅对复用浏览器的情况）
        if use_browser_reuse and driver:
            try:
                print(f"\n{'=' * 60}")
                print(f"正在关闭浏览器...")
                driver.quit()
                print(f"✓ 浏览器已关闭")
                print(f"{'=' * 60}\n")
            except Exception as e:
                print(f"✗ 关闭浏览器时出错: {str(e)}")

        # 注意：每个用例的执行记录已在执行过程中实时更新，不需要在这里统一更新

        duration = time.time() - start_time
        status = 'SUCCESS' if failed == 0 else 'FAILED'
        self.update_execution_result(status, passed, failed, skipped, duration)

    def create_selenium_driver(self):
        """创建 Selenium WebDriver（通过浏览器连接工厂，支持本地/远程）"""
        from .browser_factory import BrowserConnectionFactory
        driver = BrowserConnectionFactory.create_selenium_driver(
            browser_type=self.browser,
            headless=self.headless,
            remote_service=self.remote_service,
        )
        return driver

    def execute_test_case_selenium_no_db(self, driver, case_data):
        """使用 Selenium 执行单个测试用例（不访问数据库）

        Args:
            driver: Selenium WebDriver对象
            case_data: 预先准备的用例数据字典，包含id, name, project_id, steps等
        """
        result = {
            'test_case_id': case_data['id'],
            'test_case_name': case_data['name'],
            'status': 'passed',
            'steps': [],
            'error': None,
            'start_time': datetime.now().isoformat(),
            'screenshots': []
        }

        # 缓存当前用例的 case_parameters，execute_step_selenium() 里复用/新建引擎时
        # 会读取这个值刷新到 engine 上（同一个 driver 跨用例复用时避免用旧用例的参数）
        self._current_case_parameters = case_data.get('case_parameters') or {}

        try:
            # 遍历预先准备好的步骤数据
            for step_data in case_data['steps']:
                step_result = self.execute_step_selenium(driver, step_data)
                result['steps'].append(step_result)

                # 步骤执行完后添加短暂延迟，确保页面状态稳定
                # 特别是点击操作后，可能触发动画、下拉框展开等
                if step_result['success'] and step_data['action_type'] in ['click', 'fill', 'hover']:
                    # 点击操作后等待更长时间（下拉框展开动画）
                    if step_data['action_type'] == 'click':
                        time.sleep(0.8)  # 等待800ms，确保下拉框完全展开
                    else:
                        time.sleep(0.3)  # 其他操作等待300ms

                # 如果步骤失败,捕获失败截图
                if not step_result['success']:
                    result['status'] = 'failed'
                    # 使用step的error信息作为case的error
                    result['error'] = step_result.get('error', f"步骤 {step_data['step_number']} 执行失败")

                    # 捕获失败截图（如果引擎没有随错误一起返回，这里再补一次）
                    if step_result.get('screenshot'):
                        result['screenshots'].append({
                            'url': step_result['screenshot'],
                            'description': f'步骤 {step_data["step_number"]} 失败截图: {step_data.get("description", "")}',
                            'step_number': step_data['step_number'],
                            'timestamp': datetime.now().isoformat()
                        })
                    else:
                        try:
                            import base64
                            screenshot_bytes = driver.get_screenshot_as_png()
                            screenshot_base64 = base64.b64encode(screenshot_bytes).decode()
                            result['screenshots'].append({
                                'url': f'data:image/png;base64,{screenshot_base64}',
                                'description': f'步骤 {step_data["step_number"]} 失败截图: {step_data.get("description", "")}',
                                'step_number': step_data['step_number'],
                                'timestamp': datetime.now().isoformat()
                            })
                        except Exception as screenshot_error:
                            print(f"捕获失败截图失败: {str(screenshot_error)}")

                    break

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)

            # 捕获异常截图
            try:
                import base64
                screenshot_bytes = driver.get_screenshot_as_png()
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode()
                result['screenshots'].append({
                    'url': f'data:image/png;base64,{screenshot_base64}',
                    'description': f'异常截图: {str(e)}',
                    'step_number': None,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as screenshot_error:
                print(f"捕获异常截图失败: {str(screenshot_error)}")

        result['end_time'] = datetime.now().isoformat()
        return result

    def execute_step_selenium(self, driver, step_data):
        """使用 Selenium 执行单个步骤

        委托给 SeleniumTestEngine.execute_step()，与单用例调试执行走同一套实现，
        不再维护第二份按 action_type 手写分支的 Selenium 动作代码。

        Args:
            driver: Selenium WebDriver对象
            step_data: 预先准备的步骤数据字典
        """
        engine = getattr(self, '_selenium_step_engine', None)
        if engine is None or engine.driver is not driver:
            engine = SeleniumTestEngine.attach(
                driver, browser_type=self.browser, project_id=self.test_suite.project_id,
                case_parameters=getattr(self, '_current_case_parameters', None),
            )
            assert isinstance(engine, TestEngineProtocol), f"Engine {type(engine)} does not conform to TestEngineProtocol"
            self._selenium_step_engine = engine
        else:
            # engine 跨用例复用（同一个 driver），刷新为当前用例的 case_parameters
            engine.case_parameters = getattr(self, '_current_case_parameters', None) or {}

        element_data = step_data['element'] or {}
        success, log, screenshot_b64 = engine.execute_step(_StepAttrView(step_data), element_data)
        return _build_step_result(step_data, success, log, screenshot_b64)
