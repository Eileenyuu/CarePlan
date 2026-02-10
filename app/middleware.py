"""
======================================
统一异常处理中间件
======================================

捕获所有 BaseAppException 和 DRF ValidationError，
统一转成 JSON 响应。View 里只需 raise，不用关心返回格式。

格式统一在这一个地方控制，要改格式只改这里。
"""

from django.http import JsonResponse
from rest_framework.exceptions import ValidationError as DRFValidationError
from .exceptions import BaseAppException, WarningException


class ExceptionHandlerMiddleware:
    """
    Django 中间件：统一异常 → JSON 响应

    处理顺序：
    1. DRF ValidationError（Serializer 验证失败抛出）→ 400
    2. WarningException → 200 + warnings + requires_confirmation
    3. 其他 BaseAppException（ValidationError, BlockError）→ 对应状态码
    4. 非自定义异常 → 交给 Django 默认处理
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # 1. DRF ValidationError（Serializer 抛出的）
        if isinstance(exception, DRFValidationError):
            return JsonResponse({
                "success": False,
                "error": {
                    "type": "VALIDATION_ERROR",
                    "code": "FIELD_VALIDATION_FAILED",
                    "message": "Input validation failed",
                    "detail": exception.detail,
                }
            }, status=400)

        # 2. 自定义异常
        if isinstance(exception, BaseAppException):
            # 警告：返回 200，但带 warnings 字段和 requires_confirmation
            if isinstance(exception, WarningException):
                return JsonResponse({
                    "success": True,
                    "data": None,
                    "warnings": [exception.to_dict()],
                    "requires_confirmation": True,
                }, status=200)
            # 错误（ValidationError / BlockError）：返回对应状态码
            else:
                return JsonResponse({
                    "success": False,
                    "error": exception.to_dict(),
                }, status=exception.http_status)

        # 3. 其他异常 → 交给 Django 默认处理
        return None
