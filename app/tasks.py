"""
======================================
Celery 异步任务定义
======================================

这个文件定义了所有的异步任务。
每个任务都是一个用 @shared_task 装饰的函数。

重要概念：
- @shared_task: 让任务可以被任何 Celery 应用使用（比 @app.task 更灵活）
- bind=True: 让任务可以访问 self（用于重试等操作）
- autoretry_for: 指定哪些异常会触发自动重试
- retry_backoff: 指数退避，每次重试等待时间翻倍
"""

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError


# ============================================
# 主任务：生成 Care Plan
# ============================================
@shared_task(
    bind=True,                          # 绑定 self，可以访问任务实例
    autoretry_for=(Exception,),         # 任何异常都会触发重试
    retry_kwargs={'max_retries': 3},    # 最多重试 3 次
    retry_backoff=True,                 # 启用指数退避
    retry_backoff_max=600,              # 最大退避时间 10 分钟
    retry_jitter=True,                  # 添加随机抖动，避免重试风暴
)
def generate_care_plan_task(self, careplan_id):
    """
    异步生成 Care Plan 的 Celery 任务
    
    参数:
        self: 任务实例（因为 bind=True）
        careplan_id: CarePlan 的主键 ID
    
    重试机制说明：
    - 第 1 次重试：等待 ~1 秒
    - 第 2 次重试：等待 ~2 秒
    - 第 3 次重试：等待 ~4 秒
    - 如果还是失败，标记任务为 failed
    
    调用方式：
        # 异步调用（推荐）
        generate_care_plan_task.delay(careplan_id)
        
        # 或者带更多选项
        generate_care_plan_task.apply_async(
            args=[careplan_id],
            countdown=60  # 60秒后执行
        )
    """
    # 导入放在函数内部，避免循环导入问题
    from app.models import CarePlan
    from app.services import get_gemini_response
    
    print(f"📋 [Celery] 开始处理任务 ID: {careplan_id}")
    print(f"   当前重试次数: {self.request.retries}/{self.max_retries}")
    
    try:
        # -------- 1. 获取 CarePlan --------
        care_plan = CarePlan.objects.get(id=careplan_id)
        print(f"   患者: {care_plan.patient_first_name} {care_plan.patient_last_name}")
        
        # -------- 2. 更新状态为 processing --------
        care_plan.status = 'processing'
        care_plan.save()
        print("   状态: pending → processing")
        
        # -------- 3. 构建 Prompt --------
        prompt = f'''Generate a comprehensive Specialty Pharmacy Care Plan for:

Patient: {care_plan.patient_first_name} {care_plan.patient_last_name}
DOB: {care_plan.patient_dob}
MRN: {care_plan.patient_mrn}
Medication: {care_plan.medication_name}
Primary Diagnosis (ICD-10): {care_plan.patient_primary_diagnosis}
Additional Diagnoses: {care_plan.additional_diagnosis}
Medication History: {care_plan.medication_history}
Clinical Notes: {care_plan.clinical_notes}

Please include (simply and concisely):
1. Problem List / Drug Therapy Problems (DTPs)
2. SMART Goals
3. Pharmacist Interventions/Plan
4. Monitoring Plan & Lab Schedule
'''
        
        # -------- 4. 调用 LLM --------
        print("   🤖 正在调用 LLM 生成 Care Plan...")
        generated_plan = get_gemini_response(prompt)
        
        # -------- 5. 保存结果 --------
        care_plan.generated_plan = generated_plan
        care_plan.status = 'completed'
        care_plan.save()
        
        print("   ✅ 任务完成！状态: processing → completed")
        print(f"   生成内容长度: {len(generated_plan)} 字符")
        
        return {
            'status': 'success',
            'careplan_id': careplan_id,
            'content_length': len(generated_plan)
        }
        
    except CarePlan.DoesNotExist:
        # 找不到记录，不需要重试
        print(f"   ❌ 错误: 找不到 ID 为 {careplan_id} 的 CarePlan")
        # 不抛出异常，直接返回失败
        return {
            'status': 'error',
            'careplan_id': careplan_id,
            'error': 'CarePlan not found'
        }
        
    except Exception as e:
        # 其他错误，Celery 会自动重试
        print(f"   ⚠️ 错误: {e}")
        print(f"   将进行第 {self.request.retries + 1} 次重试...")
        
        # 如果已经是最后一次重试，更新状态为 failed
        if self.request.retries >= self.max_retries:
            try:
                care_plan = CarePlan.objects.get(id=careplan_id)
                care_plan.status = 'failed'
                care_plan.save()
                print("   ❌ 重试次数用尽，状态已更新为: failed")
            except:
                pass
        
        # 重新抛出异常，让 Celery 处理重试
        raise


# ============================================
# 辅助任务：批量处理
# ============================================
@shared_task
def process_pending_careplans():
    """
    处理所有 pending 状态的 CarePlan
    
    这个任务可以配合 Celery Beat 定时执行
    例如：每 5 分钟检查一次是否有遗漏的任务
    
    使用方式：
        process_pending_careplans.delay()
    """
    from app.models import CarePlan
    
    pending_plans = CarePlan.objects.filter(status='pending')
    count = pending_plans.count()
    
    if count == 0:
        print("📭 没有待处理的 CarePlan")
        return {'processed': 0}
    
    print(f"📬 发现 {count} 个待处理的 CarePlan")
    
    for care_plan in pending_plans:
        # 为每个 CarePlan 创建一个异步任务
        generate_care_plan_task.delay(care_plan.id)
        print(f"   → 已添加任务: CarePlan #{care_plan.id}")
    
    return {'processed': count}
