#!/usr/bin/env python3
"""
项目清理脚本
删除所有测试文件、临时文件和不必要的文档
只保留运行项目所需的核心文件
"""

import os
import glob
import shutil
from pathlib import Path


def get_core_files():
    """定义核心运行文件列表"""
    return {
        # 核心应用文件
        'py313_meditation_app.py',
        'run_py313_app.py', 
        'config.json',
        'config_manager.py',
        'audio_compat.py',
        'voice_profiles.py',
        'local_music_library.py',
        'high_quality_music_manager_clean.py',
        
        # 配置和依赖
        'requirements.txt',
        '.gitignore',
        'README.md',
        
        # 必要的示例配置
        'config.json.example',
        
        # 保留的部署文件（精简版）
        'deploy.sh',
        'Dockerfile',
        'docker-compose.yml'
    }


def get_core_directories():
    """定义核心目录列表"""
    return {
        'music_library',  # 音乐库
        '.git',          # Git仓库
        '.venv',         # 虚拟环境
        '__pycache__'    # Python缓存（会自动重建）
    }


def get_files_to_delete():
    """获取需要删除的文件模式"""
    return [
        # 测试文件
        'test_*.py',
        '*_test.py', 
        'test_*.wav',
        '*test*.wav',
        'check_*.py',
        'quick_test.py',
        'demo_*.py',
        'verify_*.py',
        
        # 语音样本和测试音频
        '*.wav',
        
        # 临时和生成的文档
        '*_REPORT.md',
        '*_GUIDE.md',
        '*_SUMMARY.md', 
        '*_COMPLETE.md',
        'PROJECT_*.md',
        'DEPLOYMENT_*.md',
        'IMPLEMENTATION_*.md',
        'CLEANUP_*.md',
        'SYNTAX_*.md',
        'VOICE_*.md',
        'SENTENCE_*.md',
        'LONGER_*.md',
        'INTEGRATION_*.md',
        
        # 部署和配置脚本（保留核心的）
        '*.bat',
        '*_deploy*.sh',
        '*deploy*.bat',
        'generate-*.bat',
        'fix_*.sh',
        'fix_*.bat',
        'reset_*.bat',
        'server-*.bat',
        'ssh*.bat',
        'web*.bat',
        'tencent_*.bat',
        'smart_*.bat',
        'stable_*.sh',
        'simple_*.bat',
        
        # 清理和分析工具
        'cleanup_*.py',
        'c_drive_*.py',
        'auto_cleaner.py',
        'storage_monitor.py',
        'project_organizer.py',
        'repo_prune.py',
        'vscode_migrator.py',
        
        # 临时生成的文件
        '_delete_*',
        'clean_voice_*',
        'cmdline_*',
        'default_config_*',
        'integration_*',
        'ssml_*',
        'normal_*',
        'original_*',
        'pause_*',
        'longer_*',
        'speech_[0-9]*',
        'music_[0-9]*',
        
        # 语音配置和测试工具
        'voice_*_config.py',
        'voice_naturalness_*.py',
        'voice_fix_*.py',
        'natural_voice_*.py',
        'simple_voice_*.py',
        'speech_naturalness_*.py',
        'sentence_pause_*.py',
        'longer_pause_*.py',
        'clean_voice_*.py',
        
        # API和服务文件
        'meditation_api.py',
        'start_meditation_api.py',
        'deploy_to_server.py',
        'enhanced_music_generator.py',
        'preset_music_library.py',
        
        # Web文件
        'meditation_web.html',
        
        # 其他工具
        'FastAPI_使用说明.md',
        '快速部署.bat',
        '手动部署指南.bat',
        'C盘优化完成报告.md'
    ]


def get_directories_to_delete():
    """获取需要删除的目录"""
    return [
        'speech_naturalness_tests',
        'voice_samples', 
        'nginx',
        'scripts',
        '.vscode'  # VS Code配置
    ]


def safe_delete_file(file_path):
    """安全删除文件"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"  ✓ 删除文件: {file_path}")
            return True
    except Exception as e:
        print(f"  ✗ 删除失败: {file_path} - {e}")
    return False


def safe_delete_directory(dir_path):
    """安全删除目录"""
    try:
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            shutil.rmtree(dir_path)
            print(f"  ✓ 删除目录: {dir_path}")
            return True
    except Exception as e:
        print(f"  ✗ 删除失败: {dir_path} - {e}")
    return False


def clean_project():
    """清理项目"""
    project_root = Path(".")
    core_files = get_core_files()
    core_dirs = get_core_directories()
    
    print("🧹 开始清理项目...")
    print("=" * 60)
    
    deleted_files = 0
    deleted_dirs = 0
    
    # 删除匹配模式的文件
    print("\n📁 删除测试和临时文件...")
    for pattern in get_files_to_delete():
        for file_path in glob.glob(pattern):
            if os.path.basename(file_path) not in core_files:
                if safe_delete_file(file_path):
                    deleted_files += 1
    
    # 删除指定目录
    print("\n📂 删除临时目录...")
    for dir_name in get_directories_to_delete():
        if dir_name not in core_dirs:
            if safe_delete_directory(dir_name):
                deleted_dirs += 1
    
    # 删除音频文件（除了在core目录中的）
    print("\n🎵 删除测试音频文件...")
    for wav_file in glob.glob("*.wav"):
        if safe_delete_file(wav_file):
            deleted_files += 1
    
    print("\n" + "=" * 60)
    print("📊 清理统计:")
    print(f"  🗑️ 删除文件: {deleted_files} 个")
    print(f"  🗂️ 删除目录: {deleted_dirs} 个")
    
    return deleted_files, deleted_dirs


def list_remaining_files():
    """列出清理后剩余的文件"""
    print("\n📋 清理后剩余文件:")
    print("=" * 40)
    
    # 列出根目录文件
    files = []
    dirs = []
    
    for item in os.listdir("."):
        if os.path.isfile(item):
            files.append(item)
        elif os.path.isdir(item) and not item.startswith('.'):
            dirs.append(item)
    
    # 显示目录
    print("📂 目录:")
    for dir_name in sorted(dirs):
        print(f"  {dir_name}/")
    
    # 显示核心文件
    print("\n📄 核心文件:")
    for file_name in sorted(files):
        if not file_name.startswith('.'):
            print(f"  {file_name}")
    
    print(f"\n📊 总计: {len(dirs)} 个目录, {len(files)} 个文件")


def main():
    """主清理流程"""
    print("🧹 项目文件清理工具")
    print("删除所有测试文件、临时文件和不必要的文档")
    print("只保留运行项目所需的核心文件")
    print("=" * 60)
    
    # 确认操作
    confirm = input("⚠️ 此操作将永久删除测试文件，是否继续？(y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ 操作已取消")
        return
    
    # 执行清理
    deleted_files, deleted_dirs = clean_project()
    
    # 显示结果
    list_remaining_files()
    
    print("\n✅ 项目清理完成！")
    print("🎯 现在项目只包含运行所需的核心文件")
    print("🚀 可以直接运行: python run_py313_app.py")


if __name__ == "__main__":
    main()
