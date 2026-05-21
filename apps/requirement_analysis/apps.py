from django.apps import AppConfig


class RequirementAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.requirement_analysis'
    verbose_name = '需求分析'

    def ready(self):
        import os
        # 避免 Django 开发服务器 auto-reloader 导致 scheduler 启动两次
        if os.environ.get('RUN_MAIN') != 'true' and os.environ.get('DJANGO_SETTINGS_MODULE'):
            return
        try:
            from .scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to start scheduler: {e}")
