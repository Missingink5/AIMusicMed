import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from audio_mastering import (
    TARGET_TRUE_PEAK_DBTP,
    analyze_loudness,
    duck_music,
    equal_power_crossfade,
    equal_power_fade,
    master_file,
    prevent_clipping,
    reject_severe_clipping,
    trim_audio,
)


class AudioMasteringTests(unittest.TestCase):
    def test_trim_and_equal_power_fades_preserve_requested_duration(self):
        source = np.ones((2, 2000), dtype=np.float32)
        trimmed = trim_audio(source, 1000, 1.25)
        faded = equal_power_fade(trimmed, 1000, 0.1, 0.1)
        self.assertEqual(faded.shape, (2, 1250))
        self.assertAlmostEqual(float(faded[0, 0]), 0.0, places=6)
        self.assertAlmostEqual(float(faded[0, -1]), 0.0, places=6)

    def test_crossfade_uses_constant_power_and_shortens_only_by_overlap(self):
        left = np.ones((1, 1000), dtype=np.float32)
        right = np.ones((1, 1000), dtype=np.float32)
        result = equal_power_crossfade(left, right, 1000, 0.2)
        self.assertEqual(result.shape[-1], 1800)
        midpoint = result[0, 900]
        self.assertGreater(midpoint, 1.3)
        self.assertLess(midpoint, 1.5)

    def test_ducking_reduces_music_during_voice_and_recovers(self):
        music = np.ones((1, 3000), dtype=np.float32) * 0.4
        voice = np.zeros((1, 3000), dtype=np.float32)
        voice[:, 800:1800] = 0.5
        ducked = duck_music(
            music, voice, 1000, attack_seconds=0.01, release_seconds=0.05
        )
        self.assertLess(float(np.mean(ducked[:, 1000:1700])), 0.2)
        self.assertGreater(float(np.mean(ducked[:, 2300:])), 0.39)

    def test_peak_guard_honors_minus_one_db_limit(self):
        guarded = prevent_clipping(np.array([[1.4, -1.2]], dtype=np.float32))
        expected = 10 ** (TARGET_TRUE_PEAK_DBTP / 20.0)
        self.assertLessEqual(float(np.max(np.abs(guarded))), expected + 1e-6)

    @patch("audio_mastering._run")
    def test_loudness_analysis_parses_only_technical_measurements(self, run):
        run.side_effect = [
            type("Result", (), {"stdout": "12.5\n", "stderr": ""})(),
            type("Result", (), {"stdout": "", "stderr": '''{
                "input_i":"-20.1", "input_tp":"-2.2", "input_lra":"4.0",
                "input_thresh":"-30.4", "target_offset":"0.1"
            }'''})(),
        ]
        stats = analyze_loudness("sample.wav")
        self.assertEqual(stats.duration_seconds, 12.5)
        self.assertEqual(stats.integrated_lufs, -20.1)
        flattened = " ".join(" ".join(call.args[0]) for call in run.call_args_list)
        self.assertNotIn("whisper", flattened.lower())
        self.assertNotIn("speech", flattened.lower())

    def test_ffmpeg_mastering_hits_loudness_and_true_peak_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.wav"
            output = Path(folder) / "master.wav"
            sample_rate = 48000
            time = np.arange(sample_rate * 3) / sample_rate
            signal = (0.04 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)
            sf.write(source, signal, sample_rate)
            stats = master_file(source, output, has_voice=True, fade_seconds=0.05)
            self.assertTrue(output.is_file())
            self.assertAlmostEqual(stats.integrated_lufs, -16.0, delta=0.5)
            self.assertLessEqual(stats.true_peak_dbtp, -0.8)

    def test_music_only_mastering_targets_minus_fourteen_lufs(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "music.wav"
            output = Path(folder) / "music-master.wav"
            sample_rate = 48000
            time = np.arange(sample_rate * 3) / sample_rate
            signal = (0.035 * np.sin(2 * np.pi * 330 * time)).astype(np.float32)
            sf.write(source, signal, sample_rate)
            stats = master_file(source, output, has_voice=False, fade_seconds=0.05)
            self.assertAlmostEqual(stats.integrated_lufs, -14.0, delta=0.5)
            self.assertLessEqual(stats.true_peak_dbtp, -0.8)

    def test_severely_clipped_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "clipped.wav"
            sf.write(source, np.ones(48000, dtype=np.float32), 48000, subtype="FLOAT")
            with self.assertRaisesRegex(ValueError, "severely clipped"):
                reject_severe_clipping(source)


if __name__ == "__main__":
    unittest.main()
