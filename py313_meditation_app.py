"""
Python 3.13兼容版的冥想应用
使用自定义音频处理模块替代pydub
"""

import os
import json
import re
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import asdict
import time

from openai import OpenAI
from transformers import MusicgenForConditionalGeneration, AutoProcessor
import scipy
import torch
import edge_tts

# 导入兼容的音频处理模块
from audio_compat import AudioSegment
from config_manager import load_config, AppConfig
from voice_profiles import get_voice_by_emotion, VOICE_PROFILES

# 导入自动清理模块
try:
    from auto_cleaner import clean_before_session, clean_after_session
    AUTO_CLEANER_AVAILABLE = True
except ImportError:
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
        
        # 预设音乐库（如果启用）
        # 高质量音乐管理器
        self.hq_music_manager = None
        if HIGH_QUALITY_MUSIC_AVAILABLE and getattr(self.config.audio, 'use_high_quality_music', False):
            self.hq_music_manager = HighQualityMusicManager()
            self.logger.info("高质量音乐管理器已启用")
        else:
            self.logger.info("高质量音乐管理器已禁用，将使用AI音乐生成")
        
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

    def generate_prompts(self, user_input: str, duration_minutes: int = None) -> Dict:
        """根据用户倾诉生成结构化的 prompts"""
        if duration_minutes is None:
            duration_minutes = self.config.meditation.default_duration_minutes
            
        # 限制时长范围
        duration_minutes = max(
            self.config.meditation.min_duration_minutes,
            min(self.config.meditation.max_duration_minutes, duration_minutes)
        )
        
        self.logger.info(f"开始生成 prompts，时长: {duration_minutes} 分钟")
        print("🤖 正在生成 prompts...")
        
        # 计算时间段数量
        segments = (duration_minutes * 60) // self.config.meditation.segment_duration_seconds
        
        prompt = f"""
你是一位温柔、专业的冥想教练和音乐治疗师，现在有用户向你倾诉了内心的烦恼。
请你根据用户的倾诉内容，返回一个结构化 JSON，完成以下任务：

1. 用一两句话进行真诚、温柔的安慰；
2. 将整个冥想体验分为 {segments} 个时间段，每段持续 {self.config.meditation.segment_duration_seconds} 秒；
3. 针对每个时间段：
   - 生成一个适合该时刻的冥想引导语（30-50字，温柔指导）；
   - 生成一个用于 AI 背景音乐生成的音乐 prompt（英文，描述音乐风格与情绪）；

请将以上内容用如下 JSON 结构输出：

{{
  "comfort": "一句安慰语...",
  "script_prompts": [
    {{ "time": "00:00", "text": "现在，请找到一个舒适的位置坐下..." }},
    {{ "time": "00:20", "text": "轻轻闭上眼睛，开始关注你的呼吸..." }},
    ...
  ],
  "music_prompts": [
    {{ "time": "00:00", "prompt": "soft ambient meditation music with gentle nature sounds" }},
    {{ "time": "00:20", "prompt": "calming instrumental music with slow piano melodies" }},
    ...
  ]
}}

用户的倾诉如下：
【{user_input}】
"""

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                timeout=60.0  # 增加超时时间到60秒
            )
            
            content = response.choices[0].message.content.strip()
            
            # 提取 JSON
            match = re.search(r"{.*}", content, re.DOTALL)
            if not match:
                raise ValueError("无法找到 JSON 格式的响应")
                
            json_text = match.group(0)
            result = json.loads(json_text)
            
            # 验证结果格式
            if not all(key in result for key in ["comfort", "script_prompts", "music_prompts"]):
                raise ValueError("返回的JSON格式不正确")
            
            # 保存结果
            output_path = os.path.join(self.config.paths.base_dir, "session_prompts.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            script_count = len(result.get('script_prompts', []))
            self.logger.info(f"Prompts 生成完成，共 {script_count} 个片段")
            print(f"✅ Prompts 生成完成，共 {script_count} 个片段")
            
            return result
            
        except Exception as e:
            error_msg = f"生成 prompts 失败: {e}"
            self.logger.error(error_msg)
            raise MeditationAppError(error_msg)

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

    def generate_music(self, music_prompts: List[Dict]) -> List[str]:
        """使用高质量音乐管理器或AI模型生成背景音乐"""
        self.logger.info("开始生成背景音乐")
        print("🎵 正在生成背景音乐...")
        
        # 优先使用高质量音乐管理器
        if self.hq_music_manager:
            return self._generate_hq_music(music_prompts)
        
        # 检查是否禁用AI音乐生成
        if not getattr(self.config.audio, 'enable_ai_music', True):
            print("🔇 AI音乐生成已禁用，使用静音")
            return self._create_silent_music_files(len(music_prompts))
        
        # 使用AI模型生成音乐
        return self._generate_ai_music(music_prompts)
    
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
                
                # 保存音频
                sample_rate = self.music_model.config.audio_encoder.sampling_rate
                scipy.io.wavfile.write(
                    file_path,
                    rate=sample_rate,
                    data=audio_values[0, 0].cpu().numpy()
                )
                
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
        
        # 会话前清理
        if AUTO_CLEANER_AVAILABLE:
            clean_before_session()
        
        try:
            # 1. 生成 prompts
            prompts_data = self.generate_prompts(user_input, duration_minutes)
            
            # 显示安慰语
            comfort = prompts_data.get("comfort", "")
            if comfort:
                print(f"\n🤗 安慰语: {comfort}\n")
                session_info["comfort"] = comfort
            
            # 2. 并行生成语音和音乐
            speech_task = asyncio.create_task(
                self.generate_speech(prompts_data["script_prompts"], user_input)
            )
            
            # 音乐生成在主线程中进行（因为涉及GPU操作）
            music_files = self.generate_music(prompts_data["music_prompts"])
            
            # 等待语音生成完成
            speech_files = await speech_task
            
            # 3. 合成音频
            final_audio_path = self.combine_audio(speech_files, music_files)
            
            # 4. 清理临时文件
            if cleanup:
                self.cleanup_temp_files()
            
            # 会话后清理
            if AUTO_CLEANER_AVAILABLE:
                clean_after_session()
            
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
