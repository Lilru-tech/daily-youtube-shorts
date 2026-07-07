import logging
import random
import time
from pathlib import Path

import requests
import yt_dlp

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
BACKGROUND_MUSIC_DIR = ROOT_DIR / "background_music"
MINECRAFT_DIR = ROOT_DIR / "minecraft_gameplay"

MINECRAFT_SOURCES = [
    {
        "url": "https://www.youtube.com/watch?v=7t2alSnE2-I",
        "filename": "minecraft_parkour_01.mp4",
        "license": "Creative Commons Attribution (CC BY)",
    },
    {
        "url": "https://www.youtube.com/watch?v=n_Dv4JMiwK8",
        "filename": "minecraft_parkour_02.mp4",
        "license": "Creative Commons Attribution (CC BY)",
    },
    {
        "url": "https://www.youtube.com/watch?v=PtMiBz40Cyo",
        "filename": "minecraft_parkour_03.mp4",
        "license": "Creative Commons Attribution (CC BY)",
    },
]

BACKGROUND_MUSIC_SOURCES = [
    {
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
        "filename": "ambient_suspense_01.mp3",
        "license": "SoundHelix (royalty-free)",
    },
    {
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-14.mp3",
        "filename": "ambient_suspense_02.mp3",
        "license": "SoundHelix (royalty-free)",
    },
    {
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-16.mp3",
        "filename": "ambient_suspense_03.mp3",
        "license": "SoundHelix (royalty-free)",
    },
]


class AssetBootstrapError(Exception):
    pass


def _list_media_files(directory: Path, extension: str) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob(f"*{extension}") if path.is_file())


def _download_http_file(url: str, destination: Path, description: str, max_attempts: int = 3) -> None:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with destination.open("wb") as output_file:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            output_file.write(chunk)
            if destination.stat().st_size == 0:
                raise AssetBootstrapError(f"Downloaded empty file from {url}")
            return
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                delay = 2.0 * attempt + random.uniform(0, 0.5)
                logger.warning(
                    "%s failed on attempt %s/%s: %s. Retrying in %.1fs.",
                    description,
                    attempt,
                    max_attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
    raise AssetBootstrapError(f"{description} failed after {max_attempts} attempts: {last_error}")


def _download_minecraft_video(source: dict[str, str], destination: Path) -> None:
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(destination.with_suffix("")),
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
    }
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([source["url"]])
            if not destination.exists() or destination.stat().st_size == 0:
                raise AssetBootstrapError(f"yt-dlp produced empty file for {source['url']}")
            logger.info(
                "Downloaded Minecraft gameplay: %s (%s)",
                destination.name,
                source["license"],
            )
            return
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                delay = 3.0 * attempt
                logger.warning(
                    "Minecraft download %s failed attempt %s/3: %s. Retrying in %.1fs.",
                    source["url"],
                    attempt,
                    exc,
                    delay,
                )
                time.sleep(delay)
    raise AssetBootstrapError(
        f"Failed to download Minecraft video from {source['url']}: {last_error}"
    )


def _ensure_minecraft_assets() -> None:
    MINECRAFT_DIR.mkdir(parents=True, exist_ok=True)
    existing = _list_media_files(MINECRAFT_DIR, ".mp4")
    if existing:
        logger.info("Minecraft gameplay assets ready (%s files)", len(existing))
        return

    sources = random.sample(MINECRAFT_SOURCES, k=min(3, len(MINECRAFT_SOURCES)))
    for source in sources:
        destination = MINECRAFT_DIR / source["filename"]
        if destination.exists() and destination.stat().st_size > 0:
            continue
        logger.info("Downloading Minecraft gameplay from %s", source["url"])
        _download_minecraft_video(source, destination)

    if not _list_media_files(MINECRAFT_DIR, ".mp4"):
        raise AssetBootstrapError("No Minecraft gameplay videos available after bootstrap")


def _ensure_background_music() -> None:
    BACKGROUND_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    existing = _list_media_files(BACKGROUND_MUSIC_DIR, ".mp3")
    if existing:
        logger.info("Background music assets ready (%s files)", len(existing))
        return

    for source in BACKGROUND_MUSIC_SOURCES:
        destination = BACKGROUND_MUSIC_DIR / source["filename"]
        if destination.exists() and destination.stat().st_size > 0:
            continue
        logger.info("Downloading background music: %s (%s)", source["filename"], source["license"])
        _download_http_file(
            source["url"],
            destination,
            f"Background music download ({source['filename']})",
        )

    if not _list_media_files(BACKGROUND_MUSIC_DIR, ".mp3"):
        raise AssetBootstrapError("No background music tracks available after bootstrap")


def ensure_assets() -> None:
    import os

    if os.environ.get("SKIP_ASSET_BOOTSTRAP", "").lower() in {"1", "true", "yes"}:
        logger.info("Skipping asset bootstrap (SKIP_ASSET_BOOTSTRAP is set)")
        BACKGROUND_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        MINECRAFT_DIR.mkdir(parents=True, exist_ok=True)
        return

    _ensure_minecraft_assets()
    _ensure_background_music()
