from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from minimax_voice_clone import MiniMaxVoiceCloneError
from webapp.worker import (
    _export_artifacts,
    _job_config,
    run_provider_voice_action,
    run_voice_clone,
)


def provider_config():
    return SimpleNamespace(
        api=SimpleNamespace(
            minimax_base_url="https://api.minimaxi.com",
            music_request_timeout_seconds=30,
        ),
        audio=SimpleNamespace(minimax_model="speech-2.8-hd"),
    )


class WorkerOperationsTests(unittest.TestCase):
    @patch("webapp.worker.shutil.which", return_value="ffmpeg")
    @patch("webapp.worker.subprocess.run")
    @patch("webapp.worker.master_file")
    def test_export_mastering_uses_voice_and_music_targets(
        self, master, run, _which
    ):
        run.return_value = SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.wav"
            target = root / "result.wav"
            source.write_bytes(b"source")

            def write_master(_source, destination, **_kwargs):
                Path(destination).write_bytes(b"master")

            master.side_effect = write_master

            def write_mp3(command, **_kwargs):
                Path(command[-1]).write_bytes(b"mp3")
                return SimpleNamespace(returncode=0)

            run.side_effect = write_mp3
            _export_artifacts(source, target, "有引导词")
            self.assertTrue(target.is_file())
            self.assertTrue(target.with_suffix(".mp3").is_file())
            self.assertTrue(master.call_args.kwargs["has_voice"])

    def test_job_config_uses_selected_provider_voice(self):
        config = SimpleNamespace(
            api=SimpleNamespace(),
            paths=SimpleNamespace(),
            audio=SimpleNamespace(),
            create_directories=Mock(),
        )
        with tempfile.TemporaryDirectory() as folder, patch(
            "webapp.worker.load_config", return_value=config
        ):
            result = _job_config(
                {"provider_voice_id": "aimusicmed_voice_1"},
                Path(folder),
            )
        self.assertEqual(result.audio.minimax_voice_id, "aimusicmed_voice_1")

    @patch("webapp.worker.MiniMaxVoiceCloneClient")
    @patch("webapp.worker._prepare_clone_audio")
    @patch("webapp.worker._provider_config")
    def test_voice_clone_uploads_clones_activates_and_completes(
        self, provider_settings, prepare, provider_class
    ):
        provider_settings.return_value = (provider_config(), "key")
        provider = provider_class.return_value
        provider.upload_clone_audio.return_value = 42
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.wav"
            source.write_bytes(b"source")
            prepare.side_effect = lambda _source, destination: destination
            api = Mock()
            run_voice_clone(api, {
                "id": "clone-1",
                "source_path": str(source),
                "provider_voice_id": "aimusicmed_voice_1",
                "preview_path": str(Path(folder) / "preview.wav"),
                "preview_relpath": "voices/user/previews/clone-1.wav",
            })
        provider.clone_voice.assert_called_once_with(
            file_id=42, voice_id="aimusicmed_voice_1"
        )
        provider.activate_voice.assert_called_once()
        api.complete_voice_clone.assert_called_once_with(
            "clone-1", 42, "voices/user/previews/clone-1.wav"
        )
        api.fail_voice_clone.assert_not_called()

    @patch("webapp.worker.MiniMaxVoiceCloneClient")
    @patch("webapp.worker._prepare_clone_audio")
    @patch("webapp.worker._provider_config")
    def test_network_clone_failure_is_free_retry_category(
        self, provider_settings, prepare, provider_class
    ):
        provider_settings.return_value = (provider_config(), "key")
        provider = provider_class.return_value
        provider.upload_clone_audio.side_effect = MiniMaxVoiceCloneError(
            "provider_unavailable", "offline", retryable=True
        )
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.wav"
            source.write_bytes(b"source")
            prepare.side_effect = lambda _source, destination: destination
            api = Mock()
            run_voice_clone(api, {
                "id": "clone-1",
                "source_path": str(source),
                "provider_voice_id": "aimusicmed_voice_1",
                "preview_path": str(Path(folder) / "preview.wav"),
                "preview_relpath": "voices/user/previews/clone-1.wav",
            })
        api.fail_voice_clone.assert_called_once_with(
            "clone-1", "provider_unavailable", "provider_network"
        )

    @patch("webapp.worker.MiniMaxVoiceCloneClient")
    @patch("webapp.worker._provider_config")
    def test_provider_cleanup_uses_remote_delete_api(
        self, provider_settings, provider_class
    ):
        provider_settings.return_value = (provider_config(), "key")
        provider = provider_class.return_value
        api = Mock()
        run_provider_voice_action(api, {
            "id": "action-1",
            "action": "delete",
            "provider_voice_id": "aimusicmed_voice_1",
            "provider_file_id": None,
        })
        provider.delete_voice.assert_called_once_with("aimusicmed_voice_1")
        api.complete_provider_voice_action.assert_called_once_with("action-1", 0)


if __name__ == "__main__":
    unittest.main()
