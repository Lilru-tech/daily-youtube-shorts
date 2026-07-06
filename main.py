import argparse
import asyncio
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

import edge_tts
import requests
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

T = TypeVar("T")

WORK_DIR = Path(os.environ.get("WORK_DIR", "work"))
AUDIO_PATH = WORK_DIR / "audio.mp3"
CAPTIONS_PATH = WORK_DIR / "captions.srt"
BACKGROUND_PATH = WORK_DIR / "background.mp4"
FINAL_PATH = WORK_DIR / "final.mp4"
CLIPS_DIR = WORK_DIR / "clips"
AUDIO_FRAGMENTS_DIR = WORK_DIR / "audio_fragments"

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30
MIN_SCRIPT_CHARS = 300
MAX_SCRIPT_CHARS = 900
PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
FALLBACK_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash",
]
DEFAULT_EDGE_VOICE = "es-ES-AlvaroNeural"
DEFAULT_PRIVACY_STATUS = "unlisted"
YOUTUBE_CATEGORY_ID = "27"
FALLBACK_KEYWORDS = ["paisaje naturaleza", "cerebro pensando", "ciudad noche"]
FFMPEG_FULL_PATH = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
FFPROBE_FULL_PATH = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffprobe")


def resolve_ffmpeg() -> str:
    if FFMPEG_FULL_PATH.exists():
        return str(FFMPEG_FULL_PATH)
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    raise PipelineError("ffmpeg not found in PATH")


def resolve_ffprobe() -> str:
    if FFPROBE_FULL_PATH.exists():
        return str(FFPROBE_FULL_PATH)
    binary = shutil.which("ffprobe")
    if binary:
        return binary
    raise PipelineError("ffprobe not found in PATH")


def with_media_binary(command: list[str]) -> list[str]:
    if not command:
        return command
    if command[0] == "ffmpeg":
        return [resolve_ffmpeg(), *command[1:]]
    if command[0] == "ffprobe":
        return [resolve_ffprobe(), *command[1:]]
    return command


@dataclass
class ScriptLine:
    text: str
    search_keywords: str


@dataclass
class VideoScript:
    video_title: str
    description: str
    tags: str
    lines: list[ScriptLine]


@dataclass
class LineSegment:
    index: int
    text: str
    search_keywords: str
    audio_path: Path
    duration: float


class PipelineError(Exception):
    pass


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise PipelineError(f"Missing required environment variable: {name}")
    return value


def retry(
    operation: Callable[[], T],
    description: str,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "%s failed on attempt %s/%s: %s. Retrying in %.1fs.",
                description,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    raise PipelineError(f"{description} failed after {max_attempts} attempts: {last_error}")


def run_command(command: list[str], description: str) -> None:
    command = with_media_binary(command)
    logger.info("Running FFmpeg: %s", " ".join(command))
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-2000:]
        raise PipelineError(f"{description} failed (exit {result.returncode}): {stderr_tail}")
    if result.stderr:
        logger.debug(result.stderr[-500:])


