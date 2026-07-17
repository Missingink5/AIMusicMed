import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from meditation_sop import build_music_segment_plan, plan_emotion_stages
from audio_compat import AudioSegment
import numpy as np
from py313_meditation_app import MeditationApp, MeditationAppError
from music_generation_backends import MusicGenerationError


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

    def test_explicit_target_emotion_controls_final_stage(self):
        stages = plan_emotion_stages("焦虑", 5, 60, target_emotion="自豪")

        self.assertEqual([stage["emotion_cn"] for stage in stages], ["焦虑", "平静", "自豪"])
        self.assertEqual(sum(stage["duration"] for stage in stages), 300)

    def test_unknown_target_emotion_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不支持的目标情绪"):
            plan_emotion_stages("焦虑", 5, 60, target_emotion="振奋")

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

    @patch("py313_meditation_app.requests.post")
    def test_deepseek_json_mode_accepts_object_response(self, post):
        app = MeditationApp.__new__(MeditationApp)
        app.config = SimpleNamespace(
            api=SimpleNamespace(
                deepseek_api_key="test-key",
                deepseek_base_url="https://api.deepseek.com/v1",
                deepseek_model="deepseek-v4-flash",
                deepseek_timeout_seconds=180,
            )
        )
        app.logger = Mock()
        response = Mock(status_code=200, headers={}, content=b"response")
        response.json.return_value = {
            "choices": [
                {
                    "message": {"content": '{"scripts": []}'},
                    "finish_reason": "stop",
                }
            ]
        }
        post.return_value = response

        result = app._request_deepseek_json("返回JSON", "测试", 500)

        self.assertEqual(result, {"scripts": []})
        request_json = post.call_args.kwargs["json"]
        self.assertEqual(request_json["response_format"], {"type": "json_object"})

    @patch("py313_meditation_app.requests.post")
    def test_deepseek_json_rejects_empty_http_body(self, post):
        app = MeditationApp.__new__(MeditationApp)
        app.config = SimpleNamespace(
            api=SimpleNamespace(
                deepseek_api_key="test-key",
                deepseek_base_url="https://api.deepseek.com/v1",
                deepseek_model="deepseek-v4-flash",
                deepseek_timeout_seconds=180,
            )
        )
        app.logger = Mock()
        response = requests.Response()
        response.status_code = 200
        response._content = b""
        post.return_value = response

        with self.assertRaisesRegex(ValueError, "响应体为空"):
            app._request_deepseek_json("返回JSON", "测试", 500)

    @patch("py313_meditation_app.requests.post")
    def test_deepseek_json_rejects_empty_message_content(self, post):
        app = MeditationApp.__new__(MeditationApp)
        app.config = SimpleNamespace(
            api=SimpleNamespace(
                deepseek_api_key="test-key",
                deepseek_base_url="https://api.deepseek.com/v1",
                deepseek_model="deepseek-v4-flash",
                deepseek_timeout_seconds=180,
            )
        )
        app.logger = Mock()
        response = Mock(status_code=200, headers={}, content=b"response")
        response.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}]
        }
        post.return_value = response

        with self.assertRaisesRegex(ValueError, "message.content为空"):
            app._request_deepseek_json("返回JSON", "测试", 500)

    @patch("py313_meditation_app.requests.post")
    def test_deepseek_json_rejects_top_level_list(self, post):
        app = MeditationApp.__new__(MeditationApp)
        app.config = SimpleNamespace(
            api=SimpleNamespace(
                deepseek_api_key="test-key",
                deepseek_base_url="https://api.deepseek.com/v1",
                deepseek_model="deepseek-v4-flash",
                deepseek_timeout_seconds=180,
            )
        )
        app.logger = Mock()
        response = Mock(status_code=200, headers={}, content=b"response")
        response.json.return_value = {
            "choices": [{"message": {"content": "[]"}, "finish_reason": "stop"}]
        }
        post.return_value = response

        with self.assertRaisesRegex(ValueError, "JSON顶层必须是对象，实际为list"):
            app._request_deepseek_json("返回JSON", "测试", 500)

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
                        "text": (
                            "跟随舒缓而轻柔的音乐，慢慢安顿呼吸，感受空气经过鼻尖，"
                            "让肩膀逐渐放松，也允许此刻的紧张被温柔看见。"
                            "继续保持自然稳定的呼吸，把注意力轻轻带回身体，"
                            "在音乐的陪伴中安静停留，让思绪慢慢沉淀。"
                            "不需要催促任何改变，只需耐心陪伴每一次吸气与呼气。"
                        ),
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
        self.assertEqual(scripts[0]["guidance_source"], "ai")
        self.assertEqual(scripts[0]["grounding_fingerprint"], manifest[0]["grounding_fingerprint"])
        request_text = app._request_deepseek_json.call_args.args[1]
        self.assertIn("tempo_bpm", request_text)
        self.assertIn(music[0]["source_file"], request_text)
        request_payload = json.loads(request_text)
        segment = request_payload["music_manifest"][0]
        self.assertEqual(segment["target_speech_seconds"], 50.0)
        self.assertEqual(segment["target_text_characters"], 119)
        self.assertEqual(app._request_deepseek_json.call_args.args[2], 4096)
        self.assertEqual(app._request_deepseek_json.call_count, 1)

    def test_guidance_budget_scales_from_60_to_400_actual_seconds(self):
        app = MeditationApp.__new__(MeditationApp)
        attach_audio_config(app)

        self.assertEqual(app._guidance_speech_budget(60), 50.0)
        self.assertEqual(app._guidance_speech_budget(400), 350.0)
        self.assertEqual(app._guidance_target_characters(50), 119)
        self.assertEqual(app._guidance_target_characters(350), 833)

    def test_guidance_token_budget_expands_for_multiple_long_segments(self):
        prompt_manifest = [
            {"target_text_characters": 833},
            {"target_text_characters": 833},
            {"target_text_characters": 833},
        ]

        self.assertEqual(MeditationApp._guidance_max_tokens(prompt_manifest), 4548)

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
        self.assertEqual(app._request_deepseek_json.call_count, 2)
        retry_system_prompt = app._request_deepseek_json.call_args_list[1].args[0]
        self.assertIn("上一次响应不符合JSON结构要求", retry_system_prompt)

    def test_guidance_retries_top_level_list_then_accepts_valid_object(self):
        app = MeditationApp.__new__(MeditationApp)
        app.logger = Mock()
        attach_audio_config(app)
        music = [sample_music()]
        manifest = app._public_music_manifest(music)
        valid_script = {
            "segment_id": manifest[0]["segment_id"],
            "music_ref": manifest[0]["music_ref"],
            "grounding_fingerprint": manifest[0]["grounding_fingerprint"],
            "text": "安静地跟随呼吸，让身体逐渐放松。" * 8,
        }
        app._request_deepseek_json = Mock(
            side_effect=[[valid_script], {"scripts": [valid_script]}]
        )
        plan = {
            "emotion_analysis": {"primary_emotion": "焦虑"},
            "emotion_journey": "焦虑 → 平静",
        }

        scripts = app.generate_guidance_for_music("紧张", plan, music)

        self.assertEqual(app._request_deepseek_json.call_count, 2)
        self.assertEqual(scripts[0]["guidance_source"], "ai")
        retry_system_prompt = app._request_deepseek_json.call_args_list[1].args[0]
        self.assertIn("实际为list", retry_system_prompt)

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
                minimax_voice_id="test-voice",
            ),
            api=SimpleNamespace(minimax_api_key="test-key"),
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

    def test_output_name_uses_duration_and_emotion_journey_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = MeditationApp.__new__(MeditationApp)
            app.config = SimpleNamespace(paths=SimpleNamespace(base_dir=temp_dir))

            first = app._build_output_path(5, "焦虑 → 平静 → 喜悦")
            Path(first).touch()
            second = app._build_output_path(5, "焦虑 → 平静 → 喜悦")

            self.assertEqual(Path(first).name, "5分钟_焦虑-平静-喜悦.wav")
            self.assertEqual(Path(second).name, "5分钟_焦虑-平静-喜悦_2.wav")

    def test_ai_stage_plan_generates_one_track_per_emotion_stage(self):
        stages = plan_emotion_stages("焦虑", 5, 60)

        plan = MeditationApp._build_ai_stage_plan(stages)

        self.assertEqual(len(plan), 3)
        self.assertEqual([item["segment_id"] for item in plan], ["stage_01", "stage_02", "stage_03"])
        self.assertEqual(sum(item["duration_seconds"] for item in plan), 300)

    def test_sensitive_music_context_is_dropped(self):
        self.assertEqual(
            MeditationApp._sanitize_music_context("工作压力，联系 13800138000"),
            "工作压力",
        )
        self.assertEqual(
            MeditationApp._sanitize_music_context("工作压力与未来的不确定感"),
            "工作压力",
        )
        self.assertEqual(MeditationApp._sanitize_music_context("张某在某公司遇到问题"), "")

    def test_music_prompt_retries_then_uses_template(self):
        app = MeditationApp.__new__(MeditationApp)
        app.logger = Mock()
        app._request_deepseek_json = Mock(side_effect=RuntimeError("offline"))
        stages = MeditationApp._build_ai_stage_plan(plan_emotion_stages("焦虑", 3, 60))

        prompts = app.generate_ai_music_prompts(
            stages,
            {"primary_emotion": "焦虑", "music_context_summary": "工作压力"},
        )

        self.assertEqual(app._request_deepseek_json.call_count, 2)
        self.assertEqual(len(prompts), 3)
        self.assertTrue(all(item["prompt_source"] == "template_fallback" for item in prompts))

    def test_ai_music_recoverable_failure_switches_provider_and_writes_manifest(self):
        class FakeBackend:
            def __init__(self, provider, fail=False):
                self.provider = provider
                self.fail = fail

            def generate(self, **kwargs):
                if self.fail:
                    raise MusicGenerationError(
                        "timeout", provider=self.provider, recoverable=True
                    )
                AudioSegment.silent(1000).export(kwargs["output_path"], format="wav")
                return {
                    "path": str(kwargs["output_path"]),
                    "provider": self.provider,
                    "model": "test-model",
                    "request_id": "request-1",
                    "generation_prompt": kwargs["prompt"],
                    "negative_prompt": kwargs["negative_prompt"],
                    "actual_duration_seconds": 1.0,
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            app = MeditationApp.__new__(MeditationApp)
            app.logger = Mock()
            app._session_id = "test-session"
            app.config = SimpleNamespace(
                api=SimpleNamespace(
                    elevenlabs_api_key="key",
                    minimax_api_key="key",
                ),
                audio=SimpleNamespace(music_transition_fade_seconds=0.1),
            )
            app._music_backend = lambda provider: FakeBackend(
                provider, fail=provider == "elevenlabs"
            )
            stage = {
                "segment_id": "stage_01",
                "stage": 1,
                "duration_seconds": 60,
                "emotion_cn": "焦虑",
                "emotion_en": "Anxiety",
                "stage_goal": "接纳情绪",
                "transition_role": "接纳当下",
            }
            prompt = {
                "segment_id": "stage_01",
                "prompt_en": "calm instrumental",
                "negative_prompt_en": "vocals",
                "prompt_source": "deepseek",
            }

            music = app._generate_ai_music(
                [stage], [prompt], "elevenlabs", Path(temp_dir), "工作压力"
            )
            manifest = json.loads(
                (Path(temp_dir) / "generation_manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(music[0]["provider"], "minimax")
            self.assertTrue(music[0]["fallback_used"])
            self.assertEqual(manifest["anonymous_context"], "工作压力")
            self.assertEqual(manifest["segments"][0]["provider"], "minimax")
            self.assertEqual(
                [item["status"] for item in manifest["segments"][0]["attempts"]],
                ["failed", "success"],
            )

    def test_ai_output_file_and_asset_directory_share_collision_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = MeditationApp.__new__(MeditationApp)
            app.config = SimpleNamespace(paths=SimpleNamespace(base_dir=temp_dir))
            (Path(temp_dir) / "5分钟_焦虑-平静-喜悦.wav").touch()

            output_path, asset_dir = app._allocate_ai_output_paths(
                5, "焦虑 → 平静 → 喜悦"
            )

            self.assertEqual(Path(output_path).name, "5分钟_焦虑-平静-喜悦_2.wav")
            self.assertEqual(Path(asset_dir).name, "5分钟_焦虑-平静-喜悦_2_素材")
            self.assertTrue(Path(output_path).is_file())
            self.assertTrue(Path(asset_dir).is_dir())

    def test_ai_output_reservation_is_removed_when_asset_directory_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = MeditationApp.__new__(MeditationApp)
            app.config = SimpleNamespace(paths=SimpleNamespace(base_dir=temp_dir))

            with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    app._allocate_ai_output_paths(5, "焦虑 → 平静 → 喜悦")

            self.assertEqual(list(Path(temp_dir).glob("*.wav")), [])

    def test_ai_partial_failure_preserves_paid_segments_and_marks_manifest_failed(self):
        class PartialBackend:
            calls = 0

            def generate(self, **kwargs):
                self.calls += 1
                if self.calls == 3:
                    raise MusicGenerationError(
                        "service unavailable",
                        provider="elevenlabs",
                        recoverable=True,
                        status_code=503,
                    )
                AudioSegment.silent(1000).export(kwargs["output_path"], format="wav")
                return {
                    "path": str(kwargs["output_path"]),
                    "provider": "elevenlabs",
                    "model": "test-model",
                    "request_id": f"request-{self.calls}",
                    "generation_prompt": kwargs["prompt"],
                    "negative_prompt": kwargs["negative_prompt"],
                    "actual_duration_seconds": 1.0,
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            app = MeditationApp.__new__(MeditationApp)
            app.logger = Mock()
            app._session_id = "partial-session"
            app.config = SimpleNamespace(
                api=SimpleNamespace(
                    elevenlabs_api_key="key",
                    minimax_api_key="",
                ),
                audio=SimpleNamespace(music_transition_fade_seconds=0.1),
            )
            backend = PartialBackend()
            app._music_backend = lambda *_: backend
            stages = MeditationApp._build_ai_stage_plan(
                plan_emotion_stages("焦虑", 3, 60)
            )
            prompts = MeditationApp._template_ai_music_prompts(stages)

            with self.assertRaisesRegex(MeditationAppError, "stage_03"):
                app._generate_ai_music(
                    stages, prompts, "elevenlabs", Path(temp_dir), "匿名主题"
                )

            manifest = json.loads(
                (Path(temp_dir) / "generation_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failed_segment_id"], "stage_03")
            self.assertEqual(len(manifest["segments"]), 2)
            self.assertEqual(len(list(Path(temp_dir).glob("阶段*.wav"))), 2)


if __name__ == "__main__":
    unittest.main()
