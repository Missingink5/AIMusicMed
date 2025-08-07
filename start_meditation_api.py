"""
FastAPI冥想应用启动脚本
"""
import os
import sys
import webbrowser
import time
from pathlib import Path

def check_dependencies():
    """检查依赖包是否已安装"""
    print("🔍 检查依赖包...")
    
    required_packages = [
        'fastapi',
        'uvicorn',
        'openai',
        'transformers',
        'torch',
        'edge_tts',
        'librosa',
        'soundfile'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"  ❌ {package}")
    
    if missing_packages:
        print(f"\n⚠️ 缺少依赖包: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements.txt")
        return False
    
    print("✅ 所有依赖包已安装")
    return True

def check_config():
    """检查配置文件"""
    print("\n🔧 检查配置文件...")
    
    config_file = Path("config.json")
    if not config_file.exists():
        print("❌ config.json 不存在")
        return False
    
    try:
        import json
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 检查关键配置
        if not config.get('api_keys', {}).get('deepseek_api_key'):
            print("❌ DeepSeek API密钥未配置")
            return False
        
        print("✅ 配置文件检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 配置文件检查失败: {e}")
        return False

def start_api_server():
    """启动FastAPI服务器"""
    print("\n🚀 启动FastAPI服务器...")
    
    try:
        import uvicorn
        
        # 在新线程中启动服务器
        def run_server():
            uvicorn.run(
                "meditation_api:app",
                host="127.0.0.1",
                port=8000,
                reload=False,
                log_level="info"
            )
        
        import threading
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # 等待服务器启动
        print("⏳ 等待服务器启动...")
        time.sleep(3)
        
        # 检查服务器是否启动成功
        try:
            import requests
            response = requests.get("http://127.0.0.1:8000/health", timeout=5)
            if response.status_code == 200:
                print("✅ 服务器启动成功")
                return True
            else:
                print(f"❌ 服务器启动失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 无法连接到服务器: {e}")
            return False
            
    except Exception as e:
        print(f"❌ 启动服务器失败: {e}")
        return False

def open_web_interface():
    """打开Web界面"""
    print("\n🌐 打开Web界面...")
    
    web_file = Path("meditation_web.html")
    if not web_file.exists():
        print("❌ meditation_web.html 不存在")
        return False
    
    try:
        # 打开本地HTML文件
        file_url = f"file:///{web_file.absolute().as_posix()}"
        webbrowser.open(file_url)
        print(f"✅ Web界面已打开: {file_url}")
        return True
        
    except Exception as e:
        print(f"❌ 打开Web界面失败: {e}")
        return False

def main():
    """主函数"""
    print("🧘‍♀️ AI冥想助手 - FastAPI版本启动器")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        input("\n按回车键退出...")
        return
    
    # 检查配置
    if not check_config():
        input("\n按回车键退出...")
        return
    
    # 启动服务器
    if not start_api_server():
        input("\n按回车键退出...")
        return
    
    # 打开Web界面
    open_web_interface()
    
    print("\n" + "=" * 50)
    print("🎉 AI冥想助手已启动！")
    print("\n📍 服务地址:")
    print("  🌐 Web界面: meditation_web.html (已自动打开)")
    print("  📚 API文档: http://127.0.0.1:8000/docs")
    print("  🔍 API状态: http://127.0.0.1:8000/status")
    print("  ❤️ 健康检查: http://127.0.0.1:8000/health")
    
    print("\n💡 使用说明:")
    print("  1. 在Web界面中输入您的烦恼或想法")
    print("  2. 选择冥想时长(1-30分钟)")
    print("  3. 点击生成按钮，等待个性化音频生成")
    print("  4. 播放音频进行冥想")
    
    print("\n⚠️ 注意事项:")
    print("  • 首次使用会下载AI模型，请耐心等待")
    print("  • 确保网络连接正常")
    print("  • 建议使用Chrome或Edge浏览器")
    
    print(f"\n按Ctrl+C停止服务器")
    
    try:
        # 保持程序运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 正在关闭服务器...")
        print("感谢使用AI冥想助手！")

if __name__ == "__main__":
    main()
