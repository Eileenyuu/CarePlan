"""
======================================
Celery 自动加载
======================================

这个文件确保 Django 启动时自动加载 Celery 应用。

工作原理：
- 当 Django 启动时，会自动执行这个 __init__.py
- 我们在这里导入 Celery 应用
- 这样 @shared_task 装饰器才能正常工作
"""

# 导入 Celery 应用，让 Django 启动时自动加载
from .celery import app as celery_app

# 声明这个模块导出的内容
# 其他模块可以通过 from careplan import celery_app 来导入
__all__ = ('celery_app',)
