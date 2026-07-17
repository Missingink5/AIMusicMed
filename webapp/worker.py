from __future__ import annotations

import asyncio
import copy
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests

from audio_mastering import master_file
from config_manager import load_config
from minimax_voice_clone import MiniMaxVoiceCloneClient, MiniMaxVoiceCloneError
from py313_meditation_app import MeditationApp

from .config import Settings
from .db import Database
from .app import safe_storage_path


class WorkerClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def post(self, path: str, payload: dict | None = None) -> requests.Response:
        response = self.session.post(f"{self.base_url}{path}", json=payload, timeout=20)
        response.raise_for_status()
        return response

    def claim(self) -> dict | None:
        response = self.post("/internal/worker/claim")
        return None if response.status_code == 204 else response.json()

    def claim_voice_clone(self) -> dict | None:
        response = self.post("/internal/worker/voice-clones/claim")
        return None if response.status_code == 204 else response.json()

    def complete_voice_clone(
        self, clone_id: str, provider_file_id: int, preview_relpath: str
    ) -> None:
        self.post(
            f"/internal/worker/voice-clones/{clone_id}/complete",
            {
                "provider_file_id": str(provider_file_id),
                "preview_relpath": preview_relpath,
                "base_resp_status_code": 0,
            },
        )

    def fail_voice_clone(self, clone_id: str, error_code: str, category: str) -> None:
        self.post(
            f"/internal/worker/voice-clones/{clone_id}/fail",
            {"error_code": error_code, "category": category},
        )

    def claim_provider_voice_action(self) -> dict | None:
        response = self.post("/internal/worker/provider-voice-actions/claim")
        return None if response.status_code == 204 else response.json()

    def complete_provider_voice_action(
        self, action_id: str, status_code: int, error_message: str | None = None
    ) -> None:
        self.post(
            f"/internal/worker/provider-voice-actions/{action_id}/complete",
            {
                "base_resp_status_code": status_code,
                "error_message": error_message,
            },
        )

    def progress(self, job_id: str, phase: str, details: dict) -> bool:
        response = self.post(
            f"/internal/worker/jobs/{job_id}/events",
            {
                "stage": phase,
                "current": details.get("current"),
                "total": details.get("total"),
                "message": "",
            },
        )
        return bool(response.json().get("cancel_requested"))

    def cancelled(self, job_id: str) -> bool:
        response = self.post(f"/internal/worker/jobs/{job_id}/heartbeat")
        return bool(response.json().get("cancel_requested"))


def _job_config(claim: dict, job_dir: Path):
    config = copy.deepcopy(load_config())
    credentials = claim.get("credentials")
    if credentials:
        config.api.deepseek_api_key = credentials["deepseek_api_key"]
        config.api.minimax_api_key = credentials["minimax_api_key"]
        config.api.elevenlabs_api_key = credentials.get("elevenlabs_api_key") or ""
    config.paths.base_dir = str(job_dir / "core")
    config.paths.cache_dir = str(job_dir / "core" / "cache")
    config.paths.temp_dir = str(job_dir / "core" / "temp")
    config.audio.minimax_voice_id = (
        claim.get("provider_voice_id") or "female-chengshu-jingpin"
    )
    config.create_directories()
    return config


def _provider_config(claim: dict):
    config = load_config()
    api_key = claim.get("minimax_api_key") or config.api.minimax_api_key
    if not api_key:
        raise RuntimeError("minimax_key_missing")
    return config, api_key


def _prepare_clone_audio(source: Path, destination: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("clone_transcode_unavailable")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    result = subprocess.run(
        [
            ffmpeg, "-y", "-v", "error", "-i", str(source), "-vn",
            "-ac", "1", "-ar", "32000", "-b:a", "128k", "-t", "300",
            "-f", "mp3", str(temporary),
        ],
        capture_output=True,
        timeout=360,
        check=False,
    )
    if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("clone_audio_invalid")
    if temporary.stat().st_size > 20 * 1024 * 1024:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("clone_audio_too_large")
    temporary.replace(destination)
    return destination


def run_voice_clone(client: WorkerClient, claim: dict) -> None:
    clone_id = claim["id"]
    source = Path(claim["source_path"])
    provider_input = source.parent / f".{clone_id}.provider.mp3"
    preview = Path(claim["preview_path"])
    provider_file_id: int | None = None
    try:
        config, api_key = _provider_config(claim)
        _prepare_clone_audio(source, provider_input)
        provider = MiniMaxVoiceCloneClient(
            api_key=api_key,
            base_url=config.api.minimax_base_url,
            timeout_seconds=config.api.music_request_timeout_seconds,
        )
        provider_file_id = provider.upload_clone_audio(provider_input)
        provider.clone_voice(
            file_id=provider_file_id,
            voice_id=claim["provider_voice_id"],
        )
        provider.activate_voice(
            voice_id=claim["provider_voice_id"],
            preview_path=preview,
            model=config.audio.minimax_model,
        )
        client.complete_voice_clone(
            clone_id, provider_file_id, claim["preview_relpath"]
        )
    except MiniMaxVoiceCloneError as exc:
        category = "provider_network" if exc.retryable else "provider_rejected"
        client.fail_voice_clone(clone_id, exc.code, category)
        if provider_file_id is not None:
            try:
                provider.delete_clone_file(provider_file_id)
            except MiniMaxVoiceCloneError:
                pass
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        code = str(exc) if str(exc) else "clone_processing_failed"
        category = "user_input" if code.startswith("clone_audio_") else "platform"
        client.fail_voice_clone(clone_id, code[:100], category)
    finally:
        provider_input.unlink(missing_ok=True)
        if not preview.is_file():
            preview.unlink(missing_ok=True)


def run_provider_voice_action(client: WorkerClient, claim: dict) -> None:
    try:
        config, api_key = _provider_config(claim)
        provider = MiniMaxVoiceCloneClient(
            api_key=api_key,
            base_url=config.api.minimax_base_url,
            timeout_seconds=config.api.music_request_timeout_seconds,
        )
        if claim["action"] == "delete":
            provider.delete_voice(claim["provider_voice_id"])
        elif claim["action"] == "delete_file":
            provider.delete_clone_file(int(claim["provider_file_id"]))
        else:
            raise RuntimeError("unsupported_provider_action")
        client.complete_provider_voice_action(claim["id"], 0)
    except MiniMaxVoiceCloneError as exc:
        client.complete_provider_voice_action(claim["id"], 503, exc.code)
    except (TypeError, ValueError, RuntimeError) as exc:
        client.complete_provider_voice_action(claim["id"], 400, str(exc)[:500])


def _export_artifacts(source_wav: Path, target_wav: Path, guidance_text: str) -> None:
    target_wav.parent.mkdir(parents=True, exist_ok=True)
    wav_part = target_wav.with_name(f".{target_wav.stem}.master.part.wav")
    master_file(
        source_wav,
        wav_part,
        has_voice=bool(guidance_text.strip()),
        fade_seconds=0,
    )
    wav_part.replace(target_wav)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("generation_export_failed")
    target_mp3 = target_wav.with_suffix(".mp3")
    mp3_part = target_mp3.with_suffix(".mp3.part")
    result = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(target_wav), "-b:a", "128k", "-f", "mp3", str(mp3_part)],
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0 or not mp3_part.is_file() or mp3_part.stat().st_size == 0:
        mp3_part.unlink(missing_ok=True)
        raise RuntimeError("generation_export_failed")
    mp3_part.replace(target_mp3)

    target_txt = target_wav.with_suffix(".txt")
    txt_part = target_txt.with_suffix(".txt.part")
    txt_part.write_text(guidance_text, encoding="utf-8")
    txt_part.replace(target_txt)


