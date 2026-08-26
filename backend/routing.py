"""
WebSocket URL 路由配置。
所有 WebSocket 连接统一在此注册。
"""
from django.urls import re_path

# Consumer 将在后续 Task 中实现，此处先用空列表占位
websocket_urlpatterns = [
    # re_path(r'ws/ui-automation/recording/(?P<session_id>\d+)/$', RecordingConsumer.as_asgi()),
]
