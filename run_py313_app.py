"""
Python 3.13兼容版的运行脚本
使用自定义音频处理模块，不依赖pydub
"""

import asyncio
import sys
from pathlib import Path


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

from py313_meditation_app import MeditationApp, MeditationAppError
from config_manager import load_config


def print_welcome():
    """打印欢迎信息"""
    print("🧘‍♀️ 欢迎使用 AI 冥想助手 (情绪转换版)")
    print("=" * 60)
    print("本应用能够根据您的倾诉内容生成个性化的冥想会话")
    print("🎭 核心功能：情绪转换引导 (消极→中性→积极)")
    print("🎵 智能音乐选择：优先使用本地音乐库，音乐与情绪同步")
    print("🗣️ 个性化引导语：温和的指导语音帮助您跟随音乐进行情绪转换")
    print("✨ 使用 librosa + soundfile 音频处理，完全兼容 Python 3.13")
    print("💾 输出与临时文件保存在配置的本地目录")
    print()
    print("🎯 情绪转换路径示例：")
    print("   焦虑 → 平静 → 喜悦")
    print("   忧郁 → 平静 → 友爱") 
    print("   敌意 → 平静 → 友爱")
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


def get_duration(config):
    """获取冥想时长"""
    minimum = config.meditation.min_duration_minutes
    maximum = config.meditation.max_duration_minutes
    default = config.meditation.default_duration_minutes
    while True:
        try:
            duration_input = input(
                f"请输入冥想时长 (分钟，{minimum}-{maximum}，默认{default}分钟): "
            ).strip()
            
            if not duration_input:
                return default
            
            duration = int(duration_input)
            if minimum <= duration <= maximum:
                return duration
            else:
                print(f"请输入{minimum}-{maximum}之间的数字")

        except ValueError:
            print("请输入有效的数字")
        except KeyboardInterrupt:
            print("\n\n👋 已取消")
            return None


def print_session_summary(user_input: str, duration: int, config):
    """打印会话摘要"""
    segments = max(3, round(duration * 60 / config.audio.preferred_track_duration_seconds))
    
    print(f"\n📋 会话设置摘要:")
    print(f"   💭 您的倾诉: {user_input}")
    print(f"   ⏰ 冥想时长: {duration} 分钟")
    print(f"   📊 音频片段: 约 {segments} 首音乐 (每首约 {config.audio.preferred_track_duration_seconds} 秒)")
    print(f"   🗣️ 语音合成: {config.audio.tts_backend}")
    print("   🎵 音乐来源: 本地正式曲库（整首播放）")
    print()


def print_system_info(app: MeditationApp):
    """打印系统信息"""
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    print(f"🔧 系统信息:")
    print(f"   🐍 Python版本: {python_version}")
    print(f"   💻 计算设备: {app.device}")
    print(f"   🎵 音频后端: librosa + soundfile")
    print(f"   📁 输出目录: {app.config.paths.base_dir}")
    
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
        
        # 加载配置
        print("🔧 正在加载配置...")
        config = load_config()
        
        print("🎵 主流程使用本地正式曲库，整首播放且不裁剪、不循环")
        
        print("✅ 配置加载成功 (已优化空间使用)")
        
        # 创建应用实例
        print("🚀 正在初始化应用...")
        
        app = MeditationApp(config)
        print("✅ 应用初始化完成")
        
        print_system_info(app)
        
        # 获取用户输入
        user_input = get_user_input()
        if user_input is None:
            return
        
        # 获取时长设置
        duration = get_duration(config)
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
        print(f"💾 输出目录: {config.paths.base_dir}")
        print("=" * 50)
        
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
        print(f"⏱️ 实际总时长: {session_info['actual_duration_seconds']:.1f} 秒")
        print(f"🎵 音频后端: {session_info['audio_backend']}")
        
        if 'comfort' in session_info:
            print(f"💭 AI安慰语: {session_info['comfort']}")
        
        print("\n💡 使用提示:")
        print("   🎧 建议使用耳机或音响播放")
        print("   🛋️ 找一个安静舒适的地方")
        print("   🧘‍♀️ 开始您的冥想之旅")
        print("   📝 音频格式为WAV，确保最佳兼容性")
        print(f"   💾 文件已保存至: {config.paths.base_dir}")
        
        # 显示存储使用情况
        print(f"\n📊 存储使用:")
        print(f"   📁 输出文件: {Path(output_file).stat().st_size / (1024*1024):.1f} MB")
        print(f"   💿 文件位置: {output_file}")
        
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
