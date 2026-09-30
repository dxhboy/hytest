# https://newpanjing.github.io/simpleui_docs/config.html#%E5%9B%BE%E6%A0%87%E8%AF%B4%E6%98%8E

from pathlib import Path
from decouple import config
import os

BASE_DIR = Path(__file__).resolve().parent.parent

from django.core.exceptions import ImproperlyConfigured

# 默认关闭 DEBUG：漏配 .env 时按生产环境处理，而不是暴露调试信息
DEBUG = config('DEBUG', default=False, cast=bool)

# SECRET_KEY 同时用于 JWT 签名和 Jira token 加密，生产环境必须显式配置强密钥
_INSECURE_SECRET_KEYS = {
    '',
    'django-insecure-your-secret-key-here',
    'your-secret-key-here-change-in-production',
}
SECRET_KEY = config('SECRET_KEY', default='')
if SECRET_KEY in _INSECURE_SECRET_KEYS:
    if not DEBUG:
        raise ImproperlyConfigured(
            'SECRET_KEY 未配置或仍为示例值。生产环境（DEBUG=False）请在 .env 中设置强随机密钥，'
            '可用 python -c "from django.core.management.utils import get_random_secret_key; '
            'print(get_random_secret_key())" 生成。'
        )
    SECRET_KEY = 'django-insecure-dev-only-key'

# 根据DEBUG模式设置ALLOWED_HOSTS，生产环境不应使用通配符
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1',
                           cast=lambda v: [s.strip() for s in v.split(',')])

DJANGO_APPS = [
    'daphne',  # 必须在 django.contrib.staticfiles 之前声明（Channels 要求）
    'simpleui',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'channels',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',  # 添加JWT支持
    'rest_framework_simplejwt.token_blacklist',  # JWT token黑名单
    'corsheaders',
    'django_filters',
    'drf_spectacular',
]

LOCAL_APPS = [
    'apps.users',
    'apps.projects',
    'apps.testcases',
    'apps.testsuites',
    'apps.executions',
    'apps.reports',
    'apps.reviews',
    'apps.versions',
    'apps.assistant',
    'apps.requirement_analysis',
    'apps.api_testing',
    'apps.ui_automation.apps.UiAutomationConfig',
    'apps.core',
    'apps.data_factory',
    'apps.ai_assistant',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 不再全局豁免 /api/ 的 CSRF：DRF 视图本身已 csrf_exempt，JWT/Token 请求不受影响；
    # 只有基于 Session 的请求会由 SessionAuthentication 强制校验 CSRF，防止跨站请求伪造
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default='testhub'),
        'USER': config('DB_USER', default='root'),
        'PASSWORD': config('DB_PASSWORD', default=''),  # 移除硬编码默认密码
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        # 持久连接：连接在请求间复用 CONN_MAX_AGE 秒（0 表示每个请求结束即关闭），
        # 配合 CONN_HEALTH_CHECKS 在复用前检测连接是否可用，避免 MySQL wait_timeout 断开后报错
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
        'CONN_HEALTH_CHECKS': True,
        # 并行运行多组测试时可通过 DB_TEST_NAME 指定不同的测试库，避免互相覆盖
        'TEST': {
            'NAME': config('DB_TEST_NAME', default=None),
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
# Supported language codes: 'en-us' (English), 'zh-hans' (Simplified Chinese), 'ja' (Japanese), 'ko' (Korean), etc.
# See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones for timezone list
LANGUAGE_CODE = config('LANGUAGE_CODE', default='zh-hans')
TIME_ZONE = config('TIME_ZONE', default='Asia/Shanghai')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static_files')

# 数据工厂的静态文件目录
STATIC_FILES_URL = '/static_files/'
STATIC_FILES_ROOT = os.path.join(BASE_DIR, 'static_files')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
# 是否由 Django 直接提供 /media/ 下的文件（Allure 报告、截图、录屏等）。
# 默认开启以兼容现有的非 Docker 部署；生产环境建议由 nginx 直接托管 /media/ 并设为 False。
SERVE_MEDIA = config('SERVE_MEDIA', default=True, cast=bool)

# 接口请求断言变更时，是否自动同步到原样复制了这组断言的测试套件步骤（见 apps/api_testing/signals.py）
API_SUITE_ASSERTION_SYNC = config('API_SUITE_ASSERTION_SYNC', default=True, cast=bool)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# DRF Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # JWT认证（优先）
        'rest_framework.authentication.TokenAuthentication',  # 保留Token认证（兼容）
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# JWT Settings
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),  # access_token 60分钟
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),  # refresh_token 7天
    'ROTATE_REFRESH_TOKENS': True,  # 刷新时轮换refresh_token
    'BLACKLIST_AFTER_ROTATION': True,  # 旧的refresh_token加入黑名单
    'UPDATE_LAST_LOGIN': True,  # 更新最后登录时间

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# CSRF Settings - 根据DEBUG模式设置
if DEBUG:
    CSRF_COOKIE_SECURE = False
    CSRF_USE_SESSIONS = False
    CSRF_COOKIE_HTTPONLY = False
    CSRF_COOKIE_SAMESITE = 'Lax'
