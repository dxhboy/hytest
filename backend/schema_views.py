# backend/schema_views.py
from drf_spectacular.views import SpectacularSwaggerView


class LangAwareSwaggerView(SpectacularSwaggerView):
    """
    Swagger UI View，使用自定义 JS 模板。
    JS 模板从 localStorage['app-lang'] 读取语言，
    动态请求 /api/schema/?lang=<zh-cn|en>，
    由 auto_tag_hook 返回对应语言的接口标签。
    """
    template_name_js = 'drf_spectacular/swagger_ui_lang.js'
