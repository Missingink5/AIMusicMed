"""
Python 3.13兼容版的运行脚本
使用自定义音频处理模块，不依赖pydub
"""

import asyncio
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.append(str(Path(__file__).parent))

from py313_meditation_app import MeditationApp, MeditationAppError
from config_manager import load_config


def print_welcome():
    """打印欢迎信息"""
    print("🧘‍♀️ 欢迎使用 AI 冥想助手 (Python 3.13 兼容版)")
    print("=" * 60)
    print("本应用能够根据您的倾诉内容生成个性化的冥想会话")
    print("包含温柔的指导语音和舒缓的背景音乐")
    print("✨ 使用 librosa + soundfile 音频处理，完全兼容 Python 3.13")
    print()


def get_user_input():
    """获取用户输入"""
    preset_inputs = [
        "我最近总是失眠，而且觉得压力很大，什么都做不好。",
        "工作上遇到了很多挫折，感觉很焦虑，需要放松一下。",
        "最近心情很低落，希望能找到内心的平静。",
        "感觉生活节奏太快，想要慢下来好好休息。",
        "人际关系让我感到困扰，需要调整心态。",
        "最近总是感到孤独，希望能找到内心的力量。"
    ]
    
    print("请选择您的情况，或者输入自定义内容：")
    for i, text in enumerate(preset_inputs, 1):
        print(f"{i}. {text}")
    print(f"{len(preset_inputs) + 1}. 自定义输入")
    
    while True:
        try:
            choice = input(f"\n请输入选择 (1-{len(preset_inputs) + 1}): ").strip()
            
            if choice == str(len(preset_inputs) + 1):
                user_input = input("\n请描述您当前的心情或困扰: ").strip()
                if not user_input:
                    print("❌ 输入为空，使用默认示例")
                    return preset_inputs[0]
                return user_input
            
            elif choice.isdigit() and 1 <= int(choice) <= len(preset_inputs):
                return preset_inputs[int(choice) - 1]
            
            else:
                print(f"请输入有效的选择 (1-{len(preset_inputs) + 1})")
                
        except KeyboardInterrupt:
            print("\n\n👋 已取消")
            return None


def get_duration():
    """获取冥想时长"""
    while True:
        try:
            duration_input = input("请输入冥想时长 (分钟，1-10，默认3分钟): ").strip()
            
            if not duration_input:
                return 3
            
            duration = int(duration_input)
            if 1 <= duration <= 10:
                return duration
            else:
                print("请输入1-10之间的数字")
                
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
        print("✅ 配置加载成功")
        
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
        print(f"⏱️ 总时长: 约 {session_info['total_duration_seconds']} 秒")
        print(f"🎵 音频后端: {session_info['audio_backend']}")
        
        if 'comfort' in session_info:
            print(f"💭 AI安慰语: {session_info['comfort']}")
        
        print("\n💡 使用提示:")
        print("   🎧 建议使用耳机或音响播放")
        print("   🛋️ 找一个安静舒适的地方")
        print("   🧘‍♀️ 开始您的冥想之旅")
        print("   📝 音频格式为WAV，确保最佳兼容性")
        
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
