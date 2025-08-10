#!/usr/bin/env python3
"""
快速部署脚本 - 将本地代码同步到GPU服务器

使用方法:
1. 确保已配置SSH密钥或密码登录
2. 修改服务器IP和路径配置
3. 运行: python deploy_to_server.py
"""

import os
import subprocess
import sys
import time

# 服务器配置
SERVER_CONFIG = {
    "host": "你的服务器IP",  # 替换为实际IP
    "user": "root",
    "remote_path": "/app",
    "ssh_key": None  # 如果使用SSH密钥，指定路径
}

# 需要同步的文件列表
SYNC_FILES = [
    "py313_meditation_app.py",
    "config_manager.py", 
    "audio_compat.py",
    "local_music_library.py",
    "voice_profiles.py",
    "config.json",
    "requirements.txt",
    "music_library/",
    "test_local_music.py"
]

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n🔄 {description}")
    print(f"命令: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 成功")
            if result.stdout.strip():
                print(f"输出: {result.stdout.strip()}")
        else:
            print(f"❌ 失败")
            print(f"错误: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False
    
    return True

def sync_to_server():
    """同步代码到服务器"""
    
    host = SERVER_CONFIG["host"]
    user = SERVER_CONFIG["user"]
    remote_path = SERVER_CONFIG["remote_path"]
    
    if host == "你的服务器IP":
        print("❌ 请先配置服务器IP地址")
        print("编辑 deploy_to_server.py 文件，修改 SERVER_CONFIG 中的 host")
        return False
    
    print(f"🚀 开始部署到服务器: {user}@{host}:{remote_path}")
    
    # 1. 测试SSH连接
    test_cmd = f"ssh {user}@{host} 'echo \"SSH连接成功\"'"
    if not run_command(test_cmd, "测试SSH连接"):
        print("❌ SSH连接失败，请检查:")
        print("1. 服务器IP是否正确")
        print("2. SSH密钥或密码是否配置正确")
        print("3. 防火墙设置是否允许SSH连接")
        return False
    
    # 2. 创建远程目录
    create_dir_cmd = f"ssh {user}@{host} 'mkdir -p {remote_path}'"
    run_command(create_dir_cmd, "创建远程目录")
    
    # 3. 同步文件
    for file_item in SYNC_FILES:
        if os.path.exists(file_item):
            if os.path.isdir(file_item):
                # 目录
                rsync_cmd = f"rsync -avz --delete {file_item}/ {user}@{host}:{remote_path}/{file_item}/"
            else:
                # 文件
                rsync_cmd = f"rsync -avz {file_item} {user}@{host}:{remote_path}/"
            
            if not run_command(rsync_cmd, f"同步 {file_item}"):
                print(f"⚠️ {file_item} 同步失败，继续...")
        else:
            print(f"⚠️ 文件不存在，跳过: {file_item}")
    
    # 4. 设置权限
    chmod_cmd = f"ssh {user}@{host} 'chmod +x {remote_path}/*.py'"
    run_command(chmod_cmd, "设置执行权限")
    
    # 5. 验证文件
    verify_cmd = f"ssh {user}@{host} 'ls -la {remote_path}/'"
    run_command(verify_cmd, "验证远程文件")
    
    print(f"\n🎉 部署完成！")
    print(f"📁 远程路径: {user}@{host}:{remote_path}")
    print(f"🔗 SSH连接: ssh {user}@{host}")
    
    return True

def install_dependencies():
    """在服务器上安装依赖"""
    
    host = SERVER_CONFIG["host"]
    user = SERVER_CONFIG["user"] 
    remote_path = SERVER_CONFIG["remote_path"]
    
    print(f"\n📦 在服务器上安装Python依赖...")
    
    # 安装依赖
    install_cmd = f"""ssh {user}@{host} '
    cd {remote_path} && 
    python3 -m pip install --upgrade pip && 
    python3 -m pip install -r requirements.txt
    '"""
    
    return run_command(install_cmd, "安装Python依赖")

def test_deployment():
    """测试部署结果"""
    
    host = SERVER_CONFIG["host"]
    user = SERVER_CONFIG["user"]
    remote_path = SERVER_CONFIG["remote_path"]
    
    print(f"\n🧪 测试部署结果...")
    
    # 测试导入
    test_cmd = f"""ssh {user}@{host} '
    cd {remote_path} && 
    python3 -c "
    try:
        from local_music_library import LocalMusicLibrary
        print(\"✅ LocalMusicLibrary 导入成功\")
        
        lib = LocalMusicLibrary(\"music_library\")
        status = lib.get_library_status()
        print(f\"📊 音乐库状态: {status}\")
        
    except Exception as e:
        print(f\"❌ 测试失败: {e}\")
    "
    '"""
    
    return run_command(test_cmd, "测试核心功能")

def main():
    """主函数"""
    
    print("🚀 冥想应用部署脚本")
    print("=" * 50)
    
    # 检查本地文件
    missing_files = []
    for file_item in SYNC_FILES:
        if not os.path.exists(file_item):
            missing_files.append(file_item)
    
    if missing_files:
        print("⚠️ 以下文件缺失:")
        for file in missing_files:
            print(f"  - {file}")
        print("\n继续部署现有文件...")
    
    # 开始部署
    if not sync_to_server():
        print("❌ 部署失败")
        sys.exit(1)
    
    # 询问是否安装依赖
    response = input("\n是否安装Python依赖？(y/n): ").lower().strip()
    if response in ['y', 'yes', '是']:
        install_dependencies()
    
    # 询问是否测试
    response = input("\n是否运行部署测试？(y/n): ").lower().strip() 
    if response in ['y', 'yes', '是']:
        test_deployment()
    
    print(f"\n✅ 部署流程完成！")
    print(f"\n下一步操作:")
    print(f"1. SSH到服务器: ssh {SERVER_CONFIG['user']}@{SERVER_CONFIG['host']}")
    print(f"2. 切换目录: cd {SERVER_CONFIG['remote_path']}")
    print(f"3. 测试本地音乐库: python3 test_local_music.py")
    print(f"4. 运行应用: python3 py313_meditation_app.py")

if __name__ == "__main__":
    main()
