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


def index(request):
    """首页：显示表单 / 处理表单提交"""
    if request.method == 'POST':
        # ========== DEBUG: 追踪请求流程 ==========
        print("\n" + "="*60)
        print("🔵 [1/4] views.py → index() 收到 POST 请求")
        print(f"   数据类型: {type(request.POST).__name__}")
        print(f"   字段: {list(request.POST.keys())}")
        print("="*60)
        
        # 检查限流（调用 service）
        print("\n🔵 [2/4] views.py → 调用 services.check_rate_limit()")
        allowed, error_msg = check_rate_limit()
        print(f"   限流结果: allowed={allowed}")
        if not allowed:
            return render(request, 'form.html', {'error': error_msg})
        
        # 创建 CarePlan（调用 service）
        print("\n🔵 [3/4] views.py → 调用 services.create_careplan()")
        care_plan = create_careplan(request.POST)
        print(f"   返回: CarePlan 对象 (id={care_plan.id})")
        
        print("\n🔵 [4/4] views.py → 重定向到结果页面")
        print("="*60 + "\n")
        return redirect('result', pk=care_plan.id)
    
    return render(request, 'form.html')


def result(request, pk):
    """显示 CarePlan 结果页面"""
    care_plan = get_object_or_404(CarePlan, pk=pk)
    return render(request, 'result.html', {'care_plan': care_plan})


def download_txt(request, pk):
    """下载 CarePlan 为 TXT 文件"""
    care_plan = get_object_or_404(CarePlan, pk=pk)
    response = HttpResponse(care_plan.generated_plan, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="careplan_{care_plan.patient_mrn}.txt"'
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
    for care_plan in CarePlan.objects.all():
        writer.writerow(serialize_careplan_for_csv(care_plan))
    
    return response


def stats(request):
    """显示数据库统计信息"""
    # 调用 service 获取统计数据
    context = get_stats_data()
    return render(request, 'stats.html', context)


def get_careplan_status(request, pk):
    """API: 获取 CarePlan 状态（用于前端轮询）"""
    care_plan = get_object_or_404(CarePlan, pk=pk)
    # 使用 serializer 格式化响应数据
    data = serialize_careplan_status(care_plan)
    return JsonResponse(data)