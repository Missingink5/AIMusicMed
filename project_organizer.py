#!/usr/bin/env python3
"""
项目文件整理脚本
帮助识别和整理项目中的必需文件和旧文件
"""

import os
import shutil
from typing import List, Dict
from datetime import datetime


class ProjectOrganizer:
    """项目整理器"""
    
    def __init__(self, project_dir: str = "."):
        self.project_dir = project_dir
        self.analysis = self.analyze_project()
    
    def analyze_project(self) -> Dict:
        """分析项目文件结构"""
        return {
            "core_files": {
                "description": "运行时必需的核心文件",
                "files": [
                    "py313_meditation_app.py",  # 主程序
                    "config_manager.py",        # 配置管理
                    "audio_compat.py",          # 音频兼容层
                    "voice_profiles.py",        # 语音配置
                    "preset_music_library.py",  # 预设音乐库
                    "high_quality_music_manager.py",  # 高质量音乐管理器
                    "enhanced_music_generator.py",    # 增强音乐生成器
                    "config.json",              # 配置文件
                    "requirements.txt"          # 依赖列表
                ]
            },
            "legacy_files": {
                "description": "旧版本/重复的文件（可以删除或归档）",
                "files": [
                    "complete_meditation_app.py",  # 旧版主程序
                    "improved_meditation_app.py",  # 旧版主程序
                    "AllTogether.py",              # 早期版本
                    "run_meditation_app.py",       # 对应旧版程序
                    "run_improved_app.py",         # 对应旧版程序
                    "MusicAI.py",                  # 早期音乐生成实验
                    "UserInput.py",                # 实验脚本
                    "script.py"                    # 实验脚本
                ]
            },
            "test_files": {
                "description": "测试和实验文件（可保留用于调试）",
                "files": [
                    "test_py313_compat.py",     # 兼容性测试
                    "audio_volume_test.py",     # 音量测试
                    "check_voices.py",          # 语音测试
                    "run_py313_app.py"          # 主运行脚本
                ]
            },
            "documentation": {
                "description": "文档和配置文件（保留）",
                "files": [
                    "README.md",
                    "PROJECT_ANALYSIS.md",
                    "meditation_script.json"
                ]
            },
            "data_folders": {
                "description": "数据和缓存文件夹（保留）",
                "folders": [
                    "preset_music/",
                    "voice_samples/",
                    "__pycache__/"
                ]
            }
        }
    
    def print_analysis(self):
        """打印项目分析结果"""
        print("📁 项目文件分析报告")
        print("=" * 60)
        
        for category, info in self.analysis.items():
            if category == "data_folders":
                continue
                
            print(f"\n🔸 {info['description']}")
            print("-" * 40)
            
            for file in info['files']:
                status = "✅" if os.path.exists(file) else "❌"
                size = ""
                if os.path.exists(file):
                    size_bytes = os.path.getsize(file)
                    size = f" ({size_bytes:,} bytes)"
                print(f"  {status} {file}{size}")
        
        print(f"\n🔸 数据和缓存文件夹")
        print("-" * 40)
        for folder in self.analysis["data_folders"]["folders"]:
            status = "✅" if os.path.exists(folder) else "❌"
            print(f"  {status} {folder}")
    
    def create_archive_folder(self) -> str:
        """创建归档文件夹"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_folder = f"_archived_{timestamp}"
        os.makedirs(archive_folder, exist_ok=True)
        return archive_folder
    
    def archive_legacy_files(self, confirm: bool = False):
        """归档旧文件"""
        legacy_files = self.analysis["legacy_files"]["files"]
        existing_legacy = [f for f in legacy_files if os.path.exists(f)]
        
        if not existing_legacy:
            print("📝 没有发现需要归档的旧文件")
            return
        
        print(f"\n📦 发现 {len(existing_legacy)} 个旧文件需要归档:")
        for file in existing_legacy:
            print(f"  - {file}")
        
        if not confirm:
            response = input("\n是否继续归档这些文件? (y/N): ").lower().strip()
            if response != 'y':
                print("❌ 归档操作已取消")
                return
        
        # 创建归档文件夹
        archive_folder = self.create_archive_folder()
        print(f"\n📁 创建归档文件夹: {archive_folder}")
        
        # 移动文件
        for file in existing_legacy:
            try:
                shutil.move(file, os.path.join(archive_folder, file))
                print(f"  ✅ 已归档: {file}")
            except Exception as e:
                print(f"  ❌ 归档失败 {file}: {e}")
        
        print(f"\n🎉 归档完成! 旧文件已移动到: {archive_folder}")
    
    def verify_core_files(self):
        """验证核心文件完整性"""
        print("\n🔍 验证核心文件完整性")
        print("-" * 40)
        
        core_files = self.analysis["core_files"]["files"]
        missing_files = []
        
        for file in core_files:
            if os.path.exists(file):
                print(f"  ✅ {file}")
            else:
                print(f"  ❌ {file} (缺失)")
                missing_files.append(file)
        
        if missing_files:
            print(f"\n⚠️ 警告: 发现 {len(missing_files)} 个缺失的核心文件:")
            for file in missing_files:
                print(f"  - {file}")
            print("\n建议重新创建这些文件以确保程序正常运行")
        else:
            print("\n🎉 所有核心文件都存在!")
    
    def get_project_size(self) -> Dict:
        """获取项目大小统计"""
        total_size = 0
        file_count = 0
        
        for root, dirs, files in os.walk(self.project_dir):
            # 跳过缓存和虚拟环境文件夹
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for file in files:
                if not file.startswith('.'):
                    file_path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(file_path)
                        total_size += size
                        file_count += 1
                    except (OSError, IOError):
                        pass
        
        return {
            "total_size": total_size,
            "file_count": file_count,
            "size_mb": total_size / (1024 * 1024)
        }
    
    def generate_summary(self):
        """生成项目摘要"""
        stats = self.get_project_size()
        
        print("\n📊 项目摘要")
        print("=" * 40)
        print(f"总文件数: {stats['file_count']}")
        print(f"总大小: {stats['size_mb']:.2f} MB")
        
        core_exists = sum(1 for f in self.analysis['core_files']['files'] if os.path.exists(f))
        core_total = len(self.analysis['core_files']['files'])
        
        legacy_exists = sum(1 for f in self.analysis['legacy_files']['files'] if os.path.exists(f))
        
        print(f"核心文件: {core_exists}/{core_total}")
        print(f"旧文件: {legacy_exists}")
        
        if core_exists == core_total and legacy_exists == 0:
            print("\n🎉 项目结构已优化!")
        elif core_exists == core_total:
            print(f"\n🟡 项目可以运行，但建议归档 {legacy_exists} 个旧文件")
        else:
            print(f"\n🔴 项目缺少 {core_total - core_exists} 个核心文件")


def main():
    """主函数"""
    print("🎯 冥想应用项目整理工具")
    print("=" * 60)
    
    organizer = ProjectOrganizer()
    
    # 显示分析结果
    organizer.print_analysis()
    
    # 验证核心文件
    organizer.verify_core_files()
    
    # 生成摘要
    organizer.generate_summary()
    
    # 询问是否归档旧文件
    legacy_files = organizer.analysis["legacy_files"]["files"]
    existing_legacy = [f for f in legacy_files if os.path.exists(f)]
    
    if existing_legacy:
        print(f"\n🗂️ 发现 {len(existing_legacy)} 个旧文件可以归档")
        response = input("是否现在归档这些旧文件? (y/N): ").lower().strip()
        if response == 'y':
            organizer.archive_legacy_files(confirm=True)


if __name__ == "__main__":
    main()
