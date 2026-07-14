"""HTTP adapters for AI music providers.

Both adapters perform one paid request for one meditation segment and normalize
the returned audio to a WAV file that the existing mixing pipeline can read.
Retry and provider fallback decisions intentionally belong to the session
orchestrator.
"""

from __future__ import annotations

import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests

from audio_compat import AudioSegment


class MusicGenerationError(RuntimeError):
    """A provider failure with an explicit fallback classification."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        recoverable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.recoverable = recoverable
        self.status_code = status_code


def _is_recoverable_request_error(exc: requests.RequestException) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return (
        isinstance(exc, (requests.Timeout, requests.ConnectionError))
        or status == 429
        or (status is not None and status >= 500)
    )


def _request_error(provider: str, exc: requests.RequestException) -> MusicGenerationError:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    detail = f"HTTP {status}" if status is not None else exc.__class__.__name__
    return MusicGenerationError(
        f"{provider} music request failed: {detail}",
        provider=provider,
        recoverable=_is_recoverable_request_error(exc),
        status_code=status,
    )


def _combined_prompt(prompt: str, negative_prompt: str, target_seconds: float) -> str:
    clean_prompt = str(prompt).strip()
    if not clean_prompt:
        raise ValueError("Music generation prompt cannot be empty")
    parts = [clean_prompt, f"Target duration: {target_seconds:g} seconds."]
    clean_negative = str(negative_prompt).strip()
    if clean_negative:
        parts.append(f"Avoid: {clean_negative}")
    return "\n".join(parts)


def _write_validated_wav(
    audio_bytes: bytes,
    output_path: str | Path,
    *,
    provider: str,
    source_suffix: str,
) -> tuple[Path, float]:
    """Decode provider bytes, atomically write WAV, and return its duration."""
    if not audio_bytes:
        raise MusicGenerationError(
            f"{provider} returned empty audio",
            provider=provider,
            recoverable=True,
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_path: Path | None = None
    wav_temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.stem}.",
            suffix=source_suffix,
            delete=False,
        ) as source_file:
            source_file.write(audio_bytes)
            source_path = Path(source_file.name)

        try:
            decoded = AudioSegment.from_file(str(source_path))
        except Exception as exc:
            raise MusicGenerationError(
                f"{provider} returned audio that cannot be decoded",
                provider=provider,
                recoverable=True,
            ) from exc
        if len(decoded) <= 0:
            raise MusicGenerationError(
                f"{provider} returned audio with no playable frames",
                provider=provider,
                recoverable=True,
            )

        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.stem}.",
            suffix=".wav",
            delete=False,
        ) as wav_file:
            wav_temporary = Path(wav_file.name)
        decoded.export(str(wav_temporary), format="wav")
        try:
            verified = AudioSegment.from_file(str(wav_temporary))
        except Exception as exc:
            raise MusicGenerationError(
                f"{provider} audio could not be normalized to WAV",
                provider=provider,
                recoverable=True,
            ) from exc
        if len(verified) <= 0:
            raise MusicGenerationError(
                f"{provider} normalized WAV has no playable frames",
                provider=provider,
                recoverable=True,
            )
        wav_temporary.replace(output)
        wav_temporary = None
        return output, len(verified) / 1000.0
    finally:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        if wav_temporary is not None:
            wav_temporary.unlink(missing_ok=True)


class MusicGenerationBackend(ABC):
    """Common one-segment generation interface."""

    provider: str

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        target_duration_seconds: float,
        output_path: str | Path,
    ) -> dict[str, Any]:
        """Generate one segment and return normalized metadata."""


class ElevenLabsMusicBackend(MusicGenerationBackend):
    provider = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.elevenlabs.io/v1",
        model: str = "music_v2",
        timeout_seconds: int = 600,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        target_duration_seconds: float,
        output_path: str | Path,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise MusicGenerationError(
                "ELEVENLABS_API_KEY is not configured",
                provider=self.provider,
                recoverable=False,
            )
        duration = float(target_duration_seconds)
        if not 3 <= duration <= 600:
            raise MusicGenerationError(
                "ElevenLabs music duration must be between 3 and 600 seconds",
                provider=self.provider,
                recoverable=False,
            )
        generation_prompt = _combined_prompt(prompt, negative_prompt, duration)
        if len(generation_prompt) > 4100:
            raise MusicGenerationError(
                "ElevenLabs music prompt exceeds 4100 characters",
                provider=self.provider,
                recoverable=False,
            )
        try:
            response = requests.post(
                f"{self.base_url}/music",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": generation_prompt,
                    "model_id": self.model,
                    "music_length_ms": round(duration * 1000),
                    "force_instrumental": True,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise _request_error(self.provider, exc) from exc

        output, actual_duration = _write_validated_wav(
            response.content,
            output_path,
            provider=self.provider,
            source_suffix=".mp3",
        )
        return {
            "path": str(output),
            "music_source": "ai",
            "provider": self.provider,
            "model": self.model,
            "request_id": response.headers.get("song-id"),
            "generation_prompt": generation_prompt,
            "negative_prompt": str(negative_prompt).strip(),
            "target_duration_seconds": duration,
            "actual_duration_seconds": actual_duration,
        }


class MiniMaxMusicBackend(MusicGenerationBackend):
    provider = "minimax"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.minimaxi.com/v1",
        model: str = "music-2.6",
        timeout_seconds: int = 600,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        target_duration_seconds: float,
        output_path: str | Path,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise MusicGenerationError(
                "MINIMAX_API_KEY is not configured",
                provider=self.provider,
                recoverable=False,
            )
        duration = float(target_duration_seconds)
        if duration <= 0:
            raise MusicGenerationError(
                "MiniMax music duration must be positive",
                provider=self.provider,
                recoverable=False,
            )
        generation_prompt = _combined_prompt(prompt, negative_prompt, duration)
        if len(generation_prompt) > 2000:
            raise MusicGenerationError(
                "MiniMax music prompt exceeds 2000 characters",
                provider=self.provider,
                recoverable=False,
            )
        try:
            response = requests.post(
                f"{self.base_url}/music_generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "prompt": generation_prompt,
                    "is_instrumental": True,
                    "stream": False,
                    "output_format": "hex",
                    "audio_setting": {
                        "sample_rate": 44100,
                        "bitrate": 256000,
                        "format": "mp3",
                    },
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise _request_error(self.provider, exc) from exc
        except ValueError as exc:
            raise MusicGenerationError(
                "MiniMax returned an invalid JSON response",
                provider=self.provider,
                recoverable=True,
            ) from exc

        base_resp = payload.get("base_resp") or {}
        api_status = base_resp.get("status_code")
        if api_status not in (None, 0):
            message = base_resp.get("status_msg") or "unknown API error"
            raise MusicGenerationError(
                f"MiniMax music API error {api_status}: {message}",
                provider=self.provider,
                recoverable=False,
            )
        data = payload.get("data") or {}
        if data.get("status") not in (None, 2):
            raise MusicGenerationError(
                f"MiniMax music generation did not complete: status={data.get('status')}",
                provider=self.provider,
                recoverable=False,
            )
        audio_hex = data.get("audio")
        if not audio_hex:
            raise MusicGenerationError(
                "MiniMax returned empty audio",
                provider=self.provider,
                recoverable=True,
            )
        try:
            audio_bytes = bytes.fromhex(audio_hex)
        except (TypeError, ValueError) as exc:
            raise MusicGenerationError(
                "MiniMax returned invalid hex audio",
                provider=self.provider,
                recoverable=True,
            ) from exc

        output, actual_duration = _write_validated_wav(
            audio_bytes,
            output_path,
            provider=self.provider,
            source_suffix=".mp3",
        )
        return {
            "path": str(output),
            "music_source": "ai",
            "provider": self.provider,
            "model": self.model,
            "request_id": payload.get("trace_id"),
            "generation_prompt": generation_prompt,
            "negative_prompt": str(negative_prompt).strip(),
            "target_duration_seconds": duration,
            "actual_duration_seconds": actual_duration,
        }


def create_music_backend(provider: str, **settings: Any) -> MusicGenerationBackend:
    """Create a configured provider adapter from the stable provider id."""
    normalized = str(provider).strip().lower()
    if normalized == "elevenlabs":
        return ElevenLabsMusicBackend(**settings)
    if normalized == "minimax":
        return MiniMaxMusicBackend(**settings)
    raise ValueError(f"Unsupported AI music provider: {provider}")
