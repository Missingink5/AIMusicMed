"""
Python 3.13兼容版的冥想应用
使用自定义音频处理模块替代pydub
"""

import os
import json
import re
import asyncio
import logging
import requests
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import asdict

try:
    from openai import OpenAI
except ImportError as e:  # 更友好的缺失依赖提示
    raise ImportError("缺少依赖 openai，请先在虚拟环境中执行: pip install -r requirements.txt 或 pip install openai") from e

try:
    from transformers import MusicgenForConditionalGeneration, AutoProcessor
except ImportError as e:
    raise ImportError("缺少依赖 transformers，请执行: pip install -r requirements.txt") from e
try:
    import torch
except ImportError as e:
    raise ImportError("缺少依赖 torch，请先安装 GPU/CPU 版 PyTorch") from e
try:
    import edge_tts
except ImportError as e:
    raise ImportError("缺少依赖 edge-tts，请执行: pip install edge-tts") from e

# 导入兼容的音频处理模块
from audio_compat import AudioSegment
from config_manager import load_config, AppConfig
from voice_profiles import get_voice_by_emotion, VOICE_PROFILES
from local_music_library import LocalMusicLibrary

# auto_cleaner 模块已删除，保留占位标记与空函数
AUTO_CLEANER_AVAILABLE = False
clean_before_session = clean_after_session = lambda: None

# 动态导入高质量音乐管理器
try:
    from high_quality_music_manager import HighQualityMusicManager
    HIGH_QUALITY_MUSIC_AVAILABLE = True
except ImportError:
    HIGH_QUALITY_MUSIC_AVAILABLE = False
    HighQualityMusicManager = None


class MeditationAppError(Exception):
    """自定义异常类"""
    pass