def probe_duration(path: Path) -> float:
    command = with_media_binary(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise PipelineError(f"Invalid media duration for {path}: {duration}")
    return duration


def reset_work_dir() -> None:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_FRAGMENTS_DIR.mkdir(parents=True, exist_ok=True)


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def validate_script_payload(payload: dict[str, Any]) -> VideoScript:
    required_keys = {"video_title", "description", "tags", "lines"}
    missing = required_keys - set(payload.keys())
    if missing:
        raise PipelineError(f"Gemini response missing keys: {sorted(missing)}")

    lines_raw = payload.get("lines")
    if not isinstance(lines_raw, list) or not lines_raw:
        raise PipelineError("Gemini response must include a non-empty 'lines' array")

    lines: list[ScriptLine] = []
    for index, item in enumerate(lines_raw):
        if not isinstance(item, dict):
            raise PipelineError(f"Line {index} is not an object")
        text = str(item.get("text", "")).strip()
        keywords = str(item.get("search_keywords", "")).strip()
        if not text:
            raise PipelineError(f"Line {index} has empty text")
        if not keywords:
            raise PipelineError(f"Line {index} has empty search_keywords")
        lines.append(ScriptLine(text=text, search_keywords=keywords))

    total_chars = sum(len(line.text) for line in lines)
    if total_chars < MIN_SCRIPT_CHARS or total_chars > MAX_SCRIPT_CHARS:
        raise PipelineError(
            f"Script length {total_chars} chars is outside target range "
            f"({MIN_SCRIPT_CHARS}-{MAX_SCRIPT_CHARS})"
        )

    title = str(payload["video_title"]).strip()[:95]
    description = str(payload["description"]).strip()[:4500]
    if looks_english(title) or looks_english(description):
        raise PipelineError("Gemini returned English metadata; Spanish content required")

    for index, line in enumerate(lines):
        if looks_english(line.text):
            raise PipelineError(f"Line {index} is not in Spanish")

    return VideoScript(
        video_title=title,
        description=description,
        tags=str(payload["tags"]).strip(),
        lines=lines,
    )


def build_script_prompt() -> str:
    return """
Eres un guionista viral de YouTube Shorts especializado en "Datos Asombrosos e Insights Psicológicos".

Escribe un guion en español (España, neutro y natural) para un Short vertical de 40-50 segundos.
Usa 6-8 líneas cortas habladas. Cada línea debe ser una frase impactante.
Cada línea debe incluir search_keywords para buscar metraje en Pexels (2-5 palabras, en español o inglés).

Devuelve SOLO JSON válido con este esquema exacto:
{
  "video_title": "Título llamativo de menos de 90 caracteres",
  "description": "Descripción de 2-3 frases con 2-3 hashtags relevantes",
  "tags": "etiquetas,separadas,por,comas,sin,espacios,despues,de,comas",
  "lines": [
    {"text": "Primera línea hablada.", "search_keywords": "cerebro neuronas"},
    {"text": "Segunda línea hablada.", "search_keywords": "galaxia estrellas"}
  ]
}

Reglas:
- Todo el contenido en español (título, descripción, tags y líneas). Prohibido usar inglés.
- Sin markdown, sin comentarios, sin claves extra.
- Los datos deben ser creíbles e interesantes desde la psicología.
- El texto hablado total debe tener entre 300 y 900 caracteres.
""".strip()


def looks_english(text: str) -> bool:
    lowered = f" {text.lower()} "
    english_markers = (
        " the ",
        " your ",
        " brain",
        " unlock",
        " secret",
        " you ",
        " and ",
        " with ",
        " this ",
        " that ",
        " what ",
        " how ",
    )
    return any(marker in lowered for marker in english_markers)


def generate_script() -> VideoScript:
    api_key = require_env("GEMINI_API_KEY")
    configured_model = os.environ.get("GEMINI_MODEL", "").strip()
    models: list[str] = []
    if configured_model:
        models.append(configured_model)
    for model in FALLBACK_GEMINI_MODELS:
        if model not in models:
            models.append(model)

    client = genai.Client(api_key=api_key)
    last_error: Exception | None = None

    for model in models:
        def _call_gemini(current_model: str = model) -> VideoScript:
            response = client.models.generate_content(
                model=current_model,
                contents=build_script_prompt(),
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_mime_type="application/json",
                ),
            )
            raw_text = (response.text or "").strip()
            if not raw_text:
                raise PipelineError("Gemini returned an empty response")
            payload = extract_json_payload(raw_text)
            return validate_script_payload(payload)

        try:
            script = retry(
                _call_gemini,
                f"Gemini script generation ({model})",
                max_attempts=4,
                base_delay=20.0,
            )
            logger.info(
                "Generated script with %s: %s (%s lines)",
                model,
                script.video_title,
                len(script.lines),
            )
            return script
        except PipelineError as exc:
            last_error = exc
            logger.warning("Model %s unavailable, trying next fallback: %s", model, exc)

    raise PipelineError(f"All Gemini models failed. Last error: {last_error}")


