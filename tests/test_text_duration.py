import unittest
from types import SimpleNamespace

from py313_meditation_app import MeditationApp, MeditationAppError


class TextDurationTests(unittest.TestCase):
    def setUp(self):
        self.app = MeditationApp.__new__(MeditationApp)
        self.app.config = SimpleNamespace(
            audio=SimpleNamespace(tts_backend="minimax", minimax_speed=0.8)
        )

    def test_long_chinese_text_without_english_ellipsis_is_not_empty(self):
        text = (
            "请把注意力轻轻带回呼吸，感受空气经过鼻尖时细微的温度变化，"
            "允许肩膀慢慢松开，也允许此刻的紧张被温柔地看见。"
            "不需要催促自己改变，只要继续安静地陪伴每一次吸气和呼气，"
            "让内心逐渐恢复稳定与清晰。"
            "如果思绪再次飘走，也只需温和地觉察，然后重新回到当下的呼吸。"
        )

        result = self.app._adjust_text_for_duration(text, 31.0)

        self.assertTrue(result.strip())
        self.assertLessEqual(len(result), int(31.0 * 3.5 * 0.8 * 0.85))

    def test_first_sentence_longer_than_budget_still_returns_text(self):
        text = "慢慢感受身体每一个部位正在放松下来" * 12

        result = self.app._adjust_text_for_duration(text, 27.0)

        self.assertTrue(result.strip())
        self.assertLessEqual(len(result), int(27.0 * 3.5 * 0.8 * 0.85))

    def test_empty_source_text_is_rejected_with_clear_error(self):
        with self.assertRaisesRegex(MeditationAppError, "引导文本为空"):
            self.app._adjust_text_for_duration("   ", 31.0)


if __name__ == "__main__":
    unittest.main()
