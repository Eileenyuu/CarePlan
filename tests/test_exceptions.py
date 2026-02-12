"""
======================================
Error Tests: 异常系统验证
======================================

这是 ERROR TEST（异常系统测试）。
- 测试的不是业务逻辑，而是"报错基础设施"本身
- 确保 exceptions.py 的异常类格式正确
- 确保 middleware.py 能正确捕获异常并转为统一 JSON 响应
- 如果这些测试失败，说明所有异常处理都有问题

与 Unit Test 的区别：
- Unit Test 测 "什么时候报错"（业务逻辑）
- Error Test 测 "报错的格式和管道对不对"（基础设施）
"""

import pytest
import json
from django.test import RequestFactory
from django.http import JsonResponse
from rest_framework.exceptions import ValidationError as DRFValidationError

from app.exceptions import ValidationError, BlockError, WarningException
from app.middleware import ExceptionHandlerMiddleware


# ============================================
# 异常类格式测试（不需要数据库）
# ============================================

class TestExceptionFormat:
    """测试异常类的 to_dict() 输出格式"""

    def test_block_error_to_dict(self):
        """测试 1: BlockError.to_dict() 格式是否正确"""
        error = BlockError(
            code="NPI_NAME_CONFLICT",
            message="NPI already exists",
            detail={"npi": "1234567890"}
        )
        result = error.to_dict()
        
        # 验证所有字段都存在且格式正确
        assert result["type"] == "BLOCK_ERROR"
        assert result["code"] == "NPI_NAME_CONFLICT"
        assert result["message"] == "NPI already exists"
        assert result["detail"]["npi"] == "1234567890"

    def test_warning_exception_to_dict(self):
        """测试 2: WarningException.to_dict() 格式是否正确"""
        error = WarningException(
            code="MRN_INFO_MISMATCH",
            message="Patient info mismatch",
            detail={"mrn": "123456"}
        )
        result = error.to_dict()
        
        assert result["type"] == "WARNING"
        assert result["code"] == "MRN_INFO_MISMATCH"

    def test_validation_error_to_dict(self):
        """测试 3: 自定义 ValidationError.to_dict() 格式是否正确"""
        error = ValidationError(
            code="INVALID_FORMAT",
            message="Input validation failed"
        )
        result = error.to_dict()
        
        assert result["type"] == "VALIDATION_ERROR"
        assert result["code"] == "INVALID_FORMAT"
        # detail 没传时默认为空 dict
        assert result["detail"] == {}

    def test_http_status_codes(self):
        """验证每种异常对应的 HTTP 状态码"""
        assert ValidationError.http_status == 400
        assert BlockError.http_status == 409
        assert WarningException.http_status == 200


# ============================================
# 中间件处理测试（模拟异常 → 验证 JSON 响应）
# ============================================

class TestMiddlewareHandling:
    """
    测试中间件能否正确捕获异常并转为统一 JSON 响应。

    原理：
    1. 创建一个 "假 view"，让它 raise 指定的异常
    2. 把这个 "假 view" 传给中间件
    3. 中间件捕获异常后返回 JsonResponse
    4. 验证返回的 JSON 格式和 HTTP 状态码
    """

    def _get_middleware(self, exception_to_raise):
        """
        辅助函数：创建一个会抛出指定异常的中间件实例
        
        中间件的 process_exception 方法需要 request 和 exception 参数。
        """
        middleware = ExceptionHandlerMiddleware(get_response=lambda r: None)
        factory = RequestFactory()
        request = factory.get("/fake-url/")
        return middleware.process_exception(request, exception_to_raise)

    def test_middleware_handles_block_error(self):
        """测试 4: 中间件处理 BlockError → 409 + 统一 JSON"""
        error = BlockError(
            code="NPI_NAME_CONFLICT",
            message="NPI already exists"
        )
        response = self._get_middleware(error)
        
        # 验证 HTTP 状态码
        assert response.status_code == 409
        
        # 验证 JSON 格式
        data = json.loads(response.content)
        assert data["success"] is False
        assert data["error"]["type"] == "BLOCK_ERROR"
        assert data["error"]["code"] == "NPI_NAME_CONFLICT"

    def test_middleware_handles_warning_exception(self):
        """测试 5: 中间件处理 WarningException → 200 + warnings + requires_confirmation"""
        error = WarningException(
            code="MRN_INFO_MISMATCH",
            message="Patient info mismatch"
        )
        response = self._get_middleware(error)
        
        # WarningException 返回 200（不是错误，是警告）
        assert response.status_code == 200
        
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["requires_confirmation"] is True
        assert len(data["warnings"]) == 1
        assert data["warnings"][0]["code"] == "MRN_INFO_MISMATCH"

    def test_middleware_handles_drf_validation_error(self):
        """测试 6: 中间件处理 DRF ValidationError → 400 + VALIDATION_ERROR"""
        error = DRFValidationError({"patient_mrn": ["This field is required."]})
        response = self._get_middleware(error)
        
        assert response.status_code == 400
        
        data = json.loads(response.content)
        assert data["success"] is False
        assert data["error"]["type"] == "VALIDATION_ERROR"
        assert data["error"]["code"] == "FIELD_VALIDATION_FAILED"
