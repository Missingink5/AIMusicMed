#!/usr/bin/env python3
"""
验证API配置
"""

from py313_meditation_app import MeditationApp

def check_api_config():
    print("🔧 检查API配置...")
    
    try:
        app = MeditationApp()
        
        api_key = app.config.api.deepseek_api_key
        api_url = app.config.api.deepseek_base_url
        
        print(f"✅ API Key: {'已设置' if api_key else '未设置'}")
        print(f"🌐 API URL: {api_url}")
        
        if api_key:
            print(f"🔑 Key 前缀: {api_key[:10]}...")
        else:
            print("⚠️ 请在 config.json 中设置 deepseek_api_key")
            
    except Exception as e:
        print(f"❌ 配置检查失败: {e}")

if __name__ == "__main__":
    check_api_config()
