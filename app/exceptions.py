"""
===============================================================================
统一异常处理系统 (Unified Exception Handling System)
===============================================================================

这个文件是整个错误处理的「中央控制室」。

核心设计理念：
--------------
1. 【关注点分离】
   - ValidationResult: 负责「收集」验证问题
   - ValidationException: 负责「传递」验证失败
   - custom_exception_handler: 负责「格式化」响应
   
2. 【为什么不直接 raise？】
   之前的设计：发现问题立即 raise → 用户只看到第一个错误
   新的设计：收集所有问题 → 用户一次看到所有错误
   
3. 【DRF 异常处理 vs Django 中间件】
   - 中间件：process_exception 在 view 之外，难以访问 request 上下文
   - DRF：exception_handler 是标准 REST API 处理方式，更专业

修改指南：
---------
Q: 我想添加新的错误类型？
A: 在 ValidationItem 的 code 字段添加新的错误代码常量

Q: 我想修改返回给前端的 JSON 格式？
A: 修改 ValidationResult.to_response_dict() 方法

Q: 我想添加新的异常类（如认证异常）？
A: 1. 创建新的 Exception 子类
   2. 在 custom_exception_handler 中添加处理逻辑

使用示例：
---------
    from app.exceptions import ValidationResult, ValidationException
    
    result = ValidationResult()
    result.add_error("DUPLICATE_NPI", "该 NPI 已被使用")
    result.add_warning("PATIENT_MISMATCH", "患者信息不一致")
    
    if result.has_errors:
        raise ValidationException(result)  # DRF 自动捕获并处理
"""

from __future__ import annotations  # 允许类型注解中使用尚未定义的类

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

# TYPE_CHECKING 是一个特殊常量，只在类型检查时为 True
# 这样可以避免循环导入，同时保持类型提示
if TYPE_CHECKING:
    from .models import Provider, Patient


# ============================================================================
# 第一部分：错误代码常量
# ============================================================================
# 
# 为什么要用常量？
# 1. 避免魔法字符串（typo 会导致 bug）
# 2. IDE 自动补全
# 3. 方便全局搜索和修改
# 
# 命名规则：{实体}_{问题类型}
# ============================================================================

class ErrorCodes:
    """
    错误代码常量类
    
    使用 class 而非 Enum 是因为：
    1. 更简单，不需要 .value 访问
    2. 这些只是字符串标识符，不需要 Enum 的完整功能
    
    【修改点】要添加新错误类型？在这里添加常量
    """
    # Provider 相关
    DUPLICATE_NPI_MISMATCH = "DUPLICATE_NPI_MISMATCH"
    
    # Patient 相关
    PATIENT_INFO_MISMATCH = "PATIENT_INFO_MISMATCH"
    POTENTIAL_DUPLICATE_PATIENT = "POTENTIAL_DUPLICATE_PATIENT"
    
    # Order 相关
    DUPLICATE_ORDER_SAME_DAY = "DUPLICATE_ORDER_SAME_DAY"
    EXISTING_MEDICATION_ORDER = "EXISTING_MEDICATION_ORDER"
    
    # 系统相关
    RATE_LIMIT = "RATE_LIMIT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ============================================================================
# 第二部分：验证结果数据类
# ============================================================================
#
# 【核心概念】ValidationResult 是一个「容器」：
# - 收集所有的 errors 和 warnings
# - 持有可复用的 Provider/Patient（如果找到了精确匹配）
# - 提供统一的 JSON 转换方法
#
# 【为什么用 @dataclass？】
# - 自动生成 __init__, __repr__, __eq__
# - 比手写 class 更简洁
# - field(default_factory=list) 避免可变默认参数陷阱
# ============================================================================

@dataclass
class ValidationItem:
    """
    单个验证问题
    
    Attributes:
        level: "error" 或 "warning"
               - error: 必须阻止操作（如 NPI 冲突）
               - warning: 可以继续但需确认（如 MRN 信息不匹配）
        code: 机器可读的错误代码（对应 ErrorCodes 中的常量）
              前端可以根据 code 做特定处理（如显示不同图标）
        message: 用户友好的错误消息
                 【安全要求】不能包含敏感信息：
                 - ❌ "NPI 12345 已存在"（暴露 NPI）
                 - ❌ "患者 John Doe 信息不匹配"（暴露姓名）
                 - ✅ "该 NPI 已被其他医疗提供者使用"
    """
    level: str
    code: str
    message: str


