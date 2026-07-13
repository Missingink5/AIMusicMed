import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from meditation_sop import build_music_segment_plan, plan_emotion_stages
from audio_compat import AudioSegment
import numpy as np
from py313_meditation_app import MeditationApp, MeditationAppError


def sample_music(segment_id="segment_01", emotion="焦虑"):
    return {
        "segment_id": segment_id,
        "stage": 1,
        "stage_goal": "接纳和缓解当前情绪",
        "transition_role": "接纳当下",
        "emotion": emotion,
        "source_file": "(1)紧张，焦虑.wav",
        "filename_tags": ["紧张", "焦虑"],
        "source_duration_seconds": 61.0,
        "duration_seconds": 60,
        "music_features": {
            "tempo_bpm": 62.0,
            "tempo_label": "舒缓",
            "rms": 0.04,
            "energy_label": "轻柔",
            "spectral_centroid_hz": 1200.0,
            "brightness_label": "柔和",
            "dynamic_label": "平稳",
        },
    }


def attach_audio_config(app):
    app.config = SimpleNamespace(
        audio=SimpleNamespace(
            tts_backend="minimax",
            minimax_speed=0.8,
            speech_start_delay_seconds=4.0,
            music_transition_fade_seconds=3.0,
        )
    )


class SopPlanningTests(unittest.TestCase):
    def test_music_fade_keeps_the_entire_song_length(self):
        app = MeditationApp.__new__(MeditationApp)
        original = AudioSegment(np.ones((1, 1000), dtype=np.float32), sample_rate=100)

        rendered = app._apply_music_fades(original, 2.0)

        self.assertEqual(rendered.data.shape, original.data.shape)
        self.assertEqual(float(rendered.data[0, 0]), 0.0)
        self.assertEqual(float(rendered.data[0, -1]), 0.0)
        self.assertAlmostEqual(float(rendered.data[0, 500]), 1.0)

    def test_track_count_scales_around_one_minute_and_preserves_duration(self):
        expected_counts = {1: 3, 5: 5, 10: 10}
        for minutes, expected in expected_counts.items():
            stages = plan_emotion_stages("焦虑", minutes, 60)
            segments = build_music_segment_plan(stages)
            self.assertEqual(len(segments), expected)
            self.assertEqual(sum(item["duration_seconds"] for item in segments), minutes * 60)
            self.assertTrue(all(stage["track_count"] >= 1 for stage in stages))

    def test_ai_emotion_is_used_when_response_is_valid(self):
        app = MeditationApp.__new__(MeditationApp)
        app._request_deepseek_json = Mock(
            return_value={
                "primary_emotion": "焦虑",
                "confidence": 0.86,
                "secondary_emotions": ["忧郁"],
                "rationale": "对即将发生的事情持续担心",
            }
        )

        result = app.analyze_emotion_with_ai("最近总担心面试")

        self.assertEqual(result["primary_emotion"], "焦虑")
        self.assertEqual(result["source"], "ai")

    @patch("py313_meditation_app.requests.post")
    def test_deepseek_402_uses_keyword_fallback_and_correct_url(self, post):
        app = MeditationApp.__new__(MeditationApp)
        app.config = SimpleNamespace(
            api=SimpleNamespace(
                deepseek_api_key="test-key",
                deepseek_base_url="https://api.deepseek.com/v1",
            )
        )
        app.local_music_lib = Mock()
        app.local_music_lib.analyze_user_emotion.return_value = "焦虑"
        app.logger = Mock()
        post.return_value.raise_for_status.side_effect = requests.HTTPError(
            "402 Payment Required"
        )

        result = app.analyze_emotion_with_ai("最近准备面试有些紧张")

        self.assertEqual(result["primary_emotion"], "焦虑")
        self.assertEqual(result["source"], "keyword_fallback")
        self.assertEqual(
            post.call_args.args[0],
            "https://api.deepseek.com/v1/chat/completions",
        )

    def test_guidance_is_strictly_grounded_in_selected_music(self):
        app = MeditationApp.__new__(MeditationApp)
        app.logger = Mock()
        attach_audio_config(app)
        music = [sample_music()]
        manifest = app._public_music_manifest(music)
        app._request_deepseek_json = Mock(
            return_value={
                "scripts": [
                    {
                        "segment_id": manifest[0]["segment_id"],
                        "music_ref": manifest[0]["music_ref"],
                        "grounding_fingerprint": manifest[0]["grounding_fingerprint"],
                        "text": "跟随舒缓而轻柔的音乐，慢慢安顿呼吸。",
                    }
                ]
            }
        )
        plan = {
            "emotion_analysis": {"primary_emotion": "焦虑"},
            "emotion_journey": "焦虑 → 平静 → 喜悦",
        }

        scripts = app.generate_guidance_for_music("准备面试有些紧张", plan, music)

        self.assertEqual(scripts[0]["music_ref"], music[0]["source_file"])
        self.assertEqual(scripts[0]["grounding_fingerprint"], manifest[0]["grounding_fingerprint"])
        request_text = app._request_deepseek_json.call_args.args[1]
        self.assertIn("tempo_bpm", request_text)
        self.assertIn(music[0]["source_file"], request_text)

    def test_duplicate_ai_segment_ids_cannot_realign_to_other_music(self):
        app = MeditationApp.__new__(MeditationApp)
        app.logger = Mock()
        attach_audio_config(app)
        music = [sample_music("segment_01"), sample_music("segment_02", "平静")]
        manifest = app._public_music_manifest(music)
        duplicate = {
            "segment_id": manifest[0]["segment_id"],
            "music_ref": manifest[0]["music_ref"],
            "grounding_fingerprint": manifest[0]["grounding_fingerprint"],
            "text": "第一段",
        }
        app._request_deepseek_json = Mock(return_value={"scripts": [duplicate, duplicate]})
        plan = {
            "emotion_analysis": {"primary_emotion": "焦虑"},
            "emotion_journey": "焦虑 → 平静",
        }

        scripts = app.generate_guidance_for_music("紧张", plan, music)

        self.assertTrue(all(item["guidance_source"] == "local_fallback" for item in scripts))
        self.assertEqual([item["segment_id"] for item in scripts], ["segment_01", "segment_02"])

    def test_script_music_count_mismatch_fails_before_tts(self):
        app = MeditationApp.__new__(MeditationApp)
        app.logger = Mock()
        with self.assertRaisesRegex(MeditationAppError, "数量不一致"):
            asyncio.run(app.generate_speech_adaptive(["一段引导"], []))

    def test_session_order_selects_music_before_guidance(self):
        app = MeditationApp.__new__(MeditationApp)
        app.logger = Mock()
        app.device = "test"
        app.config = SimpleNamespace(
            audio=SimpleNamespace(
                tts_backend="minimax",
                music_transition_fade_seconds=3.0,
            ),
            meditation=SimpleNamespace(
                default_duration_minutes=5,
                min_duration_minutes=3,
                max_duration_minutes=15,
            ),
        )
        events = []
        plan = {
            "analysis": "AI分析",
            "emotion_analysis": {"primary_emotion": "焦虑", "source": "ai"},
            "emotion_journey": "焦虑 → 平静 → 喜悦",
            "emotion_journey_plan": [{"stage": 1}],
            "music_prompts": [{"segment_id": "segment_01"}],
        }
        music = [sample_music()]
        script = [{"text": "引导", **app._public_music_manifest(music)[0]}]
        app.get_session_info = lambda *_: {}
        app.prepare_session_plan = lambda *_: events.append("detect_plan") or plan
        app.generate_music = lambda *_: events.append("select_analyze_music") or music
        app.generate_guidance_for_music = lambda *_: events.append("generate_guidance") or script

        async def fake_tts(*_):
            events.append("tts")
            return ["speech.wav"]

        app.generate_speech_adaptive = fake_tts
        app.combine_audio_adaptive = lambda *_: events.append("mix") or "final.wav"

        asyncio.run(app.create_meditation_session("面试紧张", 5, cleanup=False))

        self.assertEqual(
            events,
            ["detect_plan", "select_analyze_music", "generate_guidance", "tts", "mix"],
        )


if __name__ == "__main__":
    unittest.main()
