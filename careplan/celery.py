"""
======================================
Celery 应用配置
======================================

这个文件是 Celery 的入口配置文件。
Celery 需要知道：
1. 使用什么消息代理（Broker）- 我们用 Redis
2. Django 的设置在哪里
3. 去哪里找任务（tasks）

文件位置说明：
- 这个文件必须放在 Django 项目的配置目录下（和 settings.py 同级）
- 文件名必须是 celery.py
"""

import os
from celery import Celery

# ============================================
# 步骤 1: 设置 Django 环境变量
# ============================================
# 告诉 Celery 去哪里找 Django 的设置
# 这必须在创建 Celery 应用之前设置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'careplan.settings')

# ============================================
# 步骤 2: 创建 Celery 应用实例
# ============================================
# 'careplan' 是应用的名称，通常用项目名
# 这个名称会出现在日志和监控中
app = Celery('careplan')

# ============================================
# 步骤 3: 从 Django settings 加载配置
# ============================================
# namespace='CELERY' 表示所有 Celery 相关的配置
# 都以 CELERY_ 开头，例如：CELERY_BROKER_URL
app.config_from_object('django.conf:settings', namespace='CELERY')

# ============================================
# 步骤 4: 自动发现任务
# ============================================
# Celery 会自动扫描所有 INSTALLED_APPS 中的 tasks.py 文件
# 找到用 @app.task 装饰的函数
app.autodiscover_tasks()


# ============================================
# 步骤 5: 调试任务（可选）
# ============================================
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """
    一个简单的调试任务，用于测试 Celery 是否正常工作
    
    bind=True: 让任务可以访问 self（任务实例）
    ignore_result=True: 不保存任务结果（节省资源）
    
    使用方式：
        from careplan.celery import debug_task
        debug_task.delay()
    """
    print(f'Request: {self.request!r}')