@dataclass
class ValidationResult:
    """
    验证结果收集器
    
    这是检测函数的返回值类型。它不抛异常，只收集问题。
    由调用者（view）决定是否抛出 ValidationException。
    
    使用流程：
    1. duplicate_detection.py 创建 ValidationResult
    2. 各 check 函数向其中添加 errors/warnings
    3. views.py 检查 has_errors / has_warnings
    4. 根据结果决定：抛异常、返回警告、或继续执行
    
    Attributes:
        items: 验证问题列表
        reusable_provider: 如果找到可复用的 Provider，存在这里
        reusable_patient: 如果找到可复用的 Patient，存在这里
    """
    items: list[ValidationItem] = field(default_factory=list)
    reusable_provider: "Provider | None" = None
    reusable_patient: "Patient | None" = None
    
    def add_error(self, code: str, message: str) -> None:
        """
        添加一个错误（必须阻止的问题）
        
        【调用时机】
        - NPI 相同但名字不同
        - 同一天重复下单同一药物
        
        Args:
            code: ErrorCodes 中的常量
            message: 用户友好消息（不含敏感信息）
        """
        self.items.append(ValidationItem(
            level="error",
            code=code,
            message=message
        ))
    
    def add_warning(self, code: str, message: str) -> None:
        """
        添加一个警告（可继续但需确认）
        
        【调用时机】
        - MRN 相同但信息不匹配
        - 同名同生日但 MRN 不同
        - 曾经下过同一药物的订单
        
        Args:
            code: ErrorCodes 中的常量
            message: 用户友好消息
        """
        self.items.append(ValidationItem(
            level="warning",
            code=code,
            message=message
        ))
    
    @property
    def has_errors(self) -> bool:
        """是否有错误（需要阻止操作）"""
        return any(item.level == "error" for item in self.items)
    
    @property
    def has_warnings(self) -> bool:
        """是否有警告（需要用户确认）"""
        return any(item.level == "warning" for item in self.items)
    
    @property
    def is_clean(self) -> bool:
        """验证完全通过（无错误无警告）"""
        return len(self.items) == 0
    
    def to_response_dict(self) -> dict:
        """
        转换为 API 响应格式
        
        【修改点】想要修改返回给前端的 JSON 格式？修改这个方法
        
        返回格式：
        {
            "success": false,
            "errors": [
                {"code": "DUPLICATE_NPI_MISMATCH", "message": "该 NPI 已被使用"}
            ],
            "warnings": [
                {"code": "PATIENT_INFO_MISMATCH", "message": "患者信息不一致"}
            ]
        }
        """
        errors = [
            {"code": item.code, "message": item.message}
            for item in self.items
            if item.level == "error"
        ]
        warnings = [
            {"code": item.code, "message": item.message}
            for item in self.items
            if item.level == "warning"
        ]
        
        return {
            "success": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }


# ============================================================================
# 第三部分：自定义异常类
# ============================================================================
#
# 【为什么要自定义异常？】
# 
# Python 内置的 Exception 太通用了，我们需要：
# 1. 携带结构化的错误数据（ValidationResult）
# 2. 定义对应的 HTTP 状态码
# 3. 让异常处理器能够识别并特殊处理
#
# 【继承结构】
# Exception (Python 内置)
#   └── ValidationException (验证失败，422)
#   └── RateLimitException (请求过多，429)
#
# 【为什么不继承 DRF 的 APIException？】
# APIException 有自己的格式约定，我们的 ValidationResult 格式不同。
# 自定义异常 + 自定义 handler 给我们完全的控制权。
# ============================================================================

class ValidationException(Exception):
    """
    验证失败异常
    
    当 ValidationResult 包含 errors 时抛出。
    DRF 的 exception_handler 会捕获并转换为 HTTP 响应。
    
    HTTP 状态码: 422 Unprocessable Entity
    （表示请求格式正确，但语义错误——比如重复的 NPI）
    
    使用示例：
        result = ValidationResult()
        result.add_error("DUPLICATE_NPI", "NPI 已存在")
        
        if result.has_errors:
            raise ValidationException(result)  # DRF 自动处理
    """
    
    # HTTP 状态码
    # 422 表示"请求格式正确，但无法处理"
    # 比 400 更精确（400 通常指格式错误）
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def __init__(self, validation_result: ValidationResult):
        """
        Args:
            validation_result: 包含所有验证问题的结果对象
        """
        self.validation_result = validation_result
        # 调用父类初始化，设置异常消息（用于日志）
        super().__init__("Validation failed")


class RateLimitException(Exception):
    """
    限流异常
    
    当请求频率超过限制时抛出。
    
    HTTP 状态码: 429 Too Many Requests
    
    【安全设计】
    错误消息是固定的，不会泄露：
    - 具体的限流阈值
    - 重置时间
    - 用户的请求计数
    """
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    
    # 默认消息，不含任何敏感信息
    default_message = "请求过于频繁，请稍后再试"
    
    def __init__(self, message: str | None = None):
        """
        Args:
            message: 可选的自定义消息，默认使用 default_message
        """
        self.message = message or self.default_message
        super().__init__(self.message)


