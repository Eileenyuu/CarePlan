"""
===============================================================================
Django 项目配置 (Settings)
===============================================================================

【DRF 配置说明】
--------------
关键配置是 REST_FRAMEWORK 字典中的 EXCEPTION_HANDLER：
- 指向 app.exceptions.custom_exception_handler
- DRF 会自动调用这个函数处理所有 API 视图中的异常

【为什么移除了中间件？】
--------------------
旧配置用 ExceptionHandlerMiddleware 处理异常：
- 中间件在 Django 层面工作，难以和 DRF 完美配合
- 返回 HttpResponse，不是 DRF 的 Response

新配置用 DRF 的 exception_handler：
- 是 REST API 的标准做法
- 可以访问更多上下文信息
- 和 DRF 的其他功能无缝集成
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'dev-secret-key-change-in-production'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    # ========== DRF ==========
    # Django Rest Framework - REST API 标准库
    # 提供：@api_view, Response, exception_handler 等
    'rest_framework',
    'app',
]

# ========== 中间件配置 ==========
# 【变更】移除了 ExceptionHandlerMiddleware
# 异常处理现在由 DRF 的 exception_handler 负责
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'careplan.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
    ]},
}]

WSGI_APPLICATION = 'careplan.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'careplan'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.getenv('POSTGRES_HOST', 'db'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}

# ========== 缓存配置（用于限流 + Redis 队列） ==========
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/0",
    }
}

# ========== Redis 配置（用于队列） ==========
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = 0

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ========== Celery 配置 ==========
CELERY_BROKER_URL = f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/1"
CELERY_RESULT_BACKEND = f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/2"
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE
CELERY_RESULT_EXPIRES = 3600


# ============================================================================
# Django Rest Framework 配置
# ============================================================================
#
# 【核心配置】EXCEPTION_HANDLER
# -----------------------------
# 当 @api_view 装饰的视图抛出异常时：
#   1. DRF 捕获异常
#   2. 查找这里配置的 EXCEPTION_HANDLER
#   3. 调用 app.exceptions.custom_exception_handler
#   4. 该函数返回 Response 对象
#   5. DRF 将 Response 发送给客户端
#
# 【其他配置说明】
# DEFAULT_RENDERER_CLASSES: 默认只返回 JSON（不支持 HTML）
# DEFAULT_PARSER_CLASSES: 支持 JSON 和 Form 数据解析
#
# ============================================================================

REST_FRAMEWORK = {
    # 异常处理器：指向 app/exceptions.py 中的 custom_exception_handler
    # 这是整个错误处理系统的「入口点」
    'EXCEPTION_HANDLER': 'app.exceptions.custom_exception_handler',
    
    # 只返回 JSON 格式（API 专用）
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    
    # 支持 JSON 和 Form 数据
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
}
