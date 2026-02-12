"""
======================================
Unit Tests: 重复检测函数
======================================

这是 UNIT TEST（单元测试）。
- 直接调用 check_provider/patient/order_duplicate() 函数
- 不经过 HTTP 请求，不经过中间件
- 只测函数内部的 if/else 逻辑对不对
- 速度快，问题定位精准

每个 test 函数名以 test_ 开头，pytest 会自动发现并运行。
@pytest.mark.django_db 让 pytest 知道这个测试需要访问数据库。
"""

import pytest
from datetime import date, timedelta
from django.utils import timezone

from app.models import Provider, Patient, Order
from app.exceptions import BlockError, WarningException
from app.duplicate_detection import (
    check_provider_duplicate,
    check_patient_duplicate,
    check_order_duplicate,
)


# ============================================
# Provider 检测测试（3 个场景）
# ============================================

class TestProviderDuplicate:
    """测试 check_provider_duplicate() 的所有分支"""

    @pytest.mark.django_db
    def test_no_match_returns_none(self):
        """场景 1: 数据库里没有这个 NPI → 返回 None（新 Provider）"""
        result = check_provider_duplicate(npi="1234567890", name="Dr. Smith")
        assert result is None

    @pytest.mark.django_db
    def test_same_npi_same_name_returns_provider(self):
        """场景 2: NPI 和名字都匹配 → 返回现有 Provider（复用）"""
        # 先在数据库创建一个 Provider
        provider = Provider.objects.create(npi="1234567890", name="Dr. Smith")
        
        # 调用检测函数，传入相同的 NPI 和名字
        result = check_provider_duplicate(npi="1234567890", name="Dr. Smith")
        
        # 应该返回现有的 Provider 对象
        assert result is not None
        assert result.id == provider.id
        assert result.name == "Dr. Smith"

    @pytest.mark.django_db
    def test_same_npi_different_name_raises_block(self):
        """场景 3: NPI 相同但名字不同 → raise BlockError（阻止）"""
        # 创建一个 Provider
        Provider.objects.create(npi="1234567890", name="Dr. Smith")
        
        # 用相同 NPI 但不同名字调用 → 应该被阻止
        with pytest.raises(BlockError) as exc_info:
            check_provider_duplicate(npi="1234567890", name="Dr. Jones")
        
        # 验证错误代码和详情
        assert exc_info.value.code == "NPI_NAME_CONFLICT"
        assert "Dr. Smith" in exc_info.value.detail["existing_name"]


# ============================================
# Patient 检测测试（7 个场景）
# ============================================

class TestPatientDuplicate:
    """测试 check_patient_duplicate() 的所有分支"""

    @pytest.mark.django_db
    def test_no_match_returns_none(self):
        """场景 4: 数据库里没有匹配 → 返回 None（新患者）"""
        result = check_patient_duplicate(
            first_name="John", last_name="Smith",
            mrn="123456", dob="1985-03-15"
        )
        assert result is None

    @pytest.mark.django_db
    def test_mrn_same_all_match_returns_patient(self):
        """场景 5: MRN 相同 + 名字和DOB都匹配 → 返回现有 Patient（复用）"""
        patient = Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        
        result = check_patient_duplicate(
            first_name="John", last_name="Smith",
            mrn="123456", dob="1985-03-15"
        )
        
        assert result is not None
        assert result.id == patient.id

    @pytest.mark.django_db
    def test_mrn_same_name_different_raises_warning(self):
        """场景 6: MRN 相同 + 名字不同 → raise WarningException"""
        Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        
        # 同 MRN，但名字是 Jane
        with pytest.raises(WarningException) as exc_info:
            check_patient_duplicate(
                first_name="Jane", last_name="Smith",
                mrn="123456", dob="1985-03-15"
            )
        
        assert exc_info.value.code == "MRN_INFO_MISMATCH"

    @pytest.mark.django_db
    def test_mrn_same_dob_different_raises_warning(self):
        """场景 7: MRN 相同 + DOB 不同 → raise WarningException"""
        Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        
        with pytest.raises(WarningException) as exc_info:
            check_patient_duplicate(
                first_name="John", last_name="Smith",
                mrn="123456", dob="1990-01-01"  # DOB 不同
            )
        
        assert exc_info.value.code == "MRN_INFO_MISMATCH"

    @pytest.mark.django_db
    def test_name_dob_same_mrn_different_raises_warning(self):
        """场景 8: 名字+DOB 相同 + MRN 不同 → raise WarningException"""
        Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        
        # 同名同DOB，但 MRN 不同
        with pytest.raises(WarningException) as exc_info:
            check_patient_duplicate(
                first_name="John", last_name="Smith",
                mrn="654321", dob="1985-03-15"  # MRN 不同
            )
        
        assert exc_info.value.code == "DUPLICATE_PATIENT_SUSPECTED"

    @pytest.mark.django_db
    def test_mrn_mismatch_with_confirm_skips_warning(self):
        """场景 9: 场景 6 + confirm=True → 不 raise，返回现有 Patient"""
        patient = Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        
        # confirm=True → 跳过警告
        result = check_patient_duplicate(
            first_name="Jane", last_name="Smith",
            mrn="123456", dob="1985-03-15",
            confirm=True  # ← 用户已确认
        )
        
        # 不 raise，返回现有 Patient
        assert result.id == patient.id

    @pytest.mark.django_db
    def test_name_dob_match_with_confirm_skips_warning(self):
        """场景 10: 场景 8 + confirm=True → 不 raise"""
        Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        
        # confirm=True → 跳过警告，返回 None（不复用，因为 MRN 不同）
        result = check_patient_duplicate(
            first_name="John", last_name="Smith",
            mrn="654321", dob="1985-03-15",
            confirm=True
        )
        
        # 不 raise，正常返回
        assert result is None


