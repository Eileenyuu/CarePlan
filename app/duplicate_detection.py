"""
======================================
重复检测逻辑（Duplicate Detection）
======================================

业务判断层：查数据库，决定是否 raise 异常。

三个检测函数：
- check_provider_duplicate: NPI 冲突检测
- check_patient_duplicate: MRN / 姓名+DOB 冲突检测
- check_order_duplicate: 同患者同药物重复下单检测

异常由 middleware.py 统一捕获并转为 JSON 响应。
"""

from datetime import date
from .models import Provider, Patient, Order
from .exceptions import BlockError, WarningException


def check_provider_duplicate(npi, name):
    """
    Provider 重复检测
    
    规则：
    - NPI 相同 + 名字相同 → 返回现有 Provider（复用）
    - NPI 相同 + 名字不同 → raise BlockError（NPI 是国家执照号，全国唯一）
    - 无匹配 → 返回 None
    
    参数:
        npi: Provider 的 NPI（10位）
        name: Provider 的名字
    
    返回:
        Provider 对象 或 None
    """
    existing = Provider.objects.filter(npi=npi).first()
    
    if existing is None:
        # 全新的 NPI，没有冲突
        return None
    
    if existing.name == name:
        # NPI 和名字都匹配，复用现有 Provider
        return existing
    
    # NPI 相同但名字不同 → 必须阻止（不可跳过）
    raise BlockError(
        code="NPI_NAME_CONFLICT",
        message="A provider with this NPI already exists under a different name",
        detail={
            "npi": npi,
            "submitted_name": name,
            "existing_name": existing.name,
        }
    )


def check_patient_duplicate(first_name, last_name, mrn, dob, confirm=False):
    """
    Patient 重复检测
    
    规则：
    - MRN 相同 + 名字和DOB都相同 → 返回现有 Patient（复用）
    - MRN 相同 + 名字或DOB不同 → raise WarningException（confirm=True 可跳过）
    - 名字+DOB 相同 + MRN 不同 → raise WarningException（confirm=True 可跳过）
    - 无匹配 → 返回 None
    
    参数:
        first_name, last_name: 患者名字
        mrn: 病历号（6位，全局唯一）
        dob: 出生日期（date 或 str）
        confirm: 用户是否已确认警告
    
    返回:
        Patient 对象 或 None
    """
    # 确保 dob 是 date 类型（前端可能传字符串）
    if isinstance(dob, str):
        dob = date.fromisoformat(dob)
    
    # ---- 检查 1: 按 MRN 查 ----
    existing_by_mrn = Patient.objects.filter(mrn=mrn).first()
    
    if existing_by_mrn:
        # MRN 找到了，检查其他信息是否匹配
        if (existing_by_mrn.first_name == first_name and
            existing_by_mrn.last_name == last_name and
            existing_by_mrn.date_of_birth == dob):
            # 完全匹配，复用
            return existing_by_mrn
        
        # MRN 相同但信息不同 → 警告
        if not confirm:
            raise WarningException(
                code="MRN_INFO_MISMATCH",
                message="A patient with this MRN exists but name or DOB does not match",
                detail={
                    "mrn": mrn,
                    "submitted_name": f"{first_name} {last_name}",
                    "existing_name": f"{existing_by_mrn.first_name} {existing_by_mrn.last_name}",
                }
            )
        # confirm=True → 跳过警告，返回现有 Patient
        return existing_by_mrn
    
    # ---- 检查 2: 按名字+DOB查（MRN 不同的情况）----
    existing_by_name = Patient.objects.filter(
        first_name=first_name,
        last_name=last_name,
        date_of_birth=dob,
    ).first()
    
    if existing_by_name:
        # 名字和DOB相同但 MRN 不同 → 可能是同一个人换了 MRN
        if not confirm:
            raise WarningException(
                code="DUPLICATE_PATIENT_SUSPECTED",
                message="A patient with the same name and DOB exists with a different MRN",
                detail={
                    "submitted_mrn": mrn,
                    "existing_mrn": existing_by_name.mrn,
                }
            )
    
    # 无匹配
    return None


def check_order_duplicate(patient, medication_name, confirm=False):
    """
    Order 重复检测
    
    规则：
    - 同患者 + 同药物 + 同一天 → raise BlockError（绝对不允许）
    - 同患者 + 同药物 + 不同天 → raise WarningException（confirm=True 可跳过）
    - 无匹配 → 返回 None
    
    参数:
        patient: Patient 对象
        medication_name: 药物名称
        confirm: 用户是否已确认警告
    
    返回:
        None
    """
    today = date.today()
    
    # 查找同患者 + 同药物的历史订单
    existing_orders = Order.objects.filter(
        patient=patient,
        medication_name=medication_name,
    )
    
    for order in existing_orders:
        if order.created_at.date() == today:
            # 同一天重复下单 → 必须阻止（不可跳过，即使 confirm=True）
            raise BlockError(
                code="DUPLICATE_ORDER_SAME_DAY",
                message="An order for the same patient and medication already exists today",
                detail={
                    "patient_mrn": patient.mrn,
                    "medication": medication_name,
                    "existing_order_id": order.id,
                }
            )
    
    # 不同天但有历史订单 → 警告
    if existing_orders.exists():
        if not confirm:
            latest = existing_orders.order_by('-created_at').first()
            raise WarningException(
                code="DUPLICATE_ORDER_DIFFERENT_DAY",
                message="This patient has a previous order for the same medication",
                detail={
                    "patient_mrn": patient.mrn,
                    "medication": medication_name,
                    "last_order_date": str(latest.created_at.date()),
                }
            )
    
    return None
