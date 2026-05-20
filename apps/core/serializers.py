"""
Core 应用序列化器
"""
from rest_framework import serializers
from .models import UnifiedNotificationConfig


class UnifiedNotificationConfigSerializer(serializers.ModelSerializer):
    """统一通知配置序列化器"""

    webhook_bots_display = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedNotificationConfig
        fields = [
            'id', 'name', 'config_type', 'webhook_bots',
            'is_default', 'is_active', 'visibility',
            'created_at', 'updated_at', 'created_by', 'created_by_name',
            'webhook_bots_display',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'created_by_name', 'webhook_bots_display']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return ''

    def get_webhook_bots_display(self, obj):
        """获取 webhook 机器人显示信息（兼容新旧数据格式）"""
        data = obj.webhook_bots or {}
        # 新格式：webhook_bots 直接存储单条配置 {webhook_url, secret, ...}
        if 'webhook_url' in data or 'host' in data:
            return [{
                'name': obj.name,
                'enabled': data.get('enabled', True),
                'webhook_url': data.get('webhook_url', ''),
            }]
        # 旧格式：{bot_type: {webhook_url, ...}}
        display_list = []
        for bot_type, bot_config in data.items():
            display_list.append({
                'type': bot_type,
                'name': bot_config.get('name', obj.name),
                'enabled': bot_config.get('enabled', True),
                'webhook_url': bot_config.get('webhook_url', ''),
            })
        return display_list
