# -*- coding: utf-8 -*-
"""
Bark 冥想朗读专用脚本
- 将长文案自动分句，逐段合成并拼接
- 轻柔化处理（EQ / 轻混响 / 环境底噪）
- 可调语速、停顿、柔和度、输出采样率

用法示例：
python bark_meditation_tts.py \
  --text "现在，请闭上眼睛，慢慢地吸气……然后，缓缓呼气……" \
  --out meditation.wav \
  --speed 0.95 \
  --pause 600 \
  --softness 2 \
  --reverb 0.15 \
  --ambience none

"""

import re
import io
import argparse
from typing import List, Optional
from transformers import pipeline
import soundfile as sf
from pydub import AudioSegment, effects

# -------- 文本处理：分句与清理 --------
PUNCT = "。！？；!?;…\n"

def clean_text(text: str) -> str:
    # 去掉多余空白与不必要字符
    t = re.sub(r"[ \t]+", " ", text)
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    return t

def split_sentences(text: str, max_len: int = 140) -> List[str]:
    """
    按中文/标点分句，并确保每段不要过长（Bark 对超长文本推理更慢且易失真）
    """
    text = clean_text(text)
    # 先按换行切，再细分句
    parts = []
    for para in text.split("\n"):
        buf = ""
        for ch in para:
            buf += ch
            if ch in PUNCT or len(buf) >= max_len:
                seg = buf.strip()
                if seg:
                    parts.append(seg)
                buf = ""
        if buf.strip():
            parts.append(buf.strip())
    return parts

# -------- 音频后处理工具 --------
def change_speed(seg: AudioSegment, speed: float = 1.0) -> AudioSegment:
    """
    不改变音高的近似变速：通过改采样率再重采样
    """
    if speed == 1.0:
        return seg
    new_frame_rate = int(seg.frame_rate * speed)
    seg = seg._spawn(seg.raw_data, overrides={"frame_rate": new_frame_rate})
    return seg.set_frame_rate(24000)

def gentle_eq_soften(seg: AudioSegment, softness_db: float = 2.0) -> AudioSegment:
    """
    温和去“塑料感”：轻微低通 + 高通，和一点点整体增益回补
    softness_db：加强柔和的分贝值（2~4 较合适）
    """
    s = seg
    # 高通去低频轰鸣
    s = effects.high_pass_filter(s, cutoff=100)
    # 低通削弱齿音和过亮的高频
    s = effects.low_pass_filter(s, cutoff=8500)
    # 温和压一点峰值（避免后续混响抬头顶爆）
    s = s.apply_gain(-softness_db)
    return s

def add_simple_reverb(seg: AudioSegment, mix: float = 0.15, pre_delay_ms: int = 45) -> AudioSegment:
    """
    非常轻的“房间感”混响：用延迟副本叠加模拟（不追求音乐级算法，只求沉浸）
    mix：0~0.3 建议
    """
    if mix <= 0:
        return seg
    wet = seg - 12  # 降低副本音量
    # 多层轻延迟
    d1 = wet.delay(pre_delay_ms)
    d2 = (wet - 3).delay(pre_delay_ms + 70)
    d3 = (wet - 6).delay(pre_delay_ms + 140)
    out = seg.overlay(d1, position=0).overlay(d2, position=0).overlay(d3, position=0)
    # 轻微整体混合（再降一点，避免过“堂”）
    return out.apply_gain(-mix * 3)

def add_ambience_bed(seg: AudioSegment, ambience: str = "none", level_db: float = -28.0) -> AudioSegment:
    """
    叠加轻底噪（白噪/海浪），提升冥想沉浸感。
    这里用简单合成：白噪（纯随机）或柔化版白噪近似“海浪”。
    若你有真实海浪素材，建议改为加载 wav 并循环 overlay。
    """
    if ambience == "none":
        return seg

    import random
    import array

    duration_ms = len(seg)
    sample_rate = seg.frame_rate
    n_samples = int(sample_rate * duration_ms / 1000)
    # 生成白噪
    noise = array.array("h", (int(random.uniform(-8000, 8000)) for _ in range(n_samples)))
    noise_seg = AudioSegment(
        noise.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1
    ).set_channels(seg.channels)
    if ambience == "ocean":
        # 低通/高通塑形出“海浪感”
        noise_seg = effects.low_pass_filter(noise_seg, 1200)
        noise_seg = effects.high_pass_filter(noise_seg, 60)
    elif ambience == "white":
        # 白噪：轻轻低通去尖锐
        noise_seg = effects.low_pass_filter(noise_seg, 4000)

    noise_seg = noise_seg - (abs(level_db))
    return seg.overlay(noise_seg, loop=True)