def run_claim(client: WorkerClient, claim: dict) -> None:
    job_id = claim["id"]
    target_wav = Path(claim["output_path"])
    job_dir = target_wav.parent
    cancelled = False

    def progress(event: dict) -> None:
        nonlocal cancelled
        phase = str(event.get("phase", "working"))[:80]
        details = {key: value for key, value in event.items() if key != "phase"}
        cancelled = client.progress(job_id, phase, details)

    def cancel_requested() -> bool:
        nonlocal cancelled
        cancelled = cancelled or client.cancelled(job_id)
        return cancelled

    try:
        config = _job_config(claim, job_dir)
        app = MeditationApp(config, progress_callback=progress, cancel_requested=cancel_requested)
        target = None if claim["target_emotion"] == "auto" else claim["target_emotion"]
        if target == "自信":
            target = "自豪"
        source_wav, session_info = asyncio.run(
            app.create_meditation_session(
                claim["content"],
                claim["duration_minutes"],
                cleanup=True,
                music_source=claim["music_source"],
                ai_music_provider="minimax" if claim["music_source"] == "ai" else None,
                target_emotion=target,
                include_guidance=claim["voice_mode"] == "tts",
                guidance_style=claim.get("guidance_style", "auto"),
                language_density=claim.get("language_density", "balanced"),
                selected_music=claim.get("selected_music"),
            )
        )
        if cancel_requested():
            raise RuntimeError("cancelled")
        _export_artifacts(Path(source_wav), target_wav, session_info.get("guidance_text", ""))
        client.post(f"/internal/worker/jobs/{job_id}/complete", {"title": "我的音乐冥想"})
    except Exception as exc:
        code = str(exc) if str(exc) in {"cancelled", "generation_export_failed"} else "generation_failed"
        for artifact in (target_wav, target_wav.with_suffix(".mp3"), target_wav.with_suffix(".txt")):
            artifact.unlink(missing_ok=True)
        try:
            client.post(f"/internal/worker/jobs/{job_id}/fail", {"error_code": code})
        except requests.RequestException:
            pass


def cleanup_expired(settings: Settings) -> int:
    db = Database(settings.database_path)
    removed = 0
    with db.transaction(immediate=True) as conn:
        Database.purge_expired_conversations(conn, int(time.time()))
        rows = conn.execute(
            "SELECT file_relpath,mp3_relpath FROM works "
            "WHERE is_favorite=0 AND expires_at IS NOT NULL AND expires_at<=?",
            (int(time.time()),),
        ).fetchall()
    for row in rows:
        for relpath in row:
            if relpath:
                path = safe_storage_path(settings.storage_root, relpath)
                if path.is_file():
                    path.unlink()
                    removed += 1
    return removed


def main() -> None:
    settings = Settings.from_env()
    client = WorkerClient(os.getenv("AIMUSICMED_API_URL", "http://127.0.0.1:8000"), settings.worker_token)
    cleanup_at = 0.0
    while True:
        try:
            if time.monotonic() >= cleanup_at:
                cleanup_expired(settings)
                cleanup_at = time.monotonic() + 3600
            provider_action = client.claim_provider_voice_action()
            if provider_action:
                run_provider_voice_action(client, provider_action)
                continue
            voice_clone = client.claim_voice_clone()
            if voice_clone:
                run_voice_clone(client, voice_clone)
                continue
            claim = client.claim()
            if claim:
                run_claim(client, claim)
                continue
            time.sleep(2)
        except requests.RequestException:
            time.sleep(5)


if __name__ == "__main__":
    main()
