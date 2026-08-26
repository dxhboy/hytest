"""
ASGI 配置 — 支持 HTTP 和 WebSocket 双协议。
HTTP 请求走 Django 默认处理，WebSocket 请求走 Channels routing。
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.auth import AuthMiddlewareStack
from backend.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    # AuthMiddlewareStack 从 session 中解析出 scope['user']，
    # 供 consumer 在 connect() 中做身份校验，防止未认证客户端连入。
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
