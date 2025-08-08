#!/usr/bin/env python3
"""
原始MusicGen背景音乐测试
测试facebook/musicgen-small模型是否能正常生成音乐
"""

import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
sys.path.append(str(Path(__file__).parent))

from config_manager import load_config

def test_original_musicgen():
    """测试原始MusicGen实现"""
    print("🎵 原始MusicGen音乐测试")
    print("=" * 40)
    
    try:
        # 加载配置
        config = load_config()
        print(f"🎼 音乐模型: {config.audio.music_model}")
        print(f"🔧 音量减少: {config.audio.music_volume_reduction}dB")
        print(f"🎛️ AI音乐启用: {config.audio.enable_ai_music}")
        
        if not config.audio.enable_ai_music:
            print("❌ AI音乐被禁用，请在config.json中启用")
            return
        
        # 检查transformers是否可用
        try:
            from transformers import MusicgenForConditionalGeneration, AutoProcessor
            print("✅ transformers库导入成功")
        except ImportError as e:
            print(f"❌ transformers库导入失败: {e}")
            return
        
        # 检查torch是否可用
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"✅ PyTorch可用，设备: {device}")
        except ImportError as e:
            print(f"❌ PyTorch导入失败: {e}")
            return
        
        # 尝试加载音乐模型（注意：首次加载会下载模型）
        print("\n🔄 正在加载MusicGen模型...")
        print("⚠️ 首次运行会下载模型文件，可能需要几分钟")
        
        try:
            processor = AutoProcessor.from_pretrained(config.audio.music_model)
            model = MusicgenForConditionalGeneration.from_pretrained(config.audio.music_model)
            model.to(device)
            print("✅ MusicGen模型加载成功")
            
            # 生成短音乐片段测试
            print("\n🎵 生成测试音乐片段...")
            
            # 设置音乐描述
            text = "peaceful meditation background music"
            inputs = processor(
                text=[text],
                padding=True,
                return_tensors="pt",
            ).to(device)
            
            # 生成音频（5秒测试）
            audio_values = model.generate(
                **inputs, 
                max_new_tokens=256,  # 约5秒的音频
                do_sample=True,
                guidance_scale=3.0
            )
            
            # 获取采样率
            sample_rate = model.config.audio_encoder.sampling_rate
            
            print(f"✅ 音乐生成成功")
            print(f"   采样率: {sample_rate}Hz")
            print(f"   音频形状: {audio_values.shape}")
            print(f"   时长: {audio_values.shape[-1] / sample_rate:.1f}秒")
            
            # 保存测试音频
            output_dir = Path("D:/MyMeditationApp/test")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            import soundfile as sf
            import numpy as np
            
            # 转换为numpy数组并保存
            audio_np = audio_values[0, 0].cpu().numpy()
            output_file = output_dir / "musicgen_test.wav"
            sf.write(str(output_file), audio_np, sample_rate)
            
            print(f"📁 测试音频已保存: {output_file}")
            
            # 音频统计
            max_val = np.max(np.abs(audio_np))
            rms = np.sqrt(np.mean(audio_np**2))
            
            print(f"\n📊 音频统计:")
            print(f"   最大值: {max_val:.3f}")
            print(f"   RMS: {rms:.3f}")
            print(f"   文件大小: {output_file.stat().st_size / 1024:.1f}KB")
            
            print(f"\n🎧 请播放 {output_file.name} 测试音乐效果")
            print("✅ 原始MusicGen版本工作正常！")
            
        except Exception as e:
            print(f"❌ MusicGen模型加载或生成失败: {e}")
            print("💡 可能原因:")
            print("   - 网络连接问题，无法下载模型")
            print("   - 磁盘空间不足")
            print("   - 内存不够（模型约1.5GB）")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")

def main():
    """主函数"""
    try:
        test_original_musicgen()
    except KeyboardInterrupt:
        print("\n👋 测试已取消")
    except Exception as e:
        print(f"❌ 程序错误: {e}")

if __name__ == "__main__":
    main()
