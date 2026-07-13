"""
Python 3.13兼容版的冥想应用
使用自定义音频处理模块替代pydub
"""

import os
import sys
import json
import re
import asyncio
import logging
import requests
import time
import hashlib
import random
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import librosa
import numpy as np

# 导入兼容的音频处理模块
from audio_compat import AudioSegment
from config_manager import load_config, AppConfig
from local_music_library import LocalMusicLibrary
from minimax_tts_backend import generate_minimax_batch, MiniMaxTTSError
from meditation_sop import EMOTION_EN, build_music_segment_plan, plan_emotion_stages


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")


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
        self._session_temp_files = set()
        self._session_id = uuid.uuid4().hex[:12]
        
        # 设置日志
        self._setup_logging()
        
        self.device = "未加载（本地曲库模式）"
        
        # 本地音乐库管理器
        self.local_music_lib = LocalMusicLibrary()
        
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





    def _request_deepseek_json(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Dict:
        """Call DeepSeek and parse one JSON object."""
        if not self.config.api.deepseek_api_key:
            raise MeditationAppError("未配置 DeepSeek API Key")

        url = f"{self.config.api.deepseek_base_url.rstrip('/')}/chat/completions"
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api.deepseek_api_key}",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content.strip())

    def analyze_emotion_with_ai(self, user_input: str) -> Dict:
        """Use AI for the primary emotion; fall back transparently to keywords."""
        allowed_emotions = set(EMOTION_EN)
        try:
            result = self._request_deepseek_json(
                "你是情绪识别助手。只能从忧郁、焦虑、敌意、平静、喜悦、自豪、友爱中选择主要情绪。"
                "不要做临床诊断。返回JSON字段 primary_emotion、confidence、secondary_emotions、rationale。",
                f"用户表达：{user_input}",
                500,
            )
            primary = result.get("primary_emotion")
            if primary not in allowed_emotions:
                raise ValueError(f"AI返回了不支持的情绪: {primary}")
            secondary = [item for item in result.get("secondary_emotions", []) if item in allowed_emotions]
            analysis = {
                "primary_emotion": primary,
                "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.5)))),
                "secondary_emotions": secondary,
                "rationale": str(result.get("rationale", ""))[:300],
                "source": "ai",
            }
            print(f"🤖 AI情绪识别: {primary} (置信度 {analysis['confidence']:.0%})")
            return analysis
        except Exception as exc:
            fallback = self.local_music_lib.analyze_user_emotion(user_input)
            self.logger.warning(f"AI情绪识别不可用，使用关键词回退: {exc}")
            print(f"⚠️ AI情绪识别不可用，使用关键词回退: {fallback}")
            return {
                "primary_emotion": fallback,
                "confidence": 0.0,
                "secondary_emotions": [],
                "rationale": "AI不可用，使用本地关键词规则",
                "source": "keyword_fallback",
            }

    def prepare_session_plan(self, user_input: str, duration_minutes: int) -> Dict:
        """AI emotion -> emotion stages -> duration-based music segment plan."""
        emotion_analysis = self.analyze_emotion_with_ai(user_input)
        stages = plan_emotion_stages(
            emotion_analysis["primary_emotion"],
            duration_minutes,
            self.config.audio.preferred_track_duration_seconds,
        )
        segment_plan = build_music_segment_plan(stages)
        journey_text = " → ".join(stage["emotion_cn"] for stage in stages)
        print(f"🧭 情绪引导路径: {journey_text}")
        print(f"🎼 按每首约 {self.config.audio.preferred_track_duration_seconds} 秒规划 {len(segment_plan)} 首音乐")
        for stage in stages:
            print(
                f"  阶段{stage['stage']}: {stage['emotion_cn']} {stage['duration']}秒，"
                f"{stage['track_count']}首"
            )
        return {
            "analysis": emotion_analysis["rationale"],
            "emotion_analysis": emotion_analysis,
            "emotion_journey": journey_text,
            "emotion_journey_plan": stages,
            "music_prompts": segment_plan,
            "total_duration": duration_minutes,
            "timestamp": time.time(),
        }

    @staticmethod
    def _public_music_manifest(music_info: List[Dict]) -> List[Dict]:
        manifest = []
        for music in music_info:
            item = {
                "segment_id": music["segment_id"],
                "stage": music["stage"],
                "stage_goal": music["stage_goal"],
                "transition_role": music["transition_role"],
                "emotion": music["emotion"],
                "music_ref": music["source_file"],
                "filename_tags": music["filename_tags"],
                "source_duration_seconds": music["source_duration_seconds"],
                "render_duration_seconds": music["duration_seconds"],
                "music_features": music["music_features"],
            }
            canonical = json.dumps(item, ensure_ascii=False, sort_keys=True)
            item["grounding_fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
            manifest.append(item)
        return manifest

    def generate_guidance_for_music(self, user_input: str, plan: Dict, music_info: List[Dict]) -> List[Dict]:
        """Generate one grounded guidance segment after the concrete music is selected."""
        manifest = self._public_music_manifest(music_info)
        prompt_manifest = []
        for item in manifest:
            max_speech_seconds = max(
                1.0,
                item["render_duration_seconds"]
                - self.config.audio.speech_start_delay_seconds
                - 5.0,
            )
            max_chars = max(
                1,
                int(max_speech_seconds * 3.5 * self.config.audio.minimax_speed * 0.85),
            )
            prompt_manifest.append(
                {
                    **item,
                    "speech_start_seconds": self.config.audio.speech_start_delay_seconds,
                    "max_speech_seconds": round(max_speech_seconds, 1),
                    "max_text_characters": max_chars,
                }
            )
        try:
            result = self._request_deepseek_json(
                "你是专业冥想引导师。根据每段已经选定的音乐情绪、曲名标签、声学特征、阶段目标和时长，"
                "逐段生成中文引导词。不得虚构音乐中未提供的乐器或事件。"
                "返回JSON对象，包含scripts数组；每项必须原样返回segment_id、music_ref、grounding_fingerprint和text。"
                "text应温和自然，并与render_duration_seconds匹配。",
                json.dumps(
                    {
                        "user_context": user_input,
                        "emotion_analysis": plan["emotion_analysis"],
                        "emotion_journey": plan["emotion_journey"],
                        "music_manifest": prompt_manifest,
                    },
                    ensure_ascii=False,
                ),
                max(1800, len(manifest) * 350),
            )
            scripts = result.get("scripts")
            if not isinstance(scripts, list) or len(scripts) != len(manifest):
                raise ValueError("AI引导词数量与音乐片段数量不一致")
            expected = {item["segment_id"]: item for item in manifest}
            returned_ids = [script.get("segment_id") for script in scripts]
            if len(set(returned_ids)) != len(returned_ids) or set(returned_ids) != set(expected):
                raise ValueError("AI引导词片段ID重复、缺失或多余")
            validated = []
            for script in scripts:
                segment_id = script.get("segment_id")
                reference = expected.get(segment_id)
                if reference is None:
                    raise ValueError(f"AI返回未知片段: {segment_id}")
                if script.get("music_ref") != reference["music_ref"]:
                    raise ValueError(f"AI音乐引用不匹配: {segment_id}")
                if script.get("grounding_fingerprint") != reference["grounding_fingerprint"]:
                    raise ValueError(f"AI音乐依据指纹不匹配: {segment_id}")
                text_value = str(script.get("text", "")).strip()
                if not text_value:
                    raise ValueError(f"AI返回空引导词: {segment_id}")
                validated.append({**reference, "text": text_value, "guidance_source": "ai"})
            order = {item["segment_id"]: index for index, item in enumerate(manifest)}
            validated.sort(key=lambda item: order[item["segment_id"]])
            print(f"✅ AI已按 {len(validated)} 首具体音乐生成逐段引导词")
            return validated
        except Exception as exc:
            self.logger.warning(f"音乐对齐引导词AI生成失败，使用本地对齐模板: {exc}")
            print(f"⚠️ AI引导词生成不可用，使用音乐对齐本地模板: {exc}")
            return self._generate_grounded_fallback_guidance(manifest)

    @staticmethod
    def _generate_grounded_fallback_guidance(manifest: List[Dict]) -> List[Dict]:
        emotion_openings = {
            "焦虑": "允许此刻的紧张被看见，把注意力温柔地带回呼吸",
            "忧郁": "不必急着推开低落，让自己被稳稳地承接",
            "敌意": "觉察身体里的力量，让呼气为它留出安全的出口",
            "平静": "保持自然的呼吸，感受内在逐渐安定",
            "喜悦": "感受心中正在展开的轻盈与明亮",
            "自豪": "认可已经付出的努力，让稳定的力量留在心中",
            "友爱": "把温和与善意带向自己，也带向与他人的连接",
        }
        guidance = []
        for item in manifest:
            features = item["music_features"]
            text_value = (
                f"{emotion_openings[item['emotion']]}。"
                f"跟随这段{features['tempo_label']}、{features['energy_label']}、"
                f"音色{features['brightness_label']}、"
                f"能量{features.get('energy_trajectory', '整体平稳')}的音乐，"
                f"{item['stage_goal']}。"
                f"在{item['transition_role']}的过程中，让每一次呼吸自然衔接下一刻。"
            )
            guidance.append({**item, "text": text_value, "guidance_source": "local_fallback"})
        return guidance

    async def generate_speech_adaptive(self, script_prompts: List, music_info: List[Dict], user_input: str = "") -> List[str]:
        """根据音乐时长自适应生成语音文件"""
        self.logger.info("开始自适应语音生成")
        print("🔊 正在根据音乐时长生成自适应语音...")

        if len(script_prompts) != len(music_info):
            raise MeditationAppError(
                f"引导词与音乐片段数量不一致: {len(script_prompts)} != {len(music_info)}"
            )

        prepared_segments = []
        for i, (segment, music) in enumerate(zip(script_prompts, music_info)):
            if isinstance(segment, str):
                text_content = segment
            elif isinstance(segment, dict):
                if segment.get("segment_id") != music.get("segment_id"):
                    raise MeditationAppError(f"片段 {i+1} 的引导词与音乐ID不匹配")
                expected_fingerprint = self._public_music_manifest([music])[0]["grounding_fingerprint"]
                if segment.get("grounding_fingerprint") != expected_fingerprint:
                    raise MeditationAppError(f"片段 {i+1} 的音乐依据指纹不匹配")
                text_content = segment.get('text', str(segment))
            else:
                text_content = str(segment)

            music_duration = music['duration_seconds']
            speech_budget = max(
                1.0,
                music_duration - self.config.audio.speech_start_delay_seconds - 5.0,
            )
            adjusted_text = self._adjust_text_for_duration(
                text_content,
                speech_budget,
                allow_extension=not isinstance(segment, dict),
            )
            prepared_segments.append((adjusted_text, music_duration))

        if self.config.audio.tts_backend.lower() != "minimax":
            raise MeditationAppError("仅支持 MiniMax TTS，tts_backend 必须为 minimax")

        speech_files = [
            os.path.join(
                self.config.paths.temp_dir,
                f"speech_{self._session_id}_{i:02d}.wav",
            )
            for i in range(len(prepared_segments))
        ]
        self._session_temp_files.update(os.path.abspath(path) for path in speech_files)
        try:
            await asyncio.to_thread(
                generate_minimax_batch,
                [item[0] for item in prepared_segments],
                speech_files,
                api_key=self.config.api.minimax_api_key,
                base_url=self.config.api.minimax_base_url,
                model=self.config.audio.minimax_model,
                voice_id=self.config.audio.minimax_voice_id,
                speed=self.config.audio.minimax_speed,
                volume=self.config.audio.minimax_volume,
                pitch=self.config.audio.minimax_pitch,
                emotion=self.config.audio.minimax_emotion,
                sample_rate=self.config.audio.minimax_sample_rate,
                bitrate=self.config.audio.minimax_bitrate,
                timeout_seconds=self.config.audio.minimax_timeout_seconds,
                max_attempts=self.config.audio.minimax_max_attempts,
            )
            print(f"✅ MiniMax TTS 已完成 {len(speech_files)} 段语音")
            self.logger.info(f"MiniMax TTS 语音文件生成完成，共 {len(speech_files)} 个")
            return speech_files
        except MiniMaxTTSError as exc:
            self.logger.error(f"MiniMax TTS 语音生成失败: {exc}")
            raise MeditationAppError(str(exc)) from exc
    
    def _adjust_text_for_duration(self, text: str, target_duration: float, allow_extension: bool = True) -> str:
        """根据目标时长调整文本内容"""
        text = str(text).strip()
        if not text:
            raise MeditationAppError("冥想引导文本为空")
        if target_duration <= 0:
            raise MeditationAppError(f"音乐片段时长无效: {target_duration}")

        # 估算语音时长：中文大约每秒3-4个字符，取每秒3.5个字符
        estimated_chars_per_second = 3.5 * self.config.audio.minimax_speed * 0.85
        target_chars = max(1, int(target_duration * estimated_chars_per_second))
        
        original_length = len(text)
        
        if original_length <= target_chars:
            if not allow_extension:
                return text
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
        text = text.strip()
        if not text or target_chars <= 0:
            return ""
        if len(text) <= target_chars:
            return text

        # 同时识别中文句末标点和省略号。旧实现只按 "..." 分割，
        # 当整段中文没有三个英文句点且长度超限时会直接返回空字符串。
        sentences = [
            sentence.strip()
            for sentence in re.findall(r'.+?(?:[。！？!?]|\.{3,}|…+|$)', text)
            if sentence.strip()
        ]
        selected = []
        selected_length = 0
        for sentence in sentences:
            if selected_length + len(sentence) <= target_chars:
                selected.append(sentence)
                selected_length += len(sentence)
            else:
                break

        if selected:
            return "".join(selected)

        # 第一整句本身就超长时，优先在后半段的自然标点处截断；
        # 没有合适标点时至少保留目标长度内的正文，绝不返回空文本。
        clipped = text[:target_chars].rstrip()
        boundaries = [clipped.rfind(mark) for mark in "，；。！？,;!?"]
        boundary = max(boundaries, default=-1)
        if boundary >= max(1, target_chars // 2):
            clipped = clipped[:boundary + 1]
        return clipped or text[:1]

    def generate_music(self, music_prompts: List[Dict], emotion_journey: List[Dict] = None) -> List[Dict]:
        """按正式 SOP 从本地曲库选择整首音乐并提取内容特征。"""
        self.logger.info("开始智能音乐生成")
        if not music_prompts or not all(
            isinstance(prompt, dict) and prompt.get("segment_id") for prompt in music_prompts
        ):
            raise MeditationAppError("音乐计划必须包含有效的 segment_id")
        print("🎭 使用正式整曲情绪转换音乐系统...")
        return self._generate_planned_music(music_prompts)
    

    @staticmethod
    def _music_filename_tags(source_file: str) -> List[str]:
        stem = re.sub(r'^\(\d+\)', '', Path(source_file).stem)
        return [tag for tag in re.split(r'[，,、_\-\s]+', stem) if tag]

    @staticmethod
    def _analyze_music_content(audio: AudioSegment) -> Dict:
        """Extract short, factual acoustic descriptors for prompt grounding."""
        data = audio.data
        if data.ndim > 1:
            data = np.mean(data, axis=0)
        data = np.asarray(data, dtype=np.float32)[: audio.sample_rate * 90]
        if data.size == 0 or not np.any(data):
            return {
                "tempo_bpm": 0.0,
                "tempo_label": "无节拍",
                "rms": 0.0,
                "energy_label": "轻柔",
                "spectral_centroid_hz": 0.0,
                "brightness_label": "柔和",
                "dynamic_label": "平稳",
                "energy_trajectory": "平稳",
            }

        rms_frames = librosa.feature.rms(y=data)[0]
        rms_value = float(np.mean(rms_frames))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=data, sr=audio.sample_rate)))
        tempo, _ = librosa.beat.beat_track(y=data, sr=audio.sample_rate)
        tempo_value = float(np.asarray(tempo).reshape(-1)[0])
        dynamic_range = float(np.percentile(rms_frames, 90) - np.percentile(rms_frames, 10))
        windows = [window for window in np.array_split(data, 3) if window.size]
        window_rms = [float(np.sqrt(np.mean(np.square(window)))) for window in windows]
        if len(window_rms) == 3:
            delta = window_rms[-1] - window_rms[0]
            middle_peak = window_rms[1] > max(window_rms[0], window_rms[2]) * 1.1
            if middle_peak:
                trajectory = "中段增强后回落"
            elif delta > 0.02:
                trajectory = "逐渐增强"
            elif delta < -0.02:
                trajectory = "逐渐减弱"
            else:
                trajectory = "整体平稳"
        else:
            trajectory = "整体平稳"
        return {
            "tempo_bpm": round(tempo_value, 1),
            "tempo_label": "舒缓" if tempo_value < 75 else "中速" if tempo_value < 115 else "较快",
            "rms": round(rms_value, 4),
            "energy_label": "轻柔" if rms_value < 0.05 else "适中" if rms_value < 0.12 else "有力",
            "spectral_centroid_hz": round(centroid, 1),
            "brightness_label": "柔和" if centroid < 1800 else "均衡" if centroid < 3200 else "明亮",
            "dynamic_label": "平稳" if dynamic_range < 0.04 else "有起伏",
            "energy_trajectory": trajectory,
        }

    @staticmethod
    def _apply_music_fades(audio: AudioSegment, fade_seconds: float) -> AudioSegment:
        """Apply a symmetric fade envelope without cutting or looping the song."""
        data = np.array(audio.data, copy=True)
        if data.size == 0:
            return audio
        sample_count = data.shape[-1]
        fade_samples = min(int(max(0.0, fade_seconds) * audio.sample_rate), sample_count // 2)
        if fade_samples <= 0:
            return AudioSegment(data, audio.sample_rate)
        fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=data.dtype)
        fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=data.dtype)
        data[..., :fade_samples] *= fade_in
        data[..., -fade_samples:] *= fade_out
        return AudioSegment(data, audio.sample_rate)

    def _generate_planned_music(self, segment_plan: List[Dict]) -> List[Dict]:
        """Select and analyze concrete music according to the duration-based segment plan."""
        library = self.local_music_lib.scan_library()
        used_by_emotion = {}
        music_files = []
        print(f"🎭 按计划选择 {len(segment_plan)} 首音乐并分析内容...")

        for index, segment in enumerate(segment_plan):
            output_path = os.path.join(
                self.config.paths.temp_dir,
                f"music_{self._session_id}_{index:02d}.wav",
            )
            candidates = library.get(segment["emotion_cn"], [])
            used = used_by_emotion.setdefault(segment["emotion_cn"], set())
            unused = [path for path in candidates if path not in used]
            pool = unused or candidates
            source_path = random.choice(pool) if pool else None
            if source_path:
                used.add(source_path)

            try:
                if not source_path:
                    raise FileNotFoundError(f"{segment['emotion_cn']} 分类没有音乐")
                original_music = AudioSegment.from_file(source_path)
                source_duration = len(original_music) / 1000
                if source_duration <= 0:
                    raise ValueError("本地音乐文件为空")
                features = self._analyze_music_content(original_music)
                rendered = self._apply_music_fades(
                    original_music, self.config.audio.music_transition_fade_seconds
                )
                rendered.export(output_path, format="wav")
                self._session_temp_files.add(os.path.abspath(output_path))
                source_file = os.path.basename(source_path)
                render_duration = source_duration
                action = "整首"
            except Exception as exc:
                self.logger.error(f"音乐片段 {segment['segment_id']} 选择失败: {exc}")
                raise MeditationAppError(
                    f"音乐片段 {segment['segment_id']} 无法按整首策略生成: {exc}"
                ) from exc

            info = {
                **segment,
                "path": output_path,
                "planned_duration_seconds": segment["duration_seconds"],
                "duration_seconds": round(render_duration, 3),
                "emotion": segment["emotion_cn"],
                "source_file": source_file,
                "source_duration_seconds": round(source_duration, 2),
                "filename_tags": self._music_filename_tags(source_file),
                "music_features": features,
            }
            music_files.append(info)
            print(
                f"  ✓ {segment['segment_id']} {segment['emotion_cn']} {render_duration:.1f}秒: "
                f"{source_file}（{action}；{features['tempo_label']}、{features['energy_label']}、"
                f"{features['brightness_label']}）"
            )

        total_duration = sum(item["duration_seconds"] for item in music_files)
        print(f"✅ 音乐计划完成：{len(music_files)} 首，共 {total_duration:.1f} 秒")
        return music_files

    def combine_audio_adaptive(self, speech_files: List[str], music_info: List[Dict]) -> str:
        """基于音乐实际时长的自适应音频合成"""
        self.logger.info("开始自适应音频合成")
        print("🎧 正在进行自适应音频合成...")

        if len(speech_files) != len(music_info):
            raise MeditationAppError(
                f"语音与音乐片段数量不一致: {len(speech_files)} != {len(music_info)}"
            )
        
        final_audio = AudioSegment.empty()
        
        for i, (speech_file, music) in enumerate(zip(speech_files, music_info)):
            try:
                # 加载音频文件
                speech = AudioSegment.from_file(speech_file)
                music_segment = AudioSegment.from_file(music['path'])
                
                # 完整音乐文件决定片段实际时长，不再按规划时长裁剪或补循环。
                target_duration_ms = len(music_segment)
                
                # 使用配置的音量减少值
                music_reduction = self.config.audio.music_volume_reduction
                
                # 调整音量：语音为主，音乐为背景
                music_segment = music_segment - music_reduction
                
                speech_position_ms = int(self.config.audio.speech_start_delay_seconds * 1000)
                available_speech_ms = target_duration_ms - speech_position_ms
                if available_speech_ms <= 0:
                    raise MeditationAppError("语音起始留白不能超过整首音乐时长")
                overflow_ms = len(speech) - available_speech_ms
                if overflow_ms > 500:
                    raise MeditationAppError(
                        f"语音比可用音乐时段长 {overflow_ms / 1000:.1f} 秒，拒绝截断尾句"
                    )
                if overflow_ms > 0:
                    speech = speech[:available_speech_ms]
                
                # 合并音频
                combined = music_segment.overlay(speech, position=speech_position_ms).normalize_peak(0.95)
                crossfade_ms = int(self.config.audio.music_transition_fade_seconds * 1000)
                final_audio = final_audio.append_with_crossfade(combined, crossfade_ms)
                
                actual_duration_sec = len(combined) / 1000
                print(f"  ✓ 片段 {i+1} 合成完成 (实际时长: {actual_duration_sec:.1f}秒，音乐: {music['source_file']})")
                
            except Exception as e:
                self.logger.error(f"片段 {i+1} 合成失败: {e}")
                raise MeditationAppError(f"片段 {i+1} 合成失败: {e}") from e
        
        # 导出最终音频
        timestamp = time.time_ns()
        output_path = os.path.join(
            self.config.paths.base_dir, 
            f"meditation_session_{timestamp}.wav"
        )
        final_audio = final_audio.normalize_peak(0.95)
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
        """只清理当前会话登记的临时文件。"""
        self.logger.info("开始清理临时文件")
        print("🧹 正在清理临时文件...")
        
        failures = []
        for file_path in list(self._session_temp_files):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                self._session_temp_files.discard(file_path)
            except OSError as exc:
                failures.append(f"{file_path}: {exc}")

        if failures:
            self.logger.warning("部分临时文件清理失败: %s", "; ".join(failures))
            print(f"⚠️ 有 {len(failures)} 个临时文件清理失败，请查看日志")
        else:
            self.logger.info("临时文件清理完成")
            print("✅ 临时文件清理完成")

    def get_session_info(self, user_input: str, duration_minutes: int) -> Dict:
        """获取会话信息摘要"""
        total_seconds = duration_minutes * 60
        segments = max(3, round(total_seconds / self.config.audio.preferred_track_duration_seconds))
        
        return {
            "user_input": user_input,
            "duration_minutes": duration_minutes,
            "segments_count": segments,
            "preferred_track_duration_seconds": self.config.audio.preferred_track_duration_seconds,
            "total_duration_seconds": total_seconds,
            "device": self.device,
            "tts_backend": self.config.audio.tts_backend,
            "music_source": "local_library",
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
        user_input = str(user_input).strip()
        if not user_input:
            raise MeditationAppError("用户倾诉内容不能为空")
        if not (
            self.config.meditation.min_duration_minutes
            <= duration_minutes
            <= self.config.meditation.max_duration_minutes
        ):
            raise MeditationAppError(
                f"冥想时长必须在 {self.config.meditation.min_duration_minutes} 到 "
                f"{self.config.meditation.max_duration_minutes} 分钟之间"
            )
        self._session_id = uuid.uuid4().hex[:12]
        
        session_info = self.get_session_info(user_input, duration_minutes)
        
        self.logger.info(f"开始创建冥想会话: {session_info}")
        print(f"🧘‍♀️ 开始创建 {duration_minutes} 分钟的冥想会话...")
        print(f"用户倾诉: {user_input}")
        
        try:
            # 1. AI识别情绪，并按阶段时长规划音乐数量
            prompts_data = self.prepare_session_plan(user_input, duration_minutes)
            
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
            
            # 2. 先选择具体音乐并提取音乐内容特征
            print("🎵 开始按情绪路径选择并分析音乐...")
            
            # 传递情绪转换计划到音乐生成
            emotion_journey = prompts_data.get('emotion_journey_plan', [])
            music_info = self.generate_music(prompts_data["music_prompts"], emotion_journey)

            # 3. 根据已选音乐的情绪、内容特征和时长生成逐段引导词
            print("📝 开始生成与具体音乐对齐的引导词...")
            script_prompts = self.generate_guidance_for_music(user_input, prompts_data, music_info)

            # 4. 将对齐后的引导词交给TTS
            print("🎙️ 开始自适应语音生成...")
            speech_files = await self.generate_speech_adaptive(
                script_prompts,
                music_info,
                user_input,
            )
            
            # 5. 自适应音频合成
            print("🎧 开始自适应音频合成...")
            final_audio_path = self.combine_audio_adaptive(speech_files, music_info)
            transition_overlap = self.config.audio.music_transition_fade_seconds * max(
                0, len(music_info) - 1
            )
            actual_duration_seconds = max(
                0.0,
                sum(item["duration_seconds"] for item in music_info) - transition_overlap,
            )
            
            # 6. 清理临时文件
            if cleanup:
                self.cleanup_temp_files()
            
            session_info.update({
                "output_file": final_audio_path,
                "actual_duration_seconds": round(actual_duration_seconds, 3),
                "generated_segments": len(speech_files),
                "emotion_analysis": prompts_data["emotion_analysis"],
                "music_manifest": self._public_music_manifest(music_info),
                "guidance_sources": sorted(
                    {script.get("guidance_source", "unknown") for script in script_prompts}
                ),
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
            if cleanup:
                self.cleanup_temp_files()
            
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