def parse_srt_timestamp(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def format_srt_timestamp(seconds: float) -> str:
    total_millis = int(round(seconds * 1000))
    hours = total_millis // 3_600_000
    total_millis %= 3_600_000
    minutes = total_millis // 60_000
    total_millis %= 60_000
    secs = total_millis // 1000
    millis = total_millis % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def shift_srt_content(content: str, offset_seconds: float, start_index: int) -> tuple[str, int]:
    blocks = re.split(r"\n\s*\n", content.strip())
    shifted_blocks: list[str] = []
    cue_index = start_index
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        timing_match = re.match(
            r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",
            lines[1],
        )
        if not timing_match:
            continue
        start = parse_srt_timestamp(timing_match.group(1)) + offset_seconds
        end = parse_srt_timestamp(timing_match.group(2)) + offset_seconds
        text = "\n".join(lines[2:]).strip()
        shifted_blocks.append(
            f"{cue_index}\n"
            f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n"
            f"{text}"
        )
        cue_index += 1
    return "\n\n".join(shifted_blocks), cue_index


async def synthesize_line_audio(
    index: int,
    text: str,
    voice: str,
) -> tuple[Path, str, float]:
    audio_path = AUDIO_FRAGMENTS_DIR / f"line_{index:02d}.mp3"
    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()

    with audio_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise PipelineError(f"edge-tts produced empty audio for line {index}")

    srt_content = submaker.get_srt()
    duration = probe_duration(audio_path)
    return audio_path, srt_content, duration


async def generate_voiceover(script: VideoScript) -> tuple[list[LineSegment], float]:
    voice = os.environ.get("EDGE_TTS_VOICE", DEFAULT_EDGE_VOICE).strip() or DEFAULT_EDGE_VOICE
    segments: list[LineSegment] = []
    merged_srt_parts: list[str] = []
    cue_index = 1
    timeline_offset = 0.0

    for index, line in enumerate(script.lines):
        audio_path, srt_content, duration = await synthesize_line_audio(index, line.text, voice)
        segments.append(
            LineSegment(
                index=index,
                text=line.text,
                search_keywords=line.search_keywords,
                audio_path=audio_path,
                duration=duration,
            )
        )
        if srt_content.strip():
            shifted, cue_index = shift_srt_content(srt_content, timeline_offset, cue_index)
            if shifted:
                merged_srt_parts.append(shifted)
        else:
            start = format_srt_timestamp(timeline_offset)
            end = format_srt_timestamp(timeline_offset + duration)
            merged_srt_parts.append(f"{cue_index}\n{start} --> {end}\n{line.text}")
            cue_index += 1
        timeline_offset += duration

    concat_list_path = AUDIO_FRAGMENTS_DIR / "concat.txt"
    with concat_list_path.open("w", encoding="utf-8") as concat_file:
        for segment in segments:
            concat_file.write(f"file '{segment.audio_path.resolve().as_posix()}'\n")

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
            str(AUDIO_PATH),
        ],
        "Audio concatenation",
    )

    CAPTIONS_PATH.write_text("\n\n".join(merged_srt_parts) + "\n", encoding="utf-8")
    total_duration = probe_duration(AUDIO_PATH)
    logger.info("Voiceover ready: %.2fs (%s segments)", total_duration, len(segments))
    return segments, total_duration


def pexels_headers() -> dict[str, str]:
    return {"Authorization": require_env("PEXELS_API_KEY")}


def search_pexels_videos(query: str, used_ids: set[int]) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "per_page": 20,
        "orientation": "portrait",
    }

    def _search() -> list[dict[str, Any]]:
        response = requests.get(
            PEXELS_SEARCH_URL,
            headers=pexels_headers(),
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


def choose_video_file(video: dict[str, Any]) -> dict[str, Any] | None:
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


def download_file(url: str, destination: Path) -> None:
    def _download() -> None:
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with destination.open("wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        output_file.write(chunk)
        if destination.stat().st_size == 0:
            raise PipelineError(f"Downloaded empty file from {url}")

    retry(_download, f"Download {destination.name}")


def download_background_clips(segments: list[LineSegment]) -> list[Path]:
    used_video_ids: set[int] = set()
    clip_paths: list[Path] = []

    for segment in segments:
        keywords = [segment.search_keywords, *FALLBACK_KEYWORDS]
        selected_video: dict[str, Any] | None = None
        selected_file: dict[str, Any] | None = None

        for keyword in keywords:
            videos = search_pexels_videos(keyword, used_video_ids)
            for video in videos:
                video_file = choose_video_file(video)
                if video_file and video_file.get("link"):
                    selected_video = video
                    selected_file = video_file
                    break
            if selected_video:
                break

        if not selected_video or not selected_file:
            raise PipelineError(f"No Pexels video found for line {segment.index}: {segment.search_keywords}")

        video_id = int(selected_video["id"])
        used_video_ids.add(video_id)
        raw_clip_path = CLIPS_DIR / f"raw_{segment.index:02d}.mp4"
        download_file(str(selected_file["link"]), raw_clip_path)
        clip_paths.append(raw_clip_path)
        logger.info(
            "Downloaded clip %s for line %s (%s)",
            video_id,
            segment.index,
            segment.search_keywords,
        )

    return clip_paths


def normalize_and_trim_clip(source_path: Path, destination_path: Path, duration: float) -> None:
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


def build_background_video(raw_clips: list[Path], segments: list[LineSegment]) -> None:
    processed_clips: list[Path] = []
    for raw_clip, segment in zip(raw_clips, segments, strict=True):
        processed_path = CLIPS_DIR / f"processed_{segment.index:02d}.mp4"
        normalize_and_trim_clip(raw_clip, processed_path, segment.duration)
        processed_clips.append(processed_path)

    concat_list_path = CLIPS_DIR / "concat.txt"
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
            str(BACKGROUND_PATH),
        ],
        "Background video concatenation",
    )
    logger.info("Background video created at %s", BACKGROUND_PATH)


def resolve_subtitle_font() -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return "DejaVu Sans"


