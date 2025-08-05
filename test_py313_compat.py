"""
Python 3.13兼容版的快速测试
仅测试音频处理功能，不生成音乐
"""

import asyncio
import os
from audio_compat import AudioSegment
import edge_tts


async def test_audio_processing():
    """测试音频处理功能"""
    print("🧪 测试Python 3.13兼容的音频处理...")
    
    # 测试目录
    test_dir = "test_audio"
    os.makedirs(test_dir, exist_ok=True)
    
    try:
        # 1. 测试TTS语音生成
        print("🗣️ 测试语音合成...")
        test_text = "这是一个测试语音，用于验证Edge-TTS功能是否正常。"
        voice_file = os.path.join(test_dir, "test_voice.wav")
        
        communicate = edge_tts.Communicate(
            text=test_text,
            voice="zh-CN-XiaoxiaoNeural",
            rate="-20%",
            pitch="-5Hz"
        )
        await communicate.save(voice_file)
        print(f"✅ 语音文件生成成功: {voice_file}")
        
        # 2. 测试音频加载
        print("📂 测试音频加载...")
        voice_audio = AudioSegment.from_file(voice_file)
        print(f"✅ 音频加载成功，长度: {len(voice_audio)} ms")
        
        # 3. 测试静音生成
        print("🔇 测试静音生成...")
        silence = AudioSegment.silent(duration=2000)  # 2秒静音
        print(f"✅ 静音生成成功，长度: {len(silence)} ms")
        
        # 4. 测试音量调整
        print("🔊 测试音量调整...")
        quieter_silence = silence - 10  # 降低10dB
        print("✅ 音量调整成功")
        
        # 5. 测试音频叠加
        print("🎵 测试音频叠加...")
        combined = quieter_silence.overlay(voice_audio, position=500)  # 在0.5秒位置叠加
        print(f"✅ 音频叠加成功，最终长度: {len(combined)} ms")
        
        # 6. 测试音频连接
        print("➕ 测试音频连接...")
        final_audio = voice_audio + silence + voice_audio
        print(f"✅ 音频连接成功，最终长度: {len(final_audio)} ms")
        
        # 7. 测试音频导出
        print("💾 测试音频导出...")
        output_file = os.path.join(test_dir, "final_test.wav")
        final_audio.export(output_file, format="wav")
        print(f"✅ 音频导出成功: {output_file}")
        
        # 8. 验证导出的文件
        print("🔍 验证导出文件...")
        verified_audio = AudioSegment.from_file(output_file)
        print(f"✅ 文件验证成功，长度: {len(verified_audio)} ms")
        
        print("\n🎉 所有音频处理测试通过！")
        print("✨ Python 3.13兼容的音频处理系统工作正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")
        return False
    
    finally:
        # 清理测试文件
        try:
            import shutil
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
            print("🧹 测试文件已清理")
        except:
            pass


async def main():
    """主测试函数"""
    print("🚀 开始Python 3.13兼容性测试...\n")
    
    # 显示Python版本信息
    import sys
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"🐍 当前Python版本: {python_version}")
    
    if sys.version_info >= (3, 13):
        print("✅ 检测到Python 3.13+")
    else:
        print("ℹ️ 当前版本低于3.13，但兼容模块同样适用")
    
    print()
    
    # 运行音频处理测试
    success = await test_audio_processing()
    
    if success:
        print("\n🎊 恭喜！所有测试通过")
        print("📋 系统兼容性报告:")
        print("   ✅ Edge-TTS语音合成：正常")
        print("   ✅ Librosa音频加载：正常")
        print("   ✅ Soundfile音频导出：正常")
        print("   ✅ 自定义AudioSegment：正常")
        print("   ✅ 音频叠加和连接：正常")
        print("\n💡 您可以放心使用run_py313_app.py运行完整应用")
    else:
        print("\n❌ 测试失败，请检查依赖包安装")


if __name__ == "__main__":
    asyncio.run(main())
