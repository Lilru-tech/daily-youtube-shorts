import random
from dataclasses import dataclass
from pathlib import Path

from channel_profiles import SubtitleStyle, subtitle_force_style


@dataclass
class WordEvent:
    text: str
    start: float
    end: float


def _format_ass_time(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    hours = total_cs // 360000
    total_cs %= 360000
    minutes = total_cs // 6000
    total_cs %= 6000
    secs = total_cs // 100
    cs = total_cs % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _chunk_words(words: list[WordEvent]) -> list[tuple[str, float, float]]:
    chunks: list[tuple[str, float, float]] = []
    index = 0
    while index < len(words):
        chunk_size = random.randint(1, 3)
        group = words[index : index + chunk_size]
        text = " ".join(word.text.strip() for word in group if word.text.strip())
        if text:
            chunks.append((text, group[0].start, group[-1].end))
        index += chunk_size
    return chunks


def _style_name(subtitle_style: SubtitleStyle) -> str:
    return "YellowBold" if subtitle_style == "yellow_black" else "WhiteBold"


def _build_ass_header(font_name: str, subtitle_style: SubtitleStyle) -> str:
    style = subtitle_force_style(subtitle_style)
    style_parts = dict(part.split("=", 1) for part in style.split(",") if "=" in part)
    primary = style_parts.get("PrimaryColour", "&HFFFFFF&")
    outline_colour = style_parts.get("OutlineColour", "&H000000&")
    outline = style_parts.get("Outline", "4")
    margin_v = style_parts.get("MarginV", "100")
    style_name = _style_name(subtitle_style)
    return (
        "[Script Info]\n"
        "Title: Generated Captions\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: {style_name},{font_name},26,{primary},&H000000&,{outline_colour},&H64000000&,"
        f"-1,0,0,0,100,100,0,0,1,{outline},0,2,40,40,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def build_ass_captions(
    word_events: list[WordEvent],
    output_path: Path,
    font_name: str,
    subtitle_style: SubtitleStyle,
) -> None:
    if not word_events:
        raise ValueError("word_events must not be empty")

    chunks = _chunk_words(word_events)
    style_name = _style_name(subtitle_style)
    lines = [_build_ass_header(font_name, subtitle_style)]
    for text, start, end in chunks:
        if end <= start:
            end = start + 0.15
        lines.append(
            f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},"
            f"{style_name},,0,0,0,,{_escape_ass_text(text.upper())}\n"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="utf-8")
