from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.module_loading import autodiscover_modules
import time
import logging

from backend.celery import app as celery_app

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        '在当前进程内执行 CELERY_BEAT_SCHEDULE 中的所有调度任务（API测试 + UI自动化 + 定时用例生成）。'
        '推荐使用 `celery -A backend beat` 代替；本命令适合调试或不便部署 Beat 的环境，两者可并存不会重复执行。'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='检查间隔（秒），默认60秒'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='只执行一次检查，不循环'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        run_once = options['once']
        autodiscover_modules('tasks')  # 注册各 app 的 shared_task
        dispatchers = [entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()]

        self.stdout.write(self.style.SUCCESS(f"启动统一定时任务调度器，检查间隔 {interval} 秒"))
        self.stdout.write(f"调度任务: {', '.join(dispatchers)}")

        while True:
            now = timezone.localtime(timezone.now())
            self.stdout.write(f"\n[{now:%Y-%m-%d %H:%M:%S}] 开始检查任务...")
            for name in dispatchers:
                try:
                    # 直接在本进程调用（不经过 broker），实际执行仍提交给 Celery worker
                    count = celery_app.tasks[name]()
                    if count:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ {name}: 提交了 {count} 个任务"))
                except Exception as e:
                    logger.error(f"调度 {name} 出错: {e}", exc_info=True)
                    self.stdout.write(self.style.ERROR(f"  ✗ {name}: {e}"))

            if run_once:
                break
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\n调度器已停止"))
                break
