"""定时任务执行结果通知（邮件 / Webhook）"""
import json
import logging

import requests
from django.utils import timezone

from apps.core import notifications


class NotificationManager:
    """通知管理器 - 处理邮件和Webhook通知"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_notification(self, task, execution_log, success=True):
        """发送通知"""
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            self.logger.info(f"任务: {task}, execution_log: {execution_log}")
            self.logger.info(f"发送通知 - 任务: {task.name}, 状态: {'成功' if success else '失败'}")

            notification_setting = None
            if hasattr(task, 'notification_settings'):
                try:
                    notification_setting = task.notification_settings.first()
                except Exception as e:
                    self.logger.error(f"获取任务通知设置时出错: {e}")
                    return

            if not notification_setting or not notification_setting.is_enabled:
                self.logger.info(f"任务 {task.id} 的通知设置未启用或不存在")
                return

            execution_status = 'success' if success else 'failed'
            if not notification_setting.should_notify(execution_status):
                self.logger.info(f"根据执行状态 {execution_status}，不应该发送通知")
                return

            notification_config = notification_setting.get_notification_config()
            self.logger.info(f"notification_setting: {notification_setting}")
            self.logger.info(f"notification_config: {notification_config}")
            has_config = notification_config is not None
            has_custom_bots = bool(notification_setting.custom_webhook_bots)
            has_custom_recipients = notification_setting.custom_recipients.exists()

            # 当通知类型包含 webhook 时，还需检查是否存在任何激活的统一 Webhook 配置，
            # _send_webhook_notification 会独立查询所有激活配置，不依赖 FK 关联
            has_unified_webhook = False
            if notification_setting.notification_type in ['webhook', 'both']:
                try:
                    has_unified_webhook = notifications.has_active_webhook_config()
                except Exception as e:
                    self.logger.warning(f"检查统一Webhook配置时出错: {e}")

            if not (has_config or has_custom_bots or has_custom_recipients or has_unified_webhook):
                self.logger.warning("没有找到通知配置且无自定义设置")
                return

            if notification_setting.notification_type in ['email', 'both']:
                self._send_email_notification(task, execution_log, notification_setting, notification_config, success)

            if notification_setting.notification_type in ['webhook', 'both']:
                self._send_webhook_notification(task, execution_log, notification_setting, notification_config, success)

        except Exception as e:
            self.logger.error(f"发送通知失败: {str(e)}", exc_info=True)

    def _send_email_notification(self, task, execution_log, notification_setting, notification_config, success):
        """发送邮件通知"""
        try:
            self.logger.info("开始发送邮件通知")

            subject = f"定时任务执行{'成功' if success else '失败'}: {task.name}"

            summary_info = '无详细信息'
            if execution_log.result:
                result_data = execution_log.result
                summary_fields = {
                    'success': result_data.get('success'),
                    'execution_id': result_data.get('execution_id'),
                    'passed_count': result_data.get('passed_count'),
                    'failed_count': result_data.get('failed_count'),
                    'total_count': result_data.get('total_count')
                }
                summary_info = '\n'.join([f'{k}: {v}' for k, v in summary_fields.items() if v is not None])

            message = f"""
            任务名称: {task.name}
            执行状态: {'成功' if success else '失败'}
            执行时间: {execution_log.created_at.strftime('%Y-%m-%d %H:%M:%S')}
            任务类型: {'测试套件执行' if task.task_type == 'TEST_SUITE' else 'API请求执行'}

            执行概要:
            {summary_info}

            错误信息:
            {execution_log.error_message if execution_log.error_message else '无错误信息'}
            """

            recipients = notifications.resolve_recipients(
                users=notification_setting.custom_recipients.all(),
                emails=getattr(task, 'notify_emails', None),
            )

            if not recipients:
                self.logger.warning("没有找到任何邮件收件人")
                return

            from_email = notifications.send_email(subject, message, recipients)
            self.logger.info("邮件发送成功")

            from ..models import NotificationLog
            NotificationLog.objects.create(
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
            self.logger.error(f"发送邮件通知失败: {str(e)}", exc_info=True)

    def _send_webhook_notification(self, task, execution_log, notification_setting, notification_config, success):
        """发送Webhook通知"""
        try:
            self.logger.info("开始发送Webhook通知")

            all_webhook_bots = []

            try:
                all_webhook_bots.extend(
                    notifications.collect_unified_webhook_bots(notifications.MODULE_API_TESTING)
                )
            except ImportError:
                self.logger.warning("无法导入统一配置，尝试使用API测试模块配置")
                if notification_config:
                    bots = notification_config.get_webhook_bots()
                    all_webhook_bots.extend([b for b in bots if b.get('enabled', True)])
            except Exception as e:
                self.logger.error(f"获取统一配置时出错: {e}")

            if notification_setting.custom_webhook_bots:
                for bot_type, bot_config in notification_setting.custom_webhook_bots.items():
                    bot_data = {
                        'type': bot_type,
                        'name': bot_config.get('name', f'自定义{bot_type}机器人'),
                        'webhook_url': bot_config.get('webhook_url'),
                        'enabled': bot_config.get('enabled', True)
                    }
                    if bot_type == 'dingtalk' and bot_config.get('secret'):
                        bot_data['secret'] = bot_config.get('secret')
                    elif bot_type == 'feishu' and bot_config.get('secret'):
                        bot_data['secret'] = bot_config.get('secret')

                    if bot_data.get('enabled', True) and bot_data.get('webhook_url'):
                        all_webhook_bots.append(bot_data)

            if not all_webhook_bots:
                self.logger.warning("没有找到任何启用的webhook机器人配置")
                return

            status_text = '成功' if success else '失败'

            for bot in all_webhook_bots:
                self._send_single_webhook(bot, task, execution_log, status_text, success)

        except Exception as e:
            self.logger.error(f"发送Webhook通知失败: {str(e)}", exc_info=True)

    def _send_single_webhook(self, bot, task, execution_log, status_text, success):
        """发送单个Webhook通知，签名（飞书写请求体 / 钉钉加 URL）由 apps.core.notifications 处理"""
        bot_type = bot.get('type', 'unknown')
        webhook_url = bot['webhook_url']

        message_data = self._build_webhook_message(bot_type, task, execution_log, status_text, success)

        try:
            result = notifications.post_webhook(bot, message_data)
            webhook_url, message_data = result.url, result.payload
            if result.error is not None:
                raise result.error
            response = result.response
            response.raise_for_status()
            # 飞书/钉钉始终返回 HTTP 200，实际成功与否需检查响应体中的业务 code
            resp_text = response.text[:200]
            try:
                resp_json = response.json()
                biz_code = resp_json.get('code', resp_json.get('errcode', 0))
            except Exception:
                resp_json = {}
                biz_code = 0

            notify_status = 'success' if biz_code == 0 else 'failed'
            if notify_status == 'success':
                self.logger.info(f"Webhook通知发送成功 - {bot_type}: {response.status_code}, 响应体: {resp_text}")
            else:
                self.logger.error(f"Webhook通知业务失败 - {bot_type}: code={biz_code}, 响应体: {resp_text}")

            from ..models import NotificationLog
            NotificationLog.objects.create(
                task=task,
                task_name=task.name,
                task_type=task.task_type,
                notification_type='task_execution',
                sender_name=f'系统Webhook通知-{bot_type}',
                sender_email='',
                recipient_info=[],
                webhook_bot_info={
                    'bot_type': bot_type,
                    'bot_name': bot.get('name', 'Unknown'),
                    'webhook_url': webhook_url[:50] + '...' if len(webhook_url) > 50 else webhook_url
                },
                notification_content=json.dumps(message_data, ensure_ascii=False),
                status=notify_status,
                error_message='' if notify_status == 'success' else resp_text,
                sent_at=timezone.now(),
                response_info={
                    'status_code': response.status_code,
                    'response_text': response.text[:500]
                }
            )

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Webhook通知发送失败 - {bot_type}: {str(e)}")

            try:
                from ..models import NotificationLog
                NotificationLog.objects.create(
                    task=task,
                    task_name=task.name,
                    task_type=task.task_type,
                    notification_type='task_execution',
                    sender_name=f'系统Webhook通知-{bot_type}',
                    sender_email='',
                    recipient_info=[],
                    webhook_bot_info={
                        'bot_type': bot_type,
                        'bot_name': bot.get('name', 'Unknown'),
                        'webhook_url': webhook_url[:50] + '...' if len(webhook_url) > 50 else webhook_url
                    },
                    notification_content=json.dumps(message_data, ensure_ascii=False),
                    status='failed',
                    error_message=str(e),
                    sent_at=timezone.now()
                )
            except:
                pass

    def _build_webhook_message(self, bot_type, task, execution_log, status_text, success):
        """构建卡片格式Webhook消息"""
        import socket
        from urllib.parse import urlparse, urlunparse
        from django.conf import settings as django_settings

        exec_time = execution_log.created_at.strftime('%Y-%m-%d %H:%M:%S')
        task_type_text = '接口测试套件' if task.task_type == 'TEST_SUITE' else 'API请求'

        # 获取项目名称
        project_name = ''
        try:
            if task.test_suite:
                project_name = task.test_suite.project.name
            elif task.api_request and task.api_request.collection:
                project_name = task.api_request.collection.project.name
        except Exception:
            pass

        title = f"{'✅' if success else '❌'} {project_name + ' - ' if project_name else ''}{task_type_text}接口测试报告"

        result_data = execution_log.result or {}
        total = result_data.get('total_count', 0) or 0
        passed = result_data.get('passed_count', 0) or 0
        failed = result_data.get('failed_count', 0) or 0
        execution_id = result_data.get('execution_id')
        pass_rate = f"{round(passed / total * 100)}%" if total else 'N/A'

        # 自动将 localhost/127.0.0.1 替换为本机对外 IP，确保外网（飞书/钉钉）可访问
        configured_url = getattr(django_settings, 'SITE_BASE_URL', 'http://localhost:3000')
        parsed = urlparse(configured_url)
        if parsed.hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
            try:
                # 通过 UDP 探测对外路由接口，获取本机局域网/公网 IP
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as _s:
                    _s.settimeout(1)
                    _s.connect(('8.8.8.8', 80))
                    local_ip = _s.getsockname()[0]
            except Exception:
                try:
                    local_ip = socket.gethostbyname(socket.gethostname())
                except Exception:
                    local_ip = parsed.hostname  # 保持原值
            port_part = f":{parsed.port}" if parsed.port else ''
            site_url = f"{parsed.scheme}://{local_ip}{port_part}"
        else:
            site_url = configured_url

        # 链接指向 Allure 摘要报告页，与"生成并查看报告"入口一致
        report_url = (
            f"{site_url}/media/allure-reports/execution_{execution_id}/summary.html"
            if execution_id else site_url
        )

        if bot_type in ['feishu', 'lark']:
            elements = [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务名称**\n{task.name}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行状态**\n{status_text}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行时间**\n{exec_time}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务类型**\n{task_type_text}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**总用例数**\n{total}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**通过 / 失败**\n{passed} / {failed}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**通过率**\n{pass_rate}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**所属项目**\n{project_name or '-'}"}},
                    ]
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看测试报告"},
                            "url": report_url,
                            "type": "primary"
                        }
                    ]
                }
            ]
            if execution_log.error_message:
                elements.insert(1, {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**错误信息**\n{execution_log.error_message[:200]}"}
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

        elif bot_type == 'wechat':
            status_color = 'info' if success else 'warning'
            content = (
                f"## {title}\n\n"
                f"> **任务名称**: {task.name}\n"
                f"> **执行状态**: <font color=\"{status_color}\">{status_text}</font>\n"
                f"> **执行时间**: {exec_time}\n"
                f"> **任务类型**: {task_type_text}\n"
                f"> **所属项目**: {project_name or '-'}\n"
                f"> **总用例数**: {total}\n"
                f"> **通过 / 失败**: {passed} / {failed}\n"
                f"> **通过率**: {pass_rate}\n"
            )
            if execution_log.error_message:
                content += f"> **错误信息**: {execution_log.error_message[:200]}\n"
            content += f"\n[查看测试报告]({report_url})"
            return {
                "msgtype": "markdown",
                "markdown": {"content": content}
            }

        elif bot_type == 'dingtalk':
            text = (
                f"### {title}\n\n"
                f"**任务名称**: {task.name}\n\n"
                f"**执行状态**: {status_text}\n\n"
                f"**执行时间**: {exec_time}\n\n"
                f"**任务类型**: {task_type_text}\n\n"
                f"**所属项目**: {project_name or '-'}\n\n"
                f"**总用例数**: {total} | **通过**: {passed} | **失败**: {failed} | **通过率**: {pass_rate}\n\n"
            )
            if execution_log.error_message:
                text += f"**错误信息**: {execution_log.error_message[:200]}\n\n"
            return {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": text,
                    "singleTitle": "查看测试报告",
                    "singleURL": report_url
                }
            }

        else:
            return {
                "text": f"{title}\n任务名称: {task.name}\n执行状态: {status_text}\n执行时间: {exec_time}\n总用例: {total} 通过: {passed} 失败: {failed} 通过率: {pass_rate}"
            }
