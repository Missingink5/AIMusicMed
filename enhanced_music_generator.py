"""Deprecated module: enhanced_music_generator

此文件已弃用，仅保留占位以避免旧引用报错。
实际AI音乐生成已迁移到 high_quality_music_manager / MusicGen 模型。
"""

class EnhancedMusicGenerator:  # 保留类名避免旧代码崩溃
    def __init__(self, *_, **__):  # pragma: no cover
        raise RuntimeError("enhanced_music_generator 已弃用，请使用 high_quality_music_manager 或直接调用 MusicGen")
        
        # 多个延迟层
        delays = [delay_samples, delay_samples * 2, delay_samples * 3]
        decays = [0.3, 0.2, 0.1]
        
        for delay, decay in zip(delays, decays):
            if delay < len(audio):
                reverb[delay:] += audio[:-delay] * decay * reverb_amount
        
        return audio + reverb
    
    def _apply_master_envelope(self, audio: np.ndarray, fade_in: float, fade_out: float) -> np.ndarray:
        """应用主包络（淡入淡出）"""
        total_samples = len(audio)
        fade_in_samples = int(fade_in * self.sample_rate)
        fade_out_samples = int(fade_out * self.sample_rate)
        
        envelope = np.ones(total_samples)
        
        # 淡入
        if fade_in_samples > 0:
            fade_in_curve = np.linspace(0, 1, fade_in_samples) ** 2  # 平方曲线，更自然
            envelope[:fade_in_samples] = fade_in_curve
        
        # 淡出
        if fade_out_samples > 0:
            fade_out_curve = np.linspace(1, 0, fade_out_samples) ** 2
            envelope[-fade_out_samples:] = fade_out_curve
        
        return audio * envelope
    
    def _normalize_and_limit(self, audio: np.ndarray, target_level: float = 0.8) -> np.ndarray:
        """归一化并限制音频"""
        # 防止除零
        max_val = np.max(np.abs(audio))
        if max_val == 0:
            return audio
        
        # 归一化到目标电平
        normalized = audio / max_val * target_level
        
        # 软限制器防止削波
        return np.tanh(normalized)
    
    def save_music_to_file(self, audio: np.ndarray, filename: str):
        """保存音乐到文件"""
        try:
            import soundfile as sf
            sf.write(filename, audio, self.sample_rate)
            print(f"高质量音乐已保存到: {filename}")
        except ImportError:
            print("需要安装soundfile库: pip install soundfile")


# 测试和使用示例
def test_enhanced_music_generator():
    """测试增强音乐生成器"""
    generator = EnhancedMusicGenerator()
    
    print("🎼 增强音乐生成器测试")
    print("=" * 50)
    
    styles = ["deep_meditation", "peaceful_nature", "floating_ambient", "gentle_piano", "healing_tones"]
    
    for style in styles:
        print(f"\n测试风格: {style}")
        try:
            # 生成10秒音乐
            audio = generator.generate_enhanced_music(
                duration=10.0,
                style=style,
                fade_in=1.0,
                fade_out=1.0
            )
            
            print(f"  ✅ 生成成功")
            print(f"  - 音频长度: {len(audio)} 样本")
            print(f"  - 时长: {len(audio) / 44100:.1f} 秒")
            print(f"  - 振幅范围: {np.min(audio):.3f} 到 {np.max(audio):.3f}")
            
        except Exception as e:
            print(f"  ❌ 生成失败: {e}")


if __name__ == "__main__":
    test_enhanced_music_generator()