# ============================================
# Order 检测测试（3 个场景）
# ============================================

class TestOrderDuplicate:
    """测试 check_order_duplicate() 的所有分支"""

    @pytest.mark.django_db
    def test_same_patient_same_med_same_day_raises_block(self):
        """场景 11: 同患者 + 同药物 + 同一天 → raise BlockError（绝对不允许）"""
        # 准备数据：创建 Patient → Provider → Order（今天）
        patient = Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        provider = Provider.objects.create(npi="1234567890", name="Dr. Smith")
        Order.objects.create(
            patient=patient, provider=provider,
            medication_name="Ozempic", primary_diagnosis="E11.9"
        )
        
        # 同一天再下一个一样的单 → 必须阻止
        with pytest.raises(BlockError) as exc_info:
            check_order_duplicate(patient=patient, medication_name="Ozempic")
        
        assert exc_info.value.code == "DUPLICATE_ORDER_SAME_DAY"

    @pytest.mark.django_db
    def test_same_patient_same_med_different_day_raises_warning(self):
        """场景 12: 同患者 + 同药物 + 不同天 → raise WarningException"""
        patient = Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        provider = Provider.objects.create(npi="1234567890", name="Dr. Smith")
        
        # 创建一个昨天的订单（手动设置 created_at）
        yesterday = timezone.now() - timedelta(days=1)
        order = Order.objects.create(
            patient=patient, provider=provider,
            medication_name="Ozempic", primary_diagnosis="E11.9"
        )
        # 手动改 created_at 为昨天（auto_now_add 不能直接设置）
        Order.objects.filter(id=order.id).update(created_at=yesterday)
        
        # 今天再下同样的单 → 警告
        with pytest.raises(WarningException) as exc_info:
            check_order_duplicate(patient=patient, medication_name="Ozempic")
        
        assert exc_info.value.code == "DUPLICATE_ORDER_DIFFERENT_DAY"

    @pytest.mark.django_db
    def test_different_day_with_confirm_skips_warning(self):
        """场景 13: 场景 12 + confirm=True → 不 raise"""
        patient = Patient.objects.create(
            first_name="John", last_name="Smith",
            mrn="123456", date_of_birth=date(1985, 3, 15)
        )
        provider = Provider.objects.create(npi="1234567890", name="Dr. Smith")
        
        yesterday = timezone.now() - timedelta(days=1)
        order = Order.objects.create(
            patient=patient, provider=provider,
            medication_name="Ozempic", primary_diagnosis="E11.9"
        )
        Order.objects.filter(id=order.id).update(created_at=yesterday)
        
        # confirm=True → 不 raise
        result = check_order_duplicate(
            patient=patient, medication_name="Ozempic", confirm=True
        )
        assert result is None
