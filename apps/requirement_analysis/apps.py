from django.apps import AppConfig


class RequirementAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.requirement_analysis'
    verbose_name = '需求分析'

    def ready(self):
        import apps.requirement_analysis.signals  # noqa: F401

        import sys
        # Don't start scheduler during test runs
        if 'test' in sys.argv:
            return
        try:
            from .scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to start scheduler: {e}")