else:
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = 'Strict'

# CORS Settings
cors_origins_str = config('CORS_ALLOWED_ORIGINS', default='')
parsed_cors_origins = [s.strip() for s in cors_origins_str.split(',') if s.strip()]

if DEBUG:
    # 开发环境默认允许本地地址，同时合并环境变量里的配置
    # 优先使用环境变量配置的地址，确保服务器IP优先级最高
    CORS_ALLOWED_ORIGINS = [
        *parsed_cors_origins,  # 环境变量配置的地址优先
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    CORS_ALLOW_CREDENTIALS = True
    # 支持EventSource (SSE) 的额外CORS头部
    CORS_ALLOW_HEADERS = [
        'accept',
        'accept-encoding',
        'authorization',
        'content-type',
        'dnt',
        'origin',
        'user-agent',
        'x-csrftoken',
        'x-requested-with',
        'cache-control',  # 添加 SSE 需要的头部
    ]
else:
    # 生产环境 CORS 配置
    if parsed_cors_origins:
        # 如果配置了 CORS_ALLOWED_ORIGINS，使用配置的值
        CORS_ALLOWED_ORIGINS = parsed_cors_origins
    else:
        import warnings
        warnings.warn(
            "CORS_ALLOWED_ORIGINS is empty in production. "
            "Set CORS_ALLOWED_ORIGINS in .env to allow cross-origin requests.",
            stacklevel=1,
        )
        CORS_ALLOWED_ORIGINS = []

    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_HEADERS = [
        'accept',
        'accept-encoding',
        'authorization',
        'content-type',
        'dnt',
        'origin',
        'user-agent',
        'x-csrftoken',
        'x-requested-with',
        'cache-control',  # 添加 SSE 需要的头部
    ]
    # SSE 需要的额外配置
    CORS_EXPOSE_HEADERS = ['Content-Type', 'Cache-Control']

# CSRF Settings
# CSRF_TRUSTED_ORIGINS 环境变量（逗号分隔，需带协议，如 https://testhub.example.com）；
# DEBUG 模式下额外合并本地开发地址
_csrf_origins_str = config('CSRF_TRUSTED_ORIGINS', default='')
CSRF_TRUSTED_ORIGINS = [s.strip() for s in _csrf_origins_str.split(',') if s.strip()]
if DEBUG:
    for _origin in (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ):
        if _origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_origin)

# Site Base URL (for notification report links)
SITE_BASE_URL = config('SITE_BASE_URL', default='http://localhost:3000')

# Spectacular Settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'TestHub API',
    'DESCRIPTION': 'AI 驱动的测试管理平台 API 文档',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
        'backend.schema_hooks.auto_tag_hook',
    ],
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
    },
}

