import argparse
import asyncio
import os
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
    MIXED_AUDIO_PATH,
    ScriptLine,
    VideoScript,
    compose_final_video,
    configure_work_paths,
    ensure_ffmpeg_subtitles_filter,
    generate_voiceover,
    init_channel_profile,
    probe_duration,
    reset_work_dir,
    resolve_subtitle_font,
    trim_trailing_silence,
)
from video_assets import ensure_assets
from video_audio import mix_voiceover_with_music, select_background_music
from video_background import build_background
from video_subtitles import build_ass_captions

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
                text="Cada repeticion fortalece las conexiones que mas usas, y por eso tu cerebro puede",
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
                text="Your brain would force micro-blinks to protect you, but what happens if you stopped",
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

    configure_work_paths()
    ensure_ffmpeg_subtitles_filter()
    if not os.environ.get("SKIP_ASSET_BOOTSTRAP", "").lower() in {"1", "true", "yes"}:
        ensure_assets()

    profile = init_channel_profile(channel)
    script = SAMPLE_SCRIPTS[channel]
    reset_work_dir()
    segments, audio_duration, word_events = await generate_voiceover(script)
    audio_duration = trim_trailing_silence(AUDIO_PATH)
    print(f"Audio: {AUDIO_PATH} ({audio_duration:.2f}s)")

    _, font_name = resolve_subtitle_font()
    build_ass_captions(
        word_events,
        CAPTIONS_PATH,
        font_name=font_name,
        subtitle_style=profile.subtitle_style,
    )
    print(f"Captions: {CAPTIONS_PATH} ({CAPTIONS_PATH.stat().st_size} bytes)")

    music_path = select_background_music()
    mix_voiceover_with_music(
        AUDIO_PATH,
        music_path,
        MIXED_AUDIO_PATH,
        audio_duration,
        __import__("main").run_command,
    )
    print(f"Mixed audio: {MIXED_AUDIO_PATH}")

    from main import (  # noqa: E402
        BACKGROUND_PATH,
        CLIPS_DIR,
        download_file,
        require_env,
        retry,
        PipelineError,
    )

    build_background(
        audio_duration,
        segments,
        "pexels",
        fallback_keywords=profile.fallback_keywords,
        clips_dir=CLIPS_DIR,
        background_path=BACKGROUND_PATH,
        minecraft_state_path=profile.data_dir / "minecraft_state.json",
        run_command=__import__("main").run_command,
        download_file=download_file,
        probe_duration=probe_duration,
        require_env=require_env,
        retry=retry,
        pipeline_error=PipelineError,
    )
    print(f"Background video ready in {CLIPS_DIR}")

    compose_final_video(script, audio_path=MIXED_AUDIO_PATH, total_duration=audio_duration)
    final_duration = probe_duration(FINAL_PATH)
    print(f"Final video: {FINAL_PATH} ({final_duration:.2f}s)")
    print(f"Smoke test passed for {channel}.")


if __name__ == "__main__":
    args = parse_args()
    if args.channel == "whatifvibe":
        if not os.environ.get("YT_TARGET_CHANNEL_ID_WHATIFVIBE", "").strip():
            os.environ["YT_TARGET_CHANNEL_ID_WHATIFVIBE"] = "UC_PLACEHOLDER_WHATIFVIBE"
    asyncio.run(run_smoke_test(args.channel))
