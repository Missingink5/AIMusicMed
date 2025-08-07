"""
API测试脚本
测试冥想助手的各个API端点
"""
import requests
import json
import time
from datetime import datetime

class MeditationAPITester:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def test_health_check(self):
        """测试健康检查端点"""
        print("🔍 测试健康检查...")
        try:
            response = self.session.get(f"{self.base_url}/health")
            print(f"状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"健康状态: {data.get('status')}")
                print(f"检查项目: {data.get('checks')}")
                return True
            else:
                print(f"健康检查失败: {response.text}")
                return False
        except Exception as e:
            print(f"健康检查错误: {e}")
            return False
    
    def test_app_status(self):
        """测试应用状态端点"""
        print("\n📊 测试应用状态...")
        try:
            response = self.session.get(f"{self.base_url}/status")
            print(f"状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"应用状态: {data.get('status')}")
                print(f"版本: {data.get('version')}")
                print(f"Python版本: {data.get('python_version')}")
                print(f"AI模型已加载: {data.get('ai_models_loaded')}")
                print(f"活跃会话: {data.get('active_sessions')}")
                print(f"总会话数: {data.get('total_sessions')}")
                print(f"运行时间: {data.get('uptime_seconds'):.1f}秒")
                return True
            else:
                print(f"状态查询失败: {response.text}")
                return False
        except Exception as e:
            print(f"状态查询错误: {e}")
            return False
    
    def test_create_meditation_async(self):
        """测试异步创建冥想会话"""
        print("\n🧘‍♀️ 测试异步创建冥想会话...")
        
        test_request = {
            "user_input": "我最近工作压力很大，总是失眠，感觉很焦虑。",
            "duration_minutes": 2,
            "cleanup": True
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/meditation/create",
                json=test_request
            )
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                session_id = data.get('session_id')
                print(f"会话ID: {session_id}")
                print(f"状态: {data.get('status')}")
                print(f"消息: {data.get('message')}")
                
                # 轮询状态
                return self.poll_session_status(session_id)
            else:
                print(f"创建会话失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"创建会话错误: {e}")
            return False
    
    def poll_session_status(self, session_id, max_wait_minutes=5):
        """轮询会话状态"""
        print(f"\n⏳ 轮询会话状态: {session_id}")
        
        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60
        
        while time.time() - start_time < max_wait_seconds:
            try:
                response = self.session.get(f"{self.base_url}/meditation/status/{session_id}")
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status')
                    progress = data.get('progress', 0)
                    
                    print(f"  状态: {status}, 进度: {progress}%")
                    
                    if status == 'completed':
                        result = data.get('result')
                        if result:
                            print(f"✅ 会话完成!")
                            print(f"  音频URL: {result.get('audio_url')}")
                            print(f"  时长: {result.get('duration_seconds')}秒")
                            print(f"  安慰语: {result.get('comfort_message')}")
                            print(f"  段落数: {result.get('segments_count')}")
                            return True
                        else:
                            print("❌ 会话完成但无结果")
                            return False
                    
                    elif status == 'error':
                        print(f"❌ 会话处理失败: {data.get('message')}")
                        return False
                    
                    # 继续等待
                    time.sleep(2)
                    
                else:
                    print(f"查询状态失败: {response.status_code}")
                    return False
                    
            except Exception as e:
                print(f"查询状态错误: {e}")
                return False
        
        print(f"⏰ 等待超时 ({max_wait_minutes}分钟)")
        return False
    
    def test_create_meditation_sync(self):
        """测试同步创建冥想会话"""
        print("\n🚀 测试同步创建冥想会话...")
        
        test_request = {
            "user_input": "我需要放松一下，最近总是想太多。",
            "duration_minutes": 1,
            "cleanup": True
        }
        
        try:
            print("⏳ 发送请求...")
            response = self.session.post(
                f"{self.base_url}/meditation/create-sync",
                json=test_request,
                timeout=300  # 5分钟超时
            )
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ 同步创建成功!")
                print(f"  会话ID: {data.get('session_id')}")
                print(f"  状态: {data.get('status')}")
                print(f"  音频URL: {data.get('audio_url')}")
                print(f"  时长: {data.get('duration_seconds')}秒")
                print(f"  安慰语: {data.get('comfort_message')}")
                print(f"  段落数: {data.get('segments_count')}")
                return True
            else:
                print(f"同步创建失败: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print("⏰ 请求超时")
            return False
        except Exception as e:
            print(f"同步创建错误: {e}")
            return False
    
    def test_list_sessions(self):
        """测试获取会话列表"""
        print("\n📋 测试获取会话列表...")
        try:
            response = self.session.get(f"{self.base_url}/meditation/sessions?limit=5")
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                sessions = response.json()
                print(f"会话数量: {len(sessions)}")
                
                for i, session in enumerate(sessions):
                    print(f"  会话 {i+1}:")
                    print(f"    ID: {session.get('session_id')}")
                    print(f"    状态: {session.get('status')}")
                    print(f"    创建时间: {session.get('created_at')}")
                    print(f"    音频URL: {session.get('audio_url')}")
                
                return True
            else:
                print(f"获取会话列表失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"获取会话列表错误: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🧪 开始API测试")
        print("=" * 50)
        
        results = {}
        
        # 基础测试
        results['health_check'] = self.test_health_check()
        results['app_status'] = self.test_app_status()
        
        # 功能测试
        results['list_sessions'] = self.test_list_sessions()
        
        # 冥想会话测试（选择一种方式）
        print("\n🤔 选择测试方式:")
        print("1. 异步创建（后台处理，需要轮询）")
        print("2. 同步创建（直接等待结果）")
        
        try:
            choice = input("请选择 (1 或 2，直接回车默认选择2): ").strip()
            if choice == '1':
                results['meditation_async'] = self.test_create_meditation_async()
            else:
                results['meditation_sync'] = self.test_create_meditation_sync()
        except KeyboardInterrupt:
            print("\n用户取消测试")
            results['meditation'] = False
        
        # 显示结果
        print("\n" + "=" * 50)
        print("🏁 测试结果:")
        
        passed = 0
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ 通过" if result else "❌ 失败"
            print(f"  {test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\n📊 总计: {passed}/{total} 测试通过")
        
        if passed == total:
            print("🎉 所有测试通过！API服务运行正常")
        else:
            print("⚠️ 部分测试失败，请检查服务状态")
        
        return results

def main():
    """主函数"""
    print("🔧 AI冥想助手 API 测试工具")
    print("=" * 50)
    
    # 检查服务器是否运行
    tester = MeditationAPITester()
    
    print("🔍 检查服务器连接...")
    try:
        response = requests.get("http://127.0.0.1:8000/", timeout=5)
        if response.status_code == 200:
            print("✅ 服务器连接正常")
        else:
            print(f"⚠️ 服务器响应异常: {response.status_code}")
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        print("请确保服务器已启动: python start_meditation_api.py")
        input("\n按回车键退出...")
        return
    
    # 运行测试
    tester.run_all_tests()
    
    input("\n按回车键退出...")

if __name__ == "__main__":
    main()
