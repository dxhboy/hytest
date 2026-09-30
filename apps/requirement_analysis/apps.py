from django.apps import AppConfig


class RequirementAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.requirement_analysis'
    verbose_name = '需求分析'

    def ready(self):
        import apps.requirement_analysis.signals  # noqa: F401
        # 定时生成任务由 Celery Beat 调度（见 settings.CELERY_BEAT_SCHEDULE），
        # 不再在每个 Django 进程里各自启动 APScheduler，避免多进程重复触发
