"""
UI 自动化模块的 Celery 任务。

背景：这个模块历史上所有"批量/后台执行"都是 views.py 里手写的
`threading.Thread(target=...); thread.start()`——没有并发上限、没有重试、
不能跨进程扩容，多个请求同时进来就会无限制地起线程和浏览器进程。

这里把最关键、资源开销最大的两类执行迁移到 Celery 任务队列：
1. 测试套件/定时任务的批量执行 —— execute_test_suite_task / run_scheduled_task_now_task
2. AI 智能模式执行 —— run_ai_case_task / run_ai_adhoc_task

队列划分（部署时需要区分启动两个 worker）：
    celery -A backend worker -Q celery --concurrency=4          # 套件/用例批量执行
    celery -A backend worker -Q ai_automation --concurrency=1   # AI 智能模式，见下方说明——暂时仍需保持 1

关于 AI 智能模式的并发数，有两个独立的问题，不要混为一谈：
1. CDP 端口冲突（已修复）：ai_base.py 里原来对 browser-use 的
   LocalBrowserWatchdog._find_free_port 打了猴子补丁，Linux 下强制固定
   使用 9222 端口，导致并发跑多个 AI 任务会互相抢占同一个 CDP 端口、
   把对方的浏览器进程 kill 掉。这个根因已经修复（去掉了强制固定端口的
   补丁，恢复 browser-use 官方的动态端口分配，_cleanup_zombie_chrome
   也改成了按"孤儿进程"而不是按端口清理）。仅看这一点，并发数本可以
   放宽到 2~4。
2. GIF 录制文件名冲突（未修复）：ai_execution_helpers.process_gif_recording
   从固定的相对路径 `agent_history.gif`（当前工作目录）读取 browser-use
   产生的录制文件再搬走重命名。这个文件名是 browser-use 库自己写死的，
   不受调用方控制。如果两个 AI 任务在同一个 worker 进程里并发跑，会
   互相抢同一个源文件，导致 GIF 录制错乱或互相覆盖（详见该函数的
   docstring）。这个问题尚未修复。

结论：只要问题 2 没修，ai_automation 队列的 --concurrency 就必须保持 1，
不能因为问题 1 修复了就误以为可以放宽到 2~4——两者是独立的限制条件，
取并发数的下限（也就是 1）。等 GIF 文件名冲突也解决之后（比如给每次
执行分配独立的工作目录/临时文件名），再考虑放宽到 2~4。

单用例调试执行（TestCaseViewSet.run）和定时任务里的多用例执行分支
暂未迁移到这里，仍然用 concurrency.run_bounded() 做有界线程池限流，
见 services/case_runner.py 里的调用点和 concurrency.py 的说明。
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# 通知：消息内容与 UiNotificationLog 写入在本模块维护，
# Webhook 加签/发送、邮件发送、机器人收集等传输层逻辑统一走 apps.core.notifications
# ----------------------------------------------------------------------------

def _build_suite_webhook_message(bot_type, test_suite, engine, success, passed, failed, total, run_time, report_url):
    """构建套件手动执行完成的 Webhook 消息；未知机器人类型返回 None"""
    status_text = '成功' if success else '失败'
    emoji = '✅' if success else '❌'
    title = f"{emoji} UI测试套件执行{status_text}: {test_suite.name}"

    if bot_type == 'feishu':
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "green" if success else "red",
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**套件名称**\n{test_suite.name}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行状态**\n{status_text}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行时间**\n{run_time}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行引擎**\n{engine.upper()}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**通过 / 失败**\n{passed} / {failed}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**用例总数**\n{total}"}},
                        ],
                    },
                    {"tag": "action", "actions": [
                        {"tag": "button", "text": {"tag": "plain_text", "content": "查看报告"}, "url": report_url, "type": "primary"},
                    ]},
                ],
            },
        }
    if bot_type == 'dingtalk':
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": (
                    f"### {title}\n\n"
                    f"- **套件名称**: {test_suite.name}\n"
                    f"- **执行引擎**: {engine.upper()}\n"
                    f"- **执行时间**: {run_time}\n"
                    f"- **通过/失败**: {passed} / {failed}\n"
                    f"- **用例总数**: {total}\n\n"
                    f"[查看报告]({report_url})"
                ),
            },
        }
    if bot_type == 'wechat':
        return {
            "msgtype": "markdown",
            "markdown": {
                "content": (
                    f"### {title}\n"
                    f"> **套件名称**: {test_suite.name}\n"
                    f"> **执行引擎**: {engine.upper()}\n"
                    f"> **执行时间**: {run_time}\n"
                    f"> **通过/失败**: <font color=\"info\">{passed}</font> / <font color=\"warning\">{failed}</font>\n"
                    f"> **用例总数**: {total}\n\n"
                    f"[查看报告]({report_url})"
                ),
            },
        }
    return None


def _send_suite_notification(test_suite, engine, success):
    """套件执行完成后发送 Webhook 通知（手动执行场景）。

    从 UnifiedNotificationConfig 中查询所有启用了 UI 自动化通知的
    webhook 机器人，然后逐个发送卡片/Markdown 消息。
    """
    from django.conf import settings as django_settings
    from apps.core import notifications

    try:
        bots = notifications.collect_unified_webhook_bots(notifications.MODULE_UI_AUTOMATION)
    except ImportError:
        logger.warning("[通知] 无法导入 UnifiedNotificationConfig，跳过通知")
        return

    if not bots:
        logger.info("[通知] 没有启用 UI 自动化通知的 webhook 机器人，跳过")
        return

    # 从套件获取统计数据
    test_suite.refresh_from_db()
    passed = getattr(test_suite, 'passed_count', 0) or 0
    failed = getattr(test_suite, 'failed_count', 0) or 0
    total = passed + failed
    run_time = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S')
    site_url = getattr(django_settings, 'SITE_BASE_URL', 'http://localhost:3000')
    report_url = f"{site_url}/ui-automation/executions"

    for bot in bots:
        if not bot.get('webhook_url'):
            continue
        bot_type = bot.get('type', 'unknown')
        bot_name = bot.get('name', 'Unknown')

        try:
            payload = _build_suite_webhook_message(
                bot_type, test_suite, engine, success, passed, failed, total, run_time, report_url
            )
            if payload is None:
                logger.warning(f"[通知] 未知的机器人类型: {bot_type}，跳过 {bot_name}")
                continue

            result = notifications.post_webhook(bot, payload)
            if result.error is not None:
                raise result.error
            logger.info(f"[通知] 已发送到 {bot_type} 机器人 {bot_name}, status={result.status_code}")
        except Exception as e:
            logger.error(f"[通知] 发送到 {bot_name} 失败: {e}")


def _build_task_webhook_message(bot_type, task, success, report_url):
    """构建定时任务执行完成的 Webhook 消息；未知机器人类型返回 None"""
    status_text = '成功' if success else '失败'
    task_type_text = 'UI测试套件' if task.task_type == 'TEST_SUITE' else 'UI测试用例'
    title = f"{'✅' if success else '❌'} {task_type_text}执行{status_text}: {task.name}"

    # 获取最后执行结果的详细信息
    last_result = task.last_result or {}
    success_count = last_result.get('success_count', '-')
    failed_count = last_result.get('failed_count', '-')

    # 转换执行时间到本地时区
    local_run_time = timezone.localtime(task.last_run_time).strftime(
        '%Y-%m-%d %H:%M:%S') if task.last_run_time else '未知'

    if bot_type == 'feishu':  # 飞书
        elements = [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务名称**\n{task.name}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行状态**\n{status_text}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行时间**\n{local_run_time}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务类型**\n{task_type_text}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行引擎**\n{task.engine.upper()}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**通过 / 失败**\n{success_count} / {failed_count}"}},
                ]
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看详细报告"},
                        "url": report_url,
                        "type": "primary"
                    }
                ]
            }
        ]
        if task.error_message:
            elements.insert(1, {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**错误信息**\n{task.error_message[:200]}"}
            })
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "template": "green" if success else "red",
                    "title": {"tag": "plain_text", "content": title}
                },
                "elements": elements
            }
        }
    if bot_type == 'wechat':  # 企业微信
        status_color = 'info' if success else 'warning'
        content = (
            f"## {title}\n\n"
            f"> **任务名称**: {task.name}\n"
            f"> **执行状态**: <font color=\"{status_color}\">{status_text}</font>\n"
            f"> **执行时间**: {local_run_time}\n"
            f"> **任务类型**: {task_type_text}\n"
            f"> **执行引擎**: {task.engine.upper()}\n"
            f"> **通过 / 失败**: {success_count} / {failed_count}\n"
        )
        if task.error_message:
            content += f"> **错误信息**: {task.error_message[:200]}\n"
        content += f"\n[查看详细报告]({report_url})"
        return {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
    if bot_type == 'dingtalk':  # 钉钉
        text = (
            f"### {title}\n\n"
            f"**任务名称**: {task.name}\n\n"
            f"**执行状态**: {status_text}\n\n"
            f"**执行时间**: {local_run_time}\n\n"
            f"**任务类型**: {task_type_text}\n\n"
            f"**执行引擎**: {task.engine.upper()}\n\n"
            f"**通过 / 失败**: {success_count} / {failed_count}\n\n"
        )
        if task.error_message:
            text += f"**错误信息**: {task.error_message[:200]}\n\n"
        return {
            "msgtype": "actionCard",
            "actionCard": {
                "title": title,
                "text": text,
                "singleTitle": "查看详细报告",
                "singleURL": report_url
            }
        }
    return None


def _send_task_webhook_notification(task, success):
    """定时任务 Webhook 通知，逐个机器人写 UiNotificationLog"""
    import json
    from django.conf import settings as django_settings
    from apps.core import notifications
    from .models import UiNotificationLog

    try:
        logger.info("=== 开始发送Webhook通知 ===")

        try:
            all_webhook_bots = notifications.collect_unified_webhook_bots(
                notifications.MODULE_UI_AUTOMATION, log_skipped=True
            )
            logger.info("使用统一通知配置 (UnifiedNotificationConfig)")
        except ImportError as e:
            logger.error(f"无法导入统一通知配置: {e}")
            logger.warning("通知发送失败：无法找到通知配置模块")
            return
        except Exception as e:
            logger.error(f"获取通知配置时出错: {e}")
            return

        if not all_webhook_bots:
            logger.warning("没有找到任何启用的webhook机器人配置")
            return

        logger.info(f"找到 {len(all_webhook_bots)} 个启用的webhook机器人配置")

        site_url = getattr(django_settings, 'SITE_BASE_URL', 'http://localhost:3000')
        execution_id = (task.last_result or {}).get('execution_id')
        report_url = f"{site_url}/ui-automation/executions" + (f"/{execution_id}" if execution_id else "")

        for bot in all_webhook_bots:
            if not bot.get('webhook_url'):
                logger.info(f"跳过未启用或无URL的机器人: {bot.get('name', 'Unknown')}")
                continue

            bot_type = bot.get('type', 'unknown')
            logger.info(f"发送通知到 {bot_type} 机器人: {bot.get('name', 'Unknown')}")

            message_data = _build_task_webhook_message(bot_type, task, success, report_url)
            if message_data is None:
                logger.warning(f"未知的机器人类型: {bot_type}")
                continue

            logger.info(f"消息数据: {json.dumps(message_data, ensure_ascii=False, indent=2)}")
            result = notifications.post_webhook(bot, message_data)
            log_fields = dict(
                task=task,
                task_name=task.name,
                task_type=task.task_type,
                notification_type='task_execution',
                sender_name='系统Webhook通知',
                sender_email='system@notification.com',
                recipient_info=[{'name': bot.get('name', 'Unknown'), 'webhook_url': result.url}],
                webhook_bot_info=bot,
                notification_content=json.dumps(result.payload, ensure_ascii=False),
            )

            if result.error is not None:
                logger.error(f"发送webhook请求失败: {str(result.error)}")
                UiNotificationLog.objects.create(status='failed', error_message=str(result.error), **log_fields)
                continue

            logger.info(f"响应状态码: {result.status_code}")
            logger.info(f"响应内容: {result.text}")
            response_info = {'status_code': result.status_code, 'response': result.text}

            # UI 模块沿用 HTTP 200 即视为成功的口径
            if result.status_code == 200:
                logger.info(f"成功发送通知到 {bot.get('name', 'Unknown')}")
                UiNotificationLog.objects.create(
                    status='success', response_info=response_info, sent_at=timezone.now(), **log_fields
                )
            else:
                logger.error(f"发送通知失败，状态码: {result.status_code}, 响应: {result.text}")
                UiNotificationLog.objects.create(
                    status='failed', error_message=f'HTTP {result.status_code}: {result.text}',
                    response_info=response_info, **log_fields
                )

    except Exception as e:
        logger.error(f"发送Webhook通知失败: {str(e)}", exc_info=True)


def _send_task_email_notification(task, success):
    """定时任务邮件通知"""
    from django.conf import settings
    from apps.core import notifications
    from .models import UiNotificationLog

    recipients = []
    try:
        logger.info("=== 开始发送邮件通知 ===")

        recipients = notifications.resolve_recipients(emails=task.notify_emails)
        if not recipients:
            logger.warning("没有找到任何邮件收件人")
            return

        status_text = '成功' if success else '失败'
        task_type_text = '测试套件执行' if task.task_type == 'TEST_SUITE' else '测试用例执行'
        subject = f"UI自动化定时任务执行{status_text}: {task.name}"

        result_message = (task.last_result or {}).get('message', '')

        # 转换执行时间到本地时区
        local_run_time = timezone.localtime(task.last_run_time).strftime(
            '%Y-%m-%d %H:%M:%S') if task.last_run_time else '未知'

        message = f"""
