"""Create a MiniMax cloned voice from an explicitly authorized recording."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
import soundfile as sf
from dotenv import load_dotenv


def _check_response(payload: dict, operation: str) -> None:
    response = payload.get("base_resp") or {}
    code = response.get("status_code")
    if code not in (None, 0):
        message = response.get("status_msg") or "unknown error"
        raise RuntimeError(f"{operation}失败 ({code}): {message}")


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from minimax_tts_backend import synthesize_minimax

    load_dotenv(project_root / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("reference_audio", type=Path)
    parser.add_argument("--voice-id", required=True)
    parser.add_argument(
        "--confirm-consent",
        action="store_true",
        help="Confirm authorization and third-party biometric upload consent.",
    )
    parser.add_argument("--base-url", default="https://api.minimaxi.com")
    parser.add_argument("--model", default="speech-2.8-hd")
    parser.add_argument(
        "--smoke-output",
        type=Path,
        default=project_root / "voice_refs" / "minimax_clone_smoke.wav",
    )
    args = parser.parse_args()

    if not args.confirm_consent:
        raise RuntimeError("必须使用 --confirm-consent 明确确认已授权并同意上传声音生物特征")
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        raise RuntimeError("未配置 MINIMAX_API_KEY")
    reference = args.reference_audio.resolve()
    if not reference.is_file():
        raise RuntimeError(f"参考音频不存在: {reference}")
    if reference.stat().st_size > 20 * 1024 * 1024:
        raise RuntimeError("参考音频超过 MiniMax 20 MB 上限")
    try:
        audio_info = sf.info(reference)
    except RuntimeError as exc:
        raise RuntimeError(f"参考音频无法解码: {exc}") from exc
    if not 10 <= audio_info.duration <= 300:
        raise RuntimeError("参考音频时长必须在 10 秒到 5 分钟之间")

    auth = {"Authorization": f"Bearer {api_key}"}
    with reference.open("rb") as audio_file:
        upload = requests.post(
            f"{args.base_url.rstrip('/')}/v1/files/upload",
            headers=auth,
            data={"purpose": "voice_clone"},
            files={"file": (reference.name, audio_file, "audio/wav")},
            timeout=180,
        )
    upload.raise_for_status()
    upload_payload = upload.json()
    _check_response(upload_payload, "上传参考音频")
    file_id = (upload_payload.get("file") or {}).get("file_id")
    if not file_id:
        raise RuntimeError("上传响应中没有 file_id")

    clone = requests.post(
        f"{args.base_url.rstrip('/')}/v1/voice_clone",
        headers={**auth, "Content-Type": "application/json"},
        json={
            "file_id": file_id,
            "voice_id": args.voice_id,
            "need_noise_reduction": True,
            "need_volume_normalization": True,
            "aigc_watermark": False,
        },
        timeout=180,
    )
    clone.raise_for_status()
    _check_response(clone.json(), "创建克隆音色")
    print(f"MiniMax 克隆音色已创建: {args.voice_id}")
    smoke_output = synthesize_minimax(
        "现在，请慢慢放松肩膀，感受一次自然的呼吸。",
        args.smoke_output,
        api_key=api_key,
        base_url=args.base_url,
        model=args.model,
        voice_id=args.voice_id,
        speed=0.8,
        emotion="calm",
    )
    print(f"克隆音色已激活并通过试听验证: {smoke_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
