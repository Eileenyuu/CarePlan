"""
===============================================================================
视图层 (Views)
===============================================================================

【架构职责】
-----------
views.py 是 MVC/MTV 中的「控制器」：
1. 接收 HTTP 请求
2. 调用业务逻辑（重复检测、创建记录）
3. 返回 HTTP 响应

【与异常处理的关系】
-----------------
views.py 调用 →  duplicate_detection.py（返回 ValidationResult）
              ↓
         检查 result.has_errors?
              ↓
         是 → raise ValidationException → DRF 的 exception_handler 处理
         否 → 检查 result.has_warnings?
              ↓
         是 → 返回 requires_confirmation 响应
         否 → 正常创建 CarePlan

【DRF @api_view 装饰器】
----------------------
@api_view(['POST']) 的作用：
1. 把普通函数变成 DRF API 视图
2. 自动解析 request.data（JSON/Form 都支持）
3. 异常自动交给 exception_handler 处理
4. 返回 DRF Response（自动处理序列化）
"""

import csv
from datetime import datetime

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.core.cache import cache  # 用缓存做限流

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import CarePlan, Patient
from .tasks import generate_care_plan_task  # Celery 异步任务
from .exceptions import RateLimitException, ValidationException
from .duplicate_detection import check_all_duplicates


# ============================================================================
# 限流检查
# ============================================================================

def check_rate_limit() -> None:
    """
    检查请求频率限制
    
    【为什么用 raise 而不是返回值？】
    限流是「跨领域关注点」（cross-cutting concern）：
    - 和业务逻辑无关
    - 应该立即中断请求
    - 用异常更清晰表达「请求被拒绝」
    
    【限流策略】
    - 每分钟：15 次（Gemini 免费版是 60/分钟，保守设置）
    - 每天：1500 次（Gemini 免费版每日限额）
    
    Raises:
        RateLimitException: 如果超过限制
    """
    now = datetime.now()
    
    # ----- 检查每分钟限制 -----
    minute_key = f"gemini_calls_{now.strftime('%Y%m%d%H%M')}"
    minute_count = cache.get(minute_key, 0)
    
    if minute_count >= 15:
        raise RateLimitException("请求过于频繁，请稍等片刻再试")
    
    # ----- 检查每天限制 -----
    day_key = f"gemini_calls_{now.strftime('%Y%m%d')}"
    day_count = cache.get(day_key, 0)
    
    if day_count >= 1500:
        raise RateLimitException("今日请求配额已用完，请明天再试")
    
    # ----- 更新计数 -----
    cache.set(minute_key, minute_count + 1, timeout=60)    # 1分钟后过期
    cache.set(day_key, day_count + 1, timeout=86400)       # 1天后过期


# ============================================================================
# 主 API：创建 CarePlan
# ============================================================================

@api_view(['GET', 'POST'])
def index(request):
    """
    CarePlan 创建页面 / API
    
    【双重职责】
    GET：返回表单 HTML 页面
    POST：处理表单提交，创建 CarePlan
    
    【POST 请求流程】
    1. 限流检查 → 超限抛 RateLimitException
    2. 重复检测 → 返回 ValidationResult
    3. 检查 errors → 有则抛 ValidationException
    4. 检查 warnings → 有则返回确认请求
    5. 创建 CarePlan → 异步生成计划
    
    【DRF 自动处理】
    - request.data：自动解析 JSON/Form
    - Response：自动序列化为 JSON
    - 异常：自动交给 custom_exception_handler
    """
    # ----- GET 请求：返回表单页面 -----
    if request.method == 'GET':
        return render(request, 'form.html')
    
    # ----- POST 请求：处理表单提交 -----
    
    # 步骤 1: 限流检查
    # 如果超限，直接抛出 RateLimitException
    # DRF 会捕获并调用 custom_exception_handler
    check_rate_limit()
    
    # 步骤 2: 统一重复检测
    # 【关键变化】
    # 旧代码：三个独立的 check_xxx() 调用，每个都可能 raise
    # 新代码：一个 check_all_duplicates()，返回收集的结果
    try:
        dob = datetime.strptime(request.data.get('patient_dob', ''), '%Y-%m-%d').date()
    except ValueError:
        # 日期格式错误
        from .exceptions import ValidationResult, ErrorCodes
        result = ValidationResult()
        result.add_error(ErrorCodes.INTERNAL_ERROR, "出生日期格式错误，请使用 YYYY-MM-DD 格式")
        raise ValidationException(result)
    
    validation = check_all_duplicates(
        npi=request.data.get('referring_provider_npi', ''),
        provider_name=request.data.get('referring_provider', ''),
        mrn=request.data.get('patient_mrn', ''),
        first_name=request.data.get('patient_first_name', ''),
        last_name=request.data.get('patient_last_name', ''),
        date_of_birth=dob,
        medication_name=request.data.get('medication_name', ''),
        confirm=request.data.get('confirm') == 'true'
    )
    
    # 步骤 3: 处理 Errors（必须阻止）
    # 【Exception 流程】
    #   raise ValidationException
    #     ↓
    #   DRF 捕获
    #     ↓
    #   调用 custom_exception_handler(exc, context)
    #     ↓
    #   返回 Response(422, {errors: [...]})
    if validation.has_errors:
        raise ValidationException(validation)
    
    # 步骤 4: 处理 Warnings（需要用户确认）
    # 【Warning vs Error 的区别】
    # - Error: 抛异常，HTTP 422
    # - Warning: 正常返回，HTTP 200，带 requires_confirmation
    # 
    # 前端收到 requires_confirmation=true 后：
    # 1. 显示警告对话框
    # 2. 用户点击确认
    # 3. 重新提交，带 confirm=true
    # 4. 这次 check_all_duplicates 会跳过 warning 检查
    if validation.has_warnings:
        return Response({
            "success": False,
            "requires_confirmation": True,
            "warnings": validation.to_response_dict()["warnings"]
        })
    
    # 步骤 5: 创建 CarePlan
    # 所有检测通过，可以安全创建
    cp = CarePlan.objects.create(
        patient_first_name=request.data.get('patient_first_name', ''),
        patient_last_name=request.data.get('patient_last_name', ''),
        patient_dob=request.data.get('patient_dob', ''),
        patient_mrn=request.data.get('patient_mrn', ''),
        referring_provider=request.data.get('referring_provider', ''),
        referring_provider_npi=request.data.get('referring_provider_npi', ''),
        medication_name=request.data.get('medication_name', ''),
        patient_primary_diagnosis=request.data.get('patient_primary_diagnosis', ''),
        additional_diagnosis=request.data.get('additional_diagnosis', ''),
        medication_history=request.data.get('medication_history', ''),
        clinical_notes=request.data.get('clinical_notes', ''),
        # status 默认是 'pending'
    )
    
    # 步骤 6: 触发异步任务
    # Celery 会在后台处理，不阻塞响应
    generate_care_plan_task.delay(cp.id)
    
    # 步骤 7: 返回成功响应
    # 【注意】这里返回 JSON，不再 redirect
    # 前端需要根据 success=true 来决定跳转
    return Response({
        "success": True,
        "careplan_id": cp.id,
        "redirect_url": f"/result/{cp.id}/"
    })


