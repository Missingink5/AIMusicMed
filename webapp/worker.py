from __future__ import annotations

import asyncio
import copy
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests

from config_manager import load_config
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
    config.audio.minimax_voice_id = "female-chengshu-jingpin"
    config.create_directories()
    return config


def _export_artifacts(source_wav: Path, target_wav: Path, guidance_text: str) -> None:
    target_wav.parent.mkdir(parents=True, exist_ok=True)
    wav_part = target_wav.with_suffix(".wav.part")
    shutil.copyfile(source_wav, wav_part)
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
            claim = client.claim()
            if claim:
                run_claim(client, claim)
            else:
                time.sleep(2)
        except requests.RequestException:
            time.sleep(5)


if __name__ == "__main__":
    main()
