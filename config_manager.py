#!/usr/bin/env python3
"""
Configuration Manager
统一管理应用配置, 支持从JSON文件或环境变量加载
"""

import os
import json
from typing import Optional
from dataclasses import dataclass, asdict, fields

from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


@dataclass
class APIConfig:
    """API配置"""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: int = 180
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.com"
    elevenlabs_api_key: str = ""
    elevenlabs_music_base_url: str = "https://api.elevenlabs.io/v1"
    elevenlabs_music_model: str = "music_v2"
    minimax_music_base_url: str = "https://api.minimaxi.com/v1"
    minimax_music_model: str = "music-2.6"
    music_request_timeout_seconds: int = 600
    
    def __post_init__(self):
        minimax_env_key = os.getenv("MINIMAX_API_KEY")
        if minimax_env_key:
            self.minimax_api_key = minimax_env_key
        elif self.minimax_api_key in ("", "PUT_YOUR_KEY_OR_USE_ENV"):
            self.minimax_api_key = ""
        elevenlabs_env_key = os.getenv("ELEVENLABS_API_KEY")
        if elevenlabs_env_key:
            self.elevenlabs_api_key = elevenlabs_env_key
        elif self.elevenlabs_api_key in ("", "PUT_YOUR_KEY_OR_USE_ENV"):
            self.elevenlabs_api_key = ""

        self.elevenlabs_music_base_url = os.getenv(
            "ELEVENLABS_MUSIC_BASE_URL", self.elevenlabs_music_base_url
        )
        self.elevenlabs_music_model = os.getenv(
            "ELEVENLABS_MUSIC_MODEL", self.elevenlabs_music_model
        )
        self.minimax_music_base_url = os.getenv(
            "MINIMAX_MUSIC_BASE_URL", self.minimax_music_base_url
        )
        self.minimax_music_model = os.getenv(
            "MINIMAX_MUSIC_MODEL", self.minimax_music_model
        )
        timeout = os.getenv("MUSIC_REQUEST_TIMEOUT_SECONDS")
        if timeout:
            self.music_request_timeout_seconds = int(timeout)
        if self.music_request_timeout_seconds <= 0:
            raise ValueError("music_request_timeout_seconds 必须大于 0")
        """优先使用环境变量，避免在配置文件中保存密钥。"""
        env_key = os.getenv("DEEPSEEK_API_KEY")
        if env_key:
            self.deepseek_api_key = env_key
            print("[OK] 已从环境变量读取 DeepSeek API Key")
        elif self.deepseek_api_key in ("", "PUT_YOUR_KEY_OR_USE_ENV"):
            self.deepseek_api_key = ""
            print("[WARN] 未设置 DEEPSEEK_API_KEY，将使用本地模板降级模式")
        deepseek_timeout = os.getenv("DEEPSEEK_TIMEOUT_SECONDS")
        if deepseek_timeout:
            self.deepseek_timeout_seconds = int(deepseek_timeout)
        if self.deepseek_timeout_seconds <= 0:
            raise ValueError("deepseek_timeout_seconds 必须大于 0")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", self.deepseek_model)


@dataclass
class PathConfig:
    """路径配置 (自动根据操作系统选择合适的默认目录)
    优先级:
      1. 显式传入的 base_dir
      2. 环境变量 MEDITATION_BASE_DIR
      3. Windows: D:/MyMeditationApp  (保留原语义)
         Linux / macOS: ~/meditation_app
    """
    base_dir: str = ""  # 留空以触发自动解析
    cache_dir: Optional[str] = None
    temp_dir: Optional[str] = None

    def _resolve_base(self) -> str:
        if self.base_dir:
            return self.base_dir
        env_dir = os.getenv("MEDITATION_BASE_DIR")
        if env_dir:
            return env_dir
        if os.name == 'nt':
            return "D:/ISO音乐-AI冥想疗愈生成/示例输出"
        # 非 Windows
        return os.path.expanduser("~/meditation_app")

    def __post_init__(self):
        # 解析并标准化 base_dir
        self.base_dir = os.path.abspath(self._resolve_base()) if not (os.name == 'nt' and self._resolve_base().startswith(('D:', 'd:'))) else self._resolve_base()
        # Linux/Unix 下若用户配置了 /app* 且非 root, 直接预判不可写回退
        try:
            if os.name != 'nt':
                uid = os.geteuid() if hasattr(os, 'geteuid') else None
                if self.base_dir.startswith('/app') and (uid not in (0, None)):
                    fallback = os.path.expanduser('~/meditation_app')
                    print(f"[WARN] 检测到可能不可写目录 {self.base_dir}, 提前回退到 {fallback}")
                    self.base_dir = fallback
        except Exception:
            pass
        if self.cache_dir is None:
            self.cache_dir = os.path.join(self.base_dir, "cache")
        if self.temp_dir is None:
            self.temp_dir = os.path.join(self.base_dir, "temp")

    def ensure_writable(self):
        """确保目录可写; 若不可写则回退到用户主目录."""
        test_dir = self.base_dir
        try:
            os.makedirs(test_dir, exist_ok=True)
            test_file = os.path.join(test_dir, '.writetest')
            with open(test_file, 'w') as f:
                f.write('ok')
            os.remove(test_file)
        except Exception:
            # 回退
            fallback = os.path.expanduser('~/meditation_app')
            print(f"[WARN] 基础目录 {self.base_dir} 不可写, 回退到 {fallback}")
            self.base_dir = fallback
            self.cache_dir = os.path.join(self.base_dir, 'cache')
            self.temp_dir = os.path.join(self.base_dir, 'temp')
            os.makedirs(self.base_dir, exist_ok=True)


