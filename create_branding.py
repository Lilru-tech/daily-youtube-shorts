import argparse
import math
import os
import random
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from channel_profiles import PROFILES, ChannelProfile, load_channel_profile

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

FONT_BOLD = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_HEAVY = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def require_refresh_token(profile: ChannelProfile) -> str:
    value = os.environ.get(profile.refresh_token_env, "").strip()
    if not value and profile.name == "datos_es":
        value = os.environ.get("YT_REFRESH_TOKEN", "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {profile.refresh_token_env}")
    return value


def load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        pixels[0, y] = lerp_color(top, bottom, y / max(height - 1, 1))
    return strip.resize(size, Image.Resampling.BILINEAR)


def radial_glow_overlay(size: tuple[int, int], center: tuple[int, int], color: tuple[int, int, int], radius: int) -> Image.Image:
    width, height = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    glow = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((0, 0, radius * 2 - 1, radius * 2 - 1), fill=(*color, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=radius // 3))
    layer.paste(glow, (center[0] - radius, center[1] - radius), glow)
    return layer


def draw_perspective_grid(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple[int, int, int], alpha: int = 40) -> None:
    horizon = int(height * 0.62)
    vanish_x = width // 2
    line_color = (*color, alpha)
    for i in range(-12, 13):
        x_bottom = vanish_x + i * 140
        draw.line([(vanish_x, horizon), (x_bottom, height)], fill=line_color, width=2)
    for y in range(horizon, height, 48):
        draw.line([(0, y), (width, y)], fill=line_color, width=1)


def draw_corner_brackets(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    color: tuple[int, int, int],
    length: int = 36,
    width: int = 4,
) -> None:
    x1, y1, x2, y2 = box
    draw.line([(x1, y1 + length), (x1, y1), (x1 + length, y1)], fill=color, width=width)
    draw.line([(x2 - length, y1), (x2, y1), (x2, y1 + length)], fill=color, width=width)
    draw.line([(x1, y2 - length), (x1, y2), (x1 + length, y2)], fill=color, width=width)
    draw.line([(x2 - length, y2), (x2, y2), (x2, y2 - length)], fill=color, width=width)


def draw_neon_text(
    base: Image.Image,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    glow: tuple[int, int, int],
    stroke: int = 3,
) -> None:
    rgba = base.convert("RGBA")
    for radius, alpha in ((20, 70), (10, 120), (4, 180)):
        layer = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        layer_draw.text(
            xy,
            text,
            font=font,
            fill=(*glow, alpha),
            stroke_width=stroke + 2,
            stroke_fill=(0, 0, 0, alpha),
        )
        layer = layer.filter(ImageFilter.GaussianBlur(radius=radius))
        rgba = Image.alpha_composite(rgba, layer)
    draw = ImageDraw.Draw(rgba)
    draw.text(xy, text, font=font, fill=(*fill, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    if base.mode == "RGBA":
        base.paste(rgba, (0, 0))
    else:
        base.paste(rgba.convert("RGB"), (0, 0))


def centered_xy(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, canvas_w: int, canvas_h: int) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    return (canvas_w - tw) // 2 - bbox[0], (canvas_h - th) // 2 - bbox[1]


def draw_neural_nodes(draw: ImageDraw.ImageDraw, width: int, height: int, seed: int = 7) -> None:
    rng = random.Random(seed)
    nodes = [(rng.randint(80, width - 80), rng.randint(80, height - 80)) for _ in range(18)]
    for x1, y1 in nodes:
        for x2, y2 in nodes:
            if (x1, y1) >= (x2, y2):
                continue
            if math.hypot(x1 - x2, y1 - y2) < 280:
                draw.line([(x1, y1), (x2, y2)], fill=(120, 80, 200, 35), width=2)
    for x, y in nodes:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 210, 80, 90))


def draw_question_mark_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int) -> None:
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        outline=(0, 230, 255),
        width=8,
    )
    draw.ellipse(
        (cx - radius + 18, cy - radius + 18, cx + radius - 18, cy + radius - 18),
        outline=(140, 50, 255),
        width=3,
    )
    font = load_font(FONT_HEAVY, int(radius * 1.35))
    bbox = draw.textbbox((0, 0), "?", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1] - 8), "?", font=font, fill=(0, 245, 255))


