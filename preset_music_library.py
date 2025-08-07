#!/usr/bin/env python3
"""
预设音乐库模块
提供快速的预设音乐生成，避免AI生成的延迟
"""

import os
import json
import numpy as np
from typing import Dict, List, Optional
from audio_compat import AudioSegment


class PresetMusicLibrary:
    """预设音乐库类"""
    
    def __init__(self, base_dir: str = "preset_music"):
        self.base_dir = base_dir
        self.sample_rate = 44100
        self.metadata = self._load_or_create_metadata()
        
    def _load_or_create_metadata(self) -> Dict:
        """加载或创建音乐元数据"""
        metadata_file = os.path.join(self.base_dir, "metadata.json")
        
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载元数据失败: {e}")
        
        # 创建默认元数据
        return self._create_default_metadata()
    
    def _create_default_metadata(self) -> Dict:
        """创建默认音乐元数据"""
        return {
            "version": "1.0",
            "categories": {
                "relaxing": {
                    "description": "放松舒缓音乐",
                    "keywords": ["放松", "舒缓", "轻松", "休息"],
                    "base_frequency": 220.0,
                    "tempo": 60
                },
                "meditative": {
                    "description": "深度冥想音乐", 
                    "keywords": ["冥想", "深度", "专注", "内观"],
                    "base_frequency": 110.0,
                    "tempo": 40
                },
                "nature": {
                    "description": "自然环境音效",
                    "keywords": ["自然", "森林", "海洋", "雨声"],
                    "base_frequency": 146.83,
                    "tempo": 50
                },
                "ambient": {
                    "description": "环境氛围音乐",
                    "keywords": ["氛围", "背景", "空灵", "宁静"],
                    "base_frequency": 82.41,
                    "tempo": 45
                },
                "piano": {
                    "description": "钢琴独奏音乐",
                    "keywords": ["钢琴", "优雅", "古典", "抒情"],
                    "base_frequency": 261.63,
                    "tempo": 70
                }
            }
        }
    
    def get_music_category_by_prompt(self, music_prompt: Dict) -> str:
        """根据音乐提示选择音乐类别"""
        prompt_text = music_prompt.get("prompt", "").lower()
        
        # 关键词匹配
        for category, info in self.metadata["categories"].items():
            keywords = info.get("keywords", [])
            if any(keyword in prompt_text for keyword in keywords):
                return category
        
        # 英文关键词匹配
        english_keywords = {
            "relaxing": ["relax", "calm", "peaceful", "soft", "gentle"],
            "meditative": ["meditat", "deep", "spiritual", "mindful"],
            "nature": ["nature", "forest", "ocean", "rain", "bird"],
            "ambient": ["ambient", "atmospheric", "ethereal", "space"],
            "piano": ["piano", "classical", "instrumental", "melody"]
        }
        
        for category, keywords in english_keywords.items():
            if any(keyword in prompt_text for keyword in keywords):
                return category
        
        # 默认返回放松音乐
        return "relaxing"
    
    def generate_synthetic_music(self, category: str, duration: float) -> np.ndarray:
        """生成合成音乐"""
        if category not in self.metadata["categories"]:
            category = "relaxing"
        
        category_info = self.metadata["categories"][category]
        base_freq = category_info["base_frequency"]
        tempo = category_info["tempo"]
        
        # 生成时间轴
        total_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, total_samples, False)
        
        # 生成基础音乐
        audio = self._generate_category_music(category, base_freq, tempo, t)
        
        # 应用包络
        audio = self._apply_envelope(audio, duration)
        
        # 归一化
        if np.max(np.abs(audio)) > 0:
            audio = audio / np.max(np.abs(audio)) * 0.7
        
        return audio
    
    def _generate_category_music(self, category: str, base_freq: float, tempo: float, t: np.ndarray) -> np.ndarray:
        """根据类别生成特定风格的音乐"""
        audio = np.zeros_like(t)
        
        if category == "relaxing":
            # 放松音乐：和谐的和弦进行
            for harmonic in [1.0, 0.6, 0.4, 0.2]:
                freq = base_freq * harmonic
                wave = harmonic * np.sin(2 * np.pi * freq * t)
                audio += wave
            
        elif category == "meditative":
            # 冥想音乐：深沉的基础频率
            for i, harmonic in enumerate([1.0, 0.5, 0.25, 0.125]):
                freq = base_freq * (i + 1)
                wave = harmonic * np.sin(2 * np.pi * freq * t)
                audio += wave
            
        elif category == "nature":
            # 自然音乐：模拟自然声音
            # 基础音调
            audio += 0.6 * np.sin(2 * np.pi * base_freq * t)
            # 添加"风声"（白噪声滤波）
            noise = np.random.normal(0, 0.1, len(t))
            # 简单的低通滤波
            filtered_noise = np.convolve(noise, np.ones(50)/50, mode='same')
            audio += 0.3 * filtered_noise
            
        elif category == "ambient":
            # 环境音乐：空灵的音效
            for i in range(5):
                freq = base_freq * (0.5 + i * 0.3)
                phase = np.random.random() * 2 * np.pi
                amplitude = 0.4 * np.exp(-i * 0.2)
                wave = amplitude * np.sin(2 * np.pi * freq * t + phase)
                audio += wave
            
        elif category == "piano":
            # 钢琴音乐：模拟钢琴和弦
            chord_freqs = [base_freq, base_freq * 1.25, base_freq * 1.5]  # 大三和弦
            for freq in chord_freqs:
                # 钢琴的音符有快速衰减
                decay = np.exp(-t * 2)
                wave = 0.4 * np.sin(2 * np.pi * freq * t) * decay
                audio += wave
        
        return audio
    
    def _apply_envelope(self, audio: np.ndarray, duration: float) -> np.ndarray:
        """应用音频包络（淡入淡出）"""
        fade_duration = min(2.0, duration * 0.1)  # 淡入淡出时间
        fade_samples = int(fade_duration * self.sample_rate)
        
        if len(audio) > 2 * fade_samples:
            # 淡入
            audio[:fade_samples] *= np.linspace(0, 1, fade_samples)
            # 淡出
            audio[-fade_samples:] *= np.linspace(1, 0, fade_samples)
        
        return audio
    
    def get_music_segment(self, music_prompt: Dict, duration: float) -> AudioSegment:
        """获取音乐片段"""
        # 选择音乐类别
        category = self.get_music_category_by_prompt(music_prompt)
        
        # 生成音乐
        audio_data = self.generate_synthetic_music(category, duration)
        
        # 转换为AudioSegment
        # 确保数据格式正确
        audio_data = (audio_data * 32767).astype(np.int16)
        
        # 创建AudioSegment
        audio_segment = AudioSegment(
            audio_data.tobytes(),
            frame_rate=self.sample_rate,
            sample_width=2,  # 16-bit
            channels=1
        )
        
        return audio_segment
    
    def get_available_categories(self) -> List[str]:
        """获取可用的音乐类别"""
        return list(self.metadata["categories"].keys())
    
    def save_metadata(self):
        """保存元数据"""
        os.makedirs(self.base_dir, exist_ok=True)
        metadata_file = os.path.join(self.base_dir, "metadata.json")
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)


# 测试函数
def test_preset_music():
    """测试预设音乐库"""
    library = PresetMusicLibrary()
    
    print("🎵 预设音乐库测试")
    print("=" * 40)
    
    # 测试不同类型的音乐提示
    test_prompts = [
        {"prompt": "relaxing meditation music"},
        {"prompt": "deep meditative ambient sounds"},
        {"prompt": "peaceful nature sounds with birds"},
        {"prompt": "soft piano melody for relaxation"},
        {"prompt": "atmospheric ambient music"}
    ]
    
    for i, prompt in enumerate(test_prompts, 1):
        category = library.get_music_category_by_prompt(prompt)
        print(f"测试 {i}: {prompt['prompt']}")
        print(f"  选择类别: {category}")
        
        # 生成5秒音乐测试
        try:
            music_segment = library.get_music_segment(prompt, 5.0)
            duration_ms = len(music_segment)
            print(f"  生成成功: {duration_ms}ms 音乐")
        except Exception as e:
            print(f"  生成失败: {e}")
        print()
    
    print(f"可用类别: {library.get_available_categories()}")


if __name__ == "__main__":
    test_preset_music()
