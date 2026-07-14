import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from music_generation_backends import (
    ElevenLabsMusicBackend,
    MiniMaxMusicBackend,
    MusicGenerationError,
    create_music_backend,
)


class MusicGenerationBackendTests(unittest.TestCase):
    @patch("music_generation_backends._write_validated_wav")
    @patch("music_generation_backends.requests.post")
    def test_elevenlabs_request_and_metadata(self, post, write_wav):
        response = Mock(content=b"audio", headers={"song-id": "song-123"})
        response.raise_for_status.return_value = None
        post.return_value = response
        write_wav.return_value = (Path("segment.wav"), 59.4)
        backend = ElevenLabsMusicBackend(api_key="eleven-key")

        result = backend.generate(
            prompt="Calm ambient piano",
            negative_prompt="vocals, abrupt ending",
            target_duration_seconds=60,
            output_path="segment.wav",
        )

        request = post.call_args
        self.assertEqual(request.args[0], "https://api.elevenlabs.io/v1/music")
        self.assertEqual(request.kwargs["headers"]["xi-api-key"], "eleven-key")
        self.assertEqual(request.kwargs["json"]["model_id"], "music_v2")
        self.assertEqual(request.kwargs["json"]["music_length_ms"], 60000)
        self.assertTrue(request.kwargs["json"]["force_instrumental"])
        self.assertIn("Target duration: 60 seconds", request.kwargs["json"]["prompt"])
        self.assertEqual(result["provider"], "elevenlabs")
        self.assertEqual(result["request_id"], "song-123")
        self.assertEqual(result["actual_duration_seconds"], 59.4)
        self.assertNotIn("eleven-key", str(result))

    @patch("music_generation_backends._write_validated_wav")
    @patch("music_generation_backends.requests.post")
    def test_minimax_request_decodes_hex_and_returns_metadata(self, post, write_wav):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {"audio": b"mp3 data".hex(), "status": 2},
            "base_resp": {"status_code": 0},
            "trace_id": "trace-123",
        }
        post.return_value = response
        write_wav.return_value = (Path("segment.wav"), 47.2)
        backend = MiniMaxMusicBackend(api_key="minimax-key")

        result = backend.generate(
            prompt="Warm meditative strings",
            negative_prompt="lyrics",
            target_duration_seconds=45,
            output_path="segment.wav",
        )

        request = post.call_args
        self.assertEqual(request.args[0], "https://api.minimaxi.com/v1/music_generation")
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer minimax-key")
        body = request.kwargs["json"]
        self.assertEqual(body["model"], "music-2.6")
        self.assertTrue(body["is_instrumental"])
        self.assertEqual(body["output_format"], "hex")
        self.assertEqual(
            body["audio_setting"],
            {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"},
        )
        self.assertEqual(write_wav.call_args.args[0], b"mp3 data")
        self.assertEqual(result["target_duration_seconds"], 45.0)
        self.assertEqual(result["request_id"], "trace-123")

    @patch("music_generation_backends.requests.post")
    def test_timeout_is_recoverable(self, post):
        post.side_effect = requests.Timeout("timed out")
        backend = ElevenLabsMusicBackend(api_key="key")
        with self.assertRaises(MusicGenerationError) as caught:
            backend.generate(
                prompt="calm",
                target_duration_seconds=30,
                output_path="unused.wav",
            )
        self.assertTrue(caught.exception.recoverable)
        self.assertNotIn("key", str(caught.exception))

    @patch("music_generation_backends.requests.post")
    def test_http_500_is_recoverable(self, post):
        response = Mock(status_code=500)
        post.return_value.raise_for_status.side_effect = requests.HTTPError(
            "server error", response=response
        )
        backend = ElevenLabsMusicBackend(api_key="key")
        with self.assertRaises(MusicGenerationError) as caught:
            backend.generate(
                prompt="calm",
                target_duration_seconds=30,
                output_path="unused.wav",
            )
        self.assertTrue(caught.exception.recoverable)
        self.assertEqual(caught.exception.status_code, 500)

    @patch("music_generation_backends.requests.post")
    def test_http_401_is_not_recoverable(self, post):
        response = Mock(status_code=401)
        post.return_value.raise_for_status.side_effect = requests.HTTPError(
            "unauthorized", response=response
        )
        backend = ElevenLabsMusicBackend(api_key="key")
        with self.assertRaises(MusicGenerationError) as caught:
            backend.generate(
                prompt="calm",
                target_duration_seconds=30,
                output_path="unused.wav",
            )
        self.assertFalse(caught.exception.recoverable)
        self.assertEqual(caught.exception.status_code, 401)

    @patch("music_generation_backends.requests.post")
    def test_minimax_business_error_is_not_recoverable(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "base_resp": {"status_code": 1004, "status_msg": "invalid request"}
        }
        post.return_value = response
        backend = MiniMaxMusicBackend(api_key="key")
        with self.assertRaises(MusicGenerationError) as caught:
            backend.generate(
                prompt="calm",
                target_duration_seconds=30,
                output_path="unused.wav",
            )
        self.assertFalse(caught.exception.recoverable)

    @patch("music_generation_backends.AudioSegment.from_file")
    def test_undecodable_audio_is_recoverable_and_not_written(self, from_file):
        from_file.side_effect = ValueError("bad audio")
        backend = ElevenLabsMusicBackend(api_key="key")
        response = Mock(content=b"not audio")
        response.raise_for_status.return_value = None
        with patch("music_generation_backends.requests.post", return_value=response):
            with tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "segment.wav"
                with self.assertRaises(MusicGenerationError) as caught:
                    backend.generate(
                        prompt="calm",
                        target_duration_seconds=30,
                        output_path=output,
                    )
                self.assertTrue(caught.exception.recoverable)
                self.assertFalse(output.exists())

    def test_missing_credentials_are_not_recoverable(self):
        backend = MiniMaxMusicBackend(api_key="")
        with self.assertRaises(MusicGenerationError) as caught:
            backend.generate(
                prompt="calm",
                target_duration_seconds=30,
                output_path="unused.wav",
            )
        self.assertFalse(caught.exception.recoverable)

    def test_factory_uses_stable_provider_ids(self):
        self.assertIsInstance(
            create_music_backend("elevenlabs", api_key="key"),
            ElevenLabsMusicBackend,
        )
        self.assertIsInstance(
            create_music_backend("minimax", api_key="key"),
            MiniMaxMusicBackend,
        )
        with self.assertRaises(ValueError):
            create_music_backend("unknown", api_key="key")


if __name__ == "__main__":
    unittest.main()