任务名称: {task.name}
执行状态: {status_text}
执行时间: {local_run_time}
任务类型: {task_type_text}
执行引擎: {task.engine.upper()}
浏览器: {task.browser.capitalize()}

执行结果:
{result_message if result_message else '无详细信息'}

错误信息:
{task.error_message if task.error_message else '无错误信息'}
            """

        logger.info(f"准备发送邮件，收件人: {recipients}")
        from_email = notifications.send_email(subject, message, recipients)
        logger.info("邮件发送成功")

        UiNotificationLog.objects.create(
            task=task,
            task_name=task.name,
            task_type=task.task_type,
            notification_type='task_execution',
            sender_name='系统邮件通知',
            sender_email=from_email,
            recipient_info=[{'email': email} for email in recipients],
            notification_content=message,
            status='success',
            sent_at=timezone.now()
        )

    except Exception as e:
        logger.error(f"发送邮件通知失败: {str(e)}", exc_info=True)
        try:
            UiNotificationLog.objects.create(
                task=task,
                task_name=task.name,
                task_type=task.task_type,
                notification_type='task_execution',
                sender_name='系统邮件通知',
                sender_email=settings.DEFAULT_FROM_EMAIL,
                recipient_info=[{'email': email} for email in recipients] if recipients else [],
                notification_content=f"发送邮件通知失败: {str(e)}",
                status='failed',
                error_message=str(e)
            )
        except Exception:
            pass


def send_task_notification(task, success):
    """UiScheduledTask 执行完成后按任务配置发送通知（替代原 UiScheduledTaskViewSet._send_task_notification）"""
    try:
        logger.info(f"准备发送任务 {task.id} 的通知，执行结果: {'成功' if success else '失败'}")

        if success and not task.notify_on_success:
            logger.info("任务执行成功但未启用成功通知")
            return
        if not success and not task.notify_on_failure:
            logger.info("任务执行失败但未启用失败通知")
            return
        if not task.notification_type:
            logger.info("未设置通知类型")
            return

        logger.info(f"通知类型: {task.notification_type}")

        if task.notification_type in ['webhook', 'both']:
            logger.info("发送Webhook通知")
            _send_task_webhook_notification(task, success)

        if task.notification_type in ['email', 'both']:
            logger.info("发送邮件通知")
            _send_task_email_notification(task, success)

    except Exception as e:
        logger.error(f"发送通知失败: {str(e)}", exc_info=True)


@shared_task(bind=True, name='ui_automation.execute_test_suite', ignore_result=True)
def execute_test_suite_task(self, suite_id, engine='playwright', browser='chrome',
                             headless=False, user_id=None, remote_service_id=None):
    """执行测试套件，对应原来 TestSuiteViewSet.run_suite 里的裸线程逻辑。"""
    from django.contrib.auth import get_user_model
    from .models import TestSuite, RemoteBrowserService
    from .test_executor import TestExecutor

    User = get_user_model()

    try:
        test_suite = TestSuite.objects.get(id=suite_id)
    except TestSuite.DoesNotExist:
        logger.error(f"[Celery] 测试套件不存在: suite_id={suite_id}")
        return

    user = User.objects.filter(id=user_id).first() if user_id else None
    remote_service = None
    if remote_service_id:
        remote_service = RemoteBrowserService.objects.filter(id=remote_service_id, is_active=True).first()

    success = False
    try:
        logger.info(f"[Celery] 开始执行测试套件: {test_suite.name} (ID: {test_suite.id})")
        executor = TestExecutor(
            test_suite=test_suite,
            engine=engine,
            browser=browser,
            headless=headless,
            executed_by=user,
            remote_service=remote_service,
        )
        executor.run()
        logger.info(f"[Celery] 测试套件执行完成: {test_suite.name}")
        # 根据套件执行状态判断成功/失败
        test_suite.refresh_from_db()
        success = test_suite.execution_status == 'passed'
    except Exception as e:
        logger.error(f"[Celery] 测试套件执行异常: {test_suite.name} - {e}", exc_info=True)
        try:
            test_suite.execution_status = 'failed'
            test_suite.save(update_fields=['execution_status'])
        except Exception as save_error:
            logger.error(f"[Celery] 更新套件状态失败: {save_error}")
    finally:
        try:
            _send_suite_notification(test_suite, engine, success)
        except Exception as notify_error:
            logger.error(f"[Celery] 发送通知失败: {notify_error}", exc_info=True)


@shared_task(bind=True, name='ui_automation.run_scheduled_task_now', ignore_result=True)
def run_scheduled_task_now_task(self, scheduled_task_id):
    """
    立即执行一个 UiScheduledTask（TEST_SUITE 或 TEST_CASE 类型）。

    对应原来 UiScheduledTaskViewSet.run_now 里 run_test() / run_test_cases()
    两个裸线程闭包，逻辑保持一致，只是换成了 Celery 任务，并把所有依赖
    （task / test_suite / test_cases）都通过 ID 重新从数据库获取，
    不再依赖闭包里捕获的 request/ORM 对象。
    """
    import json
    import time
    from .models import UiScheduledTask, TestCase, TestCaseExecution
    from .test_executor import TestExecutor

    try:
        task = UiScheduledTask.objects.get(id=scheduled_task_id)
    except UiScheduledTask.DoesNotExist:
        logger.error(f"[Celery] 定时任务不存在: scheduled_task_id={scheduled_task_id}")
        return

    if task.task_type == 'TEST_SUITE':
        test_suite = task.test_suite
        if not test_suite:
            logger.error(f"[Celery] 定时任务 {task.id} 未配置测试套件")
            return
        try:
            executor = TestExecutor(
                test_suite=test_suite,
                engine=task.engine,
                browser=task.browser,
                headless=task.headless,
                executed_by=task.created_by,
            )
            executor.run()

            task.successful_runs += 1
            task.last_result = {'status': 'success', 'message': '测试套件执行成功'}
            task.error_message = ''
            task.save()

            send_task_notification(task, success=True)

        except Exception as e:
            logger.error(f"[Celery] 定时任务执行测试套件失败: {e}", exc_info=True)
            task.failed_runs += 1
            task.last_result = {'status': 'failed', 'message': str(e)}
            task.error_message = str(e)
            test_suite.execution_status = 'failed'
            test_suite.save()
            task.save()

            send_task_notification(task, success=False)

    elif task.task_type == 'TEST_CASE':
        test_case_ids = task.test_cases or []
        test_cases = TestCase.objects.filter(id__in=test_case_ids)
        success_count = 0
        failed_count = 0

        try:
            for test_case in test_cases:
                execution = TestCaseExecution.objects.create(
                    test_case=test_case,
                    project=task.project,
                    execution_source='scheduled',
                    status='running',
                    engine=task.engine,
                    browser=task.browser,
                    headless=task.headless,
                    created_by=task.created_by,
                    started_at=timezone.now()
                )

                try:
                    logger.info(f"[Celery] 开始执行定时任务的测试用例: {test_case.name} (ID: {test_case.id})")

                    start_time = time.time()

                    test_steps = list(test_case.steps.all().order_by('step_number'))
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
                        }
                        if step.element:
                            step_data['element_data'] = {
                                'locator_strategy': step.element.locator_strategy.name if step.element.locator_strategy else 'css',
                                'locator_value': step.element.locator_value,
                                'name': step.element.name,
                                'wait_timeout': step.element.wait_timeout,
                                'force_action': step.element.force_action
                            }
                        else:
                            step_data['element_data'] = None
                        steps_data.append(step_data)

                    step_results = []
                    screenshots = []
                    execution_logs = []
                    execution_result = {'status': 'passed', 'error_message': None}

                    if task.engine == 'selenium':
                        from .selenium_engine import SeleniumTestEngine

                        is_available, error_msg = SeleniumTestEngine.check_browser_available(task.browser)
                        if not is_available:
                            execution.status = 'failed'
                            execution.error_message = error_msg
                            execution.execution_logs = json.dumps([{
                                'step_number': 0,
                                'action_type': '浏览器检查',
                                'description': '执行前浏览器环境检查',
                                'success': False,
                                'error': error_msg
                            }], ensure_ascii=False)
                            execution.finished_at = timezone.now()
                            execution.save()
                            failed_count += 1
                            continue

                        engine = SeleniumTestEngine(
                            browser_type=task.browser, headless=task.headless,
                            project_id=test_case.project_id,
                        )
                        try:
                            engine.start()
                            execution_logs.append("✓ 浏览器启动成功")

                            if test_case.project.base_url:
                                success, nav_log = engine.navigate(test_case.project.base_url)
                                execution_logs.append(nav_log)
                                if not success:
                                    execution_result['status'] = 'failed'
                                    execution_result['error_message'] = "导航到测试页面失败"
                                    raise Exception("导航到测试页面失败")

                            for i, step_info in enumerate(steps_data, 1):
                                step = step_info['step']
                                action_type = step_info['action_type']
                                element_data = step_info['element_data']

                                success, step_log, screenshot_base64 = engine.execute_step(step, element_data or {})

                                step_results.append({
                                    'step_number': i,
                                    'action_type': action_type,
                                    'description': step_info['description'] or '',
                                    'success': success,
                                    'error': None if success else step_log
                                })

                                if not success:
                                    execution_result['status'] = 'failed'
                                    execution_result['error_message'] = step_log

                                    if not screenshot_base64:
                                        screenshot_base64 = engine.capture_screenshot()
                                    if screenshot_base64:
                                        screenshots.append({
                                            'url': screenshot_base64,
                                            'description': f'步骤 {i} 失败截图',
                                            'step_number': i,
                                            'timestamp': timezone.now().isoformat()
                                        })
                                    break

                                if action_type == 'screenshot' and screenshot_base64:
                                    screenshots.append({
                                        'url': screenshot_base64,
                                        'description': f'步骤 {i}: {step_info["description"] or "手动截图"}',
                                        'step_number': i,
                                        'timestamp': timezone.now().isoformat()
                                    })
                        finally:
                            engine.stop()

                    else:  # Playwright
                        import asyncio
                        from asgiref.sync import sync_to_async
                        from .playwright_engine import PlaywrightTestEngine

                        async def run_playwright_test():
                            browser_map = {'chrome': 'chromium', 'firefox': 'firefox', 'safari': 'webkit'}
                            browser_type = browser_map.get(task.browser, 'chromium')

                            engine = PlaywrightTestEngine(
                                browser_type=browser_type, headless=task.headless,
                                project_id=test_case.project_id,
                            )
                            try:
                                await engine.start()
                                execution_logs.append("✓ 浏览器启动成功")

                                base_url = await sync_to_async(lambda: test_case.project.base_url)()
                                if base_url:
                                    success, nav_log = await engine.navigate(base_url)
                                    execution_logs.append(nav_log)
                                    if not success:
                                        execution_result['status'] = 'failed'
                                        execution_result['error_message'] = "导航到测试页面失败"
                                        return False

                                for i, step_info in enumerate(steps_data, 1):
                                    step = step_info['step']
                                    action_type = step_info['action_type']
                                    element_data = step_info['element_data']

                                    success, step_log, screenshot_base64 = await engine.execute_step(step, element_data or {})

                                    step_results.append({
                                        'step_number': i,
                                        'action_type': action_type,
                                        'description': step_info['description'] or '',
                                        'success': success,
                                        'error': None if success else step_log
                                    })

                                    if not success:
                                        execution_result['status'] = 'failed'
                                        execution_result['error_message'] = step_log

                                        if not screenshot_base64:
                                            screenshot_base64 = await engine.capture_screenshot()
                                        if screenshot_base64:
                                            screenshots.append({
                                                'url': screenshot_base64,
                                                'description': f'步骤 {i} 失败截图',
                                                'step_number': i,
                                                'timestamp': timezone.now().isoformat()
                                            })
                                        return False

                                    if action_type == 'screenshot' and screenshot_base64:
                                        screenshots.append({
                                            'url': screenshot_base64,
                                            'description': f'步骤 {i}: {step_info["description"] or "手动截图"}',
                                            'step_number': i,
                                            'timestamp': timezone.now().isoformat()
                                        })
                                return True
                            finally:
                                await engine.stop()

                        # Celery worker 线程里没有正在运行的事件循环，可以放心用 asyncio.run
                        asyncio.run(run_playwright_test())

                    total_time = round(time.time() - start_time, 2)

                    execution.status = execution_result['status']
                    execution.error_message = execution_result['error_message'] or ''
                    execution.execution_logs = json.dumps(step_results, ensure_ascii=False)
                    execution.execution_time = total_time
                    execution.screenshots = screenshots
                    execution.finished_at = timezone.now()
                    execution.save()

                    if execution.status == 'passed':
                        success_count += 1
                        logger.info(f"[Celery] 测试用例 {test_case.name} 执行成功")
                    else:
                        failed_count += 1
                        logger.warning(f"[Celery] 测试用例 {test_case.name} 执行失败: {execution.error_message}")

                except Exception as e:
                    logger.error(f"[Celery] 执行测试用例 {test_case.name} 时发生异常: {e}", exc_info=True)
                    execution.status = 'failed'
                    execution.error_message = str(e)
                    execution.finished_at = timezone.now()
                    execution.save()
                    failed_count += 1

            if failed_count == 0:
                task.successful_runs += 1
                task.last_result = {
                    'status': 'success',
                    'message': f'执行完成: {success_count}个成功',
                    'success_count': success_count,
                    'failed_count': failed_count
                }
                task.error_message = ''
                task.save()
                send_task_notification(task, success=True)
            else:
                task.failed_runs += 1
                task.last_result = {
                    'status': 'partial',
                    'message': f'执行完成: {success_count}个成功, {failed_count}个失败',
                    'success_count': success_count,
                    'failed_count': failed_count
                }
                task.error_message = f'{failed_count}个测试用例执行失败'
                task.save()
                send_task_notification(task, success=False)

        except Exception as e:
            logger.error(f"[Celery] 执行定时任务测试用例时发生异常: {e}", exc_info=True)
            task.failed_runs += 1
            task.last_result = {'status': 'failed', 'message': str(e)}
            task.error_message = str(e)
            task.save()
            send_task_notification(task, success=False)


# ----------------------------------------------------------------------------
# AI 智能模式：单独路由到 ai_automation 队列（部署时用 --concurrency=1 的 worker 承接）
# ----------------------------------------------------------------------------

@shared_task(bind=True, name='ui_automation.run_ai_case', queue='ai_automation', ignore_result=True)
def run_ai_case_task(self, execution_record_id, ai_case_id):
    """执行 AI 用例，对应原来 AICaseViewSet.run 里的裸线程逻辑。"""
    from asgiref.sync import sync_to_async
    from django.db import connection, DatabaseError
    from .models import AICase, AIExecutionRecord
    from .ai_agent import run_full_process_sync
    from .ai_execution_helpers import extract_step_info
    from .ai_execution_helpers import process_gif_recording, auto_mark_completed_tasks

    try:
        execution_record = AIExecutionRecord.objects.get(id=execution_record_id)
        ai_case = AICase.objects.get(id=ai_case_id)
    except (AIExecutionRecord.DoesNotExist, AICase.DoesNotExist) as e:
        logger.error(f"[Celery] AI 用例执行记录/用例不存在: {e}")
        return

    try:
        connection.close()
    except Exception:
        pass

    def safe_save(record, update_fields=None, max_retries=3):
        import time as _time
        for attempt in range(max_retries):
            try:
                record.save(update_fields=update_fields)
                return True
            except (DatabaseError, Exception) as e:
                error_str = str(e)
                if '2006' in error_str or 'MySQL server has gone away' in error_str or error_str == '0':
                    if attempt < max_retries - 1:
                        logger.warning(f"[Celery] 数据库连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                        try:
                            connection.close()
                        except Exception:
                            pass
                        _time.sleep(0.5)
                        continue
                    logger.error(f"[Celery] 数据库保存失败，已达最大重试次数: {e}")
                    raise
                logger.error(f"[Celery] 数据库保存失败: {e}")
                raise
        return False

    def should_stop():
        # 停止信号通过数据库状态传递（AIExecutionRecordViewSet.stop_task 直接把
        # status 置为 'stopped'），这样 Django Web 进程和 Celery worker 进程
        # 之间不需要共享内存状态，天然支持跨进程。
        execution_record.refresh_from_db()
        return execution_record.status == 'stopped'

    try:
        async def on_analysis_complete(planned_tasks):
            execution_record.planned_tasks = planned_tasks
            execution_record.logs += "任务分析完成，开始执行...\n"
            await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks', 'logs'])

        async def on_step_update(step_info):
            try:
                if step_info.get('type') == 'log':
                    content = step_info.get('content')
                    if content:
                        execution_record.logs += content
                        await sync_to_async(safe_save)(execution_record, update_fields=['logs'])
                    return

                task_id = step_info.get('task_id')
                step_status = step_info.get('status')
                if task_id and step_status:
                    updated = False
                    for t in execution_record.planned_tasks:
                        if t['id'] == task_id:
                            t['status'] = step_status
                            updated = True
                            break
                    if updated:
                        await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks'])
            except Exception as e:
                logger.error(f"[Celery] 更新步骤状态失败: {e}")

        history = run_full_process_sync(
            ai_case.task_description,
            analysis_callback=on_analysis_complete,
            step_callback=on_step_update,
            should_stop=should_stop
        )

        if should_stop():
            execution_record.status = 'stopped'
            execution_record.logs += "\n[System] 任务已由用户停止。"
        else:
            execution_record.status = 'passed'
            execution_record.logs += "\n执行完成。"

        execution_record.end_time = timezone.now()
        execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()

        steps = []
        if history and hasattr(history, 'steps'):
            steps = [extract_step_info(s, i) for i, s in enumerate(history.steps)]
        execution_record.steps_completed = steps

        if execution_record.planned_tasks:
            auto_mark_completed_tasks(execution_record)

        process_gif_recording(execution_record, history)

        safe_save(execution_record)

    except Exception as e:
        logger.error(f"[Celery] AI 用例执行失败: {e}", exc_info=True)
        execution_record.status = 'failed'
        execution_record.end_time = timezone.now()
        execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()
        execution_record.logs += f"\n执行出错: {str(e)}"
        try:
            safe_save(execution_record)
        except Exception:
            logger.error("[Celery] 保存失败状态时出错", exc_info=True)


@shared_task(bind=True, name='ui_automation.run_ai_adhoc', queue='ai_automation', ignore_result=True)
def run_ai_adhoc_task(self, execution_record_id, task_description, execution_mode='text', enable_gif=True):
    """执行临时 AI 任务，对应原来 AIExecutionRecordViewSet.run_adhoc 里的裸线程逻辑。"""
    from asgiref.sync import sync_to_async
    from django.db import connection, DatabaseError
    from .models import AIExecutionRecord
    from .ai_agent import run_full_process_sync
    from .ai_execution_helpers import extract_step_info
    from .ai_execution_helpers import process_gif_recording, auto_mark_completed_tasks

    try:
        execution_record = AIExecutionRecord.objects.get(id=execution_record_id)
    except AIExecutionRecord.DoesNotExist:
        logger.error(f"[Celery] AI 执行记录不存在: {execution_record_id}")
        return

    try:
        connection.close()
    except Exception:
        pass

    def safe_save(record, update_fields=None, max_retries=3):
        import time as _time
        for attempt in range(max_retries):
            try:
                record.save(update_fields=update_fields)
                return True
            except (DatabaseError, Exception) as e:
                error_str = str(e)
                if '2006' in error_str or 'MySQL server has gone away' in error_str or error_str == '0':
                    if attempt < max_retries - 1:
                        logger.warning(f"[Celery] 数据库连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                        try:
                            connection.close()
                        except Exception:
                            pass
                        _time.sleep(0.5)
                        continue
                    logger.error(f"[Celery] 数据库保存失败，已达最大重试次数: {e}")
                    raise
                logger.error(f"[Celery] 数据库保存失败: {e}")
                raise
        return False

    async def should_stop_async():
        await sync_to_async(execution_record.refresh_from_db)()
        return execution_record.status == 'stopped'

    def should_stop_sync():
        execution_record.refresh_from_db()
        return execution_record.status == 'stopped'

    try:
        async def on_analysis_complete(planned_tasks):
            execution_record.planned_tasks = planned_tasks
            execution_record.logs += "任务分析完成，开始执行...\n"
            await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks', 'logs'])

        async def on_step_update(step_info):
            try:
                if step_info.get('type') == 'log':
                    content = step_info.get('content')
                    if content:
                        execution_record.logs += content
                        await sync_to_async(safe_save)(execution_record, update_fields=['logs'])
                    return

                task_id = step_info.get('task_id')
                step_status = step_info.get('status')
                if task_id and step_status:
                    updated = False
                    if execution_record.planned_tasks:
                        for t in execution_record.planned_tasks:
                            if str(t['id']) == str(task_id):
                                t['status'] = step_status
                                updated = True
                                break
                    if updated:
                        await sync_to_async(safe_save)(execution_record, update_fields=['planned_tasks'])
            except Exception as e:
                logger.error(f"[Celery] 更新步骤状态失败: {e}", exc_info=True)

        history = run_full_process_sync(
            task_description,
            analysis_callback=on_analysis_complete,
            step_callback=on_step_update,
            should_stop=should_stop_async,
            execution_mode=execution_mode,
            enable_gif=enable_gif,
            case_name=task_description[:50] if task_description else "Adhoc Task"
        )

        if should_stop_sync():
            execution_record.status = 'stopped'
            execution_record.logs += "\n[System] 任务已由用户停止。"
        else:
            execution_record.status = 'passed'
            execution_record.logs += "\n执行完成。"

        execution_record.end_time = timezone.now()
        execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()

        steps = []
        if history and hasattr(history, 'steps'):
            steps = [extract_step_info(s, i) for i, s in enumerate(history.steps)]
        execution_record.steps_completed = steps

        if execution_record.planned_tasks:
            auto_mark_completed_tasks(execution_record)

        process_gif_recording(execution_record, history)

        safe_save(execution_record)

    except Exception as e:
        logger.error(f"[Celery] AI adhoc 任务执行失败: {e}", exc_info=True)
        execution_record.status = 'failed'
        execution_record.end_time = timezone.now()
        execution_record.duration = (execution_record.end_time - execution_record.start_time).total_seconds()
        execution_record.logs += f"\n执行出错: {str(e)}"
        try:
            safe_save(execution_record)
        except Exception:
            logger.error("[Celery] 保存失败状态时出错", exc_info=True)


@shared_task(name='ui_automation.dispatch_due_tasks', ignore_result=True)
def dispatch_due_tasks():
    """由 Celery Beat 每分钟触发：提交所有到期的 UI 定时任务（原 run_all_scheduled_tasks 中的 UI 部分）"""
    from django.db.models import F
    from .models import UiScheduledTask

    now = timezone.now()
    dispatched = 0
    for task in UiScheduledTask.objects.filter(status='ACTIVE', next_run_time__lte=now):
        next_run = task.calculate_next_run()
        # 配置缺失就不必占用任务队列，直接推进到下一周期
        missing_config = (
            (task.task_type == 'TEST_SUITE' and not task.test_suite_id)
            or (task.task_type == 'TEST_CASE' and not task.test_cases)
        )
        updates = {'next_run_time': next_run}
        if not missing_config:
            updates.update(last_run_time=now, total_runs=F('total_runs') + 1)

        # 提交前先把 next_run_time 推到下一周期（条件更新抢占），避免长任务或多个调度器导致重复触发
        claimed = UiScheduledTask.objects.filter(
            pk=task.pk, status='ACTIVE', next_run_time=task.next_run_time
        ).update(**updates)
        if not claimed:
            continue
        if missing_config:
            logger.error(f"[UI] 定时任务 {task.name} 未配置{'测试套件' if task.task_type == 'TEST_SUITE' else '测试用例'}，已跳过")
            continue
        try:
            run_scheduled_task_now_task.delay(task.id)
            dispatched += 1
            logger.info(f"[UI] 定时任务已提交: {task.name}")
        except Exception as e:
            logger.error(f"[UI] 提交定时任务 {task.name} 失败: {e}", exc_info=True)
    return dispatched