# -------- 合成主流程 --------
def bark_tts_meditation(
    text: str,
    out_path: str = "meditation.wav",
    speed: float = 0.95,
    pause_ms: int = 600,
    softness_db: float = 2.0,
    reverb_mix: float = 0.15,
    ambience: str = "none",  # "none" | "white" | "ocean"
    target_sr: int = 24000,
    device: Optional[str] = None
):
    """
    text: 冥想引导文案
    speed: 语速（<1 慢一些，冥想建议 0.9~0.98）
    pause_ms: 句与句之间的静音时长
    softness_db: 柔和度（2~4db）
    reverb_mix: 混响比例（0~0.3）
    ambience: 背景底噪
    target_sr: 输出采样率（24k 足够冥想）
    device: 指定设备，如 "cuda:0" 或 "cpu"
    """
    # 1) 加载 Bark pipeline
    tts = pipeline("text-to-speech", model="suno/bark", device=device)

    # 2) 分句
    sentences = split_sentences(text)
    pad = AudioSegment.silent(duration=max(pause_ms, 0))

    result = AudioSegment.silent(duration=0)
    sr_ref = None

    # 3) 逐句合成 + 轻处理
    for i, sent in enumerate(sentences, 1):
        # 提示词里写明“柔和、低声、慢速地朗读”，帮助 Bark 风格更贴近冥想
        prompt_sent = f"（以温柔、缓慢、安静的女声朗读）{sent}"
        out = tts(prompt_sent)

        audio_bytes = out["audio"]
        sampling_rate = out.get("sampling_rate", 24000)
        sr_ref = sampling_rate if sr_ref is None else sr_ref

        # 用 soundfile 读内存 wav 到 pydub
        buf = io.BytesIO(audio_bytes)
        data, sr = sf.read(buf, dtype="int16")
        snd = AudioSegment(
            data.tobytes(),
            frame_rate=sr,
            sample_width=2,
            channels=1 if (len(data.shape) == 1) else data.shape[1]
        )

        # 调速（不改变音高的近似）
        snd = change_speed(snd, speed=speed)
        # 柔和化
        snd = gentle_eq_soften(snd, softness_db=softness_db)

        # 拼接：段落 + 间隔
        result += snd + pad

    # 4) 全局混响与底噪
    if reverb_mix > 0:
        result = add_simple_reverb(result, mix=reverb_mix)
    if ambience in ("white", "ocean"):
        result = add_ambience_bed(result, ambience=ambience, level_db=-28.0)

    # 5) 正常化电平并导出
    result = effects.normalize(result)
    result = result.set_frame_rate(target_sr).set_channels(1)
    result.export(out_path, format="wav")
    print(f"[OK] 已导出：{out_path}")

# -------- CLI --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=str, required=True, help="冥想引导文案")
    ap.add_argument("--out", type=str, default="meditation.wav", help="输出 wav 路径")
    ap.add_argument("--speed", type=float, default=0.95, help="语速（<1 更慢）")
    ap.add_argument("--pause", type=int, default=600, help="分句间静音毫秒")
    ap.add_argument("--softness", type=float, default=2.0, help="柔和度（dB）")
    ap.add_argument("--reverb", type=float, default=0.15, help="混响比例 0~0.3")
    ap.add_argument("--ambience", type=str, default="none", choices=["none", "white", "ocean"], help="背景底噪")
    ap.add_argument("--sr", type=int, default=24000, help="输出采样率")
    ap.add_argument("--device", type=str, default=None, help='如 "cuda:0" 或 "cpu"')
    args = ap.parse_args()

    bark_tts_meditation(
        text=args.text,
        out_path=args.out,
        speed=args.speed,
        pause_ms=args.pause,
        softness_db=args.softness,
        reverb_mix=args.reverb,
        ambience=args.ambience,
        target_sr=args.sr,
        device=args.device
    )

if __name__ == "__main__":
    main()