@dataclass
class AudioConfig:
    """音频配置"""
    preferred_track_duration_seconds: int = 60
    music_transition_fade_seconds: float = 3.0
    tts_backend: str = "minimax"
    minimax_model: str = "speech-2.8-hd"
    minimax_voice_id: str = "female-chengshu-jingpin"
    minimax_speed: float = 0.8
    minimax_volume: float = 1.0
    minimax_pitch: int = 0
    minimax_emotion: str = "calm"
    minimax_sample_rate: int = 32000
    minimax_bitrate: int = 128000
    minimax_timeout_seconds: int = 600
    minimax_max_attempts: int = 3
    speech_start_delay_seconds: float = 4.0
    music_volume_reduction: int = 8
    output_bitrate: str = "128k"

    def __post_init__(self):
        self.tts_backend = self.tts_backend.lower()
        if self.tts_backend != "minimax":
            raise ValueError("tts_backend 必须为 minimax")
        if self.preferred_track_duration_seconds <= 0:
            raise ValueError("preferred_track_duration_seconds 必须大于 0")
        if self.music_transition_fade_seconds < 0:
            raise ValueError("music_transition_fade_seconds 不能为负数")
        if not 0.5 <= self.minimax_speed <= 2.0:
            raise ValueError("minimax_speed 必须在 0.5 到 2.0 之间")
        if not 0 < self.minimax_volume <= 10:
            raise ValueError("minimax_volume 必须在 0 到 10 之间")
        if not -12 <= self.minimax_pitch <= 12:
            raise ValueError("minimax_pitch 必须在 -12 到 12 之间")
        if self.minimax_sample_rate not in {8000, 16000, 22050, 24000, 32000, 44100}:
            raise ValueError("minimax_sample_rate 不是 MiniMax 支持的采样率")
        if self.speech_start_delay_seconds < 0:
            raise ValueError("speech_start_delay_seconds 不能为负数")
        if self.minimax_max_attempts < 1:
            raise ValueError("minimax_max_attempts 必须至少为 1")


@dataclass
class MeditationConfig:
    """冥想配置"""
    default_duration_minutes: int = 5
    segment_duration_seconds: int = 20
    max_duration_minutes: int = 15
    min_duration_minutes: int = 3

    def __post_init__(self):
        if self.min_duration_minutes <= 0:
            raise ValueError("min_duration_minutes 必须大于 0")
        if self.max_duration_minutes < self.min_duration_minutes:
            raise ValueError("max_duration_minutes 不能小于 min_duration_minutes")
        if not self.min_duration_minutes <= self.default_duration_minutes <= self.max_duration_minutes:
            raise ValueError("default_duration_minutes 必须位于允许时长范围内")