# ============================================================================
# 结果页面
# ============================================================================

def result(request, pk):
    """显示 CarePlan 结果页面"""
    care_plan = get_object_or_404(CarePlan, pk=pk)
    return render(request, 'result.html', {'care_plan': care_plan})


def download_txt(request, pk):
    """下载 CarePlan 为文本文件"""
    cp = get_object_or_404(CarePlan, pk=pk)
    response = HttpResponse(cp.generated_plan, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="careplan_{cp.patient_mrn}.txt"'
    return response


def export_csv(request):
    """导出所有 CarePlan 为 CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="careplans.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Patient First Name', 'Patient Last Name', 'DOB', 'MRN',
        'Provider', 'Provider NPI', 'Medication', 'Primary Diagnosis',
        'Additional Diagnosis', 'Medication History', 'Created At'
    ])
    
    for cp in CarePlan.objects.all():
        writer.writerow([
            cp.patient_first_name, cp.patient_last_name, cp.patient_dob, cp.patient_mrn,
            cp.referring_provider, cp.referring_provider_npi, cp.medication_name,
            cp.patient_primary_diagnosis, cp.additional_diagnosis, cp.medication_history,
            cp.created_at
        ])
    
    return response


def stats(request):
    """显示数据库统计信息"""
    from .queue_utils import get_queue_length
    
    total = CarePlan.objects.count()
    pending = CarePlan.objects.filter(status='pending').count()
    processing = CarePlan.objects.filter(status='processing').count()
    completed = CarePlan.objects.filter(status='completed').count()
    failed = CarePlan.objects.filter(status='failed').count()
    queue_length = get_queue_length()
    
    recent_plans = CarePlan.objects.all().order_by('-created_at')[:10]
    
    context = {
        'total': total,
        'pending': pending,
        'processing': processing,
        'completed': completed,
        'failed': failed,
        'queue_length': queue_length,
        'recent_plans': recent_plans,
    }
    
    return render(request, 'stats.html', context)


# ============================================================================
# API：查询 CarePlan 状态
# ============================================================================

@api_view(['GET'])
def careplan_status(request, pk):
    """
    API 端点：返回 CarePlan 的当前状态
    
    URL: GET /api/careplan/<pk>/status/
    
    返回 JSON:
        {
            "status": "pending|processing|completed|failed",
            "generated_plan": "..." (仅当 status=completed 时)
        }
    
    前端轮询使用：
        fetch('/api/careplan/123/status/')
            .then(res => res.json())
            .then(data => { ... });
    """
    care_plan = get_object_or_404(CarePlan, pk=pk)
    
    response_data = {
        'status': care_plan.status,
    }
    
    if care_plan.status == 'completed':
        response_data['generated_plan'] = care_plan.generated_plan
    
    return Response(response_data)


# ============================================================================
# 附录：请求流程图
# ============================================================================
#
# 【POST /index/ 完整流程】
#
#     Client POST
#          │
#          ▼
#    ┌─────────────┐
#    │ check_rate  │ ──超限──→ raise RateLimitException
#    │   _limit()  │                    │
#    └──────┬──────┘                    ▼
#           │                 ┌───────────────────┐
#           ▼                 │ custom_exception  │
#    ┌─────────────┐          │    _handler()     │
#    │ check_all   │          └─────────┬─────────┘
#    │ _duplicates │                    │
#    └──────┬──────┘                    ▼
#           │                     HTTP 429 JSON
#           ▼
#    has_errors? ──是──→ raise ValidationException
#           │                       │
#           ▼                       ▼
#    has_warnings? ──是──→ Response(requires_confirmation)
#           │                       │
#           ▼                       ▼
#    创建 CarePlan               HTTP 200 JSON
#           │
#           ▼
#    Celery 异步任务
#           │
#           ▼
#    Response(success=true)
#           │
#           ▼
#     HTTP 200 JSON
#
# ============================================================================