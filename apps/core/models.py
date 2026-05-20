"""
Core 应用模型
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class UnifiedNotificationConfig(models.Model):
    """统一通知配置模型 - 支持飞书/企微/钉钉机器人及邮件配置，每条记录对应一个独立配置"""

    CONFIG_TYPE_CHOICES = [
        ('webhook_feishu', '飞书机器人'),
        ('webhook_wechat', '企业微信机器人'),
        ('webhook_dingtalk', '钉钉机器人'),
        ('email', '邮件'),
    ]

    VISIBILITY_CHOICES = [
        ('all', '所有人可见'),
        ('private', '仅自己可见'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称', help_text='用于标识该通知配置的名称')
    config_type = models.CharField(max_length=20, choices=CONFIG_TYPE_CHOICES, default='webhook_feishu',
                                   verbose_name='配置类型')
    # 机器人类型存储: {webhook_url, secret, enabled, enable_ui_automation, enable_api_testing}
    # 邮件类型存储: {host, port, username, password, use_tls, from_email}
    webhook_bots = models.JSONField(default=dict, blank=True, null=True, verbose_name='配置数据',
                                    help_text='机器人或邮件的具体配置参数')
    is_default = models.BooleanField(default=False, verbose_name='是否默认配置')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='all',
                                  verbose_name='可见性', help_text='all=所有人可见可用, private=仅自己可见可用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')

    class Meta:
        db_table = 'unified_notification_configs'
        verbose_name = '统一通知配置'
        verbose_name_plural = '统一通知配置'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['config_type']),
            models.Index(fields=['is_default']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.name} - {self.get_config_type_display()}"

    def get_webhook_bots(self):
        """获取配置的所有webhook机器人"""
        bots = []
        if self.webhook_bots:
            for bot_type, bot_config in self.webhook_bots.items():
                bot_data = {
                    'type': bot_type,
                    'name': bot_config.get('name', f'{bot_type}机器人'),
                    'webhook_url': bot_config.get('webhook_url'),
                    'enabled': bot_config.get('enabled', True),
                    # 业务类型勾选框
                    'enable_ui_automation': bot_config.get('enable_ui_automation', True),
                    'enable_api_testing': bot_config.get('enable_api_testing', True)
                }
                # 钉钉机器人需要额外包含secret字段
                if bot_type == 'feishu' and bot_config.get('secret'):
                    bot_data['secret'] = bot_config.get('secret')
                if bot_type == 'dingtalk' and bot_config.get('secret'):
                    bot_data['secret'] = bot_config.get('secret')
                bots.append(bot_data)
        return bots