@dataclass
class AppConfig:
    """应用配置"""
    api: APIConfig
    paths: PathConfig  
    audio: AudioConfig
    meditation: MeditationConfig
    
    def create_directories(self):
        """创建必要的目录"""
        # 先尝试保证可写, 若回退 base_dir 会更新 path 属性
        self.paths.ensure_writable()
        # 回退后重新构建目录列表
        directories = [self.paths.base_dir, self.paths.cache_dir, self.paths.temp_dir]
        for directory in directories:
            if not directory:
                continue
            try:
                os.makedirs(directory, exist_ok=True)
            except PermissionError:
                print(f"[ERROR] 无法创建目录: {directory} (权限不足)")
                raise
    
    @classmethod
    def from_json(cls, config_path: str) -> 'AppConfig':
        """从JSON文件加载配置"""
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        def known_values(config_type, values):
            """忽略旧配置中的已移除字段，保持本机配置向后兼容。"""
            allowed = {field.name for field in fields(config_type)}
            return {key: value for key, value in values.items() if key in allowed}

        # 创建配置对象
        api_config = APIConfig(**known_values(APIConfig, data.get('api_keys', {})))
        paths_config = PathConfig(**known_values(PathConfig, data.get('paths', {})))
        audio_config = AudioConfig(**known_values(AudioConfig, data.get('audio_settings', {})))
        meditation_config = MeditationConfig(
            **known_values(MeditationConfig, data.get('meditation_settings', {}))
        )
        
        return cls(
            api=api_config,
            paths=paths_config,
            audio=audio_config,
            meditation=meditation_config
        )
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """从环境变量加载配置"""
        deepseek_key = os.getenv('DEEPSEEK_API_KEY', '')
        minimax_key = os.getenv('MINIMAX_API_KEY', '')
        elevenlabs_key = os.getenv('ELEVENLABS_API_KEY', '')
        if not deepseek_key and not minimax_key and not elevenlabs_key:
            raise ValueError(
                "DEEPSEEK_API_KEY, MINIMAX_API_KEY or ELEVENLABS_API_KEY "
                "environment variable not set"
            )

        api_config = APIConfig(
            deepseek_api_key=deepseek_key,
            minimax_api_key=minimax_key,
            elevenlabs_api_key=elevenlabs_key,
        )
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
        """保存不含密钥的配置模板。"""
        api_data = asdict(self.api)
        api_data['deepseek_api_key'] = 'PUT_YOUR_KEY_OR_USE_ENV'
        api_data['minimax_api_key'] = 'PUT_YOUR_KEY_OR_USE_ENV'
        api_data['elevenlabs_api_key'] = 'PUT_YOUR_KEY_OR_USE_ENV'
        data = {
            'api_keys': api_data,
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
            cfg = AppConfig.from_json(config_path)
            # 立即确保可写并可能回退
            cfg.paths.ensure_writable()
            return cfg
        except Exception as e:
            print(f"[WARN] Failed to load from config file: {e}")
    
    # Try loading from default location
    default_config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(default_config_path):
        try:
            cfg = AppConfig.from_json(default_config_path)
            cfg.paths.ensure_writable()
            return cfg
        except Exception as e:
            print(f"[WARN] Failed to load from default config file: {e}")
    
    # Try loading from environment variables
    try:
        cfg = AppConfig.from_env()
        cfg.paths.ensure_writable()
        return cfg
    except Exception as e:
        print(f"[ERROR] Failed to load from environment variables: {e}")
    
    # If all failed, raise exception
    raise ValueError("Unable to load configuration, please check config file or environment variables")


def create_default_config(output_path: str = "config.json"):
    """创建默认配置文件"""
    default_config = AppConfig(
        api=APIConfig(deepseek_api_key="PUT_YOUR_KEY_OR_USE_ENV"),
        paths=PathConfig(),
        audio=AudioConfig(),
        meditation=MeditationConfig()
    )
    
    default_config.to_json(output_path)
    print(f"[OK] Default config file created: {output_path}")
    print(
        "请通过 DEEPSEEK_API_KEY / MINIMAX_API_KEY / ELEVENLABS_API_KEY "
        "环境变量提供密钥"
    )


if __name__ == "__main__":
    # Test configuration loading
    try:
        config = load_config()
        print("[OK] Configuration loaded successfully")
        print(f"DeepSeek configured: {bool(config.api.deepseek_api_key)}")
        print(f"MiniMax configured: {bool(config.api.minimax_api_key)}")
        print(f"ElevenLabs configured: {bool(config.api.elevenlabs_api_key)}")
        print(f"Base Dir: {config.paths.base_dir}")
        print(f"TTS Voice: {config.audio.minimax_voice_id}")
    except Exception as e:
        print(f"[ERROR] Configuration loading failed: {e}")
        print("Creating default config file...")
        create_default_config()
