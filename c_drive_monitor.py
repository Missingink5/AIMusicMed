"""
实时C盘缓存监控脚本
用于监控运行期间C盘缓存的变化
"""
import os
import time
import shutil
from pathlib import Path


class CDriveMonitor:
    def __init__(self):
        self.initial_sizes = {}
        self.cache_paths = [
            Path.home() / ".cache" / "huggingface",
            Path.home() / ".cache" / "transformers",
            Path.home() / ".cache" / "torch",
            Path(os.environ.get("APPDATA", "")) / "torch" if os.environ.get("APPDATA") else None,
            Path(os.environ.get("LOCALAPPDATA", "")) / "torch" if os.environ.get("LOCALAPPDATA") else None,
        ]
    
    def get_cache_sizes(self):
        """获取缓存目录大小"""
        sizes = {}
        for cache_path in self.cache_paths:
            if cache_path and cache_path.exists():
                try:
                    size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file())
                    sizes[str(cache_path)] = size
                except:
                    sizes[str(cache_path)] = 0
            else:
                sizes[str(cache_path)] = 0
        return sizes
    
    def start_monitoring(self):
        """开始监控"""
        print("🔍 开始C盘缓存监控...")
        self.initial_sizes = self.get_cache_sizes()
        
        # 显示初始状态
        total_initial = sum(self.initial_sizes.values()) / (1024*1024)
        print(f"📊 初始C盘缓存总大小: {total_initial:.1f} MB")
        
        for path, size in self.initial_sizes.items():
            if size > 0:
                print(f"   {Path(path).name}: {size/(1024*1024):.1f} MB")
    
    def check_changes(self):
        """检查变化"""
        current_sizes = self.get_cache_sizes()
        changes_detected = False
        
        for path, current_size in current_sizes.items():
            initial_size = self.initial_sizes.get(path, 0)
            if current_size > initial_size:
                change_mb = (current_size - initial_size) / (1024*1024)
                if change_mb > 1:  # 变化超过1MB
                    print(f"⚠️ C盘缓存增长: {Path(path).name} +{change_mb:.1f} MB")
                    changes_detected = True
        
        return changes_detected
    
    def force_cleanup_new_cache(self):
        """强制清理新增的缓存"""
        print("🧹 强制清理新增C盘缓存...")
        cleaned_total = 0
        
        for cache_path in self.cache_paths:
            if cache_path and cache_path.exists():
                try:
                    size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file())
                    if size > 1024*1024:  # 大于1MB
                        print(f"   🗑️ 清理 {cache_path} ({size/(1024*1024):.1f}MB)")
                        shutil.rmtree(cache_path)
                        cleaned_total += size
                except Exception as e:
                    print(f"   ❌ 清理失败 {cache_path}: {e}")
        
        if cleaned_total > 0:
            print(f"✅ 总计清理: {cleaned_total/(1024*1024):.1f} MB")
        
        # 更新初始大小
        self.initial_sizes = self.get_cache_sizes()


def monitor_c_drive_during_session():
    """在会话期间监控C盘"""
    monitor = CDriveMonitor()
    monitor.start_monitoring()
    
    print("⏱️ 监控运行中，按 Ctrl+C 停止...")
    
    try:
        while True:
            time.sleep(5)  # 每5秒检查一次
            if monitor.check_changes():
                print("🚨 检测到C盘缓存增长，立即清理...")
                monitor.force_cleanup_new_cache()
    except KeyboardInterrupt:
        print("\n✅ 监控已停止")
        
        # 最终检查
        final_sizes = monitor.get_cache_sizes()
        final_total = sum(final_sizes.values()) / (1024*1024)
        initial_total = sum(monitor.initial_sizes.values()) / (1024*1024)
        
        print(f"\n📊 监控结果:")
        print(f"   初始C盘缓存: {initial_total:.1f} MB")
        print(f"   最终C盘缓存: {final_total:.1f} MB")
        print(f"   净增长: {final_total - initial_total:.1f} MB")


if __name__ == "__main__":
    monitor_c_drive_during_session()
