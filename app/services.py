"""
======================================
LLM 服务层
======================================

这个文件封装了所有 LLM 调用逻辑。
通过环境变量 USE_MOCK_LLM 可以切换真实 LLM 和 Mock 版本。

使用方式：
    # 开发/测试环境（使用 Mock）
    export USE_MOCK_LLM=true

    # 生产环境（使用真实 LLM）
    export USE_MOCK_LLM=false  # 或者不设置
"""

import os
import time


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