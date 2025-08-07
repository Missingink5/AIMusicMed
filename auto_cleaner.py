"""
自动清理模块 - 定期清理老文件以释放存储空间
"""
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta


class AutoCleaner:
    def __init__(self, config_path="config.json"):
        """初始化自动清理器"""
        self.config_path = config_path
        self.load_cleanup_config()
    
    def load_cleanup_config(self):
        """加载清理配置"""
        default_config = {
            "auto_cleanup_temp": True,
            "max_session_files": 3,
            "cleanup_older_than_days": 3,
            "force_d_drive_cache": True
        }
        
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.cleanup_config = config.get("cleanup_settings", default_config)
        else:
            self.cleanup_config = default_config
    
    def cleanup_old_sessions(self, base_dir="D:/MyMeditationApp"):
        """清理旧的冥想会话文件"""
        if not self.cleanup_config.get("auto_cleanup_temp", True):
            return
        
        print("🧹 开始清理旧会话文件...")
        base_path = Path(base_dir)
        
        if not base_path.exists():
            return
        
        # 获取所有冥想会话文件
        session_files = list(base_path.glob("meditation_session_*.mp3")) + \
                       list(base_path.glob("meditation_session_*.wav"))
        
        # 按修改时间排序
        session_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        max_files = self.cleanup_config.get("max_session_files", 3)
        cleanup_days = self.cleanup_config.get("cleanup_older_than_days", 3)
        cutoff_time = time.time() - (cleanup_days * 24 * 3600)
        
        removed_count = 0
        removed_size = 0
        
        # 删除超过数量限制的文件
        if len(session_files) > max_files:
            for file in session_files[max_files:]:
                file_size = file.stat().st_size
                file.unlink()
                removed_count += 1
                removed_size += file_size
                print(f"  ✓ 删除旧文件: {file.name}")
        
        # 删除超过时间限制的文件
        for file in session_files[:max_files]:
            if file.stat().st_mtime < cutoff_time:
                file_size = file.stat().st_size
                file.unlink()
                removed_count += 1
                removed_size += file_size
                print(f"  ✓ 删除过期文件: {file.name}")
        
        if removed_count > 0:
            removed_mb = removed_size / (1024 * 1024)
            print(f"✅ 清理完成: 删除了 {removed_count} 个文件，释放 {removed_mb:.1f} MB")
        else:
            print("✅ 无需清理，文件数量正常")
    
    def cleanup_temp_files(self, temp_dir="D:/MyMeditationApp/temp"):
        """清理临时文件"""
        print("🧹 清理临时文件...")
        temp_path = Path(temp_dir)
        
        if not temp_path.exists():
            return
        
        removed_count = 0
        removed_size = 0
        
        for file in temp_path.iterdir():
            if file.is_file():
                file_size = file.stat().st_size
                file.unlink()
                removed_count += 1
                removed_size += file_size
        
        if removed_count > 0:
            removed_mb = removed_size / (1024 * 1024)
            print(f"✅ 临时文件清理完成: 删除了 {removed_count} 个文件，释放 {removed_mb:.1f} MB")
        else:
            print("✅ 临时文件夹已清空")
    
    def check_disk_space(self, path="D:/MyMeditationApp"):
        """检查磁盘空间使用情况"""
        print("📊 检查磁盘空间...")
        
        app_path = Path(path)
        if not app_path.exists():
            return
        
        # 计算应用占用的空间
        total_size = 0
        file_count = 0
        
        for file in app_path.rglob('*'):
            if file.is_file():
                total_size += file.stat().st_size
                file_count += 1
        
        total_mb = total_size / (1024 * 1024)
        total_gb = total_mb / 1024
        
        print(f"📁 应用总占用: {total_gb:.2f} GB ({total_mb:.1f} MB)")
        print(f"📄 文件总数: {file_count}")
        
        # 分类统计
        categories = {
            "音频文件": ["*.mp3", "*.wav"],
            "缓存文件": ["cache/*"],
            "临时文件": ["temp/*"],
            "配置文件": ["*.json", "*.md", "*.txt"]
        }
        
        for category, patterns in categories.items():
            category_size = 0
            category_count = 0
            
            for pattern in patterns:
                files = list(app_path.glob(pattern))
                for file in files:
                    if file.is_file():
                        category_size += file.stat().st_size
                        category_count += 1
            
            if category_size > 0:
                category_mb = category_size / (1024 * 1024)
                print(f"  {category}: {category_mb:.1f} MB ({category_count} 文件)")
    
    def auto_cleanup(self):
        """执行自动清理"""
        print("🔧 开始自动清理...")
        print("=" * 40)
        
        self.cleanup_temp_files()
        self.cleanup_old_sessions()
        self.check_disk_space()
        
        print("=" * 40)
        print("✨ 自动清理完成")


def clean_before_session():
    """会话开始前的清理"""
    cleaner = AutoCleaner()
    cleaner.cleanup_temp_files()


def clean_after_session():
    """会话结束后的清理"""
    cleaner = AutoCleaner()
    cleaner.cleanup_old_sessions()


if __name__ == "__main__":
    cleaner = AutoCleaner()
    cleaner.auto_cleanup()
