from django.apps import AppConfig


class ApiTestingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api_testing'
    verbose_name = '接口测试'

    def ready(self):
        # 请求断言变更 → 同步到原样复制了断言的套件步骤
        from . import signals  # noqa: F401
