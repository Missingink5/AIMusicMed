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
import subprocess
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
            
            system_prompt = f"""你是一位专业的情绪转换冥想指导师和情绪聚焦疗法的专家，专精于引导用户通过音乐和冥想实现情绪的健康转换。

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
            
            # 调用DeepSeek API - 优化参数减少超时
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.6,  # 降低随机性，提高生成效率
                "max_tokens": 2500,  # 适当减少最大token数
                "top_p": 0.8,       # 添加top_p参数提高效率
                "stream": False      # 确保不使用流式生成
            }
            
            # 增加超时时间并添加重试机制
            max_retries = 3
            timeout_seconds = 90  # 增加到90秒
            
            for attempt in range(max_retries):
                try:
                    print(f"🔄 正在生成情绪转换提示词... (尝试 {attempt + 1}/{max_retries})")
                    response = requests.post(url, headers=headers, json=data, timeout=timeout_seconds)
                    response.raise_for_status()
                    break  # 成功则跳出重试循环
                except requests.exceptions.Timeout:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10  # 递增等待时间: 10, 20, 30秒
                        print(f"⚠️ 请求超时，{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise requests.exceptions.Timeout("多次尝试后仍然超时，请检查网络连接或稍后再试")
                except requests.exceptions.RequestException as e:
                    if attempt < max_retries - 1:
                        print(f"⚠️ 请求失败: {e}，10秒后重试...")
                        time.sleep(10)
                        continue
                    else:
                        raise
            
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            
            # 解析JSON响应
            try:
                # 清理响应内容，移除可能的markdown标记
                content = content.strip()
                if content.startswith('```json'):
                    # 移除markdown代码块标记
                    content = content[7:]  # 移除开头的```json
                if content.endswith('```'):
                    content = content[:-3]  # 移除结尾的```
                content = content.strip()
                
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
            print(f"⚠️ API请求失败: {e}")
            
            # 降级机制：当API失败时使用本地预设模板
            print("🔄 启用降级模式，使用本地情绪转换模板...")
            return self._generate_fallback_prompts(user_input, current_emotion, emotion_journey, duration_minutes)
            
        except Exception as e:
            self.logger.error(f"提示词生成失败: {e}")
            print(f"⚠️ 提示词生成失败: {e}")
            # 同样使用降级机制
            print("🔄 启用降级模式，使用本地情绪转换模板...")
            return self._generate_fallback_prompts(user_input, current_emotion, emotion_journey, duration_minutes)

    def _generate_fallback_prompts(self, user_input: str, current_emotion: str, emotion_journey: List[Dict], duration_minutes: int) -> Dict:
        """当API失败时的降级方案：使用本地预设模板"""
        print("📝 使用本地情绪转换模板生成引导语...")
        
        # 情绪转换模板库
        emotion_templates = {
            "焦虑": {
                "analysis": f"识别到您正处于焦虑状态。我们将通过3个阶段的情绪转换，帮助您从焦虑走向内心平静，最终培养积极的心态。",
                "stage1": ["认可您当前的焦虑感受，这是正常的情绪反应", "深呼吸，让我们一起接纳这种感受"],
                "stage2": ["现在让我们慢慢放松，找到内心的平静", "感受呼吸的节奏，让平静自然流淌"],
                "stage3": ["培养内心的宁静与喜悦", "感受这份来自内心深处的平和力量"]
            },
            "忧郁": {
                "analysis": f"感受到您内心的忧郁情绪。我们将温柔地陪伴您走过这段低落期，逐步找回内心的光明与温暖。",
                "stage1": ["理解您的忧郁是暂时的，允许自己感受这份情绪", "在这份低落中，我们寻找内心的支撑点"],
                "stage2": ["慢慢地，让内心的平静开始显现", "感受那份超越忧郁的宁静力量"],
                "stage3": ["点亮内心的希望之光", "感受生命中美好事物带来的温暖"]
            },
            "敌意": {
                "analysis": f"察觉到您内心的愤怒或敌意情绪。我们将通过冥想帮助您化解这些强烈的情绪，找到内心的和谐。",
                "stage1": ["承认您的愤怒情绪，这是您内心力量的一种表达", "在安全的空间中释放这些情绪"],
                "stage2": ["让愤怒慢慢转化为内心的平静", "感受心灵深处的宁静与和谐"],
                "stage3": ["培养对自己和他人的理解与慈爱", "感受内心的温暖与包容力量"]
            },
            "平静": {
                "analysis": f"您已经处于相对平静的状态。我们将在这个基础上，进一步深化内心的宁静，并培养更多的积极情绪。",
                "stage1": ["维持当前的平静状态，感受这份内在的和谐", "让这份平静在心中稳定下来"],
                "stage2": ["在平静中连接更深层的内心智慧", "感受平静中蕴含的无限可能"],
                "stage3": ["从平静中生发出喜悦与感恩", "让积极的能量充满整个身心"]
            }
        }
        
        # 获取对应的模板，如果没有则使用通用模板
        template = emotion_templates.get(current_emotion, emotion_templates["平静"])
        
        # 生成6段引导语（每阶段2段）
        script_prompts = [
            template["stage1"][0], template["stage1"][1],
            template["stage2"][0], template["stage2"][1], 
            template["stage3"][0], template["stage3"][1]
        ]
        
        # 生成音乐提示
        music_prompts = [
            f"第一阶段前半段：{emotion_journey[0]['emotion_cn']}情绪音乐，与用户当前状态共鸣",
            f"第一阶段后半段：{emotion_journey[0]['emotion_cn']}音乐，开始舒缓",
            f"第二阶段前半段：{emotion_journey[1]['emotion_cn']}音乐，引导向平静过渡",
            f"第二阶段后半段：{emotion_journey[1]['emotion_cn']}音乐，深化平静感受",
            f"第三阶段前半段：{emotion_journey[2]['emotion_cn']}音乐，培养积极情绪",
            f"第三阶段后半段：{emotion_journey[2]['emotion_cn']}音乐，巩固积极状态"
        ]
        
        # 构建完整的降级响应
        fallback_data = {
            'analysis': template["analysis"],
            'emotion_journey': f"{emotion_journey[0]['emotion_cn']} → {emotion_journey[1]['emotion_cn']} → {emotion_journey[2]['emotion_cn']}",
            'script_prompts': script_prompts,
            'music_prompts': music_prompts,
            'stage_timings': [
                {"stage": 1, "duration": emotion_journey[0]['duration'], "emotion": emotion_journey[0]['emotion_cn']},
                {"stage": 2, "duration": emotion_journey[1]['duration'], "emotion": emotion_journey[1]['emotion_cn']},
                {"stage": 3, "duration": emotion_journey[2]['duration'], "emotion": emotion_journey[2]['emotion_cn']}
            ],
            'user_emotion': current_emotion,
            'emotion_journey_plan': emotion_journey,
            'total_duration': duration_minutes,
            'timestamp': time.time(),
            'fallback_mode': True  # 标记这是降级模式
        }
        
        print("✅ 本地模板生成完成！")
        print(f"🎭 情绪旅程: {fallback_data['emotion_journey']}")
        print(f"📝 生成了 {len(script_prompts)} 段本地冥想引导")
        
        return fallback_data

    async def generate_speech_adaptive(self, script_prompts: List, music_info: List[Dict], user_input: str = "") -> List[str]:
        """根据音乐时长自适应生成语音文件"""
        self.logger.info("开始自适应语音生成")
        print("🔊 正在根据音乐时长生成自适应语音...")
        
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
        
        for i, (segment, music) in enumerate(zip(script_prompts, music_info)):
            file_path = os.path.join(self.config.paths.temp_dir, f"speech_{i:02d}.wav")
            
            try:
                # 处理不同的数据格式：字符串或字典
                if isinstance(segment, str):
                    text_content = segment
                elif isinstance(segment, dict):
                    text_content = segment.get('text', str(segment))
                else:
                    text_content = str(segment)
                
                # 根据音乐时长调整语音内容
                music_duration = music['duration_seconds']
                adjusted_text = self._adjust_text_for_duration(text_content, music_duration)
                
                # 添加句间停顿处理
                paused_text = self._add_sentence_pauses(adjusted_text)
                
                # 直接使用普通文本生成语音
                voice_command = f'edge-tts --voice "{voice_name}" --rate="{speech_rate}" --pitch="{speech_pitch}" --text "{paused_text}" --write-media "{file_path}"'
                
                process = subprocess.run(
                    voice_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if process.returncode == 0 and os.path.exists(file_path):
                    speech_files.append(file_path)
                    print(f"  ✓ 片段 {i+1} 语音生成完成 (音乐{music_duration:.1f}秒): {adjusted_text[:30]}...")
                else:
                    self.logger.error(f"语音生成失败，片段 {i}: {process.stderr}")
                    # 创建空文件占位
                    open(file_path, 'a').close()
                    speech_files.append(file_path)
                    print(f"  ⚠️ 片段 {i+1} 语音生成失败")
                    
            except Exception as e:
                self.logger.error(f"语音生成异常，片段 {i}: {e}")
                # 创建空文件占位
                open(file_path, 'a').close()
                speech_files.append(file_path)
                print(f"  ⚠️ 片段 {i+1} 语音生成异常")
        
        self.logger.info(f"所有语音文件生成完成，共 {len(speech_files)} 个")
        print(f"✅ 所有语音文件生成完成，共 {len(speech_files)} 个")
        return speech_files

    def _add_sentence_pauses(self, text: str) -> str:
        """在句子间添加更长的停顿"""
        import re
        
        # 为每个句子结尾添加更长的停顿标记
        enhanced_text = text
        
        # 1. 在句号、问号、感叹号后添加长停顿 (更长)
        enhanced_text = re.sub(r'([。！？])(?!\s*$)', r'\1......', enhanced_text)
        
        # 2. 在逗号、分号后添加中等停顿
        enhanced_text = re.sub(r'([，；])(?!\s*$)', r'\1....', enhanced_text)
        
        # 3. 在省略号后确保有足够停顿
        enhanced_text = re.sub(r'(…)(?!\s*\.)', r'\1....', enhanced_text)
        
        # 4. 避免过多的重复点号，但保持较长停顿
        enhanced_text = re.sub(r'\.{7,}', '......', enhanced_text)
        
        return enhanced_text

    async def _generate_speech_async(self, text: str, voice: str, rate: str, pitch: str, output_path: str):
        """使用edge-tts异步API生成语音（支持SSML）"""
        # 如果是SSML文本，直接使用；否则包装成SSML
        if not text.strip().startswith('<speak'):
            text = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">{text}</speak>'
        
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)

    def _apply_ssml_enhancements(self, text: str) -> str:
        """应用简化的SSML标签改善语音自然度"""
        # 移除现有的SSML标签以避免冲突
        import re
        text = re.sub(r'<[^>]+>', '', text)
        
        # 简化的SSML增强，仅使用最基本的停顿标签
        enhanced_text = text
        
        # 1. 在句号、省略号后添加长停顿
        enhanced_text = re.sub(r'([。…]+)', r'\1<break time="1.5s"/>', enhanced_text)
        
        # 2. 在逗号、顿号后添加中等停顿
        enhanced_text = re.sub(r'([，、]+)', r'\1<break time="0.4s"/>', enhanced_text)
        
        # 3. 在问号、感叹号后添加停顿
        enhanced_text = re.sub(r'([？！]+)', r'\1<break time="0.6s"/>', enhanced_text)
        
        # 4. 为数字添加停顿（如"深呼吸4秒"）
        enhanced_text = re.sub(r'(\d+)([秒分])', r'\1<break time="0.2s"/>\2', enhanced_text)
        
        # 5. 包装在简化的SSML根标签中
        ssml_text = f'<speak>{enhanced_text}</speak>'
        
        return ssml_text
    
    def _adjust_text_for_duration(self, text: str, target_duration: float) -> str:
        """根据目标时长调整文本内容"""
        # 估算语音时长：中文大约每秒3-4个字符，取每秒3.5个字符
        estimated_chars_per_second = 3.5
        target_chars = int(target_duration * estimated_chars_per_second)
        
        original_length = len(text)
        
        if original_length <= target_chars:
            # 文本太短，需要扩展
            if target_duration > 30:  # 较长音乐，添加更多引导
                extended_text = self._extend_meditation_text(text, target_chars)
                print(f"    📝 文本扩展: {original_length}字 → {len(extended_text)}字 (音乐{target_duration:.1f}秒)")
                return extended_text
            else:
                # 短音乐，适度扩展
                return text + "...让我们在这份宁静中停留片刻..."
        else:
            # 文本太长，需要精简
            condensed_text = self._condense_meditation_text(text, target_chars)
            print(f"    ✂️ 文本精简: {original_length}字 → {len(condensed_text)}字 (音乐{target_duration:.1f}秒)")
            return condensed_text
    
    def _extend_meditation_text(self, text: str, target_chars: int) -> str:
        """扩展冥想文本以匹配较长的音乐"""
        extensions = [
            "深深地感受这一刻的美好...",
            "让这份感受在心中慢慢扩散...",
            "继续保持这样的呼吸节奏...",
            "感受内心的每一丝变化...",
            "让时间在这份宁静中缓缓流淌...",
            "拥抱这个当下的自己...",
            "在这份静谧中找到内心的力量..."
        ]
        
        extended = text
        while len(extended) < target_chars and extensions:
            addition = extensions.pop(0)
            extended += addition
            if len(extended) < target_chars:
                extended += "..."
        
        return extended[:target_chars] if len(extended) > target_chars else extended
    
    def _condense_meditation_text(self, text: str, target_chars: int) -> str:
        """精简冥想文本以匹配较短的音乐"""
        if len(text) <= target_chars:
            return text
        
        # 保留核心信息，移除重复或冗余的部分
        sentences = text.split('...')
        condensed = ""
        
        for sentence in sentences:
            if len(condensed + sentence) <= target_chars:
                condensed += sentence + "..."
            else:
                break
        
        # 确保有意义的结尾
        if condensed and not condensed.endswith('...'):
            condensed += "..."
            
        return condensed[:target_chars] if len(condensed) > target_chars else condensed

    async def generate_speech(self, script_prompts: List, user_input: str = "") -> List[str]:
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
                # 处理不同的数据格式：字符串或字典
                if isinstance(segment, str):
                    text = segment
                elif isinstance(segment, dict):
                    text = segment.get("text", segment.get("content", str(segment)))
                else:
                    text = str(segment)
                
                # 确保文本不为空
                if not text.strip():
                    text = "请深呼吸，放松身心。"
                
                communicate = edge_tts.Communicate(
                    text=text, 
                    voice=voice_name,
                    rate=speech_rate,
                    pitch=speech_pitch
                )
                await communicate.save(file_path)
                speech_files.append(file_path)
                print(f"  ✓ 片段 {i+1} 语音生成完成: {text[:30]}...")
                
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

    def generate_music(self, music_prompts: List[Dict], emotion_journey: List[Dict] = None) -> List[Dict]:
        """智能音乐生成：优先使用本地音乐库，支持情绪转换序列，返回包含时长信息的音乐数据"""
        self.logger.info("开始智能音乐生成")
        
        # 如果有情绪转换计划，使用情绪转换音乐系统
        if emotion_journey and len(emotion_journey) > 0:
            print("🎭 使用情绪转换音乐系统...")
            # 提取音乐提示文本
            music_prompt_texts = [prompt if isinstance(prompt, str) else prompt.get('prompt', '') for prompt in music_prompts]
            return self._generate_emotion_journey_music(music_prompt_texts, emotion_journey)
        else:
            print("🎵 使用标准智能音乐选择系统...")
            # 使用标准智能音乐选择系统
            music_files = self._generate_smart_music(music_prompts)
            
            # 转换为包含时长信息的格式
            music_info = []
            for i, file_path in enumerate(music_files):
                try:
                    # 尝试获取音频文件的实际时长
                    audio = AudioSegment.from_file(file_path)
                    duration_seconds = len(audio) / 1000
                except:
                    # 如果失败，使用默认时长
                    duration_seconds = self.config.meditation.segment_duration_seconds
                
                music_info.append({
                    'path': file_path,
                    'duration_seconds': duration_seconds,
                    'emotion': f"片段{i+1}",
                    'emotion_en': "Unknown",
                    'source_file': os.path.basename(file_path)
                })
            
            return music_info
    
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
    
    def _generate_emotion_journey_music(self, music_prompts: List[str], emotion_journey: List[Dict]) -> List[Dict]:
        """
        根据情绪转换计划生成音乐序列（以音乐为主导）
        
        Args:
            music_prompts: 音乐提示列表
            emotion_journey: 情绪转换计划
            
        Returns:
            List[Dict]: 音乐文件信息列表，包含路径和实际时长
        """
        print("🎭 使用情绪转换音乐系统（以音乐为主导）...")
        
        music_files = []
        
        # 根据情绪转换计划生成6个音乐片段（每阶段2个）
        for i, music_prompt in enumerate(music_prompts):
            file_path = os.path.join(self.config.paths.temp_dir, f"music_{i:02d}.wav")
            
            # 确定当前片段对应的情绪阶段
            stage_index = i // 2  # 每阶段2个片段
            if stage_index < len(emotion_journey):
                current_stage = emotion_journey[stage_index]
                target_emotion_en = current_stage['emotion_en']
                suggested_duration = current_stage['duration'] // 2  # 每阶段分为2个片段
                
                try:
                    # 尝试从本地音乐库获取对应情绪的音乐
                    local_music_path = self.local_music_lib.get_music_for_emotion_english(
                        target_emotion_en, suggested_duration
                    )
                    
                    if local_music_path and os.path.exists(local_music_path):
                        # 获取原始音乐的实际时长
                        original_music = AudioSegment.from_file(local_music_path)
                        original_duration_seconds = len(original_music) / 1000
                        
                        # 决定最终使用的时长（以音乐为主导，允许±30秒弹性）
                        min_duration = max(10, suggested_duration - 30)  # 最少10秒
                        max_duration = suggested_duration + 30
                        
                        if original_duration_seconds <= max_duration:
                            # 音乐时长在可接受范围内，使用完整音乐
                            final_duration = original_duration_seconds
                            music_segment = original_music
                            print(f"  片段 {i+1}: {current_stage['emotion_cn']} ({target_emotion_en}) - 使用完整音乐 {final_duration:.1f}秒")
                        else:
                            # 音乐太长，截取到最大允许时长
                            final_duration = max_duration
                            music_segment = original_music[:int(max_duration * 1000)]
                            print(f"  片段 {i+1}: {current_stage['emotion_cn']} ({target_emotion_en}) - 截取音乐 {final_duration:.1f}秒")
                        
                        # 如果音乐太短，适当循环
                        if original_duration_seconds < min_duration:
                            repeat_times = int(min_duration / original_duration_seconds) + 1
                            extended_segment = AudioSegment.empty()
                            for _ in range(repeat_times):
                                extended_segment += original_music
                            final_duration = min_duration
                            music_segment = extended_segment[:int(min_duration * 1000)]
                            print(f"  片段 {i+1}: {current_stage['emotion_cn']} ({target_emotion_en}) - 循环音乐 {final_duration:.1f}秒")
                        
                        # 导出音乐片段
                        music_segment.export(file_path, format="wav")
                        
                        # 保存音乐文件信息（包含实际时长）
                        music_info = {
                            'path': file_path,
                            'duration_seconds': final_duration,
                            'emotion': current_stage['emotion_cn'],
                            'emotion_en': target_emotion_en,
                            'source_file': os.path.basename(local_music_path)
                        }
                        music_files.append(music_info)
                        print(f"🎵 选择本地音乐: {os.path.basename(local_music_path)} (英文情绪: {target_emotion_en} -> 中文: {current_stage['emotion_cn']})")
                        print(f"    ✓ 使用本地音乐: {os.path.basename(local_music_path)}")
                        
                    else:
                        # 本地音乐不可用，创建调试音乐（简单的正弦波提示音）
                        print(f"    ⚠️ 本地音乐不可用，创建提示音")
                        
                        # 使用建议时长创建提示音
                        final_duration = suggested_duration
                        
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
                        tone = AudioSegment.sine(freq, duration=int(final_duration * 1000), volume=0.1)
                        tone.export(file_path, format="wav")
                        
                        music_info = {
                            'path': file_path,
                            'duration_seconds': final_duration,
                            'emotion': current_stage['emotion_cn'],
                            'emotion_en': target_emotion_en,
                            'source_file': f"提示音_{freq}Hz"
                        }
                        music_files.append(music_info)
                        
                except Exception as e:
                    self.logger.warning(f"情绪音乐生成失败，片段 {i}: {e}")
                    print(f"    ⚠️ 生成失败，使用静音")
                    
                    # 使用建议时长创建静音
                    final_duration = suggested_duration
                    
                    # 创建静音作为回退
                    silence = AudioSegment.silent(duration=int(final_duration * 1000))
                    silence.export(file_path, format="wav")
                    
                    music_info = {
                        'path': file_path,
                        'duration_seconds': final_duration,
                        'emotion': current_stage['emotion_cn'],
                        'emotion_en': target_emotion_en,
                        'source_file': "静音"
                    }
                    music_files.append(music_info)
            else:
                # 超出计划范围，使用静音
                final_duration = 20  # 默认20秒
                silence = AudioSegment.silent(duration=int(final_duration * 1000))
                silence.export(file_path, format="wav")
                
                music_info = {
                    'path': file_path,
                    'duration_seconds': final_duration,
                    'emotion': "静音",
                    'emotion_en': "Silence",
                    'source_file': "静音"
                }
                music_files.append(music_info)
        
        # 显示音乐选择结果
        total_duration = sum(info['duration_seconds'] for info in music_files)
        print(f"🎭 情绪转换音乐生成完成，共 {len(music_files)} 个片段，总时长 {total_duration:.1f}秒")
        
        # 显示每个片段的详细信息
        for i, info in enumerate(music_files):
            print(f"  📂 敌意: 9 首音乐")
            print(f"  📂 忧郁: 9 首音乐")  
            print(f"  📂 焦虑: 8 首音乐")
            print(f"  📂 平静: 10 首音乐")
            print(f"  📂 喜悦: 8 首音乐")
            print(f"  📂 自豪: 9 首音乐")
            print(f"  📂 友爱: 8 首音乐")
            break  # 只显示一次库状态
        
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

    def combine_audio_adaptive(self, speech_files: List[str], music_info: List[Dict]) -> str:
        """基于音乐实际时长的自适应音频合成"""
        self.logger.info("开始自适应音频合成")
        print("🎧 正在进行自适应音频合成...")
        
        final_audio = AudioSegment.empty()
        
        for i, (speech_file, music) in enumerate(zip(speech_files, music_info)):
            try:
                # 加载音频文件
                speech = AudioSegment.from_file(speech_file)
                music_segment = AudioSegment.from_file(music['path'])
                
                # 使用音乐的实际时长作为片段时长
                target_duration_ms = int(music['duration_seconds'] * 1000)
                
                # 使用配置的音量减少值
                music_reduction = self.config.audio.music_volume_reduction
                
                # 调整音量：语音为主，音乐为背景
                music_segment = music_segment - music_reduction
                
                # 确保音乐长度精确匹配
                if len(music_segment) != target_duration_ms:
                    if len(music_segment) > target_duration_ms:
                        music_segment = music_segment[:target_duration_ms]
                    else:
                        # 音乐太短，添加静音补充
                        padding = AudioSegment.silent(duration=target_duration_ms - len(music_segment))
                        music_segment = music_segment + padding
                
                # 调整语音长度匹配音乐
                if len(speech) < target_duration_ms:
                    # 语音太短，添加静音
                    padding_duration = target_duration_ms - len(speech)
                    padding = AudioSegment.silent(duration=padding_duration)
                    speech = speech + padding
                else:
                    # 语音太长，截取（这种情况应该很少发生，因为已经根据音乐时长调整了文本）
                    speech = speech[:target_duration_ms]
                
                # 合并音频
                combined = music_segment.overlay(speech, position=0)
                final_audio = final_audio + combined
                
                actual_duration_sec = len(combined) / 1000
                print(f"  ✓ 片段 {i+1} 合成完成 (实际时长: {actual_duration_sec:.1f}秒，音乐: {music['source_file']})")
                
            except Exception as e:
                self.logger.warning(f"片段 {i+1} 合成失败: {e}")
                print(f"  ⚠️ 片段 {i+1} 合成失败，添加静音段")
                
                # 添加目标时长的静音段
                target_duration_ms = int(music['duration_seconds'] * 1000)
                final_audio = final_audio + AudioSegment.silent(duration=target_duration_ms)
        
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
            
            # 2. 首先生成音乐（以音乐为主导）
            print("🎵 开始智能音乐生成...")
            
            # 传递情绪转换计划到音乐生成
            emotion_journey = prompts_data.get('emotion_journey_plan', [])
            music_info = self.generate_music(prompts_data["music_prompts"], emotion_journey)
            
            # 3. 根据音乐实际时长生成自适应语音
            print("🎙️ 开始自适应语音生成...")
            speech_files = await self.generate_speech_adaptive(
                prompts_data["script_prompts"], 
                music_info, 
                user_input
            )
            
            # 4. 自适应音频合成
            print("🎧 开始自适应音频合成...")
            final_audio_path = self.combine_audio_adaptive(speech_files, music_info)
            
            # 5. 清理临时文件
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
