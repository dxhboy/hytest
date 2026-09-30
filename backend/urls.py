from django.contrib import admin
import re

from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as serve_media
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
)
from backend.schema_views import LangAwareSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', LangAwareSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    path('api/auth/', include('apps.users.urls')),
    path('api/projects/', include('apps.projects.urls')),
    path('api/testcases/', include('apps.testcases.urls')),
    path('api/testsuites/', include('apps.testsuites.urls')),
    path('api/executions/', include('apps.executions.urls')),
    path('api/reports/', include('apps.reports.urls')),
    path('api/reviews/', include('apps.reviews.urls')),
    path('api/versions/', include('apps.versions.urls')),
    path('api/assistant/', include('apps.assistant.urls')),
    path('api/ai-assistant/', include('apps.ai_assistant.urls')),
    path('api/users/', include('apps.users.urls')),
    path('api/requirement-analysis/', include('apps.requirement_analysis.urls')),
    path('api/ui-automation/', include('apps.ui_automation.urls')),
    path('api/', include('apps.api_testing.urls')),
    path('api/core/', include('apps.core.urls')),
    path('api/data-factory/', include('apps.data_factory.urls')),
]

# 媒体文件（Allure 报告、截图、录屏等）统一只在这里挂载，由 SERVE_MEDIA 控制。
# 不用 static()：它在 DEBUG=False 时直接返回空列表，而现有非 Docker 部署依赖 Django 提供 /media/。
# 生产环境建议由 nginx 直接托管 /media/ 目录，并设置 SERVE_MEDIA=False。
if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % re.escape(settings.MEDIA_URL.lstrip('/')),
            serve_media,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_FILES_URL, document_root=settings.STATIC_FILES_ROOT)
