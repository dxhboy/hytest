"""仓库根目录的 pytest 全局配置：测试统一使用进程内 LocMemCache（settings 在配置了 REDIS_URL 时默认使用 RedisCache）"""


def pytest_configure(config):
    _use_locmem_cache()


def _use_locmem_cache():
    """测试统一使用进程内缓存：不依赖本机 Redis 是否启动，也不会污染开发环境的 Redis 缓存"""
    from django.conf import settings
    from django.core.cache import caches

    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'testhub-pytest',
        }
    }
    # CacheHandler 会缓存首次读取的 CACHES 配置，这里清掉以便按新配置创建
    caches.__dict__.pop('settings', None)


# apps/ui_automation/test_executor.py 是 UI 自动化执行器的业务代码，只是文件名命中了
# test_*.py 规则，并不包含测试用例，收集时忽略以免产生无意义的 PytestCollectionWarning
collect_ignore = ['apps/ui_automation/test_executor.py']
