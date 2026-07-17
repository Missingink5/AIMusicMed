from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from py313_meditation_app import MeditationApp


class SelectedMusicTests(unittest.TestCase):
    def test_selected_private_music_uses_only_declared_metadata_and_user_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "private.wav"
            sample_rate = 8000
            seconds = 3
            signal = np.sin(
                2 * np.pi * 220 * np.arange(sample_rate * seconds) / sample_rate
            ).astype(np.float32) * 0.1
            sf.write(source, signal, sample_rate)

            app = MeditationApp.__new__(MeditationApp)
            app.config = SimpleNamespace(paths=SimpleNamespace(temp_dir=str(root)))
            app._session_id = "selected"
            app._session_temp_files = set()
            rendered = app._generate_selected_music(
                [{
                    "segment_id": "segment_01",
                    "duration_seconds": 4,
                    "stage": 1,
                    "stage_goal": "陪伴",
                    "transition_role": "停留",
                    "emotion": "平静",
                }],
                {
                    "path": str(source),
                    "name": "我的晨雾",
                    "primary_emotion": "平静",
                    "tags": ["舒缓", "钢琴"],
                    "edit": {
                        "trim_start_ms": 500,
                        "trim_end_ms": 2500,
                        "fade_in_ms": 500,
                        "fade_out_ms": 500,
                        "loudness": "light",
                    },
                },
            )

            self.assertEqual(len(rendered), 1)
            item = rendered[0]
            self.assertEqual(item["source_file"], "我的晨雾")
            self.assertEqual(item["emotion"], "平静")
            self.assertEqual(item["filename_tags"], ["舒缓", "钢琴"])
            self.assertEqual(item["music_features"]["tempo_label"], "未分析")
            self.assertEqual(item["duration_seconds"], 4.0)
            data, _ = sf.read(item["path"], always_2d=True)
            self.assertAlmostEqual(float(abs(data[0, 0])), 0.0, places=5)
            self.assertAlmostEqual(float(abs(data[-1, 0])), 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
