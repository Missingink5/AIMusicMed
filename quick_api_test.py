"""
简单的API测试 - 测试基本功能
"""
import requests
import json

def test_basic_api():
    """测试基本API功能"""
    base_url = "http://127.0.0.1:8000"
    
    print("🧪 FastAPI冥想应用 - 基本功能测试")
    print("=" * 50)
    
    # 1. 健康检查
    print("1. 🔍 健康检查...")
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ 健康状态: {data['status']}")
        else:
            print(f"   ❌ 健康检查失败: {response.status_code}")
    except Exception as e:
        print(f"   ❌ 健康检查错误: {e}")
    
    # 2. 应用状态
    print("\n2. 📊 应用状态...")
    try:
        response = requests.get(f"{base_url}/status")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ 应用状态: {data['status']}")
            print(f"   📌 版本: {data['version']}")
            print(f"   🐍 Python版本: {data['python_version']}")
            print(f"   🤖 AI模型已加载: {data['ai_models_loaded']}")
            print(f"   📈 运行时间: {data['uptime_seconds']:.1f}秒")
        else:
            print(f"   ❌ 状态查询失败: {response.status_code}")
    except Exception as e:
        print(f"   ❌ 状态查询错误: {e}")
    
    # 3. 创建异步会话（快速测试）
    print("\n3. 🚀 创建异步冥想会话...")
    try:
        test_data = {
            "user_input": "我需要快速测试API功能",
            "duration_minutes": 1,
            "cleanup": True
        }
        
        response = requests.post(f"{base_url}/meditation/create", json=test_data)
        if response.status_code == 200:
            result = response.json()
            session_id = result['session_id']
            print(f"   ✅ 会话创建成功")
            print(f"   🆔 会话ID: {session_id}")
            print(f"   📝 状态: {result['status']}")
            print(f"   💬 消息: {result['message']}")
            
            # 检查会话状态
            print(f"\n4. 🔍 检查会话状态...")
            status_response = requests.get(f"{base_url}/meditation/status/{session_id}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"   📊 会话状态: {status_data['status']}")
                print(f"   📈 进度: {status_data.get('progress', 0)}%")
            
        else:
            print(f"   ❌ 会话创建失败: {response.status_code}")
            print(f"   📄 错误详情: {response.text}")
    except Exception as e:
        print(f"   ❌ 会话创建错误: {e}")
    
    # 5. 会话列表
    print("\n5. 📋 获取会话列表...")
    try:
        response = requests.get(f"{base_url}/meditation/sessions?limit=3")
        if response.status_code == 200:
            sessions = response.json()
            print(f"   ✅ 会话数量: {len(sessions)}")
            for i, session in enumerate(sessions[:3]):
                print(f"   📝 会话 {i+1}: {session['session_id']} ({session['status']})")
        else:
            print(f"   ❌ 获取会话列表失败: {response.status_code}")
    except Exception as e:
        print(f"   ❌ 获取会话列表错误: {e}")
    
    print("\n" + "=" * 50)
    print("✅ 基本功能测试完成！")
    print("\n💡 接下来可以:")
    print("   🌐 打开 http://127.0.0.1:8000/docs 查看完整API文档")
    print("   📱 使用 meditation_web.html 进行Web界面测试")
    print("   🧪 运行完整测试: python test_meditation_api.py")

if __name__ == "__main__":
    test_basic_api()
