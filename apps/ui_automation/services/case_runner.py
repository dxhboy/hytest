"""测试用例单次运行（TestCaseViewSet.run）的执行逻辑"""
from rest_framework import status
from rest_framework.response import Response
from django.utils import timezone
import logging
import json
import time
from ..models import TestCaseStep, TestCaseExecution, RemoteBrowserService
from ..serializers import TestCaseExecutionSerializer
from ..operation_logger import log_operation

logger = logging.getLogger(__name__)


def run_test_case(test_case, request):
    """运行单个测试用例 - 支持选择Playwright或Selenium执行引擎

    原 TestCaseViewSet.run 的主体逻辑，原样迁出；视图层只负责 get_object() 后调用本函数。
    """
    try:
        # 获取执行引擎选择，默认使用playwright
        engine_type = request.data.get('engine', 'playwright')

        # 获取远程浏览器服务（可选）
        remote_browser_service_id = request.data.get('remote_browser_service_id', None)
        remote_service = None
        if remote_browser_service_id:
            try:
                remote_service = RemoteBrowserService.objects.get(
                    id=remote_browser_service_id, is_active=True
                )
            except RemoteBrowserService.DoesNotExist:
                return Response({'error': '远程浏览器服务不存在或未启用'}, status=400)

        # 创建执行记录
        execution = TestCaseExecution.objects.create(
            test_case=test_case,
            project=test_case.project,
            execution_source='manual',
            status='running',
            engine=engine_type,
            browser=request.data.get('browser', 'chrome'),
            headless=request.data.get('headless', False),
            created_by=request.user,
            started_at=timezone.now(),
            remote_browser_service=remote_service
        )

        # 根据引擎类型导入对应的执行引擎
        if engine_type == 'selenium':
            from ..selenium_engine import SeleniumTestEngine

            # Selenium 引擎需要预先检查浏览器是否可用
            browser_type = request.data.get('browser', 'chrome')
            is_available, error_msg = SeleniumTestEngine.check_browser_available(browser_type)
            if not is_available:
                # 浏览器不可用，立即返回错误
                logger.error(f"Selenium 浏览器检查失败: {error_msg}")
                execution.status = 'failed'
                execution.error_message = error_msg
                execution.execution_logs = f"浏览器检查失败\n\n{error_msg}\n\n建议：\n1. 请确认已安装 {browser_type.capitalize()} 浏览器\n2. 或者尝试使用其他浏览器（Chrome、Firefox、Edge）\n3. 或者使用 Playwright 引擎（支持自动下载浏览器）"
                execution.finished_at = timezone.now()
                execution.save()

                return Response({
                    'success': False,
                    'logs': execution.execution_logs,
                    'screenshots': [],
                    'execution_time': 0,
                    'errors': [{
                        'message': f'{browser_type.capitalize()} 浏览器不可用',
                        'details': error_msg,
                        'step_number': None,
                        'action_type': '浏览器检查',
                        'element': '',
                        'description': '执行前浏览器环境检查'
                    }]
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            import asyncio
            from ..playwright_engine import PlaywrightTestEngine

        start_time = time.time()

        # 获取测试用例的所有步骤
        test_steps = list(test_case.steps.all().order_by('step_number'))

        # 预先获取所有步骤的数据,避免在异步上下文中访问ORM
        steps_data = []
        for step in test_steps:
            step_data = {
                'step': step,
                'action_type': step.action_type,
                'description': step.description,
                'input_value': step.input_value,
                'wait_time': step.wait_time,
                'assert_type': step.assert_type,
                'assert_value': step.assert_value,
                'step_parameters': step.step_parameters,
            }

            # 获取元素数据
            if step.element:
                step_data['element_data'] = {
                    'locator_strategy': step.element.locator_strategy.name if step.element.locator_strategy else 'css',
                    'locator_value': step.element.locator_value,
                    'name': step.element.name,
                    'wait_timeout': step.element.wait_timeout,  # 添加元素的等待超时设置（秒）
                    'force_action': step.element.force_action  # 添加强制操作选项
                }
            else:
                step_data['element_data'] = None

            steps_data.append(step_data)

        # 存储步骤执行结果（用于JSON格式的execution_logs）
        step_results = []

        # 生成执行日志（保留文本格式用于调试）
        execution_logs = []
        execution_logs.append(f"测试用例 '{test_case.name}' 开始执行")
        execution_logs.append(f"执行时间: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        execution_logs.append(f"执行引擎: {engine_type.upper()}")
        execution_logs.append(f"浏览器: {request.data.get('browser', 'chrome').capitalize()}")
        headless_mode = request.data.get('headless', False)
        mode_text = "无头模式" if headless_mode else "有头模式"
        execution_logs.append(f"执行模式: {mode_text}")
        execution_logs.append(f"执行用户: {request.user.username}")
        execution_logs.append(f"项目基础URL: {test_case.project.base_url}")
        execution_logs.append("")

        # 截图列表
        screenshots = []
        # 详细错误信息列表
        detailed_errors = []
        execution_result = {'status': 'passed', 'error_message': None}

        # 根据引擎类型选择执行方式
        if engine_type == 'selenium':
            # Selenium同步执行
            def run_test_selenium():
                """使用Selenium执行测试"""
                browser_type = request.data.get('browser', 'chrome')
                headless = request.data.get('headless', False)

                # 创建Selenium引擎实例
                engine = SeleniumTestEngine(
                    browser_type=browser_type, headless=headless, remote_service=remote_service,
                    project_id=test_case.project_id,
                    case_parameters=test_case.case_parameters,
                )

                try:
                    # 启动浏览器
                    execution_logs.append("========== 初始化浏览器 ==========")
                    try:
                        engine.start()
                        mode_text = "无头模式" if headless else "有头模式"
                        execution_logs.append(
                            f"✓ {browser_type.capitalize()} 浏览器启动成功 (Selenium, {mode_text})")
                        execution_logs.append("")
                    except Exception as browser_error:
                        # 浏览器启动失败
                        execution_logs.append(f"✗ {browser_type.capitalize()} 浏览器启动失败")
                        execution_logs.append(f"  错误: {str(browser_error)}")
                        execution_logs.append("")
                        execution_result['status'] = 'failed'
                        execution_result[
                            'error_message'] = f"{browser_type.capitalize()} 浏览器启动失败: {str(browser_error)}"

                        # 添加详细错误信息
                        detailed_errors.append({
                            'step_number': None,
                            'action_type': '浏览器启动',
                            'element': '',
                            'message': f"{browser_type.capitalize()} 浏览器启动失败",
                            'details': str(browser_error),
                            'description': '执行前浏览器启动检查'
                        })

                        return False

                    # 导航到项目基础URL
                    if test_case.project.base_url:
                        execution_logs.append("========== 导航到测试页面 ==========")
                        success, nav_log = engine.navigate(test_case.project.base_url)
                        execution_logs.append(nav_log)
                        execution_logs.append("")

                        if not success:
                            execution_result['status'] = 'failed'
                            execution_result['error_message'] = "导航到测试页面失败"
                            return False

                    if steps_data:
                        execution_logs.append("========== 执行测试步骤 ==========")
                        step_count = len(steps_data)
                        execution_logs.append(f"共有 {step_count} 个步骤需要执行")
                        execution_logs.append("")

                        for i, step_info in enumerate(steps_data, 1):
                            execution_logs.append(f"========== 开始执行步骤 {i}/{step_count} ==========")
                            execution_logs.append(f"步骤 {i}/{step_count}:")

                            step = step_info['step']
                            action_type = step_info['action_type']
                            description = step_info['description']
                            element_data = step_info['element_data']

                            action_choices_dict = dict(TestCaseStep.ACTION_TYPE_CHOICES)
                            action_type_text = action_choices_dict.get(action_type, action_type)
                            execution_logs.append(f"  操作: {action_type_text}")

                            if description:
                                execution_logs.append(f"  说明: {description}")

                            if element_data:
                                execution_logs.append(f"  元素: {element_data['name']}")
                                execution_logs.append(
                                    f"  定位器: {element_data['locator_strategy']}={element_data['locator_value']}")
                            else:
                                execution_logs.append(f"  (此步骤不需要元素)")

                            try:
                                success, step_log, screenshot_base64 = engine.execute_step(step, element_data or {})
                                execution_logs.append(f"  {step_log}")
                                execution_logs.append("")

                                # 记录步骤执行结果（用于JSON格式）
                                step_results.append({
                                    'step_number': i,
                                    'action_type': action_type,
                                    'description': description or '',
                                    'success': success,
                                    'error': None if success else step_log
                                })

                                if not success:
                                    logger.info(f"[调试-Selenium] 步骤 {i} 执行失败，设置状态为 failed")
                                    execution_result['status'] = 'failed'
                                    element_info = element_data['name'] if element_data else "未知元素"
                                    execution_result['error_message'] = step_log  # 使用step_log作为错误信息
                                    logger.info(f"[调试-Selenium] execution_result = {execution_result}")

                                    detailed_errors.append({
                                        'step_number': i,
                                        'action_type': action_type_text,
                                        'element': element_info,
                                        'message': f"步骤 {i}/{step_count} 执行失败",
                                        'details': step_log,
                                        'description': description or ''
                                    })

                                    if not screenshot_base64:
                                        screenshot_base64 = engine.capture_screenshot()

                                    if screenshot_base64:
                                        screenshots.append({
                                            'url': screenshot_base64,
                                            'description': f'步骤 {i} 失败截图: {description or action_type_text}',
                                            'step_number': i,
                                            'timestamp': timezone.now().isoformat()
                                            # 移除 loaded 和 error 字段，让前端自行处理
                                        })
                                        execution_logs.append(f"  📸 失败截图已捕获")

                                    return False

                                if action_type == 'screenshot' and screenshot_base64:
                                    screenshots.append({
                                        'url': screenshot_base64,
                                        'description': f'步骤 {i}: {description or "手动截图"}',
                                        'step_number': i,
                                        'timestamp': timezone.now().isoformat()
                                        # 移除 loaded 和 error 字段，让前端自行处理
                                    })

                            except Exception as e:
                                execution_logs.append(f"  ✗ 步骤执行异常: {str(e)}")
                                import traceback
                                tb_str = traceback.format_exc()
                                execution_logs.append(f"  [调试] 异常堆栈:\n{tb_str}")

                                # 记录步骤执行结果（异常情况）
                                step_results.append({
                                    'step_number': i,
                                    'action_type': action_type,
                                    'description': description or '',
                                    'success': False,
                                    'error': str(e)
                                })

                                execution_result['status'] = 'failed'
                                execution_result['error_message'] = f"步骤 {i} 执行异常: {str(e)}"

                                element_info = element_data['name'] if element_data else "未知元素"
                                detailed_errors.append({
                                    'step_number': i,
                                    'action_type': action_type_text,
                                    'element': element_info,
                                    'message': f"步骤 {i}/{step_count} 执行异常",
                                    'details': f"异常: {str(e)}\n\n堆栈跟踪:\n{tb_str}",
                                    'description': description or ''
                                })

                                try:
                                    screenshot_base64 = engine.capture_screenshot()
                                    if screenshot_base64:
                                        screenshots.append({
                                            'url': screenshot_base64,
                                            'description': f'步骤 {i} 异常截图: {str(e)}',
                                            'step_number': i,
                                            'timestamp': timezone.now().isoformat()
                                            # 移除 loaded 和 error 字段，让前端自行处理
                                        })
                                except:
                                    pass

                                return False

                        execution_logs.append(f"========== 执行完成 ({step_count} 个步骤全部通过) ==========")
                        return True
                    else:
                        execution_logs.append("警告: 测试用例没有定义任何步骤")
                        return True

                finally:
                    execution_logs.append("")
                    execution_logs.append("========== 清理资源 ==========")
                    engine.stop()
                    execution_logs.append("✓ 浏览器已关闭")

            # 通过有界线程池运行 Selenium 测试（替代原来无限制的 threading.Thread，
            # 见 concurrency.py：多个调试请求同时进来时会排队而不是无限起浏览器进程）
            from ..concurrency import run_bounded
            run_bounded(run_test_selenium).result()

        else:
            # Playwright异步执行
            def run_test_in_thread():
                """在独立线程中运行异步测试"""

                async def run_test():
                    """异步执行测试"""
                    # 根据浏览器类型选择
                    browser_map = {
                        'chrome': 'chromium',
                        'firefox': 'firefox',
                        'safari': 'webkit'
                    }
                    browser_type = browser_map.get(request.data.get('browser', 'chrome'), 'chromium')
                    headless = request.data.get('headless', False)

                    # 创建Playwright引擎实例
                    engine = PlaywrightTestEngine(
                        browser_type=browser_type, headless=headless, remote_service=remote_service,
                        project_id=test_case.project_id,
                        case_parameters=test_case.case_parameters,
                    )

                    try:
                        # 启动浏览器
                        execution_logs.append("========== 初始化浏览器 ==========")
                        await engine.start()
                        mode_text = "无头模式" if headless else "有头模式"
                        execution_logs.append(
                            f"✓ {browser_type.capitalize()} 浏览器启动成功 (Playwright, {mode_text})")
                        execution_logs.append("")

                        # 导航到项目基础URL
                        if test_case.project.base_url:
                            execution_logs.append("========== 导航到测试页面 ==========")
                            success, nav_log = await engine.navigate(test_case.project.base_url)
                            execution_logs.append(nav_log)
                            execution_logs.append("")

                            if not success:
                                execution_result['status'] = 'failed'
                                execution_result['error_message'] = "导航到测试页面失败"
                                return False

                        if steps_data:
                            execution_logs.append("========== 执行测试步骤 ==========")
                            step_count = len(steps_data)
                            execution_logs.append(f"共有 {step_count} 个步骤需要执行")
                            execution_logs.append("")

                            for i, step_info in enumerate(steps_data, 1):
                                execution_logs.append(f"========== 开始执行步骤 {i}/{step_count} ==========")
                                execution_logs.append(f"步骤 {i}/{step_count}:")

                                # 从预先获取的数据中获取信息
                                step = step_info['step']
                                action_type = step_info['action_type']
                                description = step_info['description']
                                element_data = step_info['element_data']

                                # 获取操作类型的中文显示
                                action_choices_dict = dict(TestCaseStep.ACTION_TYPE_CHOICES)
                                action_type_text = action_choices_dict.get(action_type, action_type)
                                execution_logs.append(f"  操作: {action_type_text}")

                                if description:
                                    execution_logs.append(f"  说明: {description}")

                                if element_data:
                                    execution_logs.append(f"  元素: {element_data['name']}")
                                    execution_logs.append(
                                        f"  定位器: {element_data['locator_strategy']}={element_data['locator_value']}")
                                else:
                                    execution_logs.append(f"  (此步骤不需要元素)")

                                # 执行步骤
                                try:
                                    execution_logs.append(f"  [调试] 准备执行步骤...")
                                    success, step_log, screenshot_base64 = await engine.execute_step(step,
                                                                                                     element_data or {})
                                    execution_logs.append(f"  [调试] 步骤执行完成, success={success}")

                                    execution_logs.append(f"  {step_log}")
                                    execution_logs.append("")

                                    # 记录步骤执行结果（用于JSON格式）
                                    step_results.append({
                                        'step_number': i,
                                        'action_type': action_type,
                                        'description': description or '',
                                        'success': success,
                                        'error': None if success else step_log
                                    })

                                    # 如果步骤失败,保存截图
                                    if not success:
                                        execution_logs.append(f"  [调试] 检测到步骤失败,准备处理...")
                                        execution_result['status'] = 'failed'

                                        # 获取失败的元素信息
                                        element_info = element_data['name'] if element_data else "未知元素"

                                        execution_result['error_message'] = step_log  # 使用step_log作为错误信息

                                        # 添加详细错误信息
                                        detailed_errors.append({
                                            'step_number': i,
                                            'action_type': action_type_text,
                                            'element': element_info,
                                            'message': f"步骤 {i}/{step_count} 执行失败",
                                            'details': step_log,  # 包含详细的错误日志
                                            'description': description or ''
                                        })

                                        # 如果没有截图,捕获一张
                                        if not screenshot_base64:
                                            screenshot_base64 = await engine.capture_screenshot()

                                    if screenshot_base64:
                                        screenshots.append({
                                            'url': screenshot_base64,
                                            'description': f'步骤 {i} 失败截图: {description or action_type_text}',
                                            'step_number': i,
                                            'timestamp': timezone.now().isoformat()
                                            # 移除 loaded 和 error 字段，让前端自行处理
                                        })
                                        execution_logs.append(f"  📸 失败截图已捕获")

                                        execution_logs.append(f"  [调试] 步骤失败,准备退出执行...")
                                        return False

                                    # 如果是截图步骤且成功,也保存截图
                                    if action_type == 'screenshot' and screenshot_base64:
                                        screenshots.append({
                                            'url': screenshot_base64,
                                            'description': f'步骤 {i}: {description or "手动截图"}',
                                            'step_number': i,
                                            'timestamp': timezone.now().isoformat()
                                            # 移除 loaded 和 error 字段，让前端自行处理
                                        })

                                    execution_logs.append(f"  [调试] 步骤 {i} 成功完成,准备执行下一步...")

                                except Exception as e:
                                    execution_logs.append(f"  ✗ 步骤执行异常: {str(e)}")
                                    execution_logs.append(f"  [调试] 异常详情: {repr(e)}")
                                    import traceback
                                    tb_str = traceback.format_exc()
                                    execution_logs.append(f"  [调试] 异常堆栈:\n{tb_str}")

                                    # 记录步骤执行结果（异常情况）
                                    step_results.append({
                                        'step_number': i,
                                        'action_type': action_type,
                                        'description': description or '',
                                        'success': False,
                                        'error': str(e)
                                    })

                                    execution_result['status'] = 'failed'
                                    execution_result['error_message'] = f"步骤 {i} 执行异常: {str(e)}"

                                    # 添加详细错误信息
                                    element_info = element_data['name'] if element_data else "未知元素"
                                    detailed_errors.append({
                                        'step_number': i,
                                        'action_type': action_type_text,
                                        'element': element_info,
                                        'message': f"步骤 {i}/{step_count} 执行异常",
                                        'details': f"异常: {str(e)}\n\n堆栈跟踪:\n{tb_str}",
                                        'description': description or ''
                                    })

                                    # 捕获异常截图
                                    try:
                                        screenshot_base64 = await engine.capture_screenshot()
                                        if screenshot_base64:
                                            screenshots.append({
                                                'url': screenshot_base64,
                                                'description': f'步骤 {i} 异常截图: {str(e)}',
                                                'step_number': i,
                                                'timestamp': timezone.now().isoformat()
                                                # 移除 loaded 和 error 字段，让前端自行处理
                                            })
                                    except:
                                        pass

                                    execution_logs.append(f"  [调试] 发生异常,准备退出执行...")
                                    return False

                            # 所有步骤都成功
                            execution_logs.append(f"========== 执行完成 ({step_count} 个步骤全部通过) ==========")
                            return True

                        else:
                            execution_logs.append("警告: 测试用例没有定义任何步骤")
                            return True

                    finally:
                        # 关闭浏览器
                        execution_logs.append("")
                        execution_logs.append("========== 清理资源 ==========")
                        await engine.stop()
                        execution_logs.append("✓ 浏览器已关闭")

                # 在新的事件循环中运行测试
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(run_test())
                finally:
                    loop.close()

            # 通过有界线程池运行 Playwright 测试（同上，替代无限制的 threading.Thread）
            from ..concurrency import run_bounded
            run_bounded(run_test_in_thread).result()

        # 计算总执行时间
        total_time = round(time.time() - start_time, 2)
        execution_logs.append("")
        execution_logs.append("执行环境信息:")
        execution_logs.append(f"- 执行引擎: {engine_type.upper()}")
        execution_logs.append(f"- 浏览器: {request.data.get('browser', 'chrome').capitalize()}")
        execution_logs.append(f"- 屏幕分辨率: 1920x1080")
        execution_logs.append(f"- 总执行时间: {total_time}秒")

        if screenshots:
            execution_logs.append(f"- 截图数量: {len(screenshots)} 张")

        # 保存执行日志和截图
        logger.info(f"[调试] 准备保存执行结果: execution_result['status'] = {execution_result['status']}")
        execution.status = execution_result['status']

        # 保存error_message（step_log已经是简洁的错误信息）
        execution.error_message = execution_result['error_message'] or ''

        # 保存步骤执行结果为JSON格式
        execution.execution_logs = json.dumps(step_results, ensure_ascii=False)
        execution.execution_time = total_time
        execution.finished_at = timezone.now()
        execution.screenshots = screenshots
        execution.save()
        logger.info(f"[调试] 执行结果已保存: execution.status = {execution.status}")

        serializer = TestCaseExecutionSerializer(execution)
        # 格式化错误信息为统一的对象格式
        errors = []
        if detailed_errors:
            # 使用详细的错误信息
            for error in detailed_errors:
                errors.append({
                    'message': error['message'],
                    'details': error['details'],
                    'step_number': error['step_number'],
                    'action_type': error['action_type'],
                    'element': error['element'],
                    'description': error['description']
                })
        elif execution.error_message:
            # 如果没有详细错误信息，使用简单格式
            errors.append({
                'message': execution.error_message,
                'details': ''
            })

        # 记录运行操作
        log_operation('run', 'test_case', test_case.id, test_case.name, request.user)

        return Response({
            'success': execution.status == 'passed',
            'logs': execution.execution_logs,
            'screenshots': screenshots,
            'execution_time': execution.execution_time,
            'errors': errors
        })

    except Exception as e:
        logger.error(f"执行测试用例失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'logs': f"执行失败: {str(e)}\n\n{traceback.format_exc()}",
            'screenshots': [],
            'execution_time': 0,
            'errors': [{'message': str(e), 'stack': traceback.format_exc()}]
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
