"""
===============================================================================
重复检测服务 (Duplicate Detection Service)
===============================================================================

这个模块负责检测各种重复情况：Provider、Patient、Order。

【核心设计变更】
---------------
旧设计：发现问题 → 立即 raise → 用户只看到第一个错误
新设计：收集所有问题 → 返回 ValidationResult → 用户一次看到所有问题

【职责分离】
-----------
- duplicate_detection.py（本文件）：只负责「检测」，返回结果
- views.py：负责「决策」，决定是阻止还是让用户确认
- exceptions.py：负责「格式化」，定义错误响应格式

【为什么这样设计？】
------------------
医疗软件的用户体验需求：
1. 用户填了 10 个字段，3 个有问题
2. 旧设计：用户修改第 1 个，再次提交，看到第 2 个...反复 3 次
3. 新设计：用户一次看到所有 3 个问题，一次性修改

【使用示例】
-----------
    from app.duplicate_detection import check_all_duplicates
    
    result = check_all_duplicates(
        npi="1234567890",
        provider_name="Dr. Smith",
        mrn="MRN001",
        first_name="John",
        last_name="Doe",
        date_of_birth=date(1990, 1, 1),
        medication_name="Aspirin",
        confirm=False
    )
    
    if result.has_errors:
        raise ValidationException(result)
    
    if result.has_warnings:
        # 返回警告，让前端显示确认对话框
        return Response({"requires_confirmation": True, ...})
"""

from datetime import date
from typing import Optional

from django.db.models import Q

from .models import Provider, Patient, Order
from .exceptions import ValidationResult, ErrorCodes


# ============================================================================
# 主入口函数
# ============================================================================

def check_all_duplicates(
    npi: str,
    provider_name: str,
    mrn: str,
    first_name: str,
    last_name: str,
    date_of_birth: date,
    medication_name: str,
    confirm: bool = False
) -> ValidationResult:
    """
    统一重复检测入口
    
    【为什么用一个函数而不是三个？】
    1. 调用者代码更简洁（一次调用 vs 三次）
    2. 检测之间有依赖关系（Order 检测依赖 Patient 结果）
    3. 统一的 ValidationResult 管理
    
    Args:
        npi: Provider 的 NPI（National Provider Identifier）
        provider_name: Provider 名字
        mrn: Patient 的 MRN（Medical Record Number）
        first_name: Patient 名
        last_name: Patient 姓
        date_of_birth: Patient 出生日期
        medication_name: 药物名称
        confirm: 是否已确认警告（True 时跳过 warning 级别的检查）
    
    Returns:
        ValidationResult: 包含所有检测到的 errors 和 warnings
                         以及可复用的 provider/patient（如果找到）
    
    【设计决策】
    confirm 参数的作用：
    - 第一次提交：confirm=False，返回所有 warnings
    - 用户确认后重新提交：confirm=True，跳过 warning 检查
    """
    # 创建结果收集器
    result = ValidationResult()
    
    # ----- 检测流程 -----
    # 顺序很重要！后面的检测可能依赖前面的结果
    
    # 1. 检查 Provider（可能找到可复用的）
    _check_provider(result, npi, provider_name)
    
    # 2. 检查 Patient（可能找到可复用的）
    _check_patient(result, mrn, first_name, last_name, date_of_birth)
    
    # 3. 检查 Order（只有找到现有 Patient 时才需要检查）
    #    如果是新患者，不可能有重复订单
    if result.reusable_patient:
        _check_order(result, result.reusable_patient, medication_name, confirm)
    
    return result


# ============================================================================
# Provider 检测
# ============================================================================

def _check_provider(
    result: ValidationResult,
    npi: str,
    name: str
) -> None:
    """
    检查 Provider 重复
    
    【业务规则】
    NPI (National Provider Identifier) 是美国医疗提供者的唯一标识：
    - 一个 NPI 对应一个 Provider
    - 如果 NPI 相同但名字不同，说明数据有问题
    
    【检测逻辑】
    1. NPI 不存在 → 无问题，需要创建新 Provider
    2. NPI 相同 + 名字相同 → 可复用现有 Provider
    3. NPI 相同 + 名字不同 → ERROR（必须阻止）
    
    【为什么是 Error 而不是 Warning？】
    NPI 是法律要求的唯一标识，不能容忍不一致。
    - 可能是输入错误
    - 可能是欺诈行为
    无论哪种情况，都必须阻止并让用户确认
    
    Args:
        result: ValidationResult 收集器（会被修改）
        npi: Provider 的 NPI
        name: Provider 的名字
    """
    existing = Provider.objects.filter(npi=npi).first()
    
    if not existing:
        # NPI 不存在，无问题
        return
    
    # 名字比较（忽略大小写）
    if existing.name.lower() == name.lower():
        # NPI 相同 + 名字相同 → 可以复用
        result.reusable_provider = existing
        return
    
    # NPI 相同 + 名字不同 → 必须阻止
    # 【安全注意】
    # 错误消息不能包含：
    # - 现有 Provider 的名字（隐私）
    # - 数据库 ID（内部信息）
    result.add_error(
        code=ErrorCodes.DUPLICATE_NPI_MISMATCH,
        message="该 NPI 已被其他医疗提供者使用，请核实后重新输入"
    )


# ============================================================================
# Patient 检测
# ============================================================================

