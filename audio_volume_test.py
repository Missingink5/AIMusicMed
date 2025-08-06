"""
音频音量测试和调优工具
帮助找到语音和背景音乐的最佳音量平衡
"""

import os
import json
import asyncio
from py313_meditation_app import MeditationApp
from config_manager import load_config
from audio_compat import AudioSegment


def test_volume_levels():
    """测试不同的音量级别"""
    
    print("🔊 音频音量测试工具")
    print("=" * 50)
    
    # 加载配置
    config = load_config()
    
    # 测试不同的音量减少级别
    test_levels = [5, 10, 15, 20, 25]
    
    print("当前配置的音量减少值:", config.audio.music_volume_reduction)
    print("\n建议的音量减少级别说明:")
    print("• 5-10dB:  音乐较明显，适合需要舒缓音乐的冥想")
    print("• 10-15dB: 音乐中等，平衡的语音引导体验")
    print("• 15-20dB: 音乐较轻，语音引导为主")
    print("• 20-25dB: 音乐很轻，专注语音内容")
    print("• 25dB+:   音乐作为微弱背景")
    
    print(f"\n当前设置 ({config.audio.music_volume_reduction}dB) 的效果:")
    if config.audio.music_volume_reduction <= 10:
        print("🎵 音乐声音较大，营造良好氛围")
    elif config.audio.music_volume_reduction <= 15:
        print("🎼 音乐声音适中，语音和音乐平衡")
    elif config.audio.music_volume_reduction <= 20:
        print("🔉 音乐声音较小，语音更突出")
    else:
        print("🔇 音乐声音很小，主要专注语音")


async def create_volume_test_samples():
    """创建不同音量级别的测试样本"""
    
    print("\n🎧 生成音量测试样本...")
    print("=" * 50)
    
    # 创建应用实例
    app = MeditationApp()
    
    # 简短的测试用例
    test_input = "我需要放松一下"
    
    try:
        # 生成 prompts
        prompts_data = app.generate_prompts(test_input, duration_minutes=1)
        
        # 只取第一个片段进行测试
        first_script = prompts_data["script_prompts"][:1]
        first_music = prompts_data["music_prompts"][:1]
        
        # 生成语音
        speech_files = await app.generate_speech(first_script, test_input)
        
        # 生成音乐
        music_files = app.generate_music(first_music)
        
        if speech_files and music_files:
            # 测试不同音量级别
            test_levels = [5, 10, 15, 20, 25]
            
            print(f"\n📁 测试样本将保存在: {app.config.paths.base_dir}")
            
            for level in test_levels:
                print(f"\n🔊 生成音量级别 -{level}dB 的测试样本...")
                
                # 加载音频文件
                speech = AudioSegment.from_file(speech_files[0])
                music = AudioSegment.from_file(music_files[0])
                
                # 应用音量调整
                music_adjusted = music - level
                
                # 确保长度匹配
                if len(music_adjusted) < len(speech):
                    padding_duration = len(speech) - len(music_adjusted)
                    padding = AudioSegment.silent(duration=padding_duration)
                    music_adjusted = music_adjusted + padding
                else:
                    music_adjusted = music_adjusted[:len(speech)]
                
                # 合并音频
                combined = music_adjusted.overlay(speech, position=0)
                
                # 保存测试文件
                output_path = os.path.join(
                    app.config.paths.base_dir, 
                    f"volume_test_{level}dB.wav"
                )
                combined.export(output_path, format="wav")
                
                print(f"  ✓ 已保存: volume_test_{level}dB.wav")
            
            print(f"\n✅ 音量测试样本生成完成!")
            print(f"📂 请在 {app.config.paths.base_dir} 文件夹中试听不同音量级别的样本")
            print(f"🎯 选择最合适的音量级别后，更新 config.json 中的 music_volume_reduction 值")
            
        # 清理临时文件
        app.cleanup_temp_files()
        
    except Exception as e:
        print(f"❌ 测试样本生成失败: {e}")


def update_volume_config(new_level: int):
    """更新配置文件中的音量级别"""
    
    config_path = "config.json"
    
    try:
        # 读取当前配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 更新音量级别
        old_level = config_data["audio_settings"]["music_volume_reduction"]
        config_data["audio_settings"]["music_volume_reduction"] = new_level
        
        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 音量配置已更新: {old_level}dB → {new_level}dB")
        print(f"📁 配置文件: {config_path}")
        
    except Exception as e:
        print(f"❌ 更新配置失败: {e}")


async def main():
    """主函数"""
    
    print("🎵 音频音量调优工具")
    print("=" * 60)
    
    # 1. 显示当前状态和建议
    test_volume_levels()
    
    # 2. 询问用户操作
    print("\n" + "=" * 60)
    print("请选择操作:")
    print("1. 生成不同音量级别的测试样本")
    print("2. 手动设置音量级别")
    print("3. 使用推荐设置 (10dB)")
    print("4. 退出")
    
    try:
        choice = input("\n请输入选择 (1-4): ").strip()
        
        if choice == "1":
            await create_volume_test_samples()
            
        elif choice == "2":
            level = int(input("请输入新的音量减少级别 (建议5-25): "))
            update_volume_config(level)
            
        elif choice == "3":
            update_volume_config(10)
            print("✅ 已设置为推荐的平衡音量级别 (10dB)")
            
        elif choice == "4":
            print("👋 再见!")
            
        else:
            print("❌ 无效的选择")
            
    except KeyboardInterrupt:
        print("\n👋 用户取消操作")
    except ValueError:
        print("❌ 请输入有效的数字")
    except Exception as e:
        print(f"❌ 操作失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
