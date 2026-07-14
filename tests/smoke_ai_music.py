"""显式付费 smoke test；默认不会运行或调用真实音乐 API。"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_manager import load_config
from music_generation_backends import create_music_backend


def main() -> None:
    if os.getenv("RUN_PAID_AI_MUSIC_SMOKE") != "1":
        raise SystemExit("未执行：请显式设置 RUN_PAID_AI_MUSIC_SMOKE=1")

    provider = os.getenv("AI_MUSIC_SMOKE_PROVIDER", "elevenlabs").strip().lower()
    config = load_config()
    if provider == "elevenlabs":
        backend = create_music_backend(
            provider,
            api_key=config.api.elevenlabs_api_key,
            base_url=config.api.elevenlabs_music_base_url,
            model=config.api.elevenlabs_music_model,
            timeout_seconds=config.api.music_request_timeout_seconds,
        )
    elif provider == "minimax":
        backend = create_music_backend(
            provider,
            api_key=config.api.minimax_api_key,
            base_url=config.api.minimax_music_base_url,
            model=config.api.minimax_music_model,
            timeout_seconds=config.api.music_request_timeout_seconds,
        )
    else:
        raise SystemExit(f"不支持的 AI_MUSIC_SMOKE_PROVIDER: {provider}")

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / f"{provider}_smoke.wav"
        result = backend.generate(
            prompt=(
                "Instrumental meditation music, calm and reassuring, slow tempo, "
                "warm sustained textures, gentle dynamics, soft ending."
            ),
            negative_prompt="vocals, lyrics, spoken words, abrupt loud peaks",
            target_duration_seconds=6,
            output_path=output_path,
        )
        if not output_path.exists() or result["actual_duration_seconds"] <= 0:
            raise RuntimeError("付费 smoke test 未生成有效 WAV")
        print(
            f"PAID_SMOKE_OK provider={provider} "
            f"duration={result['actual_duration_seconds']:.2f}s"
        )


if __name__ == "__main__":
    main()
