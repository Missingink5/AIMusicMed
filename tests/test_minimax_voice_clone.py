from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from minimax_voice_clone import (
    MiniMaxVoiceCloneClient,
    MiniMaxVoiceCloneError,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError()
            error.response = self
            raise error

    def json(self):
        return self.payload


class MiniMaxVoiceCloneTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock(spec=requests.Session)
        self.session.headers = {}
        self.client = MiniMaxVoiceCloneClient(
            api_key="test-key",
            session=self.session,
        )

    def test_upload_clone_audio_uses_official_purpose_and_reads_file_id(self):
        self.session.post.return_value = FakeResponse({
            "file": {"file_id": 123},
            "base_resp": {"status_code": 0},
        })
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "voice.wav"
            source.write_bytes(b"RIFF" + b"x" * 100)
            self.assertEqual(self.client.upload_clone_audio(source), 123)
        call = self.session.post.call_args
        self.assertEqual(call.kwargs["data"], {"purpose": "voice_clone"})
        self.assertEqual(call.kwargs["files"]["file"][0], "voice.wav")

    def test_business_rejection_is_not_free_retry(self):
        self.session.post.return_value = FakeResponse({
            "base_resp": {"status_code": 1004, "status_msg": "bad audio"},
        })
        with self.assertRaises(MiniMaxVoiceCloneError) as caught:
            self.client.clone_voice(file_id=1, voice_id="aimusicmed_test")
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(caught.exception.code, "minimax_1004")

    def test_network_failure_is_retryable(self):
        self.session.post.side_effect = requests.ConnectionError("offline")
        with self.assertRaises(MiniMaxVoiceCloneError) as caught:
            self.client.clone_voice(file_id=1, voice_id="aimusicmed_test")
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(caught.exception.code, "provider_unavailable")

    @patch("minimax_voice_clone.synthesize_minimax")
    def test_activation_uses_real_tts_with_selected_clone(self, synthesize):
        synthesize.return_value = Path("preview.wav")
        result = self.client.activate_voice(
            voice_id="aimusicmed_test",
            preview_path="preview.wav",
        )
        self.assertEqual(result, Path("preview.wav"))
        self.assertEqual(synthesize.call_args.kwargs["voice_id"], "aimusicmed_test")
        self.assertEqual(synthesize.call_args.kwargs["max_attempts"], 1)

    def test_remote_voice_and_source_file_have_explicit_delete_calls(self):
        self.session.post.side_effect = [
            FakeResponse({"base_resp": {"status_code": 0}}),
            FakeResponse({"base_resp": {"status_code": 0}}),
        ]
        self.client.delete_voice("aimusicmed_test")
        self.client.delete_clone_file(99)
        first, second = self.session.post.call_args_list
        self.assertTrue(first.args[0].endswith("/v1/delete_voice"))
        self.assertEqual(first.kwargs["json"]["voice_type"], "voice_cloning")
        self.assertTrue(second.args[0].endswith("/v1/files/delete"))
        self.assertEqual(second.kwargs["json"]["purpose"], "voice_clone")


if __name__ == "__main__":
    unittest.main()
