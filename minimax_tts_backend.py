"""MiniMax HTTP text-to-speech adapter."""

from __future__ import annotations

import io
import time
import wave
from pathlib import Path
from typing import Sequence

import requests


class MiniMaxTTSError(RuntimeError):
    """Raised when MiniMax cannot synthesize a valid audio file."""


def _raise_for_api_error(payload: dict) -> None:
    base_resp = payload.get("base_resp") or {}
    status_code = base_resp.get("status_code")
    if status_code not in (None, 0):
        message = base_resp.get("status_msg") or "unknown error"
        trace_id = payload.get("trace_id") or "unknown"
        raise MiniMaxTTSError(
            f"MiniMax API 错误 {status_code}: {message} (trace_id={trace_id})"
        )


def synthesize_minimax(
    text: str,
    output_path: str | Path,
    *,
    api_key: str,
    base_url: str,
    model: str,
    voice_id: str,
    speed: float = 0.8,
    volume: float = 1.0,
    pitch: int = 0,
    emotion: str = "calm",
    sample_rate: int = 32000,
    bitrate: int = 128000,
    timeout_seconds: int = 180,
    max_attempts: int = 3,
) -> Path:
    """Synthesize one non-streaming WAV response and save it locally."""
    clean_text = str(text).strip()
    if not clean_text:
        raise MiniMaxTTSError("MiniMax TTS 不接受空文本")
    if not api_key:
        raise MiniMaxTTSError("未配置 MINIMAX_API_KEY")
    if not voice_id:
        raise MiniMaxTTSError("未配置 MiniMax voice_id")

    endpoint = f"{base_url.rstrip('/')}/v1/t2a_v2"
    body = {
        "model": model,
        "text": clean_text,
        "stream": False,
        "language_boost": "Chinese",
        "output_format": "hex",
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "vol": volume,
            "pitch": pitch,
            "emotion": emotion,
        },
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": bitrate,
            "format": "wav",
            "channel": 1,
        },
        "subtitle_enable": False,
    }
    payload = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            break
        except (requests.RequestException, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            retryable = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or status == 429 or (
                status is not None and status >= 500
            )
            if not retryable or attempt >= max_attempts:
                raise MiniMaxTTSError(f"MiniMax TTS 请求失败: {exc}") from exc
            wait_seconds = attempt
            print(
                f"[MiniMax TTS] 瞬时请求失败，{wait_seconds} 秒后重试 "
                f"({attempt}/{max_attempts})",
                flush=True,
            )
            time.sleep(wait_seconds)

    if payload is None:
        raise MiniMaxTTSError("MiniMax TTS 请求未返回结果")

    _raise_for_api_error(payload)
    data = payload.get("data") or {}
    if data.get("status") not in (None, 2):
        raise MiniMaxTTSError(f"MiniMax TTS 未完成合成: status={data.get('status')}")
    audio_hex = data.get("audio")
    if not audio_hex:
        raise MiniMaxTTSError("MiniMax TTS 响应中没有音频数据")
    try:
        audio_bytes = bytes.fromhex(audio_hex)
    except ValueError as exc:
        raise MiniMaxTTSError("MiniMax TTS 返回了无效的十六进制音频") from exc
    if len(audio_bytes) < 12 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        raise MiniMaxTTSError("MiniMax TTS 返回的数据不是有效的 WAV 容器")
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            if wav_file.getnframes() <= 0 or wav_file.getnchannels() != 1:
                raise MiniMaxTTSError("MiniMax TTS WAV 必须包含有效的单声道音频")
    except (wave.Error, EOFError) as exc:
        raise MiniMaxTTSError(f"MiniMax TTS WAV 无法解码: {exc}") from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(audio_bytes)
    temporary.replace(output)
    if output.stat().st_size == 0:
        raise MiniMaxTTSError(f"MiniMax TTS 未生成有效文件: {output}")
    return output


def generate_minimax_batch(
    texts: Sequence[str],
    output_files: Sequence[str | Path],
    **settings,
) -> list[str]:
    """Generate a batch sequentially with segment-level progress."""
    if len(texts) != len(output_files):
        raise MiniMaxTTSError("MiniMax TTS 文本与输出文件数量不一致")
    if any(not str(text).strip() for text in texts):
        raise MiniMaxTTSError("MiniMax TTS 不接受空文本")

    results: list[str] = []
    total_started = time.monotonic()
    for index, (text, output) in enumerate(zip(texts, output_files), start=1):
        segment_started = time.monotonic()
        print(f"[MiniMax TTS] 正在生成 {index}/{len(texts)}: {Path(output).name}", flush=True)
        generated = synthesize_minimax(text, output, **settings)
        segment_seconds = round(time.monotonic() - segment_started, 1)
        total_seconds = round(time.monotonic() - total_started, 1)
        print(
            f"[MiniMax TTS] 已完成 {index}/{len(texts)} "
            f"(本段 {segment_seconds} 秒，累计 {total_seconds} 秒)",
            flush=True,
        )
        results.append(str(generated))
    return results
