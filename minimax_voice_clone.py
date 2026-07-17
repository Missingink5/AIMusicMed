"""MiniMax voice-cloning provider adapter.

The application keeps the user's original recording in private storage. This
adapter only handles the provider-side derivative used for cloning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

from minimax_tts_backend import synthesize_minimax


@dataclass(frozen=True)
class MiniMaxCloneResult:
    voice_id: str
    provider_file_id: int
    preview_path: Path


class MiniMaxVoiceCloneError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _provider_error(payload: dict, fallback_code: str) -> None:
    response = payload.get("base_resp") or {}
    status = response.get("status_code")
    if status not in (None, 0):
        message = str(response.get("status_msg") or fallback_code)
        raise MiniMaxVoiceCloneError(
            f"minimax_{status}",
            message,
            retryable=False,
        )


class MiniMaxVoiceCloneClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.minimaxi.com",
        timeout_seconds: int = 180,
        session: requests.Session | None = None,
    ):
        if not api_key.strip():
            raise ValueError("api_key is required")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _post(self, path: str, **kwargs) -> dict:
        try:
            response = self.session.post(
                f"{self.base_url}{path}",
                timeout=self.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise MiniMaxVoiceCloneError(
                "provider_unavailable",
                "MiniMax 暂时不可用",
                retryable=True,
            ) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            retryable = status == 429 or status >= 500
            raise MiniMaxVoiceCloneError(
                f"http_{status or 'error'}",
                "MiniMax 请求失败",
                retryable=retryable,
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            raise MiniMaxVoiceCloneError(
                "invalid_provider_response",
                "MiniMax 返回了无效响应",
                retryable=False,
            ) from exc
        _provider_error(payload, "provider_rejected")
        return payload

    def upload_clone_audio(self, path: str | Path) -> int:
        source = Path(path)
        if source.suffix.lower() not in {".mp3", ".m4a", ".wav"}:
            raise MiniMaxVoiceCloneError(
                "unsupported_clone_audio",
                "MiniMax 克隆输入必须是 MP3、M4A 或 WAV",
                retryable=False,
            )
        if not source.is_file() or source.stat().st_size <= 0:
            raise MiniMaxVoiceCloneError(
                "clone_audio_missing",
                "克隆输入文件不存在",
                retryable=False,
            )
        if source.stat().st_size > 20 * 1024 * 1024:
            raise MiniMaxVoiceCloneError(
                "clone_audio_too_large",
                "MiniMax 克隆输入不能超过 20 MB",
                retryable=False,
            )
        with source.open("rb") as stream:
            payload = self._post(
                "/v1/files/upload",
                data={"purpose": "voice_clone"},
                files={"file": (source.name, stream)},
            )
        file_id = (payload.get("file") or {}).get("file_id")
        if not isinstance(file_id, int):
            raise MiniMaxVoiceCloneError(
                "missing_file_id",
                "MiniMax 未返回克隆文件 ID",
                retryable=False,
            )
        return file_id

    def clone_voice(self, *, file_id: int, voice_id: str) -> None:
        payload = self._post(
            "/v1/voice_clone",
            headers={"Content-Type": "application/json"},
            json={
                "file_id": file_id,
                "voice_id": voice_id,
                "need_noise_reduction": True,
                "need_volume_normalization": True,
            },
        )
        if payload.get("input_sensitive") is True:
            raise MiniMaxVoiceCloneError(
                "provider_content_rejected",
                "MiniMax 拒绝了该克隆输入",
                retryable=False,
            )

    def activate_voice(
        self,
        *,
        voice_id: str,
        preview_path: str | Path,
        model: str = "speech-2.8-hd",
    ) -> Path:
        """Generate real TTS once; MiniMax previews alone do not activate a clone."""
        return synthesize_minimax(
            "现在，轻轻呼吸，让自己慢慢安定下来。",
            preview_path,
            api_key=self.session.headers["Authorization"].removeprefix("Bearer "),
            base_url=self.base_url,
            model=model,
            voice_id=voice_id,
            speed=0.8,
            emotion="calm",
            max_attempts=1,
        )

    def create_and_activate(
        self,
        *,
        provider_audio: str | Path,
        voice_id: str,
        preview_path: str | Path,
        model: str = "speech-2.8-hd",
    ) -> MiniMaxCloneResult:
        file_id = self.upload_clone_audio(provider_audio)
        try:
            self.clone_voice(file_id=file_id, voice_id=voice_id)
            preview = self.activate_voice(
                voice_id=voice_id,
                preview_path=preview_path,
                model=model,
            )
        except Exception:
            try:
                self.delete_voice(voice_id)
            except MiniMaxVoiceCloneError:
                pass
            raise
        return MiniMaxCloneResult(
            voice_id=voice_id,
            provider_file_id=file_id,
            preview_path=preview,
        )

    def delete_voice(self, voice_id: str) -> None:
        self._post(
            "/v1/delete_voice",
            headers={"Content-Type": "application/json"},
            json={"voice_type": "voice_cloning", "voice_id": voice_id},
        )

    def delete_clone_file(self, file_id: int) -> None:
        self._post(
            "/v1/files/delete",
            headers={"Content-Type": "application/json"},
            json={"file_id": file_id, "purpose": "voice_clone"},
        )
