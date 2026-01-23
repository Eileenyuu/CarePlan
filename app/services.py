import os
import google.generativeai as genai

def get_gemini_response(prompt):
    """
    统一管理 Gemini 的配置和调用
    """
    # 1. 配置 API Key
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    
    # 2. 统一管理模型名称：在这里修改模型版本，全站都会生效
    # 建议使用 gemini-1.5-flash (快且免费额度高) 或 gemini-1.5-pro
    model_name = 'gemini-2.5-flash' 
    
    model = genai.GenerativeModel(model_name)
    
    # 3. 执行调用
    response = model.generate_content(prompt)
    return response.text