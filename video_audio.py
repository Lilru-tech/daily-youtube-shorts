import logging
import random
from pathlib import Path

from video_assets import BACKGROUND_MUSIC_DIR

logger = logging.getLogger(__name__)

MUSIC_VOLUME = 0.15


def select_background_music() -> Path:
    tracks = sorted(BACKGROUND_MUSIC_DIR.glob("*.mp3"))
    if not tracks:
        raise FileNotFoundError(f"No background music tracks found in {BACKGROUND_MUSIC_DIR}")
    selected = random.choice(tracks)
    logger.info("Selected background music: %s", selected.name)
    return selected


def mix_voiceover_with_music(
  voice_path: Path,
  music_path: Path,
  output_path: Path,
  total_duration: float,
  run_command,
) -> None:
    filter_graph = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{total_duration:.3f},"
        f"asetpts=PTS-STARTPTS,volume={MUSIC_VOLUME}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(voice_path),
            "-i",
            str(music_path),
            "-filter_complex",
            filter_graph,
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output_path),
        ],
        "Background music mixing",
    )
    logger.info("Mixed audio ready at %s (%.2fs)", output_path, total_duration)