def ensure_ffmpeg_subtitles_filter() -> None:
    result = subprocess.run(
        [resolve_ffmpeg(), "-h", "filter=subtitles"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if "Unknown filter 'subtitles'" in output:
        raise PipelineError(
            "FFmpeg subtitles filter is unavailable. "
            "On Ubuntu use apt-get install ffmpeg. "
            "On macOS use brew install ffmpeg-full."
        )


def build_subtitle_filter(srt_path: Path) -> str:
    srt_ref = srt_path.as_posix()
    style = (
        "FontSize=22,"
        "PrimaryColour=&H00FFFF&,"
        "OutlineColour=&H000000&,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=90"
    )
    font_path = Path(resolve_subtitle_font())
    fonts_dir = font_path.parent.as_posix().replace(":", r"\:")
    return f"subtitles={srt_ref}:fontsdir={fonts_dir}:force_style='{style}'"


def compose_final_video() -> None:
    video_filter = build_subtitle_filter(CAPTIONS_PATH)

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(BACKGROUND_PATH),
            "-i",
            str(AUDIO_PATH),
            "-vf",
            video_filter,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(FINAL_PATH),
        ],
        "Final video composition",
    )
    logger.info("Final video created at %s (%.2fs)", FINAL_PATH, probe_duration(FINAL_PATH))


def parse_tags(tags_value: str) -> list[str]:
    return [tag.strip() for tag in tags_value.split(",") if tag.strip()][:30]


def build_youtube_client():
    credentials = Credentials(
        None,
        refresh_token=require_env("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=require_env("YT_CLIENT_ID"),
        client_secret=require_env("YT_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return build("youtube", "v3", credentials=credentials)


def upload_to_youtube(script: VideoScript) -> str:
    privacy_status = (
        os.environ.get("YT_PRIVACY_STATUS", DEFAULT_PRIVACY_STATUS).strip().lower()
        or DEFAULT_PRIVACY_STATUS
    )
    if privacy_status not in {"public", "unlisted", "private"}:
        raise PipelineError(f"Invalid YT_PRIVACY_STATUS: {privacy_status}")

    youtube = build_youtube_client()
    body = {
        "snippet": {
            "title": script.video_title,
            "description": script.description,
            "tags": parse_tags(script.tags),
            "categoryId": YOUTUBE_CATEGORY_ID,
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(str(FINAL_PATH), chunksize=8 * 1024 * 1024, resumable=True)

    def _insert() -> dict[str, Any]:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info("YouTube upload progress: %s%%", progress)
        if not response or "id" not in response:
            raise PipelineError("YouTube upload returned an invalid response")
        return response

    try:
        upload_response = retry(_insert, "YouTube video upload", max_attempts=2, base_delay=5.0)
    except HttpError as exc:
        raise PipelineError(f"YouTube upload failed: {exc}") from exc

    video_id = upload_response["id"]
    status = upload_response.get("status", {})
    actual_privacy = status.get("privacyStatus", privacy_status)
    synthetic_flag = status.get("containsSyntheticMedia")
    logger.info(
        "Upload complete: https://www.youtube.com/watch?v=%s | privacy=%s | containsSyntheticMedia=%s",
        video_id,
        actual_privacy,
        synthetic_flag,
    )
    if actual_privacy != privacy_status:
        logger.warning(
            "Requested privacy '%s' but YouTube stored '%s'. "
            "Unverified API projects may be restricted to private uploads.",
            privacy_status,
            actual_privacy,
        )
    if synthetic_flag is not True:
        logger.warning(
            "containsSyntheticMedia was not confirmed as true on the uploaded video resource."
        )
    return video_id


async def run_pipeline(skip_upload: bool = False) -> None:
    ensure_ffmpeg_subtitles_filter()
    reset_work_dir()
    script = generate_script()
    segments, _ = await generate_voiceover(script)
    raw_clips = download_background_clips(segments)
    build_background_video(raw_clips, segments)
    compose_final_video()
    if skip_upload:
        logger.info(
            "Skipping YouTube upload. Final video ready at %s (%.2fs)",
            FINAL_PATH,
            probe_duration(FINAL_PATH),
        )
        return
    video_id = upload_to_youtube(script)
    logger.info("Pipeline finished successfully. Video ID: %s", video_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and upload a daily YouTube Short.")
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Generate the video locally without uploading to YouTube.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    skip_upload = args.skip_upload or os.environ.get("SKIP_YOUTUBE_UPLOAD", "").lower() in {
        "1",
        "true",
        "yes",
    }
    try:
        asyncio.run(run_pipeline(skip_upload=skip_upload))
    except PipelineError as exc:
        logger.error("Pipeline failed: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected pipeline failure: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
