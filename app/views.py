import os
import csv
from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache  # ← 新增：用缓存做限流
import google.generativeai as genai
from .models import CarePlan
from .services import get_gemini_response
from .queue_utils import enqueue_careplan  # ← 新增：导入队列工具


    # ========== 限流函数 ==========
def check_rate_limit():
    """
    免费版限制：
    - 每分钟 15 次请求（设保守一点）
    - 每天 1500 次请求
    """
    now = datetime.now()
    
    # 检查每分钟限制
    minute_key = f"gemini_calls_{now.strftime('%Y%m%d%H%M')}"
    minute_count = cache.get(minute_key, 0)
    
    if minute_count >= 15:  # ← 保守设置，免费版是 60/分钟
        return False, "Too many requests per minute. Please wait."
    
    # 检查每天限制
    day_key = f"gemini_calls_{now.strftime('%Y%m%d')}"
    day_count = cache.get(day_key, 0)
    
    if day_count >= 1500:  # ← 免费版每天 1500 次
        return False, "Daily quota exceeded. Please try tomorrow."
    
    # 更新计数
    cache.set(minute_key, minute_count + 1, timeout=60)  # 1分钟过期
    cache.set(day_key, day_count + 1, timeout=86400)  # 1天过期
    
    return True, None

def index(request):
    if request.method == 'POST':

        # ========== 检查限流 ==========
        allowed, error_msg = check_rate_limit()
        if not allowed:
            return render(request, 'form.html', {'error': error_msg})

        # ========== 步骤 1: 保存到数据库（status='pending'） ==========
        cp = CarePlan.objects.create(
            patient_first_name=request.POST['patient_first_name'],
            patient_last_name=request.POST['patient_last_name'],
            patient_dob=request.POST['patient_dob'],
            patient_mrn=request.POST['patient_mrn'],
            referring_provider=request.POST['referring_provider'],
            referring_provider_npi=request.POST['referring_provider_npi'],
            medication_name=request.POST['medication_name'],
            patient_primary_diagnosis=request.POST['patient_primary_diagnosis'],
            additional_diagnosis=request.POST.get('additional_diagnosis', ''),
            medication_history=request.POST.get('medication_history', ''),
            clinical_notes=request.POST.get('clinical_notes', ''),
            # status 默认就是 'pending'，不需要显式设置
        )
        
        # ========== 步骤 2: 放入 Redis 队列 ==========
        success = enqueue_careplan(cp.id)
        
        if not success:
            # 如果队列失败，返回错误
            return JsonResponse({
                'error': '无法将任务加入队列，请稍后重试',
                'careplan_id': cp.id
            }, status=500)
        
        # ========== 步骤 3: 立即返回响应 ==========
        return JsonResponse({
            'message': '已收到您的请求，正在处理中',
            'careplan_id': cp.id,
            'status': 'pending'
        })
    
    return render(request, 'form.html')

def download_txt(request, pk):
    cp = get_object_or_404(CarePlan, pk=pk)
    response = HttpResponse(cp.generated_plan, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="careplan_{cp.patient_mrn}.txt"'
    return response

def export_csv(request):
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
    
    # 获取最近的 10 条记录
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