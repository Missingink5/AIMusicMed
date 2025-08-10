#!/usr/bin/env python3
"""
DeepSeek API 连接测试
"""

import requests
import json
from config_manager import load_config

def test_deepseek_api():
    print("🔧 DeepSeek API 连接测试")
    print("=" * 40)
    
    try:
        # 加载配置
        config = load_config()
        
        api_key = config.api.deepseek_api_key
        base_url = config.api.deepseek_base_url
        
        print(f"📡 API URL: {base_url}")
        print(f"🔑 API Key: {'已设置' if api_key else '未设置'}")
        
        if not api_key:
            print("❌ API Key 未设置，请在 config.json 中配置")
            return False
        
        print(f"🔑 Key 前缀: {api_key[:10]}...")
        
        # 测试API连接
        print("\n🚀 正在测试API连接...")
        
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": "你好，请简单回复一下测试API连接"}
            ],
            "max_tokens": 50,
            "temperature": 0.7
        }
        
        print("📤 发送测试请求...")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        print(f"📊 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            print(f"✅ API连接成功!")
            print(f"🤖 AI回复: {content}")
            
            # 检查用量信息
            if 'usage' in response_data:
                usage = response_data['usage']
                print(f"📈 Token使用: 输入{usage.get('prompt_tokens', 0)}, 输出{usage.get('completion_tokens', 0)}")
            
            return True
            
        else:
            print(f"❌ API请求失败")
            print(f"错误信息: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时，可能是网络问题")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误，请检查网络和API地址")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_emotion_prompts_generation():
    """测试情绪转换提示词生成"""
    print("\n🎭 测试情绪转换提示词生成")
    print("=" * 40)
    
    try:
        from py313_meditation_app import MeditationApp
        
        app = MeditationApp()
        user_input = "我最近工作压力很大，心情很焦虑"
        
        print(f"💭 测试输入: {user_input}")
        print("🤖 正在生成情绪转换提示词...")
        
        prompts_data = app.generate_prompts(user_input, 3)  # 3分钟快速测试
        
        print("✅ 提示词生成成功!")
        print(f"🧠 分析结果: {prompts_data['analysis'][:100]}...")
        print(f"🎭 情绪旅程: {prompts_data['emotion_journey']}")
        print(f"📝 生成了 {len(prompts_data['script_prompts'])} 段引导语")
        print(f"🎵 生成了 {len(prompts_data['music_prompts'])} 段音乐描述")
        
        return True
        
    except Exception as e:
        print(f"❌ 提示词生成测试失败: {e}")
        return False

if __name__ == "__main__":
    # 测试基础API连接
    api_success = test_deepseek_api()
    
    if api_success:
        # 测试完整功能
        test_emotion_prompts_generation()
    else:
        print("\n💡 解决建议:")
        print("1. 检查 config.json 中的 deepseek_api_key")
        print("2. 确认网络连接正常")
        print("3. 验证API key是否有效")
        print("4. 检查是否有余额")
    
    print("\n" + "=" * 40)
