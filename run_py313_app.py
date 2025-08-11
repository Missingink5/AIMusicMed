"""
Python 3.13兼容版的运行脚本
使用自定义音频处理模块，不依赖pydub
优化版：确保不占用C盘空间
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
sys.path.append(str(Path(__file__).parent))

def setup_d_drive_cache():
    """跨平台缓存设置: Windows 使用 D 盘; 其他平台使用 ~/meditation_app/cache 或环境变量 HF_CACHE_BASE"""
    if os.name == 'nt':
        cache_base = "D:/MyMeditationApp/cache"
    else:
        cache_base = os.environ.get('HF_CACHE_BASE') or os.path.expanduser('~/meditation_app/cache')

    Path(cache_base).mkdir(parents=True, exist_ok=True)
    cache_vars = {
        "HF_HOME": cache_base,
        "TRANSFORMERS_CACHE": f"{cache_base}/transformers",
        "TORCH_HOME": f"{cache_base}/torch",
        "HUGGINGFACE_HUB_CACHE": f"{cache_base}/hub",
        "PYTORCH_TRANSFORMERS_CACHE": f"{cache_base}/transformers",
        "XDG_CACHE_HOME": f"{cache_base}/xdg",
        "TORCH_CACHE_DIR": f"{cache_base}/torch",
        "FLAIR_CACHE_ROOT": f"{cache_base}/flair"
    }
    for var, path in cache_vars.items():
        os.environ[var] = path
        Path(path).mkdir(parents=True, exist_ok=True)
    print(f"✅ 缓存已重定向: {cache_base}")


def force_cleanup_c_drive_cache():
    if os.name != 'nt':
        return  # 非 Windows 无需执行 C 盘清理逻辑
    print("🧹 强制清理C盘AI缓存...")
    c_cache_paths = [
        Path.home() / ".cache" / "huggingface",
        Path.home() / ".cache" / "transformers",
        Path.home() / ".cache" / "torch",
        Path(os.environ.get("APPDATA", "")) / "torch" if os.environ.get("APPDATA") else None,
        Path(os.environ.get("LOCALAPPDATA", "")) / "torch" if os.environ.get("LOCALAPPDATA") else None,
    ]
    total_cleaned = 0
    for cache_path in c_cache_paths:
        if cache_path and cache_path.exists():
            try:
                import shutil
                size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file()) / (1024*1024)
                if size > 10:
                    print(f"   🗑️ 清理 {cache_path} ({size:.1f}MB)")
                    shutil.rmtree(cache_path)
                    total_cleaned += size
            except Exception as e:
                print(f"   ⚠️ 清理 {cache_path} 失败: {e}")
    if total_cleaned > 0:
        print(f"   ✅ 共清理 {total_cleaned:.1f}MB C盘缓存")
    else:
        print("   ✅ C盘无需清理")


def monitor_cache_during_run():
    """运行期间监控缓存使用"""
    print("👀 监控C盘缓存使用...")
    
    c_cache_paths = [
        Path.home() / ".cache" / "huggingface",
        Path.home() / ".cache" / "transformers"
    ]
    
    for cache_path in c_cache_paths:
        if cache_path.exists():
            try:
                size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file()) / (1024*1024)
                if size > 5:  # 大于5MB就警告
                    print(f"   ⚠️ 检测到C盘缓存增长: {cache_path} ({size:.1f}MB)")
                    print("   🔧 立即重新设置环境变量...")
                    setup_d_drive_cache()
            except:
                pass

# 在导入任何AI相关模块之前设置缓存
setup_d_drive_cache()

# 强制清理C盘遗留缓存
force_cleanup_c_drive_cache()

from py313_meditation_app import MeditationApp, MeditationAppError
from config_manager import load_config

# 导入后再次确保缓存设置
setup_d_drive_cache()


def print_welcome():
    """打印欢迎信息"""
    print("🧘‍♀️ 欢迎使用 AI 冥想助手 (情绪转换版)")
    print("=" * 60)
    print("本应用能够根据您的倾诉内容生成个性化的冥想会话")
    print("🎭 核心功能：情绪转换引导 (消极→中性→积极)")
    print("🎵 智能音乐选择：优先使用本地音乐库，音乐与情绪同步")
    print("🗣️ 个性化引导语：温和的指导语音帮助您跟随音乐进行情绪转换")
    print("✨ 使用 librosa + soundfile 音频处理，完全兼容 Python 3.13")
    print("💾 优化版：所有文件和缓存保存在D盘，保护C盘空间")
    print()
    print("🎯 情绪转换路径示例：")
    print("   焦虑 → 平静 → 喜悦")
    print("   忧郁 → 平静 → 友爱") 
    print("   敌意 → 平静 → 友爱")
    print()


def check_c_drive_protection():
    if os.name != 'nt':
        # 简化: 显示当前缓存指向
        print("🛡️ 缓存路径检查:")
        cache_vars = ["HF_HOME", "TRANSFORMERS_CACHE", "TORCH_HOME", "HUGGINGFACE_HUB_CACHE"]
        for var in cache_vars:
            value = os.environ.get(var, '未设置')
            print(f"   {var}: {value}")
        print()
        return
    print("🛡️ C盘保护检查:")
    protected_vars = 0
    total_vars = 0
    cache_vars = ["HF_HOME", "TRANSFORMERS_CACHE", "TORCH_HOME", "HUGGINGFACE_HUB_CACHE"]
    for var in cache_vars:
        total_vars += 1
        value = os.environ.get(var, "")
        if value.startswith("D:"):
            protected_vars += 1
            print(f"   ✅ {var}: 已重定向到D盘")
        else:
            print(f"   ⚠️ {var}: {value or '未设置'}")
    c_cache_found = False
    c_cache_paths = [
        Path.home() / ".cache" / "huggingface",
        Path.home() / ".cache" / "transformers",
        Path("C:/Users") / os.getlogin() / ".cache" / "huggingface" if os.getlogin() else None
    ]
    for cache_path in c_cache_paths:
        if cache_path and cache_path.exists():
            try:
                size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file()) / (1024*1024)
                if size > 10:
                    c_cache_found = True
                    print(f"   ⚠️ 发现C盘缓存: {cache_path} ({size:.1f}MB)")
            except:
                pass
    if protected_vars == total_vars and not c_cache_found:
        print("   🎉 C盘完全受保护，无AI缓存占用")
    elif protected_vars > 0:
        print(f"   🔄 部分保护已启用 ({protected_vars}/{total_vars})")
    else:
        print("   ❌ C盘保护未启用，建议运行清理工具")
    print()


def get_user_input():
    """获取用户输入"""
    preset_inputs = [
        "我最近工作压力特别大，总是失眠，心里很焦虑，担心做不好。",
        "失恋了，心情很低落，觉得生活没有意义，很悲伤。",
        "和同事发生了激烈争吵，现在很生气，想要发泄这种愤怒。",
        "今天心情不错，但想要更加平静安宁，享受内心的宁静。",
        "刚完成了重要项目，很有成就感，想要保持这种积极状态。",
        "感受到朋友们的关爱，心里很温暖，希望延续这种美好感受。"
    ]
    
    print("💭 请描述您当前的情绪状态（越详细越好，有助于AI准确分析）：")
    print("   情绪转换系统将根据您的描述制定个性化的转换路径")
    print()
    print("📋 您可以选择以下示例，或者输入自定义内容：")
    
    emotions = ["焦虑压力", "悲伤低落", "愤怒敌意", "平静状态", "自豪成就", "温暖关爱"]
    for i, (text, emotion) in enumerate(zip(preset_inputs, emotions), 1):
        print(f"{i}. [{emotion}] {text}")
    print(f"{len(preset_inputs) + 1}. 💬 自定义输入")
    
    while True:
        try:
            choice = input(f"\n请输入选择 (1-{len(preset_inputs) + 1}): ").strip()
            
            if choice == str(len(preset_inputs) + 1):
                print("\n💡 提示：请尽量详细描述您的情绪，例如：")
                print("   - 具体的情况或事件")
                print("   - 当前的感受和情绪强度")
                print("   - 希望达到的情绪状态")
                user_input = input("\n📝 请描述您当前的心情或困扰: ").strip()
                if not user_input:
                    print("❌ 输入为空，使用默认示例")
                    return preset_inputs[0]
                if len(user_input) < 10:
                    print("💡 建议描述更详细一些，有助于情绪分析的准确性")
                return user_input
            
            elif choice.isdigit() and 1 <= int(choice) <= len(preset_inputs):
                selected = preset_inputs[int(choice) - 1]
                print(f"✅ 您选择了: {selected}")
                return selected
            
            else:
                print(f"请输入有效的选择 (1-{len(preset_inputs) + 1})")
                
        except KeyboardInterrupt:
            print("\n\n👋 已取消")
            return None


def get_duration():
    """获取冥想时长"""
    while True:
        try:
            duration_input = input("请输入冥想时长 (分钟，3-20，默认5分钟): ").strip()
            
            if not duration_input:
                return 5
            
            duration = int(duration_input)
            if 3 <= duration <= 20:
                return duration
            else:
                print("请输入3-20之间的数字")

        except ValueError:
            print("请输入有效的数字")
        except KeyboardInterrupt:
            print("\n\n👋 已取消")
            return None


def print_session_summary(user_input: str, duration: int, config):
    """打印会话摘要"""
    segments = (duration * 60) // config.meditation.segment_duration_seconds
    
    print(f"\n📋 会话设置摘要:")
    print(f"   💭 您的倾诉: {user_input}")
    print(f"   ⏰ 冥想时长: {duration} 分钟")
    print(f"   📊 音频片段: {segments} 个片段 (每片段 {config.meditation.segment_duration_seconds} 秒)")
    print(f"   🗣️ 语音合成: {config.audio.tts_voice}")
    print(f"   🎵 音乐模型: {config.audio.music_model}")
    print()


def print_system_info(app: MeditationApp):
    """打印系统信息"""
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    print(f"🔧 系统信息:")
    print(f"   🐍 Python版本: {python_version}")
    print(f"   💻 计算设备: {app.device}")
    print(f"   🎵 音频后端: librosa + soundfile")
    print(f"   📁 输出目录: {app.config.paths.base_dir}")
    print(f"   📦 缓存目录: {app.config.paths.cache_dir}")
    
    # 显示环境变量设置状态
    print(f"   🔧 缓存重定向状态:")
    cache_vars = ["HF_HOME", "TRANSFORMERS_CACHE", "TORCH_HOME"]
    for var in cache_vars:
        value = os.environ.get(var, "未设置")
        if value.startswith("D:"):
            print(f"      {var}: ✅ D盘")
        else:
            print(f"      {var}: ⚠️ {value}")
    
    # 显示情绪转换系统状态
    print(f"   🎭 情绪转换系统:")
    try:
        music_status = app.local_music_lib.get_library_status()
        total_music = sum(music_status.values())
        print(f"      本地音乐库: ✅ {total_music}首音乐")
        print(f"      情绪分类: {len(music_status)}种 ({', '.join(music_status.keys())})")
        print(f"      转换路径: 消极→中性→积极")
    except Exception as e:
        print(f"      音乐库状态: ⚠️ 检查失败 ({e})")
    
    print()


async def run_session():
    """运行冥想会话生成"""
    try:
        print_welcome()
        
        # 检查Python版本兼容性
        if sys.version_info < (3, 8):
            print("❌ 需要 Python 3.8 或更高版本")
            return
        
        if sys.version_info >= (3, 13):
            print("✅ 检测到 Python 3.13+，使用兼容音频处理模块")
        
        # 再次确认缓存设置（防止被其他模块覆盖）
        setup_d_drive_cache()
        
        # 强制清理可能的C盘缓存
        force_cleanup_c_drive_cache()
        
        # 检查C盘保护状态
        check_c_drive_protection()
        
        # 加载配置
        print("🔧 正在加载配置...")
        config = load_config()
        
        # 强制优化配置以保护C盘空间（但允许AI音乐）
        if hasattr(config.audio, 'music_model'):
            # 确保使用小型模型以减少缓存占用
            if config.audio.music_model == "facebook/musicgen-medium":
                print("⚡ 检测到大型音乐模型，为节省空间自动切换到小型模型")
                config.audio.music_model = "facebook/musicgen-small"
            
            # 根据配置文件设置决定是否启用AI音乐
            if config.audio.enable_ai_music:
                print("🎵 AI音乐生成已启用，使用小型模型以保护C盘空间")
                print("💾 所有AI模型缓存将保存在D盘")
            else:
                print("🔒 AI音乐生成已禁用，将使用静音音乐")
        
        print("✅ 配置加载成功 (已优化空间使用)")
        
        # 创建应用实例
        print("🚀 正在初始化应用...")
        
        # 在创建应用前再次强制设置缓存
        setup_d_drive_cache()
        
        app = MeditationApp(config)
        print("✅ 应用初始化完成")
        
        # 初始化后检查缓存使用情况
        monitor_cache_during_run()
        
        print_system_info(app)
        
        # 获取用户输入
        user_input = get_user_input()
        if user_input is None:
            return
        
        # 获取时长设置
        duration = get_duration()
        if duration is None:
            return
        
        # 显示会话摘要
        print_session_summary(user_input, duration, config)
        
        # 确认开始
        confirm = input("是否开始生成冥想会话？(Y/N): ").strip().lower()
        if confirm not in ['', 'y', 'yes', '是']:
            print("👋 已取消生成")
            return
        
        print("\n🎬 开始生成您的个性化冥想会话...")
        print("💾 提醒: 所有文件将保存在D盘，不占用C盘空间")
        print("=" * 50)
        
        # 运行前清理检查
        print("🧹 运行前检查...")
        
        # 再次强制设置缓存（关键时刻）
        setup_d_drive_cache()
        
        # 如果启用AI音乐，进行额外的保护措施
        if config.audio.enable_ai_music:
            print("🤖 AI音乐已启用，执行额外C盘保护措施...")
            # 强制清理任何可能的C盘缓存
            force_cleanup_c_drive_cache()
            # 再次确认环境变量设置
            setup_d_drive_cache()
            print("✅ AI音乐C盘保护措施已就位")
        
        # 检查C盘是否有遗留缓存
        c_cache_paths = [
            Path.home() / ".cache" / "huggingface",
            Path.home() / ".cache" / "transformers"
        ]
        
        for cache_path in c_cache_paths:
            if cache_path.exists():
                size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file()) / (1024*1024)
                if size > 100:  # 大于100MB
                    print(f"⚠️ 发现C盘缓存: {cache_path} ({size:.1f}MB)")
                    print("   已自动保护D盘缓存；如需手动清理，请删除该目录或重新运行本程序以自动清空")
        
        # 生成冥想会话前最后一次检查
        monitor_cache_during_run()
        
        # 生成冥想会话
        output_file, session_info = await app.create_meditation_session(
            user_input=user_input,
            duration_minutes=duration,
            cleanup=True
        )
        
        # 显示结果
        print("\n" + "=" * 50)
        print("🎉 恭喜！您的冥想音频已生成完成")
        print(f"📁 文件位置: {output_file}")
        print(f"🔊 实际生成片段: {session_info['generated_segments']} 个")
        print(f"⏱️ 总时长: 约 {session_info['total_duration_seconds']} 秒")
        print(f"🎵 音频后端: {session_info['audio_backend']}")
        
        if 'comfort' in session_info:
            print(f"💭 AI安慰语: {session_info['comfort']}")
        
        print("\n💡 使用提示:")
        print("   🎧 建议使用耳机或音响播放")
        print("   🛋️ 找一个安静舒适的地方")
        print("   🧘‍♀️ 开始您的冥想之旅")
        print("   📝 音频格式为WAV，确保最佳兼容性")
        print("   💾 所有文件保存在D盘，C盘空间安全")
        
        # 显示存储使用情况
        print(f"\n📊 存储使用:")
        print(f"   📁 输出文件: {Path(output_file).stat().st_size / (1024*1024):.1f} MB")
        print(f"   💿 文件位置: D盘 (不占用C盘)")
        
        # 会话结束后检查C盘缓存
        print("\n🔍 会话结束后检查C盘缓存...")
        monitor_cache_during_run()
        
        # 如果使用了AI音乐，进行额外检查
        if config.audio.enable_ai_music:
            print("\n🤖 AI音乐使用后安全检查...")
            
            # 检查是否有新的C盘缓存
            c_total_size = 0
            c_cache_paths = [
                Path.home() / ".cache" / "huggingface",
                Path.home() / ".cache" / "transformers",
                Path.home() / ".cache" / "torch"
            ]
            
            for cache_path in c_cache_paths:
                if cache_path.exists():
                    try:
                        size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file()) / (1024*1024)
                        c_total_size += size
                        if size > 5:
                            print(f"   ⚠️ 检测到C盘缓存: {cache_path.name} ({size:.1f}MB)")
                    except:
                        pass
            
            if c_total_size > 50:  # 总缓存大于50MB
                print(f"   🚨 C盘总缓存: {c_total_size:.1f}MB，建议手动删除 ~/.cache 下相关 huggingface/transformers/torch 目录")
                print("   💡 也可以退出后重新运行本程序，它会尝试再次清理")
            else:
                print(f"   ✅ C盘缓存安全: {c_total_size:.1f}MB")
        
    except MeditationAppError as e:
        print(f"\n❌ 冥想应用错误: {e}")
        print("请检查配置设置和网络连接")
        
    except KeyboardInterrupt:
        print("\n\n👋 程序已被用户终止")
        
    except Exception as e:
        print(f"\n❌ 意外错误: {e}")
        print("请联系技术支持或查看日志文件")
        import traceback
        print(f"详细错误信息: {traceback.format_exc()}")


def main():
    """主入口函数"""
    try:
        # 运行异步主程序
        asyncio.run(run_session())
        
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
    except Exception as e:
        print(f"❌ 程序启动失败: {e}")


if __name__ == "__main__":
    main()
