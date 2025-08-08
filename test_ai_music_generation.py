#!/usr/bin/env python3
"""
AI音乐生成测试
直接测试MusicGen模型的音乐生成功能
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
sys.path.append(str(Path(__file__).parent))

from py313_meditation_app import MeditationApp, MeditationAppError
from config_manager import load_config

async def test_ai_music_only():
    """测试AI音乐生成（跳过高质量音乐管理器）"""
    print("🎵 AI音乐生成测试")
    print("=" * 40)
    
    try:
        # 加载配置
        config = load_config()
        
        print(f"🔧 当前配置:")
        print(f"   AI音乐启用: {config.audio.enable_ai_music}")
        print(f"   高质量音乐: {config.audio.use_high_quality_music}")
        print(f"   音乐模型: {config.audio.music_model}")
        
        # 创建应用
        app = MeditationApp(config)
        
        print(f"\n🤖 AI音乐管理器状态:")
        print(f"   高质量音乐管理器: {'已启用' if app.hq_music_manager else '已禁用'}")
        
        # 创建测试音乐提示
        music_prompts = [
            {
                "emotion": "calm",
                "prompt": "soft peaceful meditation music with gentle tones",
                "duration": 10  # 10秒测试
            }
        ]
        
        print(f"\n🎼 开始生成AI音乐...")
        print(f"   提示词: {music_prompts[0]['prompt']}")
        print(f"   时长: {music_prompts[0]['duration']}秒")
        
        # 直接调用AI音乐生成方法
        if app.hq_music_manager:
            print("⚠️ 高质量音乐管理器仍在使用，将跳过AI生成")
            music_files = app._generate_hq_music(music_prompts)
        else:
            print("✅ 使用AI模型生成音乐")
            music_files = app._generate_ai_music(music_prompts)
        
        if music_files:
            print(f"\n✅ 音乐生成成功:")
            for i, file in enumerate(music_files):
                if os.path.exists(file):
                    file_size = os.path.getsize(file) / 1024
                    print(f"   文件 {i+1}: {file} ({file_size:.1f}KB)")
                    
                    # 检查音频内容
                    try:
                        import librosa
                        audio, sr = librosa.load(file, sr=None)
                        duration = len(audio) / sr
                        max_val = max(abs(audio)) if len(audio) > 0 else 0
                        
                        print(f"     时长: {duration:.1f}秒")
                        print(f"     采样率: {sr}Hz")
                        print(f"     最大值: {max_val:.3f}")
                        
                        if max_val < 0.001:
                            print("     ⚠️ 音频几乎为静音")
                        else:
                            print("     ✅ 音频有内容")
                            
                    except Exception as e:
                        print(f"     ❌ 音频分析失败: {e}")
                else:
                    print(f"   文件 {i+1}: {file} (不存在)")
        else:
            print("❌ 音乐生成失败，未返回文件")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")

def main():
    """主函数"""
    try:
        asyncio.run(test_ai_music_only())
    except KeyboardInterrupt:
        print("\n👋 测试已取消")
    except Exception as e:
        print(f"❌ 程序错误: {e}")

if __name__ == "__main__":
    main()
