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
        self.base_dir = "preset_music"
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
            
        # 3. 最后使用增强的合成音乐
        return self._generate_enhanced_synthetic_music(emotion, duration)
    
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
                        
                        # 导入AI音乐生成相关模块
                        from transformers import MusicgenForConditionalGeneration, AutoProcessor
                        import torch
                        import scipy.io.wavfile
                        import tempfile
                        
                        # 情绪到音乐提示的映射
                        emotion_prompts = {
                            "stressed": "calm and soothing meditation music with soft ambient tones",
                            "anxious": "peaceful and gentle music with nature sounds for relaxation",
                            "sad": "healing and comforting music with warm tones",
                            "angry": "calming ambient music with floating ethereal sounds",
                            "tired": "gentle piano music with soft melodies for rest",
                            "neutral": "deep meditation music with low frequency tones",
                            "happy": "peaceful nature music with harmonious melodies",
                            "calm": "floating ambient music with ethereal atmospheric sounds"
                        }
                        
                        prompt = emotion_prompts.get(emotion, "calm meditation music")
                        
                        # 加载AI音乐生成模型
                        model_name = config.get("audio_settings", {}).get("music_model", "facebook/musicgen-small")
                        
                        processor = AutoProcessor.from_pretrained(model_name)
                        model = MusicgenForConditionalGeneration.from_pretrained(model_name)
                        
                        device = "cuda" if torch.cuda.is_available() else "cpu"
                        model.to(device)
                        
                        # 生成音乐
                        inputs = processor(text=[prompt], return_tensors="pt").to(device)
                        
                        # 计算需要的token数量
                        estimated_tokens = int(duration * 100)  # 每秒约100个token
                        
                        with torch.no_grad():
                            audio_values = model.generate(
                                **inputs,
                                max_new_tokens=estimated_tokens,
                                do_sample=True,
                                guidance_scale=3.0
                            )
                        
                        # 转换为numpy数组
                        sample_rate = model.config.audio_encoder.sampling_rate
                        audio_data = audio_values[0, 0].cpu().numpy()
                        
                        # 调整时长
                        current_duration = len(audio_data) / sample_rate
                        if abs(current_duration - duration) > 1.0:
                            audio_data = self._adjust_duration(audio_data, sample_rate, duration)
                        
                        print(f"🎵 AI音乐生成完成: {emotion} (质量: AI生成)")
                        return MusicSelection(
                            audio_data=audio_data,
                            source="ai_generated",
                            style=f"ai_{emotion}",
                            duration=duration,
                            quality_level="ai_highest"
                        )
                        
                    except Exception as e:
                        print(f"AI音乐生成失败: {e}")
                        print("回退到增强合成音乐...")
                        return None
        
        return None
    
    def _generate_enhanced_synthetic_music(self, emotion: str, duration: float) -> MusicSelection:
        """生成增强的合成音乐"""
        try:
            from enhanced_music_generator import EnhancedMusicGenerator
            
            # 情绪到增强音乐风格的映射
            emotion_to_enhanced_style = {
                "stressed": "deep_meditation",
                "anxious": "peaceful_nature",
                "sad": "healing_tones",
                "angry": "floating_ambient", 
                "tired": "gentle_piano",
                "neutral": "deep_meditation",
                "happy": "peaceful_nature",
                "calm": "floating_ambient"
            }
            
            style = emotion_to_enhanced_style.get(emotion, "deep_meditation")
            
            generator = EnhancedMusicGenerator()
            audio = generator.generate_enhanced_music(
                duration=duration,
                style=style,
                fade_in=1.0,
                fade_out=1.0
            )
            
            print(f"🎼 生成增强合成音乐: {style} (质量: 增强)")
            return MusicSelection(
                audio_data=audio,
                source="enhanced_synthetic",
                style=style,
                duration=duration,
                quality_level="enhanced"
            )
            
        except Exception as e:
            print(f"增强音乐生成失败，使用基础合成: {e}")
            # 回退到基础合成音乐
            audio = self._generate_basic_synthetic_music(emotion, duration)
            return MusicSelection(
                audio_data=audio,
                source="basic_synthetic",
                style="basic",
                duration=duration,
                quality_level="basic"
            )
    
    def _generate_basic_synthetic_music(self, emotion: str, duration: float) -> np.ndarray:
        """生成基础合成音乐（回退方案）"""
        sample_rate = 44100
        t = np.linspace(0, duration, int(duration * sample_rate), False)
        
        # 基础参数
        base_freq = 220.0  # A3
        if emotion in ["sad", "tired"]:
            base_freq = 110.0  # A2，更低沉
        elif emotion in ["happy", "excited"]:
            base_freq = 330.0  # E4，更明亮
        
        # 生成基础和弦
        harmonics = [1.0, 0.5, 0.3, 0.2, 0.1]
        audio = np.zeros_like(t)
        
        for i, harmonic in enumerate(harmonics):
            freq = base_freq * (i + 1)
            wave = harmonic * np.sin(2 * np.pi * freq * t)
            audio += wave
        
        # 应用包络
        envelope = np.ones_like(audio)
        fade_samples = int(0.1 * len(audio))
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        
        audio *= envelope
        
        # 归一化
        if np.max(np.abs(audio)) > 0:
            audio = audio / np.max(np.abs(audio)) * 0.7
        
        return audio
    
    def _adjust_duration(self, audio: np.ndarray, sample_rate: int, target_duration: float) -> np.ndarray:
        """调整音频时长"""
        current_duration = len(audio) / sample_rate
        target_samples = int(target_duration * sample_rate)
        
        if target_duration > current_duration:
            # 需要延长：无缝循环
            loops_needed = int(np.ceil(target_duration / current_duration))
            extended = np.tile(audio, loops_needed)
            
            # 添加交叉淡化以实现无缝循环
            if len(extended) > target_samples:
                extended = extended[:target_samples]
                
            return extended
        else:
            # 需要缩短：保留开头和结尾，添加淡出
            fade_samples = int(0.5 * sample_rate)  # 0.5秒淡出
            shortened = audio[:target_samples]
            if len(shortened) > fade_samples:
                shortened[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            return shortened
    
    def get_available_styles(self) -> List[str]:
        """获取可用的音乐风格"""
        styles = set()
        
        # 高质量音乐风格
        if "high_quality_music" in self.metadata:
            styles.update(self.metadata["high_quality_music"].keys())
        
        # 增强合成音乐风格  
        enhanced_styles = ["deep_meditation", "peaceful_nature", "floating_ambient", 
                          "gentle_piano", "healing_tones"]
        styles.update(enhanced_styles)
        
        return list(styles)
    
    def get_quality_info(self) -> Dict:
        """获取音乐质量信息"""
        return {
            "high_quality_available": bool(os.path.exists(self.hq_dir)),
            "enhanced_generator_available": True,
            "available_styles": self.get_available_styles(),
            "quality_levels": ["high", "enhanced", "basic"]
        }


# 使用示例和测试函数
def test_music_quality():
    """测试音乐质量"""
    manager = HighQualityMusicManager()
    
    print("🎵 音乐质量测试")
    print("=" * 50)
    
    # 测试不同情绪
    emotions = ["stressed", "calm", "sad", "happy"]
    duration = 10.0
    
    for emotion in emotions:
        print(f"\n测试情绪: {emotion}")
        selection = manager.get_best_music_for_emotion(emotion, duration)
        print(f"  音源: {selection.source}")
        print(f"  风格: {selection.style}")
        print(f"  质量: {selection.quality_level}")
        print(f"  时长: {selection.duration:.1f}秒")
        print(f"  音频形状: {selection.audio_data.shape}")
    
    # 显示质量信息
    print(f"\n质量信息:")
    quality_info = manager.get_quality_info()
    for key, value in quality_info.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    test_music_quality()
