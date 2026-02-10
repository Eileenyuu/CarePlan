"""
======================================
数据序列化层
======================================

负责数据格式转换：
- 前端数据 → 后端格式（输入验证）
- 后端数据 → 前端格式（JSON、CSV 等）
"""

from rest_framework import serializers


# ========== 输入验证：前端 → 后端 ==========
class CarePlanInputSerializer(serializers.Serializer):
    """
    CarePlan 创建请求的输入验证

    - 验证字段格式（NPI 10位、MRN 6位等）
    - 验证失败时 DRF 自动 raise ValidationError
    - 中间件捕获后转为统一格式返回 400
    """
    patient_first_name = serializers.CharField(max_length=100)
    patient_last_name = serializers.CharField(max_length=100)
    patient_dob = serializers.DateField()
    patient_mrn = serializers.CharField(min_length=6, max_length=6)
    referring_provider = serializers.CharField(max_length=200)
    referring_provider_npi = serializers.CharField(min_length=10, max_length=10)
    medication_name = serializers.CharField(max_length=200)
    patient_primary_diagnosis = serializers.CharField(max_length=20)
    additional_diagnosis = serializers.CharField(required=False, allow_blank=True)
    medication_history = serializers.CharField(required=False, allow_blank=True)
    clinical_notes = serializers.CharField(required=False, allow_blank=True)

def serialize_careplan_status(care_plan):
    """
    将 CarePlan 转换为状态 API 的 JSON 格式
    """
    print("   🟡 serializers.py → serialize_careplan_status() 执行中...")
    print(f"   输入: CarePlan 对象 (id={care_plan.id}, status={care_plan.status})")
    
    result = {
        'status': care_plan.status,
        'content': care_plan.generated_plan if care_plan.status == 'completed' else None
    }
    
    print(f"   输出: JSON dict (keys={list(result.keys())})")
    return result


def serialize_careplan_for_csv(care_plan):
    """
    将 CarePlan 转换为 CSV 导出的行格式
    """
    print(f"   🟡 serializers.py → serialize_careplan_for_csv() 执行中...")
    print(f"   输入: CarePlan 对象 (id={care_plan.id})")
    
    result = [
        care_plan.patient_first_name,
        care_plan.patient_last_name,
        care_plan.patient_dob,
        care_plan.patient_mrn,
        care_plan.referring_provider,
        care_plan.referring_provider_npi,
        care_plan.medication_name,
        care_plan.patient_primary_diagnosis,
        care_plan.additional_diagnosis,
        care_plan.medication_history,
        care_plan.created_at
    ]
    
    print(f"   输出: list (长度={len(result)})")
    return result

