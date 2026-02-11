"""
======================================
业务逻辑层（Service Layer）
======================================

这个文件封装了所有业务逻辑：
- LLM 调用
- 限流检查
- CarePlan 创建和触发异步任务
- 统计数据查询
"""

import os
import time
from datetime import datetime
from django.core.cache import cache


# ============================================
# 限流服务
# ============================================
def check_rate_limit():
    """
    检查 API 调用频率限制（从 views.py 迁移）
    
    返回:
        (allowed, error_msg) - 是否允许，错误信息
    """
    print("   🟢 services.py → check_rate_limit() 执行中...")
    
    now = datetime.now()
    
    # 检查每分钟限制
    minute_key = f"gemini_calls_{now.strftime('%Y%m%d%H%M')}"
    minute_count = cache.get(minute_key, 0)
    print(f"   当前分钟请求数: {minute_count}/15")
    
    if minute_count >= 15:
        return False, "Too many requests per minute. Please wait."
    
    # 检查每天限制
    day_key = f"gemini_calls_{now.strftime('%Y%m%d')}"
    day_count = cache.get(day_key, 0)
    print(f"   当前每日请求数: {day_count}/1500")
    
    if day_count >= 1500:
        return False, "Daily quota exceeded. Please try tomorrow."
    
    # 更新计数
    cache.set(minute_key, minute_count + 1, timeout=60)
    cache.set(day_key, day_count + 1, timeout=86400)
    
    return True, None


# ============================================
# CarePlan 业务逻辑
# ============================================
def create_careplan(data):
    """
    创建 CarePlan 并触发异步任务
    
    流程：Provider → Patient → Order → CarePlan → Celery 任务
    
    参数:
        data: 请求数据（request.POST 或 dict）
    
    返回:
        创建的 CarePlan 对象
    """
    print("   🟢 services.py → create_careplan() 执行中...")
    print(f"   接收数据类型: {type(data).__name__}")
    
    from .models import Patient, Provider, Order, CarePlan
    from .tasks import generate_care_plan_task
    
    # 1. 查找或创建 Provider
    print("   📝 查找/创建 Provider...")
    provider, provider_created = Provider.objects.get_or_create(
        npi=data['referring_provider_npi'],
        defaults={'name': data['referring_provider']}
    )
    print(f"   {'✨ 新建' if provider_created else '♻️ 复用'} Provider: {provider}")
    
    # 2. 查找或创建 Patient
    print("   📝 查找/创建 Patient...")
    patient, patient_created = Patient.objects.get_or_create(
        mrn=data['patient_mrn'],
        defaults={
            'first_name': data['patient_first_name'],
            'last_name': data['patient_last_name'],
            'date_of_birth': data['patient_dob'],
        }
    )
    print(f"   {'✨ 新建' if patient_created else '♻️ 复用'} Patient: {patient}")
    
    # 3. 创建 Order
    print("   📝 创建 Order...")
    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name=data['medication_name'],
        primary_diagnosis=data.get('patient_primary_diagnosis', ''),
        additional_diagnosis=data.get('additional_diagnosis', ''),
        medication_history=data.get('medication_history', ''),
        clinical_notes=data.get('clinical_notes', ''),
    )
    print(f"   ✅ Order 创建成功: {order}")
    
    # 4. 创建 CarePlan
    print("   📝 创建 CarePlan...")
    care_plan = CarePlan.objects.create(order=order)
    print(f"   ✅ CarePlan 创建成功: {care_plan}")
    
    # 5. 触发异步任务
    print("   🚀 触发 Celery 异步任务...")
    generate_care_plan_task.delay(care_plan.id)
    print("   ✅ 任务已发送到 Redis 队列")
    
    return care_plan


def get_stats_data():
    """
    获取统计数据（从 views.py 迁移）
    
    返回:
        包含统计信息的字典
    """
    from .models import CarePlan
    from careplan.celery import app
    
    # 数据库统计
    total = CarePlan.objects.count()
    pending = CarePlan.objects.filter(status='pending').count()
    processing = CarePlan.objects.filter(status='processing').count()
    completed = CarePlan.objects.filter(status='completed').count()
    failed = CarePlan.objects.filter(status='failed').count()
    
    # Celery 队列统计
    try:
        inspect = app.control.inspect()
        reserved = inspect.reserved() or {}
        active = inspect.active() or {}
        queue_length = sum(len(tasks) for tasks in reserved.values())
        queue_length += sum(len(tasks) for tasks in active.values())
    except Exception:
        queue_length = 0
    
    # 最近记录
    recent_plans = CarePlan.objects.select_related(
        'order__patient', 'order__provider'
    ).all().order_by('-created_at')[:10]
    
    return {
        'total': total,
        'pending': pending,
        'processing': processing,
        'completed': completed,
        'failed': failed,
        'queue_length': queue_length,
        'recent_plans': recent_plans,
    }


# ============================================
# Mock LLM 函数
# ============================================
def get_mock_response(prompt):
    """
    Mock LLM 响应函数，用于开发和测试。
    
    特点：
    - 不调用任何外部 API
    - 返回固定的 Care Plan 模板
    - 模拟 2 秒延迟（模拟真实 API 调用时间）
    
    参数:
        prompt: 提示词（这里不会使用，但保持接口一致）
    
    返回:
        固定的 Care Plan 文本
    """
    print("   🎭 [MOCK] 使用 Mock LLM 响应（非真实 API 调用）")
    
    # 模拟 API 延迟
    time.sleep(5)
    
    mock_care_plan = """
=====================================
SPECIALTY PHARMACY CARE PLAN (MOCK)
=====================================

📋 PROBLEM LIST / DRUG THERAPY PROBLEMS (DTPs)
----------------------------------------------
1. High-cost specialty medication requiring prior authorization
2. Potential adherence challenges due to complex dosing schedule
3. Need for patient education on self-administration
4. Risk of adverse effects requiring monitoring

🎯 SMART GOALS
--------------
1. Patient will demonstrate proper self-injection technique within 2 weeks
2. Achieve 90%+ medication adherence over 3 months
3. Complete all required lab monitoring as scheduled
4. Report any adverse effects within 24 hours

💊 PHARMACIST INTERVENTIONS/PLAN
---------------------------------
1. Initial Consultation:
   - Review medication therapy and expected outcomes
   - Educate patient on proper storage and handling
   - Demonstrate injection technique with training device

2. Ongoing Support:
   - Monthly adherence check-in calls
   - Coordinate refill timing with insurance
   - Address any side effect concerns

📊 MONITORING PLAN & LAB SCHEDULE
----------------------------------
- Baseline: CBC, CMP, LFTs before starting therapy
- Week 2: Follow-up call to assess tolerance
- Month 1: Repeat labs, efficacy assessment
- Month 3: Comprehensive therapy review

=====================================
⚠️  THIS IS A MOCK RESPONSE FOR TESTING
    Set USE_MOCK_LLM=false for production
=====================================
"""
    
    return mock_care_plan


# ============================================
# 真实 LLM 函数（Gemini）
# ============================================
def get_real_gemini_response(prompt):
    """
    调用真实的 Gemini API。
    
    参数:
        prompt: 提示词
    
    返回:
        LLM 生成的文本
    """
    import google.generativeai as genai
    
    # 1. 配置 API Key
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    
    # 2. 统一管理模型名称
    model_name = 'gemini-2.5-flash'
    
    model = genai.GenerativeModel(model_name)
    
    # 3. 执行调用
    response = model.generate_content(prompt)
    return response.text


# ============================================
# 统一入口函数
# ============================================
def get_gemini_response(prompt):
    """
    统一的 LLM 调用入口。
    
    根据环境变量 USE_MOCK_LLM 决定使用 Mock 还是真实 API：
    - USE_MOCK_LLM=true  → 使用 Mock（开发/测试）
    - USE_MOCK_LLM=false 或未设置 → 使用真实 API（生产）
    
    参数:
        prompt: 提示词
    
    返回:
        生成的 Care Plan 文本
    """
    use_mock = os.getenv('USE_MOCK_LLM', 'false').lower() == 'true'
    
    if use_mock:
        return get_mock_response(prompt)
    else:
        return get_real_gemini_response(prompt)