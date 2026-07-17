import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from audio_compat import AudioSegment
from py313_meditation_app import MeditationApp


class AudioMixTests(unittest.TestCase):
    def test_crossfade_overlaps_adjacent_segments(self):
        left = AudioSegment(np.ones((1, 1000), dtype=np.float32) * 0.25, 1000)
        right = AudioSegment(np.ones((1, 1000), dtype=np.float32) * 0.25, 1000)

        combined = left.append_with_crossfade(right, 100)

        self.assertEqual(combined.data.shape[-1], 1900)
        self.assertAlmostEqual(float(combined.data[0, 950]), 0.5, places=5)

    def test_peak_normalization_prevents_clipping(self):
        loud = AudioSegment(np.array([[1.4, -1.2, 0.4]], dtype=np.float32), 1000)

        normalized = loud.normalize_peak(0.95)

        self.assertLessEqual(float(np.max(np.abs(normalized.data))), 0.950001)

    def test_music_only_mix_does_not_require_speech_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            music_path = Path(temp_dir) / "music.wav"
            output_path = Path(temp_dir) / "result.wav"
            AudioSegment(np.ones((1, 1000), dtype=np.float32) * 0.2, 1000).export(
                str(music_path)
            )
            app = MeditationApp.__new__(MeditationApp)
            app.logger = Mock()
            app.config = SimpleNamespace(
                audio=SimpleNamespace(
                    music_volume_reduction=8,
                    speech_start_delay_seconds=4.0,
                    music_transition_fade_seconds=0.0,
                )
            )

            result = app.combine_audio_adaptive(
                [],
                [{"path": str(music_path), "source_file": "music.wav"}],
                3,
                "平静 → 平静 → 平静",
                output_path=str(output_path),
            )

            self.assertEqual(result, str(output_path))
            self.assertTrue(output_path.exists())
            self.assertFalse(output_path.with_suffix(".part.wav").exists())


if __name__ == "__main__":
    unittest.main()
