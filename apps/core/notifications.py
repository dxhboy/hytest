"""
通知发送的传输层公共逻辑（Webhook 机器人 / 邮件）

各业务模块（api_testing / ui_automation）仍各自负责：
- 消息内容（卡片 / Markdown 文案）
- 通知日志（NotificationLog / UiNotificationLog）的写入
- 成功与否的判定口径

这里只负责：
- 从统一通知配置（UnifiedNotificationConfig）收集启用的机器人
- 飞书 / 钉钉签名
- 发送 Webhook 请求、发送邮件、整理收件人
"""
import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

import requests

logger = logging.getLogger(__name__)

WEBHOOK_CONFIG_TYPES = ('webhook_wechat', 'webhook_feishu', 'webhook_dingtalk')
WEBHOOK_TIMEOUT = 10

# 业务模块在机器人配置上的开关字段
MODULE_API_TESTING = 'enable_api_testing'
MODULE_UI_AUTOMATION = 'enable_ui_automation'

FEISHU_TYPES = ('feishu', 'lark')


# ---------------------------------------------------------------------- #
# 机器人收集
# ---------------------------------------------------------------------- #
def has_active_webhook_config() -> bool:
    """是否存在任何激活的统一 Webhook 配置"""
    from apps.core.models import UnifiedNotificationConfig
    return UnifiedNotificationConfig.objects.filter(
        config_type__in=list(WEBHOOK_CONFIG_TYPES),
        is_active=True
    ).exists()


def collect_unified_webhook_bots(module_flag: str, log_skipped: bool = False) -> List[dict]:
    """
    从所有激活的统一通知配置中收集机器人

    Args:
        module_flag: 模块开关字段（MODULE_API_TESTING / MODULE_UI_AUTOMATION），为 False 的机器人跳过
        log_skipped: 是否记录被跳过/被添加的机器人日志

    Raises:
        数据库/导入异常原样抛出，由调用方决定降级策略
    """
    from apps.core.models import UnifiedNotificationConfig
    configs = UnifiedNotificationConfig.objects.filter(
        config_type__in=list(WEBHOOK_CONFIG_TYPES),
        is_active=True
    )
    bots = []
    for config in configs:
        for bot in (config.get_webhook_bots() or []):
            if not bot.get('enabled', True):
                continue
            if bot.get(module_flag, True):
                bots.append(bot)
                if log_skipped:
                    logger.info(f"添加机器人: {bot.get('name')} ({module_flag} 已启用)")
            elif log_skipped:
                logger.info(f"配置中心机器人 {bot.get('name')} 未启用 {module_flag}，跳过")
    return bots


# ---------------------------------------------------------------------- #
# 签名
# ---------------------------------------------------------------------- #
def feishu_sign(secret: str, timestamp: Optional[str] = None) -> tuple:
    """飞书签名：timestamp(秒)，签名串 `timestamp\\nsecret` 作为 HMAC key，返回 (timestamp, sign)"""
    timestamp = timestamp or str(int(time.time()))
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    return timestamp, base64.b64encode(hmac_code).decode('utf-8')


def dingtalk_signed_url(webhook_url: str, secret: str, timestamp: Optional[str] = None) -> str:
    """钉钉签名：timestamp(毫秒) + sign 追加到 URL 查询参数"""
    timestamp = timestamp or str(round(time.time() * 1000))
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode('utf-8'))
    separator = '&' if '?' in webhook_url else '?'
    return f'{webhook_url}{separator}timestamp={timestamp}&sign={sign}'


def prepare_webhook_request(bot: dict, payload: dict) -> tuple:
    """
    按机器人类型加签，返回 (url, payload)
    - 飞书：timestamp/sign 写入请求体（不能加到 URL）
    - 钉钉：timestamp/sign 追加到 URL
    - 企业微信等：原样
    """
    bot_type = bot.get('type', 'unknown')
    url = bot['webhook_url']
    secret = bot.get('secret')
    payload = dict(payload)
    if secret:
        if bot_type in FEISHU_TYPES:
            payload['timestamp'], payload['sign'] = feishu_sign(secret)
        elif bot_type == 'dingtalk':
            url = dingtalk_signed_url(url, secret)
    return url, payload


# ---------------------------------------------------------------------- #
# 发送
# ---------------------------------------------------------------------- #
@dataclass
class WebhookResult:
    """单次 Webhook 发送结果（不抛异常，调用方按各自口径判定成功与否）"""
    bot_type: str
    url: str
    payload: dict
    response: Any = None
    error: Optional[Exception] = None

    @property
    def status_code(self) -> Optional[int]:
        return self.response.status_code if self.response is not None else None

    @property
    def text(self) -> str:
        return self.response.text if self.response is not None else ''

    @property
    def biz_code(self):
        """飞书/钉钉/企微始终返回 HTTP 200，业务结果看响应体 code / errcode；解析失败视为 0"""
        if self.response is None:
            return None
        try:
            data = self.response.json()
            return data.get('code', data.get('errcode', 0))
        except Exception:
            return 0

    @property
    def delivered(self) -> bool:
        """HTTP 200 且业务 code 为 0"""
        return self.error is None and self.status_code == 200 and self.biz_code == 0


def post_webhook(bot: dict, payload: dict, timeout: int = WEBHOOK_TIMEOUT) -> WebhookResult:
    """加签并 POST 到机器人 Webhook"""
    bot_type = bot.get('type', 'unknown')
    url, payload = prepare_webhook_request(bot, payload)
    result = WebhookResult(bot_type=bot_type, url=url, payload=payload)
    try:
        result.response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=timeout
        )
    except requests.exceptions.RequestException as e:
        result.error = e
    return result


def mask_url(url: str, keep: int = 50) -> str:
    """日志里只保留 URL 前缀，避免泄露 access_token"""
    return url[:keep] + '...' if len(url) > keep else url


# ---------------------------------------------------------------------- #
# 邮件
# ---------------------------------------------------------------------- #
def normalize_emails(value) -> List[str]:
    """notify_emails 字段可能是 list / 单个字符串 / 空"""
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [e for e in value if e]
    return [value]


def resolve_recipients(users: Optional[Iterable] = None, emails=None) -> List[str]:
    """合并用户邮箱与额外邮箱，去重并保持顺序"""
    recipients = []
    for user in (users or []):
        if getattr(user, 'email', None):
            recipients.append(user.email)
    recipients.extend(normalize_emails(emails))
    return list(dict.fromkeys(recipients))


def send_email(subject: str, message: str, recipients: List[str]) -> str:
    """发送纯文本邮件（失败抛异常），返回发件人地址"""
    from django.conf import settings
    from django.core.mail import send_mail

    from_email = settings.DEFAULT_FROM_EMAIL
    send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=recipients,
        fail_silently=False,
    )
    return from_email
