"""Technical audio mastering primitives for AIMusicMed.

This module deliberately analyses signal characteristics only: duration,
integrated loudness and peak levels.  It never performs speech recognition,
classification, tagging or any other content analysis.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


TARGET_WITH_VOICE_LUFS = -16.0
TARGET_MUSIC_ONLY_LUFS = -14.0
TARGET_TRUE_PEAK_DBTP = -1.0


@dataclass(frozen=True)
class LoudnessStats:
    duration_seconds: float
    integrated_lufs: float
    true_peak_dbtp: float
    loudness_range_lu: float
    threshold_lufs: float
    target_offset_lu: float


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command), check=True, capture_output=True, text=True, encoding="utf-8"
    )


def _last_json_object(text: str) -> dict[str, object]:
    matches = re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)
    if not matches:
        raise ValueError("FFmpeg loudnorm output did not contain JSON measurements")
    return json.loads(matches[-1])


def analyze_loudness(
    path: str | Path, target_lufs: float = TARGET_WITH_VOICE_LUFS
) -> LoudnessStats:
    """Return technical loudness, true-peak and duration measurements."""
    source = str(Path(path))
    duration_result = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", source,
    ])
    duration = float(duration_result.stdout.strip())
    loudness_result = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", source,
        "-af", f"loudnorm=I={target_lufs}:TP=-1:LRA=11:print_format=json",
        "-f", "null", "-",
    ])
    measured = _last_json_object(loudness_result.stderr)
    return LoudnessStats(
        duration_seconds=duration,
        integrated_lufs=float(measured["input_i"]),
        true_peak_dbtp=float(measured["input_tp"]),
        loudness_range_lu=float(measured["input_lra"]),
        threshold_lufs=float(measured["input_thresh"]),
        target_offset_lu=float(measured["target_offset"]),
    )


def reject_severe_clipping(path: str | Path, maximum_clipped_fraction: float = 0.001) -> None:
    """Reject corrupt/flat-topped sources instead of hiding them with a limiter."""
    source = str(Path(path))
    probe = _run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=channels", "-of", "json", source,
    ])
    channels = int(json.loads(probe.stdout)["streams"][0]["channels"])
    stats = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", source,
        "-af", "astats=metadata=1:reset=0", "-f", "null", "-",
    ])
    peaks = re.findall(r"Peak level dB:\s*(-?inf|[-+0-9.]+)", stats.stderr)
    counts = re.findall(r"Peak count:\s*([-+0-9.]+)", stats.stderr)
    samples = re.findall(r"Number of samples:\s*([-+0-9.]+)", stats.stderr)
    if not peaks or not counts or not samples:
        raise ValueError("FFmpeg could not verify source clipping integrity")
    peak_db = float(peaks[-1])
    peak_count = float(counts[-1])
    sample_count = float(samples[-1]) * max(1, channels)
    clipped_fraction = peak_count / sample_count if sample_count else 1.0
    if peak_db >= -0.05 and clipped_fraction >= maximum_clipped_fraction:
        raise ValueError(
            f"source is severely clipped ({clipped_fraction:.2%} samples at full scale)"
        )


def trim_audio(data: np.ndarray, sample_rate: int, duration_seconds: float) -> np.ndarray:
    """Trim without padding or looping; channel-first and mono arrays are supported."""
    if sample_rate <= 0 or duration_seconds < 0:
        raise ValueError("sample_rate must be positive and duration_seconds non-negative")
    count = min(data.shape[-1], int(round(duration_seconds * sample_rate)))
    return np.array(data[..., :count], copy=True)


def equal_power_fade(
    data: np.ndarray, sample_rate: int, fade_in_seconds: float, fade_out_seconds: float
) -> np.ndarray:
    """Apply sine/cosine equal-power edge fades without changing duration."""
    output = np.asarray(data, dtype=np.float32).copy()
    length = output.shape[-1]
    fade_in = min(length, max(0, int(round(fade_in_seconds * sample_rate))))
    fade_out = min(length, max(0, int(round(fade_out_seconds * sample_rate))))
    if fade_in:
        phase = np.linspace(0.0, math.pi / 2.0, fade_in, endpoint=True, dtype=np.float32)
        output[..., :fade_in] *= np.sin(phase)
    if fade_out:
        phase = np.linspace(0.0, math.pi / 2.0, fade_out, endpoint=True, dtype=np.float32)
        output[..., -fade_out:] *= np.cos(phase)
    return output


def equal_power_crossfade(
    left: np.ndarray, right: np.ndarray, sample_rate: int, seconds: float
) -> np.ndarray:
    """Join two channel-first arrays with a short constant-power overlap."""
    lhs = left if left.ndim == 2 else left.reshape(1, -1)
    rhs = right if right.ndim == 2 else right.reshape(1, -1)
    if lhs.shape[0] != rhs.shape[0]:
        lhs = np.mean(lhs, axis=0, keepdims=True)
        rhs = np.mean(rhs, axis=0, keepdims=True)
    overlap = min(max(0, int(round(seconds * sample_rate))), lhs.shape[-1], rhs.shape[-1])
    if overlap == 0:
        return np.concatenate((lhs, rhs), axis=-1).astype(np.float32)
    # Use float32 throughout the crossfade to avoid a silent 2× memory
    # amplification from float64 upcast before the final cast.
    phase = np.linspace(0.0, math.pi / 2.0, overlap, endpoint=True, dtype=np.float32)
    mixed = lhs[..., -overlap:] * np.cos(phase) + rhs[..., :overlap] * np.sin(phase)
    return np.concatenate((lhs[..., :-overlap], mixed, rhs[..., overlap:]), axis=-1).astype(np.float32)


def duck_music(
    music: np.ndarray,
    voice: np.ndarray,
    sample_rate: int,
    reduction_db: float = 9.0,
    attack_seconds: float = 0.08,
    release_seconds: float = 0.6,
    threshold: float = 0.015,
) -> np.ndarray:
    """Lower background music smoothly while a voice envelope is present."""
    music_data = music if music.ndim == 2 else music.reshape(1, -1)
    voice_data = voice if voice.ndim == 2 else voice.reshape(1, -1)
    length = music_data.shape[-1]
    voice_mono = np.mean(np.abs(voice_data), axis=0)
    if voice_mono.size < length:
        voice_mono = np.pad(voice_mono, (0, length - voice_mono.size))
    else:
        voice_mono = voice_mono[:length]
    target = np.where(voice_mono >= threshold, 10 ** (-reduction_db / 20.0), 1.0)
    attack = max(1, int(round(attack_seconds * sample_rate)))
    release = max(1, int(round(release_seconds * sample_rate)))
    envelope = np.empty(length, dtype=np.float64)
    current = 1.0
    for index, desired in enumerate(target):
        window = attack if desired < current else release
        current += (desired - current) / window
        envelope[index] = current
    return (music_data * envelope).astype(np.float32)


def prevent_clipping(data: np.ndarray, peak_dbtp: float = TARGET_TRUE_PEAK_DBTP) -> np.ndarray:
    """Apply a conservative sample-peak guard; FFmpeg loudnorm remains the true-peak authority."""
    output = np.asarray(data, dtype=np.float64)
    limit = 10 ** (peak_dbtp / 20.0)
    peak = float(np.max(np.abs(output))) if output.size else 0.0
    if peak > limit and peak > 0:
        output = output * (limit / peak)
    return output.astype(np.float32)


def master_file(
    source: str | Path,
    destination: str | Path,
    *,
    has_voice: bool,
    duration_seconds: float | None = None,
    fade_seconds: float = 1.0,
) -> LoudnessStats:
    """Two-pass EBU R128 mastering to -16 LUFS (voice) or -14 LUFS (music)."""
    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    target = TARGET_WITH_VOICE_LUFS if has_voice else TARGET_MUSIC_ONLY_LUFS
    reject_severe_clipping(source_path)
    measured = analyze_loudness(source_path, target_lufs=target)
    filters: list[str] = []
    if duration_seconds is not None:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        filters.append(f"atrim=duration={duration_seconds:.6f}")
        filters.append("asetpts=PTS-STARTPTS")
    effective_duration = min(duration_seconds or measured.duration_seconds, measured.duration_seconds)
    fade = min(max(0.0, fade_seconds), effective_duration / 2.0)
    if fade:
        filters.append(f"afade=t=in:st=0:d={fade:.6f}:curve=qsin")
        filters.append(
            f"afade=t=out:st={max(0.0, effective_duration - fade):.6f}:d={fade:.6f}:curve=qsin"
        )
    filters.append(
        "loudnorm="
        f"I={target}:TP={TARGET_TRUE_PEAK_DBTP}:LRA=11:"
        f"measured_I={measured.integrated_lufs}:measured_LRA={measured.loudness_range_lu}:"
        f"measured_TP={measured.true_peak_dbtp}:measured_thresh={measured.threshold_lufs}:"
        f"offset={measured.target_offset_lu}:linear=true:print_format=summary"
    )
    filters.append(
        f"alimiter=limit={10 ** (TARGET_TRUE_PEAK_DBTP / 20.0):.8f}:level=false"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-i", str(source_path),
        "-af", ",".join(filters), "-ar", "48000", "-c:a", "pcm_s24le",
        str(destination_path),
    ])
    return analyze_loudness(destination_path, target_lufs=target)


def mix_voice_over_music(
    music: str | Path,
    voice: str | Path,
    destination: str | Path,
    *,
    voice_delay_seconds: float = 0.0,
    duck_reduction_db: float = 9.0,
    crossfade_seconds: float = 0.25,
) -> None:
    """Side-chain duck music under speech and produce a guarded intermediate WAV."""
    if voice_delay_seconds < 0 or crossfade_seconds < 0:
        raise ValueError("delays and crossfades must be non-negative")
    delay_ms = int(round(voice_delay_seconds * 1000))
    threshold = 0.02
    ratio = max(1.0, 10 ** (duck_reduction_db / 20.0))
    filter_complex = (
        f"[1:a]adelay={delay_ms}|{delay_ms},afade=t=in:d={crossfade_seconds:.3f}:curve=qsin[voice];"
        f"[0:a][voice]sidechaincompress=threshold={threshold}:ratio={ratio:.3f}:"
        "attack=80:release=600[ducked];"
        "[ducked][voice]amix=inputs=2:duration=longest:normalize=0,"
        f"alimiter=limit={10 ** (TARGET_TRUE_PEAK_DBTP / 20.0):.8f}:level=false[mixed]"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-i", str(music), "-i", str(voice),
        "-filter_complex", filter_complex, "-map", "[mixed]", "-ar", "48000",
        "-c:a", "pcm_s24le", str(Path(destination)),
    ])
