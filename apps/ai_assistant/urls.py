from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatView, SessionViewSet

router = DefaultRouter()
router.register(r'sessions', SessionViewSet, basename='ai-assistant-sessions')

urlpatterns = [
    path('chat/send_message/', ChatView.as_view(), name='ai-assistant-chat'),
    path('', include(router.urls)),
]
