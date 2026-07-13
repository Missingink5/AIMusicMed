import unittest

import numpy as np

from audio_compat import AudioSegment


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


if __name__ == "__main__":
    unittest.main()
