"""Manual smoke test for full-song selection and fade envelopes."""

from audio_compat import AudioSegment
from config_manager import load_config
from py313_meditation_app import MeditationApp


def main() -> None:
    config = load_config()
    config.api.deepseek_api_key = ""
    app = MeditationApp(config)
    user_input = "准备面试时有些紧张，希望逐渐平静。"
    plan = app.prepare_session_plan(user_input, 3)
    music = app.generate_music(plan["music_prompts"], plan["emotion_journey_plan"])
    scripts = app.generate_guidance_for_music(user_input, plan, music)

    checks = []
    for item in music:
        audio = AudioSegment.from_file(item["path"])
        checks.append(
            {
                "duration_matches_source": abs(len(audio) / 1000 - item["source_duration_seconds"]) < 0.02,
                "first_sample": float(abs(audio.data[..., 0]).max()),
                "last_sample": float(abs(audio.data[..., -1]).max()),
            }
        )

    print("WHOLE_COUNTS", len(music), len(scripts))
    print("WHOLE_PLANNED", sum(item["planned_duration_seconds"] for item in music))
    print("WHOLE_ACTUAL", sum(item["duration_seconds"] for item in music))
    print(
        "WHOLE_DURATIONS",
        "|".join(
            f"{item['source_duration_seconds']}/{item['duration_seconds']}" for item in music
        ),
    )
    print("WHOLE_FADE_CHECKS", checks)
    assert all(
        check["duration_matches_source"]
        and check["first_sample"] < 1e-4
        and check["last_sample"] < 1e-4
        for check in checks
    )


if __name__ == "__main__":
    main()
