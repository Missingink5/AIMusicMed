#!/usr/bin/env python3
"""
Configuration Manager
统一管理应用配置, 支持从JSON文件或环境变量加载
"""

import os
import json
from typing import Optional
from dataclasses import dataclass, asdict


@dataclass
class APIConfig:
    """API配置"""
    deepseek_api_key: str = ""
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
    music_model: str = "facebook/musicgen-small"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    speech_rate: str = "-20%"
    speech_pitch: str = "-5Hz"
    music_volume_reduction: int = 8
    output_bitrate: str = "128k"
    enable_smart_voice_selection: bool = False
    enable_ai_music: bool = True
    use_high_quality_music: bool = False
    music_quality_preference: str = "high"


@dataclass
class MeditationConfig:
    """冥想配置"""
    default_duration_minutes: int = 5
    segment_duration_seconds: int = 20
    max_duration_minutes: int = 15
    min_duration_minutes: int = 1


@dataclass
class AppConfig:
    """应用配置"""
    api: APIConfig
    paths: PathConfig  
    audio: AudioConfig
    meditation: MeditationConfig
    
    def create_directories(self):
        """创建必要的目录"""
        directories = [
            self.paths.base_dir,
            self.paths.cache_dir,
            self.paths.temp_dir
        ]
        
        for directory in directories:
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
    
    @classmethod
    def from_json(cls, config_path: str) -> 'AppConfig':
        """从JSON文件加载配置"""
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 创建配置对象
        api_config = APIConfig(**data.get('api_keys', {}))
        paths_config = PathConfig(**data.get('paths', {}))
        audio_config = AudioConfig(**data.get('audio_settings', {}))
        meditation_config = MeditationConfig(**data.get('meditation_settings', {}))
        
        return cls(
            api=api_config,
            paths=paths_config,
            audio=audio_config,
            meditation=meditation_config
        )
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """从环境变量加载配置"""
        api_key = os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable not set")
        
        api_config = APIConfig(deepseek_api_key=api_key)
        paths_config = PathConfig()
        audio_config = AudioConfig()
        meditation_config = MeditationConfig()
        
        return cls(
            api=api_config,
            paths=paths_config,
            audio=audio_config,
            meditation=meditation_config
        )
    
    def to_json(self, config_path: str):
        """保存配置到JSON文件"""
        data = {
            'api_keys': asdict(self.api),
            'paths': asdict(self.paths),
            'audio_settings': asdict(self.audio),
            'meditation_settings': asdict(self.meditation)
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration with priority: config file > environment variables"""
    if config_path and os.path.exists(config_path):
        try:
            return AppConfig.from_json(config_path)
        except Exception as e:
            print(f"⚠️ Failed to load from config file: {e}")
    
    # Try loading from default location
    default_config_path = "config.json"
    if os.path.exists(default_config_path):
        try:
            return AppConfig.from_json(default_config_path)
        except Exception as e:
            print(f"⚠️ Failed to load from default config file: {e}")
    
    # Try loading from environment variables
    try:
        return AppConfig.from_env()
    except Exception as e:
        print(f"❌ Failed to load from environment variables: {e}")
    
    # If all failed, raise exception
    raise ValueError("Unable to load configuration, please check config file or environment variables")


def create_default_config(output_path: str = "config.json"):
    """创建默认配置文件"""
    default_config = AppConfig(
        api=APIConfig(),
        paths=PathConfig(),
        audio=AudioConfig(),
        meditation=MeditationConfig()
    )
    
    default_config.to_json(output_path)
    print(f"✅ Default config file created: {output_path}")
    print("Please edit the config file and set your API keys")


if __name__ == "__main__":
    # Test configuration loading
    try:
        config = load_config()
        print("✅ Configuration loaded successfully")
        print(f"API Key: {config.api.deepseek_api_key[:10]}...")
        print(f"Base Dir: {config.paths.base_dir}")
        print(f"TTS Voice: {config.audio.tts_voice}")
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        print("Creating default config file...")
        create_default_config()
