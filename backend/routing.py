"""
WebSocket URL 路由配置。
所有 WebSocket 连接统一在此注册。
"""
from django.urls import re_path
from apps.ui_automation.recording.consumer import RecordingConsumer

websocket_urlpatterns = [
    re_path(r'ws/ui-automation/recording/(?P<session_id>\d+)/$', RecordingConsumer.as_asgi()),
]