# Celery Configuration
# 注意：以前这里默认值写的是 'redis://:127.0.0.1:6379/0'——按 redis URL 的格式，
# 冒号后面应该是密码而不是主机地址，这个默认值本身解析就会报错
# ("Port could not be cast to integer value as '127.0.0.1:6379'")。
# 因为重构前没有任何 Celery task，这个 bug 一直是"死代码"式的存在，没人发现；
# 现在 apps/ui_automation/tasks.py 里的执行路径都依赖 Celery，这行配置必须是
# 一个能正常解析的 URL，否则 worker 连不上 broker、.delay() 提交时也会直接抛异常。
# 部署时建议通过环境变量 REDIS_URL 显式配置（连接串格式：redis://[:password@]host:port/db）。
CELERY_BROKER_URL = config('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://127.0.0.1:6379/0')

# Celery 可靠性配置：
# - task_time_limit：单个任务硬超时（秒），防止浏览器操作卡死（比如等一个永远不出现
#   的元素）导致这个任务永远占着 worker 的一个并发槽位，把整个 worker 的并发耗尽。
# - task_soft_time_limit：软超时，先给任务一个可以自己捕获、做清理（比如关闭浏览器）
#   的机会，硬超时到了才强制杀掉。
# - worker_prefetch_multiplier=1 + task_acks_late=True：任务先执行、成功后才 ack，
#   这样如果 worker 进程被杀（比如内存超限被 OOM kill——浏览器自动化对内存不算友好，
#   是比较常见的场景），未完成的任务会被重新投递给其他 worker，而不是直接丢失。
#   代价是任务需要保证幂等或至少"重复执行不会产生更差的后果"，UI 自动化执行本身
#   是幂等的（重新跑一次用例不会有副作用累加），可以接受。
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 分钟硬超时
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 分钟软超时
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TIMEZONE = TIME_ZONE

# 任务路由：AI 智能模式任务固定进入 ai_automation 队列（由单并发的 solo worker 消费，
# 受 GIF 录制文件名限制不能并发）。tasks.py 装饰器上也声明了 queue，这里集中显式配置，
# 避免通过 send_task / apply_async 等方式投递时漏掉队列参数而落入默认队列。
CELERY_TASK_ROUTES = {
    'ui_automation.run_ai_case': {'queue': 'ai_automation'},
    'ui_automation.run_ai_adhoc': {'queue': 'ai_automation'},
}

# 所有模块的定时任务统一由 Celery Beat 触发（启动：celery -A backend beat）。
# 各 dispatch 任务通过条件更新抢占到期任务，即使 Beat 与 run_all_scheduled_tasks 命令并存也不会重复执行。
CELERY_BEAT_SCHEDULE = {
    'api-testing-dispatch-due-tasks': {
        'task': 'api_testing.dispatch_due_tasks',
        'schedule': 60.0,
    },
    'ui-automation-dispatch-due-tasks': {
        'task': 'ui_automation.dispatch_due_tasks',
        'schedule': 60.0,
    },
    'requirement-analysis-dispatch-due-generation-tasks': {
        'task': 'requirement_analysis.dispatch_due_generation_tasks',
        'schedule': 60.0,
    },
}

# Cache Configuration
# 配置了 Redis 时使用 Django 内置的 RedisCache，多进程（uvicorn workers / Celery）共享缓存与限流计数；
# 未配置时回退到进程内的 LocMemCache（仅适合单进程开发）。
# CACHE_REDIS_URL 默认沿用 REDIS_URL，并通过 KEY_PREFIX 与 Celery broker/结果的键隔离；
# 也可以单独指定另一个 DB（如 redis://127.0.0.1:6379/1）。
_cache_redis_url = config('CACHE_REDIS_URL', default=config('REDIS_URL', default=''))
if _cache_redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _cache_redis_url,
            'KEY_PREFIX': 'testhub',
            'TIMEOUT': 300,  # 默认缓存超时5分钟
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
            'TIMEOUT': 300,  # 默认缓存超时5分钟
        }
    }

