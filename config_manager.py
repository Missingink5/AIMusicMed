"""
配置管理模块
统一管理应用配置，支持从JSON文件或环境变量加载
"""

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class APIConfig:
    """API配置"""
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com/v1"


@dataclass
class PathConfig:
    """路径配置"""
    base_dir: str = "D:/MyMeditationApp"
    cache_dir: Optional[str] = None
    temp_dir: Optional[str] = None
    
    def __post_init__(self):
        if self.cache_dir is None:
            self.cache_dir = os.path.join(self.base_dir, "cache")
        if self.temp_dir is None:
            self.temp_dir = os.path.join(self.base_dir, "temp")


@dataclass
class AudioConfig:
    """音频配置"""
    music_model: str = "facebook/musicgen-medium"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    speech_rate: str = "-20%"
    speech_pitch: str = "-5Hz"
    music_volume_reduction: int = 15
    output_bitrate: str = "128k"


@dataclass
class MeditationConfig:
    """冥想会话配置"""
    default_duration_minutes: int = 3
    segment_duration_seconds: int = 20
    max_duration_minutes: int = 10
    min_duration_minutes: int = 1


@dataclass
class AppConfig:
    """应用总配置"""
    api: APIConfig
    paths: PathConfig
    audio: AudioConfig
    meditation: MeditationConfig
    
    @classmethod
    def from_json(cls, config_path: str) -> 'AppConfig':
        """从JSON文件加载配置"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls(
            api=APIConfig(**data['api_keys']),
            paths=PathConfig(**data['paths']),
            audio=AudioConfig(**data['audio_settings']),
            meditation=MeditationConfig(**data['meditation_settings'])
        )
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """从环境变量加载配置"""
        api_key = os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 环境变量未设置")
        
        return cls(
            api=APIConfig(deepseek_api_key=api_key),
            paths=PathConfig(),
            audio=AudioConfig(),
            meditation=MeditationConfig()
        )
    
    def create_directories(self):
        """创建必要的目录"""
        for dir_path in [self.paths.base_dir, self.paths.cache_dir, self.paths.temp_dir]:
            os.makedirs(dir_path, exist_ok=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "api_keys": {
                "deepseek_api_key": self.api.deepseek_api_key,
                "deepseek_base_url": self.api.deepseek_base_url
            },
            "paths": {
                "base_dir": self.paths.base_dir,
                "cache_dir": self.paths.cache_dir,
                "temp_dir": self.paths.temp_dir
            },
            "audio_settings": {
                "music_model": self.audio.music_model,
                "tts_voice": self.audio.tts_voice,
                "speech_rate": self.audio.speech_rate,
                "speech_pitch": self.audio.speech_pitch,
                "music_volume_reduction": self.audio.music_volume_reduction,
                "output_bitrate": self.audio.output_bitrate
            },
            "meditation_settings": {
                "default_duration_minutes": self.meditation.default_duration_minutes,
                "segment_duration_seconds": self.meditation.segment_duration_seconds,
                "max_duration_minutes": self.meditation.max_duration_minutes,
                "min_duration_minutes": self.meditation.min_duration_minutes
            }
        }


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    加载配置，优先级：配置文件 > 环境变量
    """
    if config_path and os.path.exists(config_path):
        try:
            return AppConfig.from_json(config_path)
        except Exception as e:
            print(f"⚠️ 从配置文件加载失败: {e}")
    
    # 尝试从默认位置加载
    default_config_path = "config.json"
    if os.path.exists(default_config_path):
        try:
            return AppConfig.from_json(default_config_path)
        except Exception as e:
            print(f"⚠️ 从默认配置文件加载失败: {e}")
    
    # 从环境变量加载
    try:
        return AppConfig.from_env()
    except Exception as e:
        print(f"❌ 从环境变量加载失败: {e}")
        raise ValueError("无法加载配置，请检查配置文件或环境变量")


if __name__ == "__main__":
    # 测试配置加载
    try:
        config = load_config()
        print("✅ 配置加载成功")
        print(f"API Base URL: {config.api.deepseek_base_url}")
        print(f"Base Directory: {config.paths.base_dir}")
        print(f"TTS Voice: {config.audio.tts_voice}")
        print(f"Default Duration: {config.meditation.default_duration_minutes} 分钟")
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
