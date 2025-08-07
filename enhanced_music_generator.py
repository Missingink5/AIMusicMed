#!/usr/bin/env python3
"""
Enhanced Music Generator - High Quality Synthetic Music
为冥想应用生成高质量的合成音乐
"""

import numpy as np
import json
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import os


@dataclass
class MusicParameters:
    """音乐生成参数"""
    tempo: float  # BPM
    base_frequency: float  # 基础频率 (Hz)
    harmonics: List[float]  # 和声比例
    envelope_attack: float  # 音符起始时间
    envelope_decay: float  # 音符衰减时间
    envelope_sustain: float  # 音符持续音量
    envelope_release: float  # 音符释放时间
    reverb_amount: float  # 混响量
    dynamics_variation: float  # 动态变化


class EnhancedMusicGenerator:
    """增强版音乐生成器"""
    
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.music_styles = self._init_music_styles()
    
    def _init_music_styles(self) -> Dict[str, MusicParameters]:
        """初始化音乐风格参数"""
        return {
            "deep_meditation": MusicParameters(
                tempo=45.0,
                base_frequency=110.0,  # A2
                harmonics=[1.0, 0.5, 0.25, 0.125, 0.0625],
                envelope_attack=2.0,
                envelope_decay=1.0,
                envelope_sustain=0.7,
                envelope_release=4.0,
                reverb_amount=0.8,
                dynamics_variation=0.3
            ),
            "peaceful_nature": MusicParameters(
                tempo=50.0,
                base_frequency=146.83,  # D3
                harmonics=[1.0, 0.6, 0.3, 0.15, 0.1, 0.05],
                envelope_attack=1.5,
                envelope_decay=0.8,
                envelope_sustain=0.6,
                envelope_release=3.0,
                reverb_amount=0.7,
                dynamics_variation=0.4
            ),
            "floating_ambient": MusicParameters(
                tempo=40.0,
                base_frequency=82.41,  # E2
                harmonics=[1.0, 0.7, 0.4, 0.2, 0.1, 0.05, 0.025],
                envelope_attack=3.0,
                envelope_decay=1.5,
                envelope_sustain=0.8,
                envelope_release=5.0,
                reverb_amount=0.9,
                dynamics_variation=0.2
            ),
            "gentle_piano": MusicParameters(
                tempo=60.0,
                base_frequency=261.63,  # C4
                harmonics=[1.0, 0.4, 0.2, 0.1, 0.05],
                envelope_attack=0.1,
                envelope_decay=0.3,
                envelope_sustain=0.4,
                envelope_release=2.0,
                reverb_amount=0.5,
                dynamics_variation=0.6
            ),
            "healing_tones": MusicParameters(
                tempo=35.0,
                base_frequency=174.0,  # 疗愈频率
                harmonics=[1.0, 0.618, 0.382, 0.236, 0.146],  # 黄金比例和声
                envelope_attack=2.5,
                envelope_decay=1.2,
                envelope_sustain=0.75,
                envelope_release=4.5,
                reverb_amount=0.85,
                dynamics_variation=0.25
            )
        }
    
    def generate_enhanced_music(self, 
                              duration: float, 
                              style: str = "deep_meditation",
                              fade_in: float = 2.0,
                              fade_out: float = 2.0) -> np.ndarray:
        """
        生成增强版高质量音乐
        
        Args:
            duration: 音乐时长（秒）
            style: 音乐风格
            fade_in: 淡入时间（秒）
            fade_out: 淡出时间（秒）
        
        Returns:
            numpy数组格式的音频数据
        """
        if style not in self.music_styles:
            style = "deep_meditation"
        
        params = self.music_styles[style]
        total_samples = int(duration * self.sample_rate)
        
        # 生成基础音轨
        audio = self._generate_base_track(params, duration)
        
        # 添加和声层
        audio += self._generate_harmony_layers(params, duration) * 0.6
        
        # 添加环境音效
        audio += self._generate_ambient_layer(params, duration) * 0.3
        
        # 添加动态变化
        audio = self._apply_dynamics(audio, params)
        
        # 添加混响效果
        audio = self._apply_reverb(audio, params.reverb_amount)
        
        # 应用音量包络
        audio = self._apply_master_envelope(audio, fade_in, fade_out)
        
        # 归一化和限制
        audio = self._normalize_and_limit(audio)
        
        return audio
    
    def _generate_base_track(self, params: MusicParameters, duration: float) -> np.ndarray:
        """生成基础音轨"""
        total_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, total_samples, False)
        
        # 基础频率调制
        freq_modulation = 1.0 + 0.02 * np.sin(2 * np.pi * 0.1 * t)  # 慢速调制
        base_freq = params.base_frequency * freq_modulation
        
        # 生成基础波形
        audio = np.zeros(total_samples)
        for i, harmonic in enumerate(params.harmonics):
            if harmonic > 0.01:  # 忽略过小的和声
                harmonic_freq = base_freq * (i + 1)
                phase_offset = np.random.random() * 2 * np.pi  # 随机相位
                wave = harmonic * np.sin(2 * np.pi * harmonic_freq * t + phase_offset)
                audio += wave
        
        return audio
    
    def _generate_harmony_layers(self, params: MusicParameters, duration: float) -> np.ndarray:
        """生成和声层"""
        total_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, total_samples, False)
        
        # 和弦音程（完美五度、大三度等）
        intervals = [1.5, 1.25, 0.75, 0.667]  # 五度、大三度、四度、小三度
        harmony = np.zeros(total_samples)
        
        for interval in intervals:
            freq = params.base_frequency * interval
            # 缓慢的振幅调制
            amplitude_mod = 0.3 + 0.2 * np.sin(2 * np.pi * 0.05 * t * interval)
            wave = amplitude_mod * np.sin(2 * np.pi * freq * t)
            harmony += wave * 0.4
        
        return harmony
    
    def _generate_ambient_layer(self, params: MusicParameters, duration: float) -> np.ndarray:
        """生成环境音效层"""
        total_samples = int(duration * self.sample_rate)
        
        # 生成低频环境音
        t = np.linspace(0, duration, total_samples, False)
        ambient = np.zeros(total_samples)
        
        # 多层低频音
        low_freqs = [40, 60, 80, 120]
        for freq in low_freqs:
            amplitude = 0.15 * np.exp(-freq / 100)  # 频率越高振幅越小
            phase_mod = 0.1 * np.sin(2 * np.pi * 0.02 * t)  # 相位调制
            wave = amplitude * np.sin(2 * np.pi * freq * t + phase_mod)
            ambient += wave
        
        # 添加白噪声纹理
        noise = np.random.normal(0, 0.02, total_samples)
        # 低通滤波器模拟
        filtered_noise = np.convolve(noise, np.ones(100)/100, mode='same')
        ambient += filtered_noise
        
        return ambient
    
    def _apply_dynamics(self, audio: np.ndarray, params: MusicParameters) -> np.ndarray:
        """应用动态变化"""
        duration = len(audio) / self.sample_rate
        t = np.linspace(0, duration, len(audio))
        
        # 缓慢的动态变化
        dynamics = 1.0 + params.dynamics_variation * np.sin(2 * np.pi * 0.03 * t) * 0.5
        dynamics *= 1.0 + params.dynamics_variation * np.sin(2 * np.pi * 0.07 * t) * 0.3
        
        # 确保动态范围合理
        dynamics = np.clip(dynamics, 0.3, 1.2)
        
        return audio * dynamics
    
    def _apply_reverb(self, audio: np.ndarray, reverb_amount: float) -> np.ndarray:
        """应用混响效果"""
        if reverb_amount <= 0:
            return audio
        
        # 简单的延迟混响实现
        delay_samples = int(0.05 * self.sample_rate)  # 50ms延迟
        reverb = np.zeros_like(audio)
        
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