def _check_patient(
    result: ValidationResult,
    mrn: str,
    first_name: str,
    last_name: str,
    dob: date
) -> None:
    """
    检查 Patient 重复
    
    【业务规则】
    MRN (Medical Record Number) 是医院内部的患者标识：
    - 主要用于内部记录查找
    - 不像 NPI 那样严格唯一
    
    【检测逻辑】
    1. MRN 相同 + 信息匹配 → 可复用
    2. MRN 相同 + 信息不匹配 → WARNING（可能是同一人的旧记录）
    3. MRN 不同 + 同名同生日 → WARNING（可能是重复录入）
    
    【为什么是 Warning 而不是 Error？】
    - 同一患者可能在不同时期更新信息（改名、修正生日）
    - 可能确实需要为同一人创建新记录
    - 让用户确认比直接阻止更合理
    
    Args:
        result: ValidationResult 收集器（会被修改）
        mrn: Patient 的 MRN
        first_name: Patient 名
        last_name: Patient 姓
        dob: Patient 出生日期
    """
    # ----- 情况 1: 按 MRN 查找 -----
    existing = Patient.objects.filter(mrn=mrn).first()
    
    if existing:
        # MRN 找到了，检查信息是否匹配
        name_matches = (
            existing.first_name.lower() == first_name.lower() and
            existing.last_name.lower() == last_name.lower()
        )
        dob_matches = existing.date_of_birth == dob
        
        if name_matches and dob_matches:
            # 完全匹配 → 可复用
            result.reusable_patient = existing
            return
        
        # 信息不匹配 → 警告
        result.add_warning(
            code=ErrorCodes.PATIENT_INFO_MISMATCH,
            message="该病历号已存在，但患者信息不一致。请确认患者身份后继续。"
        )
        # 仍然设置为可复用，让用户确认后可以继续
        result.reusable_patient = existing
        return
    
    # ----- 情况 2: MRN 不存在，按 名字+DOB 查找 -----
    # 这是为了捕捉"同一患者，不同 MRN"的情况
    by_name_dob = Patient.objects.filter(
        Q(first_name__iexact=first_name) &
        Q(last_name__iexact=last_name) &
        Q(date_of_birth=dob)
    ).first()
    
    if by_name_dob:
        result.add_warning(
            code=ErrorCodes.POTENTIAL_DUPLICATE_PATIENT,
            message="系统中已存在同名同生日的患者，请确认是否为同一人。"
        )
        # 注意：这里不设置 reusable_patient
        # 因为 MRN 不同，可能确实是需要新建的
    
    # 既没有 MRN 匹配，也没有名字 DOB 匹配 → 无问题，会创建新 Patient


# ============================================================================
# Order 检测
# ============================================================================

def _check_order(
    result: ValidationResult,
    patient: Patient,
    medication_name: str,
    confirm: bool
) -> None:
    """
    检查 Order 重复
    
    【业务规则】
    防止重复开药：
    - 同一天两次开同一药 → 明显的错误，必须阻止
    - 不同天开同一药 → 可能是正常续药，只警告
    
    【检测逻辑】
    1. 同一天 + 同一药物 → ERROR
    2. 不同天 + 同一药物 → WARNING（confirm=True 时跳过）
    
    Args:
        result: ValidationResult 收集器（会被修改）
        patient: 患者对象（必须已存在）
        medication_name: 药物名称
        confirm: 用户是否已确认（True 时跳过 warning）
    """
    today = date.today()
    
    # ----- 情况 1: 同一天重复 → 必须阻止 -----
    same_day_order = Order.objects.filter(
        patient=patient,
        medication_name__iexact=medication_name,
        created_at__date=today
    ).first()
    
    if same_day_order:
        result.add_error(
            code=ErrorCodes.DUPLICATE_ORDER_SAME_DAY,
            message="今天已为该患者创建过相同药物的订单，请勿重复提交。"
        )
        # 已经是 Error，无需继续检查
        return
    
    # ----- 情况 2: 不同天重复 → 警告（可跳过） -----
    # 如果用户已确认（confirm=True），跳过这个检查
    if confirm:
        return
    
    # 使用 exists() 而不是 first()，性能更好
    # （只需要知道是否存在，不需要获取数据）
    has_previous_order = Order.objects.filter(
        patient=patient,
        medication_name__iexact=medication_name
    ).exists()
    
    if has_previous_order:
        result.add_warning(
            code=ErrorCodes.EXISTING_MEDICATION_ORDER,
            message="该患者之前已有此药物的订单记录。如需继续，请确认后重新提交。"
        )


# ============================================================================
# 附录：检测规则速查表
# ============================================================================
#
# | 实体     | 条件                      | 结果    | 可复用 |
# |----------|---------------------------|---------|--------|
# | Provider | NPI 不存在                | 通过    | 否     |
# | Provider | NPI + 名字 都匹配         | 通过    | 是     |
# | Provider | NPI 匹配 + 名字不匹配     | ERROR   | 否     |
# |----------|---------------------------|---------|--------|
# | Patient  | MRN 不存在 + 无同名同DOB  | 通过    | 否     |
# | Patient  | MRN + 信息 都匹配         | 通过    | 是     |
# | Patient  | MRN 匹配 + 信息不匹配     | WARNING | 是     |
# | Patient  | MRN 不匹配 + 有同名同DOB  | WARNING | 否     |
# |----------|---------------------------|---------|--------|
# | Order    | 同一天 + 同一药物         | ERROR   | -      |
# | Order    | 不同天 + 同一药物         | WARNING | -      |
# | Order    | 无重复                    | 通过    | -      |
#
# ============================================================================
