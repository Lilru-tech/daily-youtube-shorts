import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
    probe_duration,
    reset_work_dir,
)

SAMPLE_SCRIPT = VideoScript(
    video_title="Smoke Test Short",
    description="Local pipeline validation #test",
    tags="test,smoke,pipeline",
    lines=[
        ScriptLine(
            text="Your brain can rewire itself throughout your entire life.",
            search_keywords="brain neurons",
        ),
        ScriptLine(
            text="This is called neuroplasticity, and it powers every new skill you learn.",
            search_keywords="learning focus",
        ),
        ScriptLine(
            text="Even small daily habits can reshape how you think and feel.",
            search_keywords="meditation calm",
        ),
    ],
)


async def run_smoke_test() -> None:
    if not Path("/opt/homebrew/bin/ffmpeg").exists() and not Path("/usr/bin/ffmpeg").exists():
        import shutil

        if shutil.which("ffmpeg") is None:
            raise RuntimeError("FFmpeg is not installed")

    reset_work_dir()
    segments, audio_duration = await generate_voiceover(SAMPLE_SCRIPT)
    print(f"Audio: {AUDIO_PATH} ({audio_duration:.2f}s)")
    print(f"Captions: {CAPTIONS_PATH} ({CAPTIONS_PATH.stat().st_size} bytes)")

    raw_clips = download_background_clips(segments)
    print(f"Downloaded {len(raw_clips)} clips into {CLIPS_DIR}")

    build_background_video(raw_clips, segments)
    compose_final_video()
    final_duration = probe_duration(FINAL_PATH)
    print(f"Final video: {FINAL_PATH} ({final_duration:.2f}s)")
    print("Smoke test passed.")


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
