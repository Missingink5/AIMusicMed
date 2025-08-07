"""
清理C盘占用并重定向缓存到D盘
"""
import os
import shutil
import json
from pathlib import Path

def cleanup_c_drive_cache():
    """清理C盘上的AI模型缓存"""
    print("🧹 正在清理C盘缓存...")
    
    # 常见的AI模型缓存位置
    cache_locations = [
        Path.home() / ".cache" / "huggingface",
        Path.home() / ".cache" / "transformers", 
        Path.home() / ".cache" / "torch",
        Path(os.environ.get("APPDATA", "")) / "torch",
        Path(os.environ.get("LOCALAPPDATA", "")) / "torch",
        Path("C:/Users") / os.getlogin() / ".cache" / "huggingface",
    ]
    
    cleaned_size = 0
    
    for cache_dir in cache_locations:
        if cache_dir.exists():
            try:
                # 计算目录大小
                size = sum(f.stat().st_size for f in cache_dir.rglob('*') if f.is_file())
                size_mb = size / (1024 * 1024)
                
                if size_mb > 10:  # 只清理大于10MB的缓存
                    print(f"📁 发现缓存: {cache_dir} ({size_mb:.1f} MB)")
                    
                    user_input = input(f"是否删除 {cache_dir}? (y/n): ")
                    if user_input.lower() == 'y':
                        shutil.rmtree(cache_dir)
                        cleaned_size += size_mb
                        print(f"✅ 已删除 {cache_dir}")
                    
            except Exception as e:
                print(f"⚠️ 处理 {cache_dir} 时出错: {e}")
    
    print(f"\n🎉 清理完成，释放了 {cleaned_size:.1f} MB 空间")

def setup_d_drive_cache():
    """设置D盘缓存环境"""
    print("\n🔧 设置D盘缓存环境...")
    
    # 创建D盘缓存目录
    d_cache_dir = Path("D:/MyMeditationApp/cache")
    d_cache_dir.mkdir(parents=True, exist_ok=True)
    
    # 设置环境变量（当前会话）
    os.environ["HF_HOME"] = str(d_cache_dir)
    os.environ["TRANSFORMERS_CACHE"] = str(d_cache_dir / "transformers")
    os.environ["TORCH_HOME"] = str(d_cache_dir / "torch")
    
    print(f"✅ 缓存目录设置为: {d_cache_dir}")
    
    # 创建批处理文件来永久设置环境变量
    batch_content = f"""@echo off
echo 设置AI缓存环境变量到D盘...
setx HF_HOME "D:\\MyMeditationApp\\cache"
setx TRANSFORMERS_CACHE "D:\\MyMeditationApp\\cache\\transformers"
setx TORCH_HOME "D:\\MyMeditationApp\\cache\\torch"
echo 环境变量设置完成！请重启命令行窗口使其生效。
pause
"""
    
    with open("set_cache_env.bat", "w", encoding="gbk") as f:
        f.write(batch_content)
    
    print("📝 已创建 set_cache_env.bat 文件")
    print("💡 请以管理员身份运行该文件来永久设置环境变量")

def check_current_cache_usage():
    """检查当前缓存使用情况"""
    print("\n📊 检查当前缓存使用情况...")
    
    cache_dirs = [
        ("D盘缓存", Path("D:/MyMeditationApp/cache")),
        ("用户缓存", Path.home() / ".cache"),
        ("应用数据", Path(os.environ.get("APPDATA", "")) / "torch" if os.environ.get("APPDATA") else None),
    ]
    
    for name, path in cache_dirs:
        if path and path.exists():
            try:
                size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                size_mb = size / (1024 * 1024)
                print(f"  {name}: {size_mb:.1f} MB")
            except Exception as e:
                print(f"  {name}: 无法计算大小 ({e})")
        else:
            print(f"  {name}: 不存在")

def optimize_config():
    """优化配置文件以减少存储占用"""
    print("\n⚙️ 优化配置以减少存储占用...")
    
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 优化音频设置以减少文件大小
        if "audio_settings" not in config:
            config["audio_settings"] = {}
        
        # 降低音频质量以节省空间
        config["audio_settings"].update({
            "output_bitrate": "128k",  # 降低比特率
            "use_preset_music": True,   # 优先使用预设音乐避免AI生成
            "enable_ai_music": False,   # 暂时禁用AI音乐以节省缓存
            "music_quality_preference": "balanced"  # 平衡质量和存储
        })
        
        # 添加清理设置
        config["cleanup_settings"] = {
            "auto_cleanup_temp": True,
            "max_session_files": 5,  # 最多保留5个会话文件
            "cleanup_older_than_days": 7
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print("✅ 配置已优化")
    else:
        print("⚠️ 配置文件不存在")

def main():
    """主函数"""
    print("🔧 C盘空间优化工具")
    print("=" * 50)
    
    while True:
        print("\n请选择操作:")
        print("1. 检查当前缓存使用情况")
        print("2. 清理C盘AI模型缓存")
        print("3. 设置D盘缓存环境")
        print("4. 优化配置以减少存储占用")
        print("5. 全部执行")
        print("0. 退出")
        
        choice = input("\n请输入选项 (0-5): ").strip()
        
        if choice == "1":
            check_current_cache_usage()
        elif choice == "2":
            cleanup_c_drive_cache()
        elif choice == "3":
            setup_d_drive_cache()
        elif choice == "4":
            optimize_config()
        elif choice == "5":
            check_current_cache_usage()
            cleanup_c_drive_cache()
            setup_d_drive_cache()
            optimize_config()
        elif choice == "0":
            print("👋 再见！")
            break
        else:
            print("❌ 无效选项，请重新选择")

if __name__ == "__main__":
    main()
