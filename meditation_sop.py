"""Pure planning helpers for the meditation generation SOP."""

from __future__ import annotations

from typing import Dict, List


EMOTION_EN = {
    "忧郁": "Sad",
    "焦虑": "Anxiety",
    "敌意": "Hostility",
    "平静": "Quiet",
    "喜悦": "Happy",
    "自豪": "Pride",
    "友爱": "Love",
}

EMOTION_PATHS = {
    "忧郁": ["忧郁", "平静", "友爱"],
    "焦虑": ["焦虑", "平静", "喜悦"],
    "敌意": ["敌意", "平静", "友爱"],
    "平静": ["平静", "友爱", "喜悦"],
    "喜悦": ["喜悦", "平静", "喜悦"],
    "自豪": ["自豪", "平静", "友爱"],
    "友爱": ["友爱", "平静", "喜悦"],
}


def _stage_weights(current_emotion: str) -> List[float]:
    if current_emotion in {"忧郁", "焦虑", "敌意"}:
        return [0.40, 0.35, 0.25]
    if current_emotion == "平静":
        return [0.30, 0.40, 0.30]
    return [0.35, 0.30, 0.35]


def _allocate_track_counts(stage_durations: List[int], preferred_seconds: int) -> List[int]:
    stage_count = len(stage_durations)
    total_tracks = max(stage_count, round(sum(stage_durations) / max(1, preferred_seconds)))
    counts = [1] * stage_count
    remaining = total_tracks - stage_count
    if remaining <= 0:
        return counts

    total_duration = sum(stage_durations)
    quotas = [remaining * duration / total_duration for duration in stage_durations]
    floors = [int(quota) for quota in quotas]
    counts = [count + floor for count, floor in zip(counts, floors)]
    leftover = remaining - sum(floors)
    order = sorted(
        range(stage_count),
        key=lambda index: (quotas[index] - floors[index], stage_durations[index]),
        reverse=True,
    )
    for index in order[:leftover]:
        counts[index] += 1
    return counts


def _split_seconds(total_seconds: int, count: int) -> List[int]:
    base, remainder = divmod(total_seconds, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def plan_emotion_stages(
    current_emotion: str,
    duration_minutes: int,
    preferred_track_seconds: int = 60,
    target_emotion: str | None = None,
) -> List[Dict]:
    total_seconds = int(duration_minutes * 60)
    if total_seconds <= 0:
        raise ValueError("冥想总时长必须大于 0")

    if target_emotion is not None and target_emotion not in EMOTION_EN:
        raise ValueError(f"不支持的目标情绪: {target_emotion}")
    emotion_path = (
        [current_emotion, "平静", target_emotion]
        if target_emotion
        else EMOTION_PATHS.get(current_emotion, EMOTION_PATHS["平静"])
    )
    weights = _stage_weights(current_emotion)
    stage_durations = [int(total_seconds * weights[0]), int(total_seconds * weights[1])]
    stage_durations.append(total_seconds - sum(stage_durations))
    track_counts = _allocate_track_counts(stage_durations, preferred_track_seconds)
    descriptions = ["接纳和缓解当前情绪", "转向内心平静", "培养积极的情绪状态"]

    stages = []
    current_time = 0
    for index, (emotion, seconds, track_count) in enumerate(
        zip(emotion_path, stage_durations, track_counts)
    ):
        stages.append(
            {
                "stage": index + 1,
                "emotion_cn": emotion,
                "emotion_en": EMOTION_EN[emotion],
                "start_time": current_time,
                "duration": seconds,
                "end_time": current_time + seconds,
                "description": descriptions[index],
                "time_percentage": seconds / total_seconds,
                "track_count": track_count,
                "segment_durations": _split_seconds(seconds, track_count),
            }
        )
        current_time += seconds
    return stages


def build_music_segment_plan(stages: List[Dict]) -> List[Dict]:
    segments = []
    segment_number = 1
    for stage in stages:
        count = stage["track_count"]
        for position, seconds in enumerate(stage["segment_durations"], start=1):
            if position == 1:
                role = "进入阶段" if stage["stage"] > 1 else "接纳当下"
            elif position == count:
                role = "阶段收束"
            else:
                role = "阶段深化"
            segments.append(
                {
                    "segment_id": f"segment_{segment_number:02d}",
                    "stage": stage["stage"],
                    "stage_position": position,
                    "stage_track_count": count,
                    "duration_seconds": seconds,
                    "emotion_cn": stage["emotion_cn"],
                    "emotion_en": stage["emotion_en"],
                    "stage_goal": stage["description"],
                    "transition_role": role,
                    "prompt": f"{stage['emotion_cn']}音乐，用于{stage['description']}，{role}",
                }
            )
            segment_number += 1
    return segments