# Email Configuration
EMAIL_BACKEND = 'apps.api_testing.custom_email_backend.CustomEmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='webmaster@localhost')

# For 163 email with SSL, you might need this setting
EMAIL_TIMEOUT = 30

# 确保日志目录存在
log_dir = os.path.join(BASE_DIR, 'logs')
os.makedirs(log_dir, exist_ok=True)

# 日志级别（DEBUG/INFO/WARNING/ERROR），控制台和 app.log 共用；error.log 固定只记录 ERROR 及以上
LOG_LEVEL = config('LOG_LEVEL', default='INFO').upper()
# 单个日志文件最大字节数及保留的历史文件个数（按大小滚动，避免日志文件无限增长）
LOG_FILE_MAX_BYTES = config('LOG_FILE_MAX_BYTES', default=10 * 1024 * 1024, cast=int)
LOG_FILE_BACKUP_COUNT = config('LOG_FILE_BACKUP_COUNT', default=5, cast=int)

import time as _time
from logging.handlers import RotatingFileHandler as _RotatingFileHandler


class _SafeRotatingFileHandler(_RotatingFileHandler):
    """按大小滚动的文件日志，滚动失败时继续写原文件。

    Windows 下 uvicorn、Celery worker/beat 等多个进程同时打开同一个日志文件，
    滚动时重命名会因文件被占用失败；标准 RotatingFileHandler 会在之后每条日志都
    重试并打印异常堆栈。这里失败后继续追加写原文件，并在 60 秒内不再重试滚动。
    """

    _retry_interval = 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rollover_blocked_until = 0.0

    def shouldRollover(self, record):
        if _time.monotonic() < self._rollover_blocked_until:
            return False
        return super().shouldRollover(record)

    def doRollover(self):
        try:
            super().doRollover()
        except OSError:
            self._rollover_blocked_until = _time.monotonic() + self._retry_interval
            if self.stream is None:
                self.stream = self._open()

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        # 文件日志按大小滚动（默认 10MB x 5 份），多进程并发写入时滚动失败会自动跳过，见 _SafeRotatingFileHandler
        'file': {
            'level': LOG_LEVEL,
            '()': _SafeRotatingFileHandler,
            'filename': os.path.join(BASE_DIR, 'logs', 'app.log'),
            'maxBytes': LOG_FILE_MAX_BYTES,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            '()': _SafeRotatingFileHandler,
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
            'maxBytes': LOG_FILE_MAX_BYTES,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
        'console': {
            'level': LOG_LEVEL,
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # 其他具体模块的 logger 配置
        'django': {
            'handlers': ['file', 'error_file', 'console'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
        'apps.api_testing.views': {
            'handlers': ['file', 'error_file', 'console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        # 通知、报告、请求执行等逻辑从 views 拆到 services 后沿用同一日志配置
        'apps.api_testing.services': {
            'handlers': ['file', 'error_file', 'console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.data_factory.tools.json_tools': {
            'handlers': ['file', 'error_file', 'console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.data_factory.tools.encoding_tools': {
            'handlers': ['file', 'error_file', 'console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps.data_factory.tools': {
            'handlers': ['file', 'error_file', 'console'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
    },
    'root': {
        'handlers': ['file', 'error_file', 'console'],
        'level': LOG_LEVEL,
        # 'propagate': True,
    },
}

# 指定simpleui默认的主题,指定一个文件名，相对路径就从simpleui的theme目录读取
SIMPLEUI_DEFAULT_THEME = 'admin.lte.css'
# 是否显示图标
SIMPLEUI_DEFAULT_ICON = True
# 是否关闭登录页粒子效果
SIMPLEUI_LOGIN_PARTICLES = True
# 后台管理首页，可以是url或者html文件
# SIMPLEUI_HOME_PAGE = 'https://www.baidu.com/'  # 后面可以扩展为大屏显示做统计
# 自定义首页标题
# SIMPLEUI_HOME_TITLE = 'Dashboard'
# # 自定义首页图标 首页图标,支持element-ui和fontawesome的图标，参考https://fontawesome.com/icons图标
# SIMPLEUI_HOME_ICON = 'fa fa-gauge'
# 设置simpleui 点击首页图标跳转的地址
SIMPLEUI_INDEX = config('SIMPLEUI_INDEX', default=SITE_BASE_URL)
# 自定义后台的Logo
SIMPLEUI_LOGO = 'https://static.djangoproject.com/img/favicon.6dbf28c0650e.ico'
# 是否显示首页信息
SIMPLEUI_HOME_INFO = False
# 是否显示快捷入口
SIMPLEUI_HOME_QUICK = True
# 是否显示最近动作
SIMPLEUI_HOME_ACTION = True
# 使用分析
SIMPLEUI_ANALYSIS = False
# 离线模式
SIMPLEUI_STATIC_OFFLINE = True
# True或None 默认显示加载遮罩层，指定为False 不显示遮罩层。默认显示
SIMPLEUI_LOADING = True
# 设置菜单icon，参考https://element.eleme.cn/#/zh-CN/component/icon
SIMPLEUI_ICON = {
    # 一级菜单项
    '测试执行管理': 'el-icon-s-tools',
    '用户管理': 'el-icon-user-solid',
    '令牌黑名单': 'el-icon-warning-outline',
    '接口测试': 'el-icon-s-platform',
    '智能助手': 'el-icon-chat-dot-round',
    '用例评审管理': 'el-icon-edit-outline',
    '认证令牌': 'el-icon-key',
    '认证和授权': 'el-icon-s-check',
    '需求分析': 'el-icon-notebook-2',

    # 二级菜单项
    '测试执行': 'el-icon-s-operation',
    '测试执行历史': 'el-icon-time',
    '测试执行用例': 'el-icon-document',
    '测试计划': 'el-icon-document-checked',
    '用户': 'el-icon-user',
    '用户配置': 'el-icon-setting',
    'Blacklisted Tokens': 'el-icon-warning-outline',
    'Outstanding Tokens': 'el-icon-s-custom',
    'API请求': 'el-icon-s-promotion',
    'API集合': 'el-icon-s-grid',
    'API项目': 'el-icon-s-custom',
    '任务执行日志': 'el-icon-s-data',
    '定时任务': 'el-icon-time',
    '测试套件': 'el-icon-suitcase',
    '环境变量': 'el-icon-school',
    '请求历史': 'el-icon-odometer',
    '智能助手会话': 'el-icon-chat-dot-round',
    '智能助手消息': 'el-icon-message',
    '测试用例评审': 'el-icon-check',
    '评审分配': 'el-icon-guide',
    '评审意见': 'el-icon-s-custom',
    '评审模板': 'el-icon-document',
    'Tokens': 'el-icon-key',
    '组': 'el-icon-s-custom',
    '业务需求': 'el-icon-document-checked',
    '分析任务': 'el-icon-stopwatch',
    '生成的测试用例': 'el-icon-document',
    '需求文档': 'el-icon-document',
}

# 开发环境，暂时禁用迁移历史检查
# SILENCED_SYSTEM_CHECKS = ['django.db.migrations.InconsistentMigrationHistory']

import base64
import hashlib as _hashlib
# 从 SECRET_KEY 派生 32 字节 Fernet 密钥
_jira_raw = _hashlib.sha256(SECRET_KEY.encode()).digest()
JIRA_TOKEN_ENCRYPT_KEY = base64.urlsafe_b64encode(_jira_raw)

# ---------- Django Channels (WebSocket) ----------
ASGI_APPLICATION = 'backend.asgi.application'
_redis_url = config('REDIS_URL', default='')
try:
    import channels_redis  # noqa: F401
    _has_channels_redis = True
except ImportError:
    _has_channels_redis = False
# 多进程部署需要 Redis 通道层（pip install channels-redis），否则跨进程/Celery 的 WebSocket 推送会丢失
if _redis_url and _has_channels_redis:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [_redis_url],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
