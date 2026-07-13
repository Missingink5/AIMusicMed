import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from config_manager import AudioConfig, MeditationConfig, PathConfig
from py313_meditation_app import MeditationApp, MeditationAppError


class ConfigurationTests(unittest.TestCase):
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
            ),
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


if __name__ == "__main__":
    unittest.main()
