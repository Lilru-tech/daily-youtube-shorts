import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from channel_profiles import PROFILES
from main import (  # noqa: E402
    AUDIO_PATH,
    CAPTIONS_PATH,
    CLIPS_DIR,
    FINAL_PATH,
    ScriptLine,
    VideoScript,
    build_background_video,
    compose_final_video,
    download_background_clips,
    generate_voiceover,
    init_channel_profile,
    probe_duration,
    reset_work_dir,
)

SAMPLE_SCRIPTS: dict[str, VideoScript] = {
    "datos_es": VideoScript(
        video_title="🧠 Tu cerebro puede cambiar",
        hook_text="TU CEREBRO CAMBIA",
        description="Validacion local del pipeline #test #psicologia",
        tags="test,prueba,pipeline,psicologia",
        lines=[
            ScriptLine(
                text="Tu cerebro puede reorganizarse durante toda tu vida.",
                search_keywords="cerebro neuronas",
            ),
            ScriptLine(
                text="A esto se le llama neuroplasticidad, y es la base de cada habilidad nueva.",
                search_keywords="aprendizaje enfoque",
            ),
            ScriptLine(
                text="Incluso pequenos habitos diarios pueden cambiar como piensas y sientes.",
                search_keywords="meditacion calma",
            ),
            ScriptLine(
                text="Cada repeticion fortalece las conexiones que mas usas en tu mente.",
                search_keywords="mente pensando",
            ),
        ],
    ),
    "whatifvibe": VideoScript(
        video_title="What If You Stop Blinking for 24 Hours?",
        hook_text="STOP BLINKING",
        description="A mind-bending look at what happens when you stop blinking. #whatif #science #shorts",
        tags="what if,science,shorts,hypothetical,test",
        lines=[
            ScriptLine(
                text="What happens if you stopped blinking for 24 hours?",
                search_keywords="human eye close",
            ),
            ScriptLine(
                text="Within minutes, your eyes would dry out and turn bloodshot.",
                search_keywords="red eye medical",
            ),
            ScriptLine(
                text="After an hour, your vision would blur and ulcers could form on your cornea.",
                search_keywords="eye doctor exam",
            ),
            ScriptLine(
                text="Your brain would force micro-blinks to protect you before permanent damage set in.",
                search_keywords="brain scan medical",
            ),
        ],
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the Shorts pipeline for a channel profile.")
    parser.add_argument(
        "--channel",
        choices=sorted(PROFILES.keys()),
        default="whatifvibe",
        help="Channel profile to test.",
    )
    return parser.parse_args()


async def run_smoke_test(channel: str) -> None:
    if not Path("/opt/homebrew/bin/ffmpeg").exists() and not Path("/usr/bin/ffmpeg").exists():
        import shutil

        if shutil.which("ffmpeg") is None:
            raise RuntimeError("FFmpeg is not installed")

    init_channel_profile(channel)
    script = SAMPLE_SCRIPTS[channel]
    reset_work_dir()
    segments, audio_duration = await generate_voiceover(script)
    print(f"Audio: {AUDIO_PATH} ({audio_duration:.2f}s)")
    print(f"Captions: {CAPTIONS_PATH} ({CAPTIONS_PATH.stat().st_size} bytes)")

    raw_clips = download_background_clips(segments)
    print(f"Downloaded {len(raw_clips)} clips into {CLIPS_DIR}")

    build_background_video(raw_clips, segments)
    compose_final_video(script)
    final_duration = probe_duration(FINAL_PATH)
    print(f"Final video: {FINAL_PATH} ({final_duration:.2f}s)")
    print(f"Smoke test passed for {channel}.")


if __name__ == "__main__":
    args = parse_args()
    if args.channel == "whatifvibe":
        import os

        if not os.environ.get("YT_TARGET_CHANNEL_ID_WHATIFVIBE", "").strip():
            os.environ["YT_TARGET_CHANNEL_ID_WHATIFVIBE"] = "UC_PLACEHOLDER_WHATIFVIBE"
    asyncio.run(run_smoke_test(args.channel))
