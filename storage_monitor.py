"""
存储空间监控脚本
"""
import os
import shutil
from pathlib import Path

def check_storage_status():
    """检查存储空间状态"""
    print("💾 存储空间监控报告")
    print("=" * 50)
    
    # 检查C盘剩余空间
    c_drive = "C:\\"
    c_total, c_used, c_free = shutil.disk_usage(c_drive)
    c_free_gb = c_free / (1024**3)
    c_total_gb = c_total / (1024**3)
    c_used_gb = c_used / (1024**3)
    
    print(f"C盘状态:")
    print(f"  总容量: {c_total_gb:.1f} GB")
    print(f"  已使用: {c_used_gb:.1f} GB")
    print(f"  剩余空间: {c_free_gb:.1f} GB")
    print(f"  使用率: {(c_used_gb/c_total_gb)*100:.1f}%")
    
    # 检查D盘剩余空间
    d_drive = "D:\\"
    if os.path.exists(d_drive):
        d_total, d_used, d_free = shutil.disk_usage(d_drive)
        d_free_gb = d_free / (1024**3)
        d_total_gb = d_total / (1024**3)
        d_used_gb = d_used / (1024**3)
        
        print(f"\nD盘状态:")
        print(f"  总容量: {d_total_gb:.1f} GB")
        print(f"  已使用: {d_used_gb:.1f} GB")
        print(f"  剩余空间: {d_free_gb:.1f} GB")
        print(f"  使用率: {(d_used_gb/d_total_gb)*100:.1f}%")
    
    # 检查应用占用
    app_dir = Path("D:/MyMeditationApp")
    if app_dir.exists():
        app_size = sum(f.stat().st_size for f in app_dir.rglob('*') if f.is_file())
        app_size_gb = app_size / (1024**3)
        print(f"\n应用占用:")
        print(f"  冥想应用总占用: {app_size_gb:.2f} GB")
    
    # 环境变量检查
    print(f"\n🔧 缓存环境检查:")
    cache_vars = ["HF_HOME", "TRANSFORMERS_CACHE", "TORCH_HOME"]
    for var in cache_vars:
        value = os.environ.get(var, "未设置")
        if value.startswith("D:"):
            status = "✅ 正确(D盘)"
        elif value.startswith("C:"):
            status = "⚠️ 警告(C盘)"
        else:
            status = "❓ 未知"
        print(f"  {var}: {value} {status}")
    
    print("\n" + "=" * 50)
    if c_free_gb < 5:
        print("⚠️ 警告: C盘剩余空间不足5GB，建议进一步清理")
    else:
        print("✅ 存储空间状态良好")

if __name__ == "__main__":
    check_storage_status()
