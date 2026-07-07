import json
import logging
import math
import random
from pathlib import Path
from typing import Any, Literal

import requests

from video_assets import MINECRAFT_DIR

logger = logging.getLogger(__name__)

BackgroundMode = Literal["pexels", "minecraft"]
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30
MIN_SEGMENT_GAP = 30.0
PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"


def _load_minecraft_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        logger.warning("Could not parse %s, resetting Minecraft state", state_path)
    return {}


def _save_minecraft_state(state_path: Path, video_name: str, end_offset: float) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"video": video_name, "last_end_offset": end_offset}, indent=2) + "\n",
        encoding="utf-8",
    )


def _pexels_headers(require_env) -> dict[str, str]:
    return {"Authorization": require_env("PEXELS_API_KEY")}


def _search_pexels_videos(
    query: str,
    used_ids: set[int],
    require_env,
    retry,
) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "per_page": 20,
        "orientation": "portrait",
    }

    def _search() -> list[dict[str, Any]]:
        response = requests.get(
            PEXELS_SEARCH_URL,
            headers=_pexels_headers(require_env),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        videos = payload.get("videos", [])
        if not isinstance(videos, list):
            return []
        return videos

    videos = retry(_search, f"Pexels search for '{query}'")
    return [video for video in videos if video.get("id") not in used_ids]


def _choose_video_file(video: dict[str, Any]) -> dict[str, Any] | None:
    files = video.get("video_files", [])
    if not isinstance(files, list) or not files:
        return None

    portrait_candidates = [
        item
        for item in files
        if item.get("width") and item.get("height") and item["height"] > item["width"]
    ]
    candidates = portrait_candidates or files
    candidates.sort(
        key=lambda item: (
            item.get("height", 0),
            item.get("width", 0),
        ),
        reverse=True,
    )
    return candidates[0]


def _normalize_and_trim_clip(
    source_path: Path,
    destination_path: Path,
    duration: float,
    run_command,
) -> None:
    filter_chain = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},"
        f"setsar=1,fps={TARGET_FPS},format=yuv420p"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source_path),
            "-t",
            f"{duration:.3f}",
            "-vf",
            filter_chain,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(destination_path),
        ],
        f"Normalize clip {source_path.name}",
    )



def build_pexels_background(
    total_duration: float,
    segments: list[Any],
    fallback_keywords: list[str],
    clips_dir: Path,
    background_path: Path,
    *,
    run_command,
    download_file,
    require_env,
    retry,
    pipeline_error,
) -> None:
    clip_duration = random.uniform(2.5, 3.0)
    clip_count = max(1, math.ceil(total_duration / clip_duration))
    keyword_pool = [segment.search_keywords for segment in segments] + fallback_keywords
    if not keyword_pool:
        keyword_pool = ["cinematic abstract"]

    used_video_ids: set[int] = set()
    processed_clips: list[Path] = []
    elapsed = 0.0

    for clip_index in range(clip_count):
        remaining = total_duration - elapsed
        if remaining <= 0.05:
            break
        current_duration = min(clip_duration, remaining)
        keywords = [keyword_pool[clip_index % len(keyword_pool)], *fallback_keywords]

        selected_video: dict[str, Any] | None = None
        selected_file: dict[str, Any] | None = None
        for keyword in keywords:
            videos = _search_pexels_videos(keyword, used_video_ids, require_env, retry)
            for video in videos:
                video_file = _choose_video_file(video)
                if video_file and video_file.get("link"):
                    selected_video = video
                    selected_file = video_file
                    break
            if selected_video:
                break

        if not selected_video or not selected_file:
            raise pipeline_error(f"No Pexels video found for fast-cut clip {clip_index}")

        video_id = int(selected_video["id"])
        used_video_ids.add(video_id)
        raw_clip_path = clips_dir / f"raw_{clip_index:02d}.mp4"
        download_file(str(selected_file["link"]), raw_clip_path)
        processed_path = clips_dir / f"processed_{clip_index:02d}.mp4"
        _normalize_and_trim_clip(raw_clip_path, processed_path, current_duration, run_command)
        processed_clips.append(processed_path)
        elapsed += current_duration
        logger.info(
            "Pexels fast-cut clip %s/%s (%.2fs) from video %s",
            clip_index + 1,
            clip_count,
            current_duration,
            video_id,
        )

    concat_list_path = clips_dir / "concat.txt"
    with concat_list_path.open("w", encoding="utf-8") as concat_file:
        for clip_path in processed_clips:
            concat_file.write(f"file '{clip_path.resolve().as_posix()}'\n")

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            str(background_path),
        ],
        "Pexels background concatenation",
    )
    logger.info("Pexels background ready at %s (%.2fs target)", background_path, total_duration)


def build_minecraft_background(
    total_duration: float,
    minecraft_state_path: Path,
    background_path: Path,
    *,
    run_command,
    probe_duration,
    pipeline_error,
) -> None:
    videos = sorted(MINECRAFT_DIR.glob("*.mp4"))
    if not videos:
        raise pipeline_error(f"No Minecraft gameplay videos found in {MINECRAFT_DIR}")

    state = _load_minecraft_state(minecraft_state_path)
    last_video = str(state.get("video", ""))
    last_end_offset = float(state.get("last_end_offset", 0.0))

    if last_video and any(video.name == last_video for video in videos):
        source_video = next(video for video in videos if video.name == last_video)
    else:
        source_video = random.choice(videos)
        last_end_offset = 0.0

    source_duration = probe_duration(source_video)
    max_start = max(0.0, source_duration - total_duration - 1.0)
    start_offset = last_end_offset + MIN_SEGMENT_GAP
    if start_offset > max_start:
        start_offset = random.uniform(0.0, max(0.0, max_start))

    filter_chain = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},"
        f"setsar=1,fps={TARGET_FPS},format=yuv420p"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-ss",
            f"{start_offset:.3f}",
            "-i",
            str(source_video),
            "-t",
            f"{total_duration:.3f}",
            "-vf",
            filter_chain,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(background_path),
        ],
        "Minecraft background extraction",
    )

    end_offset = start_offset + total_duration
    if end_offset >= source_duration - 5.0:
        end_offset = 0.0
    _save_minecraft_state(minecraft_state_path, source_video.name, end_offset)
    logger.info(
        "Minecraft background ready at %s from %s (start=%.2fs, duration=%.2fs)",
        background_path,
        source_video.name,
        start_offset,
        total_duration,
    )


def build_background(
    total_duration: float,
    segments: list[Any],
    mode: BackgroundMode,
    *,
    fallback_keywords: list[str],
    clips_dir: Path,
    background_path: Path,
    minecraft_state_path: Path,
    run_command,
    download_file,
    probe_duration,
    require_env,
    retry,
    pipeline_error,
) -> None:
    if mode == "pexels":
        build_pexels_background(
            total_duration,
            segments,
            fallback_keywords,
            clips_dir,
            background_path,
            run_command=run_command,
            download_file=download_file,
            require_env=require_env,
            retry=retry,
            pipeline_error=pipeline_error,
        )
        return

    build_minecraft_background(
        total_duration,
        minecraft_state_path,
        background_path,
        run_command=run_command,
        probe_duration=probe_duration,
        pipeline_error=pipeline_error,
    )