class MeditationApp:
    def __init__(self, config: Optional[AppConfig] = None):
        """
        初始化冥想应用
        """
        # 加载配置
        self.config = config or load_config()
        self.config.create_directories()
        
        # 设置日志
        self._setup_logging()
        
        # 初始化OpenAI客户端
        self.client = OpenAI(
            api_key=self.config.api.deepseek_api_key,
            base_url=self.config.api.deepseek_base_url
        )
        
        # 强制设置所有AI缓存到D盘，避免占用C盘
        os.environ["HF_HOME"] = self.config.paths.cache_dir
        os.environ["TRANSFORMERS_CACHE"] = os.path.join(self.config.paths.cache_dir, "transformers")
        os.environ["TORCH_HOME"] = os.path.join(self.config.paths.cache_dir, "torch")
        os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(self.config.paths.cache_dir, "hub")
        
        # 音乐生成模型（延迟加载）
        self.music_processor = None
        self.music_model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # 本地音乐库管理器
        self.local_music_lib = LocalMusicLibrary()
        
        # 预设音乐库（如果启用）
        # 高质量音乐管理器
        self.hq_music_manager = None
        if HIGH_QUALITY_MUSIC_AVAILABLE:
            self.hq_music_manager = HighQualityMusicManager()
            self.logger.info("高质量音乐管理器已启用")
        
        self.logger.info(f"MeditationApp 初始化完成，使用设备: {self.device}")

    def _setup_logging(self):
        """设置日志系统"""
        log_file = os.path.join(self.config.paths.base_dir, "meditation_app.log")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def initialize_music_model(self):
        """初始化音乐生成模型（延迟加载）"""
        if self.music_processor is None:
            try:
                self.logger.info("正在加载音乐生成模型...")
                print("🎵 正在加载音乐生成模型...")
                
                self.music_processor = AutoProcessor.from_pretrained(
                    self.config.audio.music_model, 
                    cache_dir=self.config.paths.cache_dir
                )
                self.music_model = MusicgenForConditionalGeneration.from_pretrained(
                    self.config.audio.music_model, 
                    cache_dir=self.config.paths.cache_dir
                )
                self.music_model.to(self.device)
                
                self.logger.info("音乐生成模型加载完成")
                print("✅ 音乐生成模型加载完成")
                
            except Exception as e:
                self.logger.error(f"音乐模型加载失败: {e}")
                raise MeditationAppError(f"音乐模型加载失败: {e}")

    def plan_emotion_journey(self, user_input: str, duration_minutes: int) -> List[Dict]:
        """
        规划情绪转换旅程：消极情绪 → 中性平静 → 积极情绪
        
        Args:
            user_input: 用户倾诉内容
            duration_minutes: 冥想总时长
            
        Returns:
            List[Dict]: 情绪转换计划，包含每个阶段的情绪、时长、描述
        """
        # 分析用户当前情绪
        current_emotion = self.local_music_lib.analyze_user_emotion(user_input)
        
        # 定义情绪转换映射
        emotion_journey_map = {
            # 消极情绪的转换路径
            "忧郁": ["忧郁", "平静", "友爱"],      # 悲伤 → 平静 → 关爱
            "焦虑": ["焦虑", "平静", "喜悦"],      # 焦虑 → 平静 → 喜悦  
            "敌意": ["敌意", "平静", "友爱"],      # 愤怒 → 平静 → 友爱
            # 中性情绪的转换路径
            "平静": ["平静", "友爱", "喜悦"],      # 平静 → 友爱 → 喜悦
            # 积极情绪的维持路径
            "喜悦": ["喜悦", "平静", "喜悦"],      # 喜悦 → 平静 → 喜悦
            "自豪": ["自豪", "平静", "友爱"],      # 自豪 → 平静 → 友爱
            "友爱": ["友爱", "平静", "喜悦"],      # 友爱 → 平静 → 喜悦
        }
        
        # 获取情绪转换路径
        emotion_path = emotion_journey_map.get(current_emotion, ["平静", "友爱", "喜悦"])
        
        # 计算每个阶段的时长（动态分配）
        total_seconds = duration_minutes * 60
        
        if current_emotion in ["忧郁", "焦虑", "敌意"]:
            # 消极情绪：更长的缓解阶段
            stage_durations = [
                int(total_seconds * 0.4),  # 40% 缓解当前消极情绪
                int(total_seconds * 0.35), # 35% 转向平静
                int(total_seconds * 0.25)  # 25% 培养积极情绪
            ]
        elif current_emotion == "平静":
            # 中性情绪：平衡分配
            stage_durations = [
                int(total_seconds * 0.3),  # 30% 维持平静
                int(total_seconds * 0.4),  # 40% 培养连接感
                int(total_seconds * 0.3)   # 30% 培养喜悦
            ]
        else:
            # 积极情绪：维持和深化
            stage_durations = [
                int(total_seconds * 0.35), # 35% 维持当前积极情绪
                int(total_seconds * 0.3),  # 30% 深度平静
                int(total_seconds * 0.35)  # 35% 强化积极情绪
            ]
        
        # 构建情绪旅程计划
        emotion_journey = []
        current_time = 0
        
        for i, (emotion, duration) in enumerate(zip(emotion_path, stage_durations)):
            # 英文情绪映射（用于音乐目录）
            emotion_en_map = {
                "忧郁": "Sad", "焦虑": "Anxiety", "敌意": "Hostility",
                "平静": "Quiet", "喜悦": "Happy", "自豪": "Pride", "友爱": "Love"
            }
            
            # 情绪阶段描述
            stage_descriptions = {
                0: "接纳和缓解当前情绪",
                1: "转向内心平静",
                2: "培养积极的情绪状态"
            }
            
            emotion_journey.append({
                "stage": i + 1,
                "emotion_cn": emotion,
                "emotion_en": emotion_en_map.get(emotion, "Quiet"),
                "start_time": current_time,
                "duration": duration,
                "end_time": current_time + duration,
                "description": stage_descriptions.get(i, "情绪调节"),
                "time_percentage": duration / total_seconds
            })
            
            current_time += duration
        
        self.logger.info(f"情绪转换计划: {current_emotion} → {' → '.join(emotion_path)}")
        print(f"🧭 情绪引导路径: {current_emotion} → {' → '.join(emotion_path)}")
        
        return emotion_journey

    def generate_prompts(self, user_input: str, duration_minutes: int = None) -> Dict:
        """生成情绪转换冥想提示词，遵循消极→中性→积极的情绪旅程"""
        try:
            # 使用默认时长
            if duration_minutes is None:
                duration_minutes = self.config.get('default_duration', 10)
            
            self.logger.info(f"开始生成情绪转换冥想提示词，时长: {duration_minutes}分钟")
            
            # 规划情绪转换旅程
            emotion_journey = self.plan_emotion_journey(user_input, duration_minutes)
            
            # 准备音乐选择和情绪分析
            current_emotion = self.local_music_lib.analyze_user_emotion(user_input)
            print(f"😊 用户当前情绪: {current_emotion}")
            print("🎭 情绪转换计划:")
            for stage in emotion_journey:
                print(f"  阶段{stage['stage']}: {stage['emotion_cn']} ({stage['duration']}秒) - {stage['description']}")
            
            # 准备DeepSeek API调用
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api.deepseek_api_key}"
            }
            
            # 构建情绪转换指导的系统提示词
            journey_description = " → ".join([stage['emotion_cn'] for stage in emotion_journey])
            
            system_prompt = f"""你是一位专业的情绪转换冥想指导师，专精于引导用户通过音乐和冥想实现情绪的健康转换。

情绪转换计划：{journey_description}
总时长：{duration_minutes}分钟

情绪转换阶段：
"""
            
            # 添加每个阶段的详细描述
            for stage in emotion_journey:
                system_prompt += f"""
阶段{stage['stage']} ({stage['duration']}秒): {stage['emotion_cn']}情绪
- 描述: {stage['description']}
- 音乐情绪: {stage['emotion_en']}
- 时间占比: {stage['time_percentage']:.1%}"""
            
            system_prompt += f"""

任务要求：
1. 严格按照上述情绪转换阶段生成冥想引导
2. 每个阶段生成2个音频段落，总共6个段落
3. 引导语要与音乐情绪同步，帮助用户跟随音乐进行情绪转换
4. 语言风格：温和、支持性、具有治愈力
5. 呼吸引导：在每个阶段融入适合的呼吸技巧
6. 平滑过渡：确保情绪转换自然流畅，不突兀

返回格式为JSON：
{{
    "analysis": "用户情绪分析和转换目标",
    "emotion_journey": "{journey_description}",
    "script_prompts": [
        "阶段1前半段：{emotion_journey[0]['emotion_cn']}情绪引导语",
        "阶段1后半段：{emotion_journey[0]['emotion_cn']}情绪深化语", 
        "阶段2前半段：{emotion_journey[1]['emotion_cn']}情绪转换语",
        "阶段2后半段：{emotion_journey[1]['emotion_cn']}情绪稳定语",
        "阶段3前半段：{emotion_journey[2]['emotion_cn']}情绪培养语",
        "阶段3后半段：{emotion_journey[2]['emotion_cn']}情绪巩固语"
    ],
    "music_prompts": [
        "阶段1前半段：{emotion_journey[0]['emotion_en']}音乐（匹配用户当前情绪）",
        "阶段1后半段：{emotion_journey[0]['emotion_en']}音乐（开始缓解）",
        "阶段2前半段：{emotion_journey[1]['emotion_en']}音乐（转向平静）", 
        "阶段2后半段：{emotion_journey[1]['emotion_en']}音乐（深化平静）",
        "阶段3前半段：{emotion_journey[2]['emotion_en']}音乐（培养积极）",
        "阶段3后半段：{emotion_journey[2]['emotion_en']}音乐（巩固收尾）"
    ],
    "stage_timings": [
        {{"stage": 1, "duration": {emotion_journey[0]['duration']}, "emotion": "{emotion_journey[0]['emotion_cn']}"}},
        {{"stage": 2, "duration": {emotion_journey[1]['duration']}, "emotion": "{emotion_journey[1]['emotion_cn']}"}},
        {{"stage": 3, "duration": {emotion_journey[2]['duration']}, "emotion": "{emotion_journey[2]['emotion_cn']}"}}
    ]
}}"""
            
            user_prompt = f"""用户倾诉：{user_input}

检测到的当前情绪：{current_emotion}
请为这位用户生成{duration_minutes}分钟的情绪转换冥想指导，帮助用户从{current_emotion}情绪逐步转换到积极平和的状态。

特别注意：
- 冥想指导语要引导用户情绪跟随音乐的情绪转换
- 在第一阶段认可和接纳用户当前的{current_emotion}情绪
- 在第二阶段温和地引导向平静过渡
- 在第三阶段培养积极正面的情绪体验"""
            
            # 调用DeepSeek API
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 3000
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            
            # 解析JSON响应
            try:
                prompts_data = json.loads(content)
                
                # 验证响应格式
                required_keys = ['analysis', 'emotion_journey', 'script_prompts', 'music_prompts', 'stage_timings']
                if not all(key in prompts_data for key in required_keys):
                    raise ValueError("API响应缺少必要字段")
                
                if len(prompts_data['script_prompts']) != 6 or len(prompts_data['music_prompts']) != 6:
                    raise ValueError("提示词数量不正确")
                
                # 添加情绪转换元信息
                prompts_data.update({
                    'user_emotion': current_emotion,
                    'emotion_journey_plan': emotion_journey,
                    'total_duration': duration_minutes,
                    'timestamp': time.time()
                })
                
                self.logger.info("情绪转换提示词生成成功")
                print(f"✅ 生成了 {len(prompts_data['script_prompts'])} 段情绪转换冥想引导")
                print(f"🎭 情绪旅程: {prompts_data['emotion_journey']}")
                print(f"📋 分析结果: {prompts_data['analysis'][:100]}...")
                
                return prompts_data
                
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON解析失败: {e}, 内容: {content[:200]}")
                raise MeditationAppError(f"提示词解析失败: {e}")
        
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API请求失败: {e}")
            raise MeditationAppError(f"网络请求失败: {e}")
        except Exception as e:
            self.logger.error(f"提示词生成失败: {e}")
            raise MeditationAppError(f"提示词生成失败: {e}")

    async def generate_speech(self, script_prompts: List[Dict], user_input: str = "") -> List[str]:
        """使用 edge-tts 生成语音文件，支持智能语音选择"""
        self.logger.info("开始生成语音文件")
        print("🔊 正在生成语音文件...")
        
        # 智能选择语音
        if user_input:
            voice_profile = get_voice_by_emotion(user_input)
            voice_name = voice_profile['voice']
            speech_rate = voice_profile['rate']
            speech_pitch = voice_profile['pitch']
            print(f"🎙️ 智能选择语音: {voice_profile['description']}")
        else:
            # 使用配置文件中的默认设置
            voice_name = self.config.audio.tts_voice
            speech_rate = self.config.audio.speech_rate
            speech_pitch = self.config.audio.speech_pitch
        
        speech_files = []
        
        for i, segment in enumerate(script_prompts):
            file_path = os.path.join(self.config.paths.temp_dir, f"speech_{i:02d}.wav")
            
            try:
                communicate = edge_tts.Communicate(
                    text=segment["text"], 
                    voice=voice_name,
                    rate=speech_rate,
                    pitch=speech_pitch
                )
                await communicate.save(file_path)
                speech_files.append(file_path)
                print(f"  ✓ 片段 {i+1} 语音生成完成")
                
            except Exception as e:
                self.logger.warning(f"片段 {i+1} 语音生成失败: {e}")
                print(f"  ⚠️ 片段 {i+1} 语音生成失败，使用静音替代")
                
                # 创建静音文件作为备选
                silence = AudioSegment.silent(duration=3000)
                silence.export(file_path, format="wav")
                speech_files.append(file_path)
        
        self.logger.info(f"所有语音文件生成完成，共 {len(speech_files)} 个")
        print(f"✅ 所有语音文件生成完成，共 {len(speech_files)} 个")
        return speech_files

    def generate_music(self, music_prompts: List[Dict], emotion_journey: List[Dict] = None) -> List[str]:
        """智能音乐生成：优先使用本地音乐库，支持情绪转换序列"""
        self.logger.info("开始智能音乐生成")
        
        # 如果有情绪转换计划，使用情绪转换音乐系统
        if emotion_journey and len(emotion_journey) > 0:
            print("� 使用情绪转换音乐系统...")
            # 提取音乐提示文本
            music_prompt_texts = [prompt if isinstance(prompt, str) else prompt.get('prompt', '') for prompt in music_prompts]
            return self._generate_emotion_journey_music(music_prompt_texts, emotion_journey)
        else:
            print("🎵 使用标准智能音乐选择系统...")
            # 使用标准智能音乐选择系统
            return self._generate_smart_music(music_prompts)
    
    def _generate_hq_music(self, music_prompts: List[Dict]) -> List[str]:
        """使用高质量音乐管理器生成音乐"""
        print("🎼 使用高质量音乐管理器...")
        music_files = []
        
        for i, segment in enumerate(music_prompts):
            file_path = os.path.join(self.config.paths.temp_dir, f"music_{i:02d}.wav")
            
            try:
                # 提取情绪（如果可用）
                emotion = segment.get('emotion', 'neutral')
                if not emotion:
                    # 从内容中推断情绪
                    content = segment.get('content', '').lower()
                    if any(word in content for word in ['stress', 'anxiety', 'worry']):
                        emotion = 'stressed'
                    elif any(word in content for word in ['sad', 'grief', 'loss']):
                        emotion = 'sad'
                    elif any(word in content for word in ['calm', 'peace', 'relax']):
                        emotion = 'calm'
                    elif any(word in content for word in ['happy', 'joy', 'positive']):
                        emotion = 'happy'
                    else:
                        emotion = 'neutral'
                
                # 使用高质量音乐管理器
                duration_seconds = self.config.meditation.segment_duration_seconds
                music_selection = self.hq_music_manager.get_best_music_for_emotion(
                    emotion, duration_seconds
                )
                
                # 保存音频文件
                import soundfile as sf
                sf.write(file_path, music_selection.audio_data, 44100)
                
                music_files.append(file_path)
                print(f"  ✅ 片段 {i+1}: {music_selection.style} ({music_selection.quality_level}质量)")
                
            except Exception as e:
                self.logger.error(f"高质量音乐生成失败，片段 {i}: {e}")
                # 创建静音文件作为回退
                silence_duration = self.config.meditation.segment_duration_seconds
                silence = AudioSegment.silent(duration=int(silence_duration * 1000))
                silence.export(file_path, format="wav")
                music_files.append(file_path)
                print(f"  ⚠️ 片段 {i+1}: 使用静音（生成失败）")
        
        return music_files
    
    def _generate_smart_music(self, music_prompts: List[Dict]) -> List[str]:
        """
        智能音乐生成：优先使用本地音乐库，失败时回退到AI生成
        
        Args:
            music_prompts: 音乐提示列表
            
        Returns:
            List[str]: 生成的音乐文件路径列表
        """
        music_files = []
        
        print("🎵 启动智能音乐选择系统...")
        
        # 获取本地音乐库状态
        library_status = self.local_music_lib.get_library_status()
        total_local_music = sum(library_status.values())
        
        if total_local_music > 0:
            print(f"📚 发现本地音乐库: {total_local_music} 首音乐")
            print(f"📊 音乐分布: {library_status}")
            
            # 尝试使用本地音乐
            local_music_files = self._generate_local_music(music_prompts)
            if local_music_files and len(local_music_files) == len(music_prompts):
                print("✅ 使用本地音乐库")
                return local_music_files
            else:
                print("⚠️ 本地音乐不足，回退到AI生成")
        else:
            print("📭 本地音乐库为空，使用AI生成")
        
        # 回退到AI生成音乐
        return self._generate_ai_music(music_prompts)
    
    def _generate_emotion_journey_music(self, music_prompts: List[str], emotion_journey: List[Dict]) -> List[str]:
        """
        根据情绪转换计划生成音乐序列
        
        Args:
            music_prompts: 音乐提示列表
            emotion_journey: 情绪转换计划
            
        Returns:
            List[str]: 音乐文件路径列表
        """
        print("🎭 使用情绪转换音乐系统...")
        
        music_files = []
        
        # 根据情绪转换计划生成6个音乐片段（每阶段2个）
        for i, music_prompt in enumerate(music_prompts):
            file_path = os.path.join(self.config.paths.temp_dir, f"music_{i:02d}.wav")
            
            # 确定当前片段对应的情绪阶段
            stage_index = i // 2  # 每阶段2个片段
            if stage_index < len(emotion_journey):
                current_stage = emotion_journey[stage_index]
                target_emotion_en = current_stage['emotion_en']
                segment_duration = current_stage['duration'] // 2  # 每阶段分为2个片段
                
                print(f"  片段 {i+1}: {current_stage['emotion_cn']} ({target_emotion_en}) - {segment_duration}秒")
                
                try:
                    # 尝试从本地音乐库获取对应情绪的音乐
                    local_music_path = self.local_music_lib.get_music_for_emotion_english(
                        target_emotion_en, segment_duration
                    )
                    
                    if local_music_path and os.path.exists(local_music_path):
                        # 使用本地音乐
                        music_segment = AudioSegment.from_file(local_music_path)
                        
                        # 调整音乐长度
                        target_length_ms = segment_duration * 1000
                        if len(music_segment) > target_length_ms:
                            music_segment = music_segment[:target_length_ms]
                        elif len(music_segment) < target_length_ms:
                            repeat_times = int(target_length_ms / len(music_segment)) + 1
                            extended_segment = AudioSegment.empty()
                            for _ in range(repeat_times):
                                extended_segment += music_segment
                            music_segment = extended_segment[:target_length_ms]
                        
                        # 导出音乐片段
                        music_segment.export(file_path, format="wav")
                        music_files.append(file_path)
                        print(f"    ✓ 使用本地音乐: {os.path.basename(local_music_path)}")
                        
                    else:
                        # 本地音乐不可用，创建调试音乐（简单的正弦波提示音）
                        print(f"    ⚠️ 本地音乐不可用，创建提示音")
                        
                        # 创建不同频率的提示音来区分情绪
                        emotion_frequencies = {
                            "Sad": 200,      # 低频，悲伤
                            "Anxiety": 300,  # 中低频，焦虑
                            "Hostility": 400, # 中频，敌意
                            "Quiet": 220,    # 低频，安静
                            "Love": 350,     # 中频，友爱
                            "Happy": 500,    # 高频，快乐
                            "Pride": 450     # 中高频，自豪
                        }
                        
                        freq = emotion_frequencies.get(target_emotion_en, 250)
                        tone = AudioSegment.sine(freq, duration=segment_duration * 1000, volume=0.1)
                        tone.export(file_path, format="wav")
                        music_files.append(file_path)
                        
                except Exception as e:
                    self.logger.warning(f"情绪音乐生成失败，片段 {i}: {e}")
                    print(f"    ⚠️ 生成失败，使用静音")
                    
                    # 创建静音作为回退
                    silence = AudioSegment.silent(duration=segment_duration * 1000)
                    silence.export(file_path, format="wav")
                    music_files.append(file_path)
            else:
                # 超出计划范围，使用静音
                silence = AudioSegment.silent(duration=20 * 1000)  # 20秒静音
                silence.export(file_path, format="wav")
                music_files.append(file_path)
        
        print(f"🎭 情绪转换音乐生成完成，共 {len(music_files)} 个片段")
        return music_files
    
    def _generate_local_music(self, music_prompts: List[Dict]) -> List[str]:
        """
        使用本地音乐库生成背景音乐
        
        Args:
            music_prompts: 音乐提示列表
            
        Returns:
            List[str]: 本地音乐文件路径列表
        """
        print("🎼 使用本地音乐库生成背景音乐...")
        
        music_files = []
        segment_duration = self.config.meditation.segment_duration_seconds
        
        # 从音乐提示中提取用户情绪信息
        # 如果第一个片段包含用户输入，用它来分析情绪
        user_content = ""
        if music_prompts and len(music_prompts) > 0:
            first_segment = music_prompts[0]
            user_content = first_segment.get('content', '') or first_segment.get('text', '')
        
        # 分析用户情绪，确定主要音乐情绪
        target_emotion = self.local_music_lib.analyze_user_emotion(user_content)
        
        for i, segment in enumerate(music_prompts):
            file_path = os.path.join(self.config.paths.temp_dir, f"music_{i:02d}.wav")
            
            try:
                # 获取本地音乐文件
                local_music_path = self.local_music_lib.get_music_for_emotion(
                    target_emotion, segment_duration
                )
                
                if local_music_path and os.path.exists(local_music_path):
                    # 加载本地音乐
                    music_segment = AudioSegment.from_file(local_music_path)
                    
                    # 调整长度到目标时长
                    target_length_ms = segment_duration * 1000
                    if len(music_segment) > target_length_ms:
                        # 截取前面部分
                        music_segment = music_segment[:target_length_ms]
                    elif len(music_segment) < target_length_ms:
                        # 循环播放以达到目标时长
                        repeat_times = int(target_length_ms / len(music_segment)) + 1
                        extended_segment = AudioSegment.empty()
                        for _ in range(repeat_times):
                            extended_segment += music_segment
                        music_segment = extended_segment[:target_length_ms]
                    
                    # 导出处理后的音乐片段
                    music_segment.export(file_path, format="wav")
                    music_files.append(file_path)
                    print(f"  ✓ 片段 {i+1}: 使用本地音乐 {os.path.basename(local_music_path)}")
                    
                else:
                    # 本地音乐不可用，创建静音
                    print(f"  ⚠️ 片段 {i+1}: 本地音乐不可用，使用静音")
                    silence = AudioSegment.silent(duration=segment_duration * 1000)
                    silence.export(file_path, format="wav")
                    music_files.append(file_path)
                    
            except Exception as e:
                self.logger.warning(f"本地音乐处理失败，片段 {i}: {e}")
                print(f"  ⚠️ 片段 {i+1}: 处理失败，使用静音")
                
                # 创建静音作为回退
                silence = AudioSegment.silent(duration=segment_duration * 1000)
                silence.export(file_path, format="wav")
                music_files.append(file_path)
        
        print(f"🎵 本地音乐生成完成，共 {len(music_files)} 个片段")
        return music_files
    
    def _generate_ai_music(self, music_prompts: List[Dict]) -> List[str]:
        """使用AI模型生成音乐"""
        try:
            self.initialize_music_model()
        except Exception as e:
            self.logger.error(f"音乐模型初始化失败: {e}")
            # 返回静音文件列表
            return self._create_silent_music_files(len(music_prompts))
        
        music_files = []
        
        for i, segment in enumerate(music_prompts):
            file_path = os.path.join(self.config.paths.temp_dir, f"music_{i:02d}.wav")
            
            try:
                # 处理输入
                inputs = self.music_processor(
                    text=[segment["prompt"]], 
                    return_tensors="pt"
                ).to(self.device)
                
                # 生成音乐
                with torch.no_grad():
                    # 计算需要的token数量以生成足够长的音乐
                    # 大约每秒需要80-100个token，20秒需要约1600-2000个token
                    target_duration_seconds = self.config.meditation.segment_duration_seconds
                    estimated_tokens = target_duration_seconds * 100  # 每秒100个token
                    
                    audio_values = self.music_model.generate(
                        **inputs, 
                        max_new_tokens=estimated_tokens,
                        do_sample=True,
                        guidance_scale=3.0
                    )
                
                # 保存音频（使用 soundfile 代替 scipy.io.wavfile.write 以移除 scipy 依赖）
                import soundfile as sf
                sample_rate = self.music_model.config.audio_encoder.sampling_rate
                audio_array = audio_values[0, 0].cpu().numpy()
                # transformers MusicGen 输出通常为 float32 [-1,1]，直接写入保持浮点精度
                sf.write(file_path, audio_array, sample_rate)
                
                music_files.append(file_path)
                print(f"  ✓ 片段 {i+1} AI音乐生成完成")
                
            except Exception as e:
                self.logger.warning(f"片段 {i+1} AI音乐生成失败: {e}")
                print(f"  ⚠️ 片段 {i+1} AI音乐生成失败，使用静音替代")
                
                # 创建静音文件作为备选
                silence_duration = self.config.meditation.segment_duration_seconds * 1000
                silence = AudioSegment.silent(duration=silence_duration)
                silence.export(file_path, format="wav")
                music_files.append(file_path)
        
        self.logger.info(f"AI音乐生成完成，共 {len(music_files)} 个")
        print(f"✅ AI音乐生成完成，共 {len(music_files)} 个")
        return music_files

    def _create_silent_music_files(self, count: int) -> List[str]:
        """创建静音音乐文件作为备选"""
        self.logger.info("创建静音音乐文件作为备选")
        print("🔇 音乐生成失败，使用静音音频")
        
        music_files = []
        silence_duration = self.config.meditation.segment_duration_seconds * 1000
        
        for i in range(count):
            file_path = os.path.join(self.config.paths.temp_dir, f"music_{i:02d}.wav")
            silence = AudioSegment.silent(duration=silence_duration)
            silence.export(file_path, format="wav")
            music_files.append(file_path)
        
        return music_files

    def combine_audio(self, speech_files: List[str], music_files: List[str]) -> str:
        """合并语音和音乐文件"""
        self.logger.info("开始合成最终音频")
        print("🎧 正在合成最终音频...")
        
        final_audio = AudioSegment.empty()
        target_segment_duration = self.config.meditation.segment_duration_seconds * 1000  # 转换为毫秒
        
        for i, (speech_file, music_file) in enumerate(zip(speech_files, music_files)):
            try:
                # 加载音频文件
                speech = AudioSegment.from_file(speech_file)
                music = AudioSegment.from_file(music_file)
                
                # 使用配置的音量减少值
                music_reduction = self.config.audio.music_volume_reduction
                
                # 调整音量：语音为主，音乐为背景
                music = music - music_reduction
                
                # 确定这个片段的实际长度（以语音和目标时长中的较长者为准）
                segment_length = max(len(speech), target_segment_duration)
                
                # 确保音乐长度足够
                if len(music) < segment_length:
                    # 如果音乐太短，通过循环或添加静音来延长
                    if len(music) > 0:
                        # 循环音乐直到达到所需长度
                        repeats_needed = (segment_length // len(music)) + 1
                        extended_music = AudioSegment.empty()
                        for _ in range(repeats_needed):
                            extended_music = extended_music + music
                        music = extended_music[:segment_length]
                    else:
                        # 如果音乐为空，创建静音
                        music = AudioSegment.silent(duration=segment_length)
                else:
                    # 如果音乐太长，截取到所需长度
                    music = music[:segment_length]
                
                # 确保语音长度匹配
                if len(speech) < segment_length:
                    padding_duration = segment_length - len(speech)
                    padding = AudioSegment.silent(duration=padding_duration)
                    speech = speech + padding
                else:
                    speech = speech[:segment_length]
                
                # 合并音频
                combined = music.overlay(speech, position=0)
                final_audio = final_audio + combined
                
                actual_duration_sec = len(combined) / 1000
                print(f"  ✓ 片段 {i+1} 合成完成 (实际时长: {actual_duration_sec:.1f}秒)")
                
            except Exception as e:
                self.logger.warning(f"片段 {i+1} 合成失败: {e}")
                print(f"  ⚠️ 片段 {i+1} 合成失败，添加静音段")
                
                # 添加目标时长的静音段
                final_audio = final_audio + AudioSegment.silent(duration=target_segment_duration)
        
        # 导出最终音频
        timestamp = int(time.time())
        output_path = os.path.join(
            self.config.paths.base_dir, 
            f"meditation_session_{timestamp}.mp3"
        )
        
        final_audio.export(output_path, format="wav")  # 使用WAV格式确保兼容性
        
        # 计算并报告实际时长
        actual_duration_seconds = len(final_audio) / 1000
        actual_duration_minutes = actual_duration_seconds / 60
        
        self.logger.info(f"最终音频合成完成: {output_path}")
        self.logger.info(f"实际时长: {actual_duration_seconds:.1f}秒 ({actual_duration_minutes:.2f}分钟)")
        print(f"✅ 最终音频合成完成: {output_path}")
        print(f"📊 实际时长: {actual_duration_seconds:.1f}秒 ({actual_duration_minutes:.2f}分钟)")
        return output_path

    def cleanup_temp_files(self):
        """清理临时文件"""
        self.logger.info("开始清理临时文件")
        print("🧹 正在清理临时文件...")
        
        try:
            temp_dir = self.config.paths.temp_dir
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
            
            self.logger.info("临时文件清理完成")
            print("✅ 临时文件清理完成")
            
        except Exception as e:
            self.logger.warning(f"清理临时文件时出错: {e}")
            print(f"⚠️ 清理临时文件时出错: {e}")

    def get_session_info(self, user_input: str, duration_minutes: int) -> Dict:
        """获取会话信息摘要"""
        segments = (duration_minutes * 60) // self.config.meditation.segment_duration_seconds
        
        return {
            "user_input": user_input,
            "duration_minutes": duration_minutes,
            "segments_count": segments,
            "segment_duration_seconds": self.config.meditation.segment_duration_seconds,
            "total_duration_seconds": segments * self.config.meditation.segment_duration_seconds,
            "device": self.device,
            "tts_voice": self.config.audio.tts_voice,
            "music_model": self.config.audio.music_model,
            "python_version": "3.13 兼容版",
            "audio_backend": "librosa + soundfile"
        }

    async def create_meditation_session(
        self, 
        user_input: str, 
        duration_minutes: int = None, 
        cleanup: bool = True
    ) -> Tuple[str, Dict]:
        """
        创建完整的冥想会话
        返回: (音频文件路径, 会话信息)
        """
        if duration_minutes is None:
            duration_minutes = self.config.meditation.default_duration_minutes
        
        session_info = self.get_session_info(user_input, duration_minutes)
        
        self.logger.info(f"开始创建冥想会话: {session_info}")
        print(f"🧘‍♀️ 开始创建 {duration_minutes} 分钟的冥想会话...")
        print(f"用户倾诉: {user_input}")
        
    # auto_cleaner 已移除（占位，无操作）
        
        try:
            # 1. 生成 prompts
            prompts_data = self.generate_prompts(user_input, duration_minutes)
            
            # 显示安慰语或分析结果
            if "analysis" in prompts_data:
                print(f"\n🧠 情绪分析: {prompts_data['analysis']}\n")
                session_info["analysis"] = prompts_data["analysis"]
            
            comfort = prompts_data.get("comfort", "")
            if comfort:
                print(f"\n🤗 安慰语: {comfort}\n")
                session_info["comfort"] = comfort
            
            # 显示情绪转换计划
            if "emotion_journey" in prompts_data:
                print(f"🎭 情绪转换计划: {prompts_data['emotion_journey']}")
                session_info["emotion_journey"] = prompts_data["emotion_journey"]
            
            # 2. 并行生成语音和音乐
            speech_task = asyncio.create_task(
                self.generate_speech(prompts_data["script_prompts"], user_input)
            )
            
            # 音乐生成在主线程中进行（因为涉及GPU操作）
            # 传递情绪转换计划到音乐生成
            emotion_journey = prompts_data.get('emotion_journey_plan', [])
            music_files = self.generate_music(prompts_data["music_prompts"], emotion_journey)
            
            # 等待语音生成完成
            speech_files = await speech_task
            
            # 3. 合成音频
            final_audio_path = self.combine_audio(speech_files, music_files)
            
            # 4. 清理临时文件
            if cleanup:
                self.cleanup_temp_files()
            
            # auto_cleaner 已移除（占位，无操作）
            
            session_info.update({
                "output_file": final_audio_path,
                "generated_segments": len(speech_files),
                "success": True
            })
            
            self.logger.info("冥想会话创建完成")
            print(f"\n🎉 冥想会话创建完成!")
            print(f"📁 输出文件: {final_audio_path}")
            
            return final_audio_path, session_info
            
        except Exception as e:
            error_msg = f"创建冥想会话失败: {e}"
            self.logger.error(error_msg)
            
            session_info.update({
                "error": str(e),
                "success": False
            })
            
            raise MeditationAppError(error_msg)


# 使用示例
async def main():
    """主函数示例"""
    try:
        # 创建应用实例
        app = MeditationApp()
        
        # 创建冥想会话
        user_input = "我最近总是失眠，而且觉得压力很大，什么都做不好。"
        output_file, session_info = await app.create_meditation_session(
            user_input=user_input,
            duration_minutes=3,
            cleanup=True
        )
        
        print(f"\n✨ 您的个性化冥想音频已准备好: {output_file}")
        print(f"📊 会话信息: {session_info}")
        
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
