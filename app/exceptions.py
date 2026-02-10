"""
======================================
统一异常类
======================================

所有自定义异常继承 BaseAppException。
中间件（middleware.py）捕获后统一转成 JSON 响应。

异常类型：
- ValidationError: 输入格式验证失败 → 400
- BlockError: 业务规则阻止 → 409
- WarningException: 业务警告，可确认跳过 → 200 + warnings
"""


class BaseAppException(Exception):
    """
    统一异常基类

    类属性（子类覆盖）:
        type: 错误类型字符串，如 "BLOCK_ERROR"
        http_status: HTTP 状态码

    实例属性（每次 raise 时传入）:
        code: 错误代码，如 "NPI_NAME_CONFLICT"
        message: 用户友好的错误信息
        detail: 额外详情字典
    """
    type = "ERROR"
    http_status = 500

    def __init__(self, code, message, detail=None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)

    def to_dict(self):
        return {
            "type": self.type,
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
        }


class ValidationError(BaseAppException):
    """验证错误：用户输入格式不对（NPI不是10位、MRN不是6位等）"""
    type = "VALIDATION_ERROR"
    http_status = 400


class BlockError(BaseAppException):
    """业务阻止：业务规则不允许，无法通过 confirm 跳过"""
    type = "BLOCK_ERROR"
    http_status = 409


class WarningException(BaseAppException):
    """业务警告：可能有问题但允许用户确认后继续"""
    type = "WARNING"
    http_status = 200