# ============================================================================
# 第四部分：DRF 异常处理器
# ============================================================================
#
# 【工作原理】
# 
# 当 DRF 的 @api_view 装饰的 view 抛出异常时：
#   1. DRF 捕获异常
#   2. 查找 settings.py 中配置的 EXCEPTION_HANDLER
#   3. 调用我们的 custom_exception_handler
#   4. 我们返回 Response，DRF 发送给客户端
#
# 【为什么比中间件更好？】
# 
# 中间件 (process_exception):
#   - 在 view 之外执行，难以访问 DRF 的 Request 对象
#   - 返回 HttpResponse，不是 DRF 的 Response
#   - 不是 REST API 的标准做法
#
# DRF Exception Handler:
#   - REST API 的标准处理方式
#   - 可以访问 context（包含 view、request 等）
#   - 返回 DRF Response，自动处理内容协商
#
# 【Error vs Warning 的处理区别】
#
# Error（错误）:
#   - HTTP 422 状态码
#   - success: false
#   - 前端收到后停止提交，显示错误
#
# Warning（警告）:
#   - 由 view 直接返回，不抛异常
#   - HTTP 200 状态码 + requires_confirmation: true
#   - 前端显示确认对话框，用户确认后带 confirm=true 重新提交
# ============================================================================

def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    DRF 自定义异常处理器
    
    【配置位置】settings.py -> REST_FRAMEWORK -> EXCEPTION_HANDLER
    
    Args:
        exc: 抛出的异常对象
        context: 上下文信息，包含：
                 - view: 抛出异常的 view 函数/类
                 - request: DRF 的 Request 对象
                 - args, kwargs: view 的参数
    
    Returns:
        Response: DRF 响应对象
        None: 返回 None 表示不处理，让异常继续传播（会变成 500）
    
    【修改点】要添加新类型的异常处理？在这里添加 elif 分支
    """
    
    # ========== 处理验证异常 ==========
    # 这是最常见的情况：重复检测发现问题
    if isinstance(exc, ValidationException):
        return Response(
            exc.validation_result.to_response_dict(),
            status=exc.status_code
        )
    
    # ========== 处理限流异常 ==========
    if isinstance(exc, RateLimitException):
        return Response(
            {
                "success": False,
                "errors": [{
                    "code": ErrorCodes.RATE_LIMIT,
                    "message": exc.message
                }],
                "warnings": []
            },
            status=exc.status_code
        )
    
    # ========== 处理 DRF 内置异常 ==========
    # 调用 DRF 默认的异常处理器
    # 它会处理：AuthenticationFailed, NotAuthenticated, PermissionDenied 等
    response = exception_handler(exc, context)
    
    if response is not None:
        # DRF 处理了这个异常，统一格式后返回
        return Response(
            {
                "success": False,
                "errors": [{
                    "code": "API_ERROR",
                    "message": str(exc)
                }],
                "warnings": []
            },
            status=response.status_code
        )
    
    # ========== 未处理的异常 → 返回通用错误 ==========
    # 【安全关键】
    # 不能把真实错误信息返回给前端，可能包含：
    # - 数据库连接字符串
    # - SQL 语句
    # - 文件路径
    # - 堆栈跟踪
    # 
    # 正确做法：
    # 1. 返回通用消息给前端
    # 2. 在服务器日志中记录详细错误（TODO: 添加日志）
    return Response(
        {
            "success": False,
            "errors": [{
                "code": ErrorCodes.INTERNAL_ERROR,
                "message": "服务暂时不可用，请稍后重试"
            }],
            "warnings": []
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


# ============================================================================
# 附录：模块结构总结
# ============================================================================
#
# exceptions.py（本文件）
# ├── ErrorCodes          # 错误代码常量
# ├── ValidationItem      # 单个验证问题
# ├── ValidationResult    # 验证结果收集器
# ├── ValidationException # 验证失败异常
# ├── RateLimitException  # 限流异常
# └── custom_exception_handler  # DRF 异常处理器
#
# 【依赖关系】
# duplicate_detection.py → 使用 ValidationResult, ErrorCodes
# views.py → 使用 ValidationException, RateLimitException
# settings.py → 配置 custom_exception_handler
#
# 【修改清单】
# | 需求                     | 修改位置                    |
# |--------------------------|----------------------------|
# | 添加新错误代码            | ErrorCodes 类               |
# | 修改返回 JSON 格式        | ValidationResult.to_response_dict |
# | 添加新异常类型            | 新建 Exception 子类 + handler |
# | 修改 HTTP 状态码          | Exception.status_code      |
# ============================================================================
