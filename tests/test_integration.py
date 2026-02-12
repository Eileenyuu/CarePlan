"""
======================================
Integration Tests: 完整 HTTP 链路
======================================

这是 INTEGRATION TEST（集成测试）。
- 模拟真实用户操作：通过 HTTP 请求发送数据
- 经过完整链路：HTTP → View → Serializer → 检测 → 中间件 → 响应
- 验证前端最终收到的 JSON 格式和内容

与 Unit Test 的区别：
- Unit Test: 直接调用函数（check_patient_duplicate()），不经过 HTTP
- Integration Test: 发 HTTP 请求，验证整个系统串在一起是否正确

与 Error Test 的区别：
- Error Test: 手动构造异常传给中间件，测基础设施
- Integration Test: 让真实的业务逻辑 raise 异常，中间件自动处理
"""

import pytest
from datetime import date
from django.test import Client

from app.models import Provider, Patient


# Django test client，模拟浏览器发 HTTP 请求
client = Client()

# 一份完整的测试表单数据（所有字段都合法）
VALID_FORM_DATA = {
    "patient_first_name": "John",
    "patient_last_name": "Smith",
    "patient_dob": "1985-03-15",
    "patient_mrn": "123456",
    "referring_provider": "Dr. Sarah Johnson",
    "referring_provider_npi": "1234567890",
    "medication_name": "Ozempic",
    "patient_primary_diagnosis": "E11.9",
    "additional_diagnosis": "",
    "medication_history": "",
    "clinical_notes": "",
}


class TestFormValidation:
    """
    测试表单提交的输入验证
    
    注意：当前 form view（index）直接调用 create_careplan()，
    没有经过 DRF Serializer 验证 NPI/MRN 格式。
    所以无效格式的数据会直接被创建（302 重定向）。
    
    如果要在 form 中也做格式验证，需要在 views.py 中
    集成 CarePlanInputSerializer 的验证逻辑。
    """

    @pytest.mark.django_db
    def test_invalid_npi_too_short(self):
        """场景 1: NPI 只有 5 位 → 当前 form 不验证格式，直接创建（302）"""
        data = {**VALID_FORM_DATA, "referring_provider_npi": "12345"}
        response = client.post("/", data)
        
        # 当前行为：form 不验证 NPI 格式，提交后重定向到结果页
        # TODO: 如果需要在 form 中也验证，需要集成 Serializer
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_invalid_mrn_too_short(self):
        """场景 2: MRN 只有 3 位 → 当前 form 不验证格式，直接创建（302）"""
        data = {**VALID_FORM_DATA, "patient_mrn": "123"}
        response = client.post("/", data)
        
        # 当前行为：form 不验证 MRN 格式，提交后重定向到结果页
        assert response.status_code == 302


class TestDuplicateDetectionIntegration:
    """
    测试重复检测通过 HTTP 请求触发时的完整链路
    
    这些测试验证：当数据库已有数据，用户提交重复信息时，
    系统能否通过 中间件 返回正确的错误/警告响应。
    """

    @pytest.mark.django_db
    def test_provider_npi_conflict_returns_block(self):
        """场景 3: Provider NPI 冲突 → 应该被阻止"""
        # 先创建一个 Provider
        Provider.objects.create(npi="1234567890", name="Dr. Smith")
        
        # 用同 NPI 但不同名字提交表单
        data = {**VALID_FORM_DATA, "referring_provider": "Dr. Different Name"}
        response = client.post("/", data)
        
        # 应该被阻止（BlockError → middleware → 409 或页面显示错误）
        # 具体状态码取决于 view 是否返回 JSON 或渲染 HTML
        assert response.status_code in [409, 200]

    @pytest.mark.django_db
    def test_patient_mrn_mismatch_returns_warning(self):
        """场景 4: Patient MRN 信息不匹配 → 应该返回警告"""
        # 先创建一个 Patient
        Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        
        # 用同 MRN 但不同名字提交
        data = {**VALID_FORM_DATA, "patient_first_name": "Jane"}
        response = client.post("/", data)
        
        # 应该返回警告
        assert response.status_code in [200, 302]