def draw_brain_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
    r = size // 2
    left = (cx - r - 8, cy - r + 10, cx - 8, cy + r)
    right = (cx + 8, cy - r + 10, cx + r + 8, cy + r)
    draw.chord(left, start=90, end=270, fill=(70, 35, 120), outline=(255, 200, 70), width=5)
    draw.chord(right, start=270, end=90, fill=(70, 35, 120), outline=(255, 200, 70), width=5)
    draw.line([(cx, cy - r + 8), (cx, cy + r - 8)], fill=(255, 200, 70), width=4)
    for offset in (-28, 0, 28):
        draw.arc(
            (cx - r // 2 + offset, cy - r // 3, cx + r // 2 + offset, cy + r // 3),
            start=200,
            end=340,
            fill=(255, 210, 90),
            width=3,
        )


def apply_safe_vignette(image: Image.Image, strength: float = 0.7) -> Image.Image:
    width, height = image.size
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    pad_x = int(width * 0.08)
    pad_y = int(height * 0.12)
    mask_draw.rectangle((pad_x, pad_y, width - pad_x, height - pad_y), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=min(width, height) // 8))
    dark = Image.new("RGB", image.size, (0, 0, 0))
    return Image.composite(image, dark, mask)


def generate_whatifvibe_assets(profile: ChannelProfile) -> tuple[Path, Path]:
    branding_dir = profile.branding_dir
    profile_path = branding_dir / "profile_800x800.png"
    banner_path = branding_dir / "banner_2560x1440.png"

    cyan = (0, 245, 255)
    purple = (155, 60, 255)
    violet_dark = (12, 8, 28)

    profile_img = vertical_gradient((800, 800), (18, 10, 42), (6, 6, 14)).convert("RGBA")
    profile_draw = ImageDraw.Draw(profile_img)
    draw_perspective_grid(profile_draw, 800, 800, cyan, alpha=28)
    profile_img = Image.alpha_composite(
        profile_img,
        radial_glow_overlay((800, 800), (400, 380), purple, 280),
    )
    profile_draw = ImageDraw.Draw(profile_img)
    draw_corner_brackets(profile_draw, (48, 48, 752, 752), cyan, length=54, width=5)
    draw_question_mark_icon(profile_draw, 400, 360, 165)
    tag_font = load_font(FONT_BOLD, 64)
    vibe_xy = ((800 - 140) // 2, 560)
    draw_neon_text(profile_img, "VIBE", vibe_xy, tag_font, purple, cyan, stroke=3)

    banner = vertical_gradient((2560, 1440), (14, 8, 36), (4, 4, 12)).convert("RGBA")
    banner_draw = ImageDraw.Draw(banner)
    draw_perspective_grid(banner_draw, 2560, 1440, cyan, alpha=32)
    banner = Image.alpha_composite(banner, radial_glow_overlay((2560, 1440), (1280, 520), purple, 520))
    banner = Image.alpha_composite(banner, radial_glow_overlay((2560, 1440), (1280, 720), cyan, 360))
    banner_draw = ImageDraw.Draw(banner)

    safe_x, safe_y, safe_w, safe_h = 507, 508, 1546, 423
    draw_corner_brackets(banner_draw, (safe_x, safe_y, safe_x + safe_w, safe_y + safe_h), cyan, length=70, width=4)

    title_font = load_font(FONT_HEAVY, 148)
    subtitle_font = load_font(FONT_BOLD, 54)
    title = "WhatIfVibe"
    subtitle = "Daily Mind-Bending Questions"

    title_bbox = banner_draw.textbbox((0, 0), title, font=title_font)
    subtitle_bbox = banner_draw.textbbox((0, 0), subtitle, font=subtitle_font)
    title_h = title_bbox[3] - title_bbox[1]
    subtitle_h = subtitle_bbox[3] - subtitle_bbox[1]
    gap = 28
    block_h = title_h + gap + subtitle_h + 16
    center_y = safe_y + safe_h // 2
    title_xy = (
        (2560 - (title_bbox[2] - title_bbox[0])) // 2 - title_bbox[0],
        center_y - block_h // 2 - title_bbox[1],
    )
    subtitle_xy = (
        (2560 - (subtitle_bbox[2] - subtitle_bbox[0])) // 2 - subtitle_bbox[0],
        title_xy[1] + title_h + gap,
    )
    draw_neon_text(banner, title, title_xy, title_font, cyan, purple, stroke=5)
    banner_draw = ImageDraw.Draw(banner)
    pill_w = subtitle_bbox[2] - subtitle_bbox[0] + 80
    pill_h = subtitle_h + 28
    pill_x = subtitle_xy[0] + (subtitle_bbox[0] - subtitle_bbox[0]) - 40
    pill_y = subtitle_xy[1] - 12
    banner_draw.rounded_rectangle(
        (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
        radius=24,
        outline=(*cyan, 180),
        width=2,
        fill=(20, 12, 40, 160),
    )
    banner_draw.text(subtitle_xy, subtitle, font=subtitle_font, fill=(245, 245, 255))

    accent_y = subtitle_xy[1] + subtitle_h + 26
    banner_draw.line([(safe_x + 180, accent_y), (safe_x + safe_w - 180, accent_y)], fill=(*purple, 200), width=3)

    banner = apply_safe_vignette(banner.convert("RGB"))

    branding_dir.mkdir(parents=True, exist_ok=True)
    profile_img.convert("RGB").save(profile_path, format="PNG", optimize=True)
    banner.save(banner_path, format="PNG", optimize=True)
    return profile_path, banner_path


def generate_datos_es_assets(profile: ChannelProfile) -> tuple[Path, Path]:
    branding_dir = profile.branding_dir
    profile_path = branding_dir / "profile_800x800.png"
    banner_path = branding_dir / "banner_2560x1440.png"

    gold = (255, 205, 70)
    purple = (110, 55, 175)
    deep = (22, 12, 48)

    profile_img = vertical_gradient((800, 800), (48, 22, 88), (16, 8, 32)).convert("RGBA")
    profile_draw = ImageDraw.Draw(profile_img)
    draw_neural_nodes(profile_draw, 800, 800)
    profile_img = Image.alpha_composite(
        profile_img,
        radial_glow_overlay((800, 800), (400, 400), (160, 90, 220), 300),
    )
    profile_draw = ImageDraw.Draw(profile_img)
    draw_corner_brackets(profile_draw, (52, 52, 748, 748), gold, length=50, width=4)
    draw_brain_icon(profile_draw, 400, 320, 190)
    font = load_font(FONT_HEAVY, 76)
    datos_xy = centered_xy(profile_draw, "DATOS", font, 800, 800)
    draw_neon_text(profile_img, "DATOS", (datos_xy[0], 560), font, gold, purple, stroke=3)

    banner = vertical_gradient((2560, 1440), (42, 18, 78), (12, 6, 28)).convert("RGBA")
    banner_draw = ImageDraw.Draw(banner)
    draw_neural_nodes(banner_draw, 2560, 1440, seed=19)
    banner = Image.alpha_composite(banner, radial_glow_overlay((2560, 1440), (1280, 620), (130, 70, 200), 500))
    banner_draw = ImageDraw.Draw(banner)

    safe_x, safe_y, safe_w, safe_h = 507, 508, 1546, 423
    draw_corner_brackets(banner_draw, (safe_x, safe_y, safe_x + safe_w, safe_y + safe_h), gold, length=70, width=4)

    title_font = load_font(FONT_HEAVY, 118)
    subtitle_font = load_font(FONT_BOLD, 50)
    title = "Datos Interesantes"
    subtitle = "Psicologia, cerebro y curiosidades cada dia"

    title_bbox = banner_draw.textbbox((0, 0), title, font=title_font)
    subtitle_bbox = banner_draw.textbbox((0, 0), subtitle, font=subtitle_font)
    title_h = title_bbox[3] - title_bbox[1]
    subtitle_h = subtitle_bbox[3] - subtitle_bbox[1]
    gap = 26
    block_h = title_h + gap + subtitle_h + 12
    center_y = safe_y + safe_h // 2
    title_xy = (
        (2560 - (title_bbox[2] - title_bbox[0])) // 2 - title_bbox[0],
        center_y - block_h // 2 - title_bbox[1],
    )
    subtitle_xy = (
        (2560 - (subtitle_bbox[2] - subtitle_bbox[0])) // 2 - subtitle_bbox[0],
        title_xy[1] + title_h + gap,
    )
    draw_neon_text(banner, title, title_xy, title_font, gold, purple, stroke=5)
    banner_draw = ImageDraw.Draw(banner)
    banner_draw.text(subtitle_xy, subtitle, font=subtitle_font, fill=(240, 235, 255), stroke_width=2, stroke_fill=(0, 0, 0))

    icon_x = title_xy[0] - 120
    if icon_x > 80:
        draw_brain_icon(banner_draw, icon_x, center_y, 110)

    banner = apply_safe_vignette(banner.convert("RGB"))

    branding_dir.mkdir(parents=True, exist_ok=True)
    profile_img.convert("RGB").save(profile_path, format="PNG", optimize=True)
    banner.save(banner_path, format="PNG", optimize=True)
    return profile_path, banner_path


def generate_assets(profile: ChannelProfile) -> tuple[Path, Path]:
    if profile.name == "whatifvibe":
        return generate_whatifvibe_assets(profile)
    return generate_datos_es_assets(profile)


def build_youtube_client(profile: ChannelProfile):
    credentials = Credentials(
        None,
        refresh_token=require_refresh_token(profile),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=require_env("YT_CLIENT_ID"),
        client_secret=require_env("YT_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=credentials)


def update_channel_branding(youtube, profile: ChannelProfile) -> None:
    channel_id = profile.channel_id
    current = youtube.channels().list(part="brandingSettings", id=channel_id).execute()
    branding = current["items"][0].get("brandingSettings", {})
    channel_branding = branding.get("channel", {})
    channel_branding["description"] = profile.channel_description
    channel_branding["keywords"] = profile.channel_keywords
    channel_branding["defaultLanguage"] = profile.language
    youtube.channels().update(
        part="brandingSettings",
        body={
            "id": channel_id,
            "brandingSettings": {"channel": channel_branding},
        },
    ).execute()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate channel branding assets.")
    parser.add_argument(
        "--channel",
        choices=sorted(PROFILES.keys()),
        required=True,
        help="Channel profile to brand.",
    )
    parser.add_argument(
        "--update-youtube",
        action="store_true",
        help="Push channel description and keywords via YouTube Data API.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = load_channel_profile(args.channel)
    profile_path, banner_path = generate_assets(profile)
    print(f"Profile picture saved: {profile_path}")
    print(f"Channel banner saved:  {banner_path}")

    if args.update_youtube:
        try:
            youtube = build_youtube_client(profile)
            update_channel_branding(youtube, profile)
            print("YouTube channel description and keywords updated successfully.")
        except (RuntimeError, HttpError) as exc:
            print(f"\nYouTube API update failed: {exc}", file=sys.stderr)
            print("Assets were still generated locally.", file=sys.stderr)
            sys.exit(1)

    print("\nUpload these assets manually in YouTube Studio -> Customization:")
    print(f"  Profile picture: {profile_path}")
    print(f"  Channel banner:  {banner_path}")


if __name__ == "__main__":
    main()
