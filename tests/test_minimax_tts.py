import tempfile
import unittest
import io
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from minimax_tts_backend import MiniMaxTTSError, synthesize_minimax


class MiniMaxTTSTests(unittest.TestCase):
    @staticmethod
    def _wav_bytes():
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(32000)
            wav_file.writeframes(b"\x00\x00" * 32)
        return buffer.getvalue()

    def _settings(self):
        return {
            "api_key": "test-key",
            "base_url": "https://api.minimaxi.com",
            "model": "speech-2.8-hd",
            "voice_id": "AIMusicMedTestVoice",
            "max_attempts": 1,
        }

    @patch("minimax_tts_backend.requests.post")
    def test_success_decodes_hex_wav(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {"audio": self._wav_bytes().hex(), "status": 2},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }
        post.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "speech.wav"
            synthesize_minimax("请慢慢呼吸。", output, **self._settings())
            self.assertEqual(output.read_bytes(), self._wav_bytes())

        request_json = post.call_args.kwargs["json"]
        self.assertEqual(request_json["model"], "speech-2.8-hd")
        self.assertEqual(request_json["audio_setting"]["format"], "wav")
        self.assertFalse(request_json["stream"])

    @patch("minimax_tts_backend.requests.post")
    def test_business_error_is_rejected(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "base_resp": {"status_code": 1004, "status_msg": "invalid request"},
            "trace_id": "trace-test",
        }
        post.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(MiniMaxTTSError, "1004"):
                synthesize_minimax(
                    "请慢慢呼吸。",
                    Path(temp_dir) / "speech.wav",
                    **self._settings(),
                )

    @patch("minimax_tts_backend.requests.post")
    def test_bad_hex_is_rejected(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {"audio": "not-hex", "status": 2},
            "base_resp": {"status_code": 0},
        }
        post.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(MiniMaxTTSError, "十六进制"):
                synthesize_minimax(
                    "请慢慢呼吸。",
                    Path(temp_dir) / "speech.wav",
                    **self._settings(),
                )

    @patch("minimax_tts_backend.requests.post")
    def test_non_wav_payload_is_rejected(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {"audio": b"not a wav file".hex(), "status": 2},
            "base_resp": {"status_code": 0},
        }
        post.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "speech.wav"
            with self.assertRaisesRegex(MiniMaxTTSError, "WAV"):
                synthesize_minimax("请慢慢呼吸。", output, **self._settings())
            self.assertFalse(output.exists())

    @patch("minimax_tts_backend.requests.post")
    def test_timeout_is_wrapped_without_credentials(self, post):
        post.side_effect = requests.Timeout("timed out")
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(MiniMaxTTSError, "请求失败") as caught:
                synthesize_minimax(
                    "请慢慢呼吸。",
                    Path(temp_dir) / "speech.wav",
                    **self._settings(),
                )
        self.assertNotIn("test-key", str(caught.exception))

    @patch("minimax_tts_backend.time.sleep")
    @patch("minimax_tts_backend.requests.post")
    def test_transient_timeout_is_retried(self, post, sleep):
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {
            "data": {"audio": self._wav_bytes().hex(), "status": 2},
            "base_resp": {"status_code": 0},
        }
        post.side_effect = [requests.Timeout("timed out"), success]
        settings = self._settings()
        settings["max_attempts"] = 2

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "speech.wav"
            synthesize_minimax("请慢慢呼吸。", output, **settings)
            self.assertTrue(output.exists())

        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
