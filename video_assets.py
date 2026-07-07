import logging
import os
import random
import time
from pathlib import Path

import requests
import yt_dlp

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
BACKGROUND_MUSIC_DIR = ROOT_DIR / "background_music"
MINECRAFT_DIR = ROOT_DIR / "minecraft_gameplay"

MIN_MINECRAFT_VIDEOS = 2

MINECRAFT_SOURCES = [
    {
        "url": (
            "https://archive.org/download/minecraft-find-the-button-parkour-champion/"
            "Minecraft%20FIND%20THE%20BUTTON%20-%20PARKOUR%20CHAMPION%21.mp4"
        ),
        "filename": "minecraft_parkour_archive_01.mp4",
        "kind": "http",
        "license": "Internet Archive (Vintage Software Collection)",
    },
    {
        "url": (
            "https://archive.org/download/MinecraftParkourEdgeCraft916.3/"
            "Minecraft%20Parkour%20_%20EdgeCraft%20_%209_16.3.mp4"
        ),
        "filename": "minecraft_parkour_archive_02.mp4",
        "kind": "http",
        "license": "Internet Archive (AntVenom EdgeCraft)",
    },
    {
        "url": "https://www.youtube.com/watch?v=XBIaqOm0RKQ",
        "filename": "minecraft_parkour_ccby_01.mp4",
        "kind": "yt-dlp",
        "license": "CC BY 4.0 - GameplaysForFree",
    },
    {
        "url": "https://www.youtube.com/watch?v=u7kdVe8q5zs",
        "filename": "minecraft_parkour_ccby_02.mp4",
        "kind": "yt-dlp",
        "license": "CC BY / royalty-free - Orbital No Copyright Gameplay",
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
            with requests.get(url, stream=True, timeout=180) as response:
                response.raise_for_status()
                with destination.open("wb") as output_file:
                    for chunk in response.iter_content(chunk_size=1024 * 512):
                        if chunk:
                            output_file.write(chunk)
            if destination.stat().st_size == 0:
                raise AssetBootstrapError(f"Downloaded empty file from {url}")
            return
        except Exception as exc:
            last_error = exc
            if destination.exists():
                destination.unlink(missing_ok=True)
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


def _download_via_yt_dlp(source: dict[str, str], destination: Path) -> None:
    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(destination.with_suffix("")) + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([source["url"]])
    if destination.exists() and destination.stat().st_size > 0:
        return
    produced = sorted(destination.parent.glob(destination.stem + ".*"))
    for candidate in produced:
        if candidate.suffix == ".mp4" and candidate.stat().st_size > 0:
            if candidate != destination:
                candidate.rename(destination)
            return
    raise AssetBootstrapError(f"yt-dlp produced no usable mp4 for {source['url']}")


def _download_minecraft_source(source: dict[str, str], destination: Path) -> None:
    if source.get("kind") == "http":
        _download_http_file(source["url"], destination, f"Minecraft download ({source['filename']})")
    else:
        _download_via_yt_dlp(source, destination)
    logger.info("Downloaded Minecraft gameplay: %s (%s)", destination.name, source["license"])


def _ensure_minecraft_assets() -> None:
    MINECRAFT_DIR.mkdir(parents=True, exist_ok=True)
    existing = _list_media_files(MINECRAFT_DIR, ".mp4")
    if len(existing) >= MIN_MINECRAFT_VIDEOS:
        logger.info("Minecraft gameplay assets ready (%s files)", len(existing))
        return

    downloaded = len(existing)
    for source in MINECRAFT_SOURCES:
        if downloaded >= MIN_MINECRAFT_VIDEOS:
            break
        destination = MINECRAFT_DIR / source["filename"]
        if destination.exists() and destination.stat().st_size > 0:
            continue
        logger.info("Downloading Minecraft gameplay from %s", source["url"])
        try:
            _download_minecraft_source(source, destination)
            downloaded += 1
        except Exception as exc:
            logger.warning("Minecraft source failed (%s): %s", source["url"], exc)

    if not _list_media_files(MINECRAFT_DIR, ".mp4"):
        logger.warning(
            "No Minecraft gameplay could be downloaded; pipeline will fall back to Pexels backgrounds."
        )


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
        try:
            _download_http_file(
                source["url"],
                destination,
                f"Background music download ({source['filename']})",
            )
        except Exception as exc:
            logger.warning("Background music source failed (%s): %s", source["url"], exc)

    if not _list_media_files(BACKGROUND_MUSIC_DIR, ".mp3"):
        logger.warning(
            "No background music could be downloaded; pipeline will skip music ducking."
        )


def has_minecraft_assets() -> bool:
    return bool(_list_media_files(MINECRAFT_DIR, ".mp4"))


def has_background_music() -> bool:
    return bool(_list_media_files(BACKGROUND_MUSIC_DIR, ".mp3"))


def ensure_assets() -> None:
    if os.environ.get("SKIP_ASSET_BOOTSTRAP", "").lower() in {"1", "true", "yes"}:
        logger.info("Skipping asset bootstrap (SKIP_ASSET_BOOTSTRAP is set)")
        BACKGROUND_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        MINECRAFT_DIR.mkdir(parents=True, exist_ok=True)
        return

    _ensure_minecraft_assets()
    _ensure_background_music()
