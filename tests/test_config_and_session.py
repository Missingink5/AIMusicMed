import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config_manager import APIConfig, AppConfig, AudioConfig, MeditationConfig, PathConfig
from py313_meditation_app import MeditationApp, MeditationAppError
from run_py313_app import get_ai_music_provider, get_music_source


class ConfigurationTests(unittest.TestCase):
    def test_default_minimax_voice_is_premium_mature_female(self):
        self.assertEqual(AudioConfig().minimax_voice_id, "female-chengshu-jingpin")

    def test_windows_default_output_directory(self):
        if os.name == "nt":
            self.assertEqual(
                PathConfig().base_dir,
                "D:/ISO音乐-AI冥想疗愈生成/示例输出",
            )

    def test_rejects_invalid_minimax_speed(self):
        with self.assertRaisesRegex(ValueError, "minimax_speed"):
            AudioConfig(minimax_speed=0.1)

    def test_rejects_non_minimax_tts_backend(self):
        with self.assertRaisesRegex(ValueError, "tts_backend 必须为 minimax"):
            AudioConfig(tts_backend="edge")

    def test_rejects_invalid_duration_range(self):
        with self.assertRaisesRegex(ValueError, "max_duration_minutes"):
            MeditationConfig(min_duration_minutes=5, max_duration_minutes=3)

    def test_music_environment_variables_override_file_values(self):
        environment = {
            "ELEVENLABS_API_KEY": "env-elevenlabs",
            "ELEVENLABS_MUSIC_BASE_URL": "https://elevenlabs.example/v1",
            "ELEVENLABS_MUSIC_MODEL": "env-elevenlabs-model",
            "MINIMAX_API_KEY": "env-minimax",
            "MINIMAX_MUSIC_BASE_URL": "https://minimax.example/v1",
            "MINIMAX_MUSIC_MODEL": "env-minimax-model",
            "MUSIC_REQUEST_TIMEOUT_SECONDS": "321",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = APIConfig(
                elevenlabs_api_key="file-elevenlabs",
                minimax_api_key="file-minimax",
                music_request_timeout_seconds=600,
            )

        self.assertEqual(config.elevenlabs_api_key, "env-elevenlabs")
        self.assertEqual(config.minimax_api_key, "env-minimax")
        self.assertEqual(config.elevenlabs_music_base_url, "https://elevenlabs.example/v1")
        self.assertEqual(config.elevenlabs_music_model, "env-elevenlabs-model")
        self.assertEqual(config.minimax_music_base_url, "https://minimax.example/v1")
        self.assertEqual(config.minimax_music_model, "env-minimax-model")
        self.assertEqual(config.music_request_timeout_seconds, 321)

    def test_export_redacts_all_api_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig(
                api=APIConfig(
                    deepseek_api_key="deepseek-secret",
                    minimax_api_key="minimax-secret",
                    elevenlabs_api_key="elevenlabs-secret",
                ),
                paths=PathConfig(base_dir=tempfile.gettempdir()),
                audio=AudioConfig(),
                meditation=MeditationConfig(),
            )
        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "config.json")
            config.to_json(output_path)
            with open(output_path, encoding="utf-8") as file:
                exported = json.load(file)["api_keys"]

        self.assertEqual(exported["deepseek_api_key"], "PUT_YOUR_KEY_OR_USE_ENV")
        self.assertEqual(exported["minimax_api_key"], "PUT_YOUR_KEY_OR_USE_ENV")
        self.assertEqual(exported["elevenlabs_api_key"], "PUT_YOUR_KEY_OR_USE_ENV")
        self.assertNotIn("deepseek-secret", json.dumps(exported))
        self.assertNotIn("minimax-secret", json.dumps(exported))
        self.assertNotIn("elevenlabs-secret", json.dumps(exported))


class MusicSourceCliTests(unittest.TestCase):
    @patch("builtins.input", return_value="")
    def test_blank_music_source_defaults_to_library(self, _input):
        self.assertEqual(get_music_source(), "library")

    @patch("builtins.input", return_value="2")
    def test_ai_music_source_can_be_selected(self, _input):
        self.assertEqual(get_music_source(), "ai")

    @patch("builtins.input", return_value="1")
    def test_configured_elevenlabs_provider_can_be_selected(self, _input):
        config = SimpleNamespace(
            api=SimpleNamespace(elevenlabs_api_key="configured", minimax_api_key="")
        )
        self.assertEqual(get_ai_music_provider(config), "elevenlabs")

    @patch("builtins.input", return_value="2")
    def test_missing_primary_provider_key_stops_before_generation(self, _input):
        config = SimpleNamespace(
            api=SimpleNamespace(elevenlabs_api_key="configured", minimax_api_key="")
        )
        self.assertIsNone(get_ai_music_provider(config))


class SessionValidationTests(unittest.TestCase):
    @staticmethod
    def _app():
        app = MeditationApp.__new__(MeditationApp)
        app.logger = Mock()
        app.device = "test"
        app._session_temp_files = set()
        app.config = SimpleNamespace(
            meditation=SimpleNamespace(
                default_duration_minutes=5,
                min_duration_minutes=3,
                max_duration_minutes=15,
            ),
            audio=SimpleNamespace(
                preferred_track_duration_seconds=60,
                tts_backend="minimax",
                minimax_voice_id="test-voice",
            ),
            api=SimpleNamespace(minimax_api_key="test-key"),
        )
        return app

    def test_empty_user_input_is_rejected(self):
        app = self._app()
        with self.assertRaisesRegex(MeditationAppError, "不能为空"):
            asyncio.run(app.create_meditation_session("   ", 3))

    def test_out_of_range_duration_is_rejected(self):
        app = self._app()
        with self.assertRaisesRegex(MeditationAppError, "3 到 15"):
            asyncio.run(app.create_meditation_session("面试紧张", 2))

    def test_failure_cleans_registered_temp_files(self):
        app = self._app()
        app.prepare_session_plan = Mock(side_effect=RuntimeError("planned failure"))
        app.cleanup_temp_files = Mock()
        with self.assertRaisesRegex(MeditationAppError, "planned failure"):
            asyncio.run(app.create_meditation_session("面试紧张", 3, cleanup=True))
        app.cleanup_temp_files.assert_called_once_with()

    def test_missing_tts_key_stops_before_any_music_generation(self):
        app = self._app()
        app.config.api.minimax_api_key = ""
        app.prepare_session_plan = Mock()

        with self.assertRaisesRegex(MeditationAppError, "MiniMax TTS"):
            asyncio.run(
                app.create_meditation_session(
                    "面试紧张",
                    3,
                    music_source="ai",
                    ai_music_provider="elevenlabs",
                )
            )

        app.prepare_session_plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
