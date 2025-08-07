#!/usr/bin/env python3
"""
High Quality Music Integration
高质量音乐集成模块
"""

import os
import json
import numpy as np
from typing import Optional, Dict, List
from dataclasses import dataclass


@dataclass 
class MusicSelection:
    """音乐选择结果"""
    audio_data: np.ndarray
    source: str  # "high_quality", "ai_generated", "synthetic"
    style: str
    duration: float
    quality_level: str


class HighQualityMusicManager:
    """高质量音乐管理器"""
    
    def __init__(self):
        self.base_dir = "generated_music"
        self.hq_dir = os.path.join(self.base_dir, "high_quality")
        self.metadata = self._load_metadata()
        self.sample_rate = 44100
        
    def _load_metadata(self) -> Dict:
        """加载音乐元数据"""
        metadata_file = os.path.join(self.hq_dir, "metadata.json")
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def get_best_music_for_emotion(self, emotion: str, duration: float) -> MusicSelection:
        """
        根据情绪获取最佳音乐
        
        Args:
            emotion: 情绪状态
            duration: 目标时长
            
        Returns:
            MusicSelection对象
        """
        # 1. 首先尝试高质量预设音乐
        hq_result = self._try_high_quality_music(emotion, duration)
        if hq_result:
            return hq_result
            
        # 2. 回退到AI生成（如果启用）
        ai_result = self._try_ai_music(emotion, duration)
        if ai_result:
            return ai_result
            
        # 3. 最后使用合成音乐
        return self._generate_synthetic_music(emotion, duration)
    
    def _try_high_quality_music(self, emotion: str, duration: float) -> Optional[MusicSelection]:
        """尝试使用高质量预设音乐"""
        try:
            import soundfile as sf
            
            # 情绪到音乐风格的映射
            emotion_style_map = {
                "stressed": "deep_meditation",
                "anxious": "peaceful_nature",
                "sad": "healing_tones", 
                "angry": "floating_ambient",
                "tired": "gentle_piano",
                "neutral": "deep_meditation",
                "happy": "peaceful_nature",
                "calm": "floating_ambient",
                "excited": "gentle_piano",
                "overwhelmed": "healing_tones"
            }
            
            style = emotion_style_map.get(emotion, "deep_meditation")
            
            # 查找最接近的时长
            if "high_quality_music" in self.metadata and style in self.metadata["high_quality_music"]:
                music_files = self.metadata["high_quality_music"][style]
                
                # 找到最匹配的文件
                best_file = None
                min_duration_diff = float('inf')
                
                for file_info in music_files:
                    file_duration = file_info["duration"]
                    duration_diff = abs(file_duration - duration)
                    if duration_diff < min_duration_diff:
                        min_duration_diff = duration_diff
                        best_file = file_info
                
                if best_file and os.path.exists(best_file["file"]):
                    audio, sample_rate = sf.read(best_file["file"])
                    
                    # 调整时长
                    audio = self._adjust_duration(audio, sample_rate, duration)
                    
                    print(f"🎵 使用高质量音乐: {style} (质量: 高)")
                    return MusicSelection(
                        audio_data=audio,
                        source="high_quality",
                        style=style,
                        duration=duration,
                        quality_level="high"
                    )
                    
        except Exception as e:
            print(f"高质量音乐加载失败: {e}")
        
        return None
    
    def _try_ai_music(self, emotion: str, duration: float) -> Optional[MusicSelection]:
        """尝试使用AI生成音乐"""
        # 检查是否启用AI音乐
        config_file = "config.json"
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if config.get("audio_settings", {}).get("enable_ai_music", False):
                    try:
                        print("🤖 正在使用AI生成高质量音乐...")
                        
                        # 这里可以集成AI音乐生成模型
                        # 目前先跳过，直接返回None
                        
                        return None
                        
                    except Exception as e:
                        print(f"AI音乐生成失败: {e}")
                        print("回退到合成音乐...")
                        return None
        
        return None
    
    def _generate_synthetic_music(self, emotion: str, duration: float) -> MusicSelection:
        """生成简单的合成音乐"""
        try:
            # 使用基础合成音乐生成
            audio = self._generate_simple_synthetic_music(emotion, duration)
            
            return MusicSelection(
                audio_data=audio,
                source="synthetic",
                style=emotion,
                duration=duration,
                quality_level="basic"
            )
            
        except Exception as e:
            print(f"合成音乐生成失败: {e}")
            # 返回静音作为备选
            silence_samples = int(duration * self.sample_rate)
            audio = np.zeros(silence_samples)
            
            return MusicSelection(
                audio_data=audio,
                source="silence",
                style="neutral",
                duration=duration,
                quality_level="basic"
            )
    
    def _generate_simple_synthetic_music(self, emotion: str, duration: float) -> np.ndarray:
        """生成简单的合成音乐"""
        total_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, total_samples, False)
        
        # 根据情绪选择基础频率
        emotion_to_freq = {
            "stressed": 110.0,    # A2 - 深沉放松
            "anxious": 146.83,    # D3 - 平静
            "sad": 174.0,         # 疗愈频率
            "angry": 82.41,       # E2 - 低频平静
            "tired": 261.63,      # C4 - 柔和
            "neutral": 110.0,     # A2
            "happy": 146.83,      # D3
            "calm": 82.41         # E2
        }
        
        base_freq = emotion_to_freq.get(emotion, 110.0)
        
        # 生成基础正弦波
        audio = np.sin(2 * np.pi * base_freq * t)
        
        # 添加和声
        audio += 0.5 * np.sin(2 * np.pi * base_freq * 1.5 * t)  # 五度
        audio += 0.3 * np.sin(2 * np.pi * base_freq * 1.25 * t) # 大三度
        
        # 应用包络（淡入淡出）
        fade_samples = int(2.0 * self.sample_rate)  # 2秒淡入淡出
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        
        if len(audio) > 2 * fade_samples:
            audio[:fade_samples] *= fade_in
            audio[-fade_samples:] *= fade_out
        
        # 归一化
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val * 0.5  # 限制到50%音量
        
        return audio
    
    def _adjust_duration(self, audio: np.ndarray, sample_rate: int, target_duration: float) -> np.ndarray:
        """调整音频时长"""
        current_duration = len(audio) / sample_rate
        
        if abs(current_duration - target_duration) < 0.5:
            return audio
        
        if current_duration < target_duration:
            # 需要延长，循环播放
            repeat_times = int(np.ceil(target_duration / current_duration))
            extended_audio = np.tile(audio, repeat_times)
            
            # 裁剪到目标长度
            target_samples = int(target_duration * sample_rate)
            return extended_audio[:target_samples]
        else:
            # 需要缩短，直接裁剪
            target_samples = int(target_duration * sample_rate)
            return audio[:target_samples]
    
    def get_available_styles(self) -> List[str]:
        """获取可用的音乐风格"""
        return ["deep_meditation", "peaceful_nature", "healing_tones", "floating_ambient", "gentle_piano"]
    
    def get_style_for_emotion(self, emotion: str) -> str:
        """根据情绪获取推荐风格"""
        emotion_style_map = {
            "stressed": "deep_meditation",
            "anxious": "peaceful_nature", 
            "sad": "healing_tones",
            "angry": "floating_ambient",
            "tired": "gentle_piano",
            "neutral": "deep_meditation",
            "happy": "peaceful_nature",
            "calm": "floating_ambient"
        }
        return emotion_style_map.get(emotion, "deep_meditation")


# 测试功能
def test_high_quality_music_manager():
    """测试高质量音乐管理器"""
    manager = HighQualityMusicManager()
    
    print("🎵 高质量音乐管理器测试")
    print("=" * 40)
    
    test_emotions = ["stressed", "anxious", "calm", "happy"]
    
    for emotion in test_emotions:
        print(f"\n测试情绪: {emotion}")
        
        try:
            music = manager.get_best_music_for_emotion(emotion, 10.0)
            print(f"  ✅ 音乐生成成功")
            print(f"  - 来源: {music.source}")
            print(f"  - 风格: {music.style}")
            print(f"  - 质量: {music.quality_level}")
            print(f"  - 时长: {music.duration}秒")
            print(f"  - 音频大小: {len(music.audio_data)} 样本")
            
        except Exception as e:
            print(f"  ❌ 生成失败: {e}")


if __name__ == "__main__":
    test_high_quality_music_manager()
