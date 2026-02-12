"""
======================================
视图层（View Layer）
======================================

只负责 HTTP 请求/响应处理：
- 接收请求
- 调用 service 层处理业务逻辑
- 调用 serializer 层格式化数据
- 返回响应
"""

import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse

from .models import CarePlan
from .services import check_rate_limit, create_careplan, get_stats_data
from .serializers import serialize_careplan_status, serialize_careplan_for_csv
from .duplicate_detection import (
    check_provider_duplicate,
    check_patient_duplicate,
    check_order_duplicate,
)
from rest_framework.decorators import api_view
from rest_framework.response import Response


def index(request):
    """首页：显示表单 / 处理表单提交"""
    if request.method == 'POST':
        # ========== DEBUG: 追踪请求流程 ==========
        print("\n" + "="*60)
        print("🔵 [1/5] views.py → index() 收到 POST 请求")
        print(f"   数据类型: {type(request.POST).__name__}")
        print(f"   字段: {list(request.POST.keys())}")
        print("="*60)
        
        # 检查限流（调用 service）
        print("\n🔵 [2/5] views.py → 调用 services.check_rate_limit()")
        allowed, error_msg = check_rate_limit()
        print(f"   限流结果: allowed={allowed}")
        if not allowed:
            return render(request, 'form.html', {'error': error_msg})
        
        # ========== 重复检测（在创建之前检查）==========
        # 如果检测到问题，会 raise BlockError 或 WarningException
        # 中间件（middleware.py）会自动捕获并转为 JSON 响应
        print("\n🔵 [3/5] views.py → 调用重复检测函数")
        confirm = request.POST.get('confirm') == 'true'
        
        # Provider 检测：NPI 冲突会 raise BlockError
        check_provider_duplicate(
            npi=request.POST.get('referring_provider_npi', ''),
            name=request.POST.get('referring_provider', ''),
        )
        
        # Patient 检测：MRN/名字不匹配会 raise WarningException
        check_patient_duplicate(
            first_name=request.POST.get('patient_first_name', ''),
            last_name=request.POST.get('patient_last_name', ''),
            mrn=request.POST.get('patient_mrn', ''),
            dob=request.POST.get('patient_dob', ''),
            confirm=confirm,
        )
        
        # Order 检测需要 Patient 对象，从 create_careplan 里处理
        # 暂时跳过（Order 检测会在 service 层集成后补充）
        
        print("   检测通过 ✅")
        
        # 创建 CarePlan（调用 service）
        print("\n🔵 [4/5] views.py → 调用 services.create_careplan()")
        care_plan = create_careplan(request.POST)
        print(f"   返回: CarePlan 对象 (id={care_plan.id})")
        
        print("\n🔵 [5/5] views.py → 重定向到结果页面")
        print("="*60 + "\n")
        return redirect('result', pk=care_plan.id)
    
    return render(request, 'form.html')


def result(request, pk):
    """显示 CarePlan 结果页面"""
    care_plan = get_object_or_404(
        CarePlan.objects.select_related('order__patient', 'order__provider'),
        pk=pk
    )
    return render(request, 'result.html', {'care_plan': care_plan})


def download_txt(request, pk):
    """下载 CarePlan 为 TXT 文件"""
    care_plan = get_object_or_404(
        CarePlan.objects.select_related('order__patient'),
        pk=pk
    )
    response = HttpResponse(care_plan.generated_plan, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="careplan_{care_plan.order.patient.mrn}.txt"'
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
    
    # 使用 serializer 格式化每行数据
    for care_plan in CarePlan.objects.select_related('order__patient', 'order__provider').all():
        writer.writerow(serialize_careplan_for_csv(care_plan))
    
    return response


def stats(request):
    """显示数据库统计信息"""
    # 调用 service 获取统计数据
    context = get_stats_data()
    return render(request, 'stats.html', context)


@api_view(['GET'])
def get_careplan_status(request, pk):
    """API: 获取 CarePlan 状态（用于前端轮询）"""
    care_plan = get_object_or_404(
        CarePlan.objects.select_related('order__patient', 'order__provider'),
        pk=pk
    )
    # 使用 serializer 格式化响应数据
    data = serialize_careplan_status(care_plan)
    return Response({"success": True, "data": data})