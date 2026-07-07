import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

ROOT_DIR = Path(__file__).resolve().parent

MAX_TITLE_CHARS = 55
MIN_SCRIPT_CHARS = 300
MAX_SCRIPT_CHARS = 900

SubtitleStyle = Literal["yellow_black", "white_yellow"]
ThumbnailStyle = Literal["purple_yellow", "cyberpunk_cyan"]
ProfileName = Literal["datos_es", "whatifvibe"]


ContentType = Literal["facts", "story"]


@dataclass
class ChannelProfile:
    name: ProfileName
    display_name: str
    youtube_handle: str
    channel_id: str
    timezone: str
    language: str
    voice: str
    voice_fallbacks: list[str]
    gemini_model: str
    gemini_fallback_models: list[str]
    fallback_keywords: list[str]
    hook_duration_seconds: float
    hook_fontsize: int
    hook_borderw: int
    subtitle_style: SubtitleStyle
    thumbnail_style: ThumbnailStyle
    require_title_emoji: bool
    refresh_token_env: str
    channel_id_env: str
    channel_description: str
    channel_keywords: str
    data_dir: Path
    branding_dir: Path
    build_prompt: Callable[[list[str], str], str]
    validate_metadata: Callable[[str, str, list[str]], None]


def has_emoji(text: str) -> bool:
    return bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text))


def looks_spanish(text: str) -> bool:
    lowered = text.lower()
    spanish_markers = (
        "qué",
        "cerebro",
        "tu ",
        "tú",
        "mente",
        "datos",
        "español",
        "¿",
        "cómo",
        "por qué",
        "estás",
        "está",
        "nuestro",
        "ningún",
        "también",
    )
    if any(marker in lowered for marker in spanish_markers):
        return True
    return bool(re.search(r"[áéíóúüñ]", lowered))


def looks_english(text: str) -> bool:
    lowered = f" {text.lower()} "
    english_markers = (
        " the ",
        " your ",
        " brain",
        " you ",
        " and ",
        " with ",
        " this ",
        " that ",
        " what ",
        " how ",
    )
    return any(marker in lowered for marker in english_markers)


def build_datos_es_prompt(recent_titles: list[str], content_type: str = "facts") -> str:
    recent_block = ""
    if recent_titles:
        joined = "\n".join(f"- {title}" for title in recent_titles)
        recent_block = f"""
No repitas estos temas ni titulos recientes:
{joined}
"""

    if content_type == "story":
        content_block = """
Modo de contenido: HISTORIA CORTA DE SUSPENSO (30%).
Escribe una micro-historia inmersiva en primera persona sobre un encuentro inquietante o un dilema psicologico.
Mantén alta tension, ritmo cinematografico y un giro final perturbador.
"""
    else:
        content_block = """
Modo de contenido: DATOS Y HECHOS PSICOLOGICOS (70%).
Escribe datos asombrosos e insights psicologicos con escalada, giro y cierre con cliffhanger.
Rota subtemas: trucos psicologicos, datos del cerebro, sesgos cognitivos, habitos, emociones, percepcion.
"""

    return f"""
Eres un guionista viral de YouTube Shorts especializado en retencion maxima.

Escribe un guion en espanol (Espana, neutro y natural) para un Short vertical de 40-50 segundos.
Usa 6-8 lineas cortas habladas. Cada linea debe ser una frase impactante.
{content_block}
REGLA BRUTAL DE GANCHO: La primera linea (lines[0].text) DEBE ser un gancho psicologico agresivo.
Prohibido saludos, intros conversacionales o relleno tipo "hola", "sabias que", "atencion".
Debe enganchar en menos de 2 segundos de lectura.

Devuelve SOLO JSON valido con este esquema exacto:
{{
  "video_title": "🧠 Tu cerebro te engana asi",
  "hook_text": "TU CEREBRO ENGAÑA",
  "description": "Descripcion de 2-3 frases con 2-3 hashtags relevantes",
  "tags": "psicologia,cerebro,datos,curiosos,shorts",
  "lines": [
    {{"text": "Primera linea hablada.", "search_keywords": "cerebro neuronas"}},
    {{"text": "Segunda linea hablada.", "search_keywords": "mente pensando"}}
  ]
}}

Reglas de titulo viral:
- Maximo 50 caracteres y 5-6 palabras.
- Empieza con 1 emoji.
- Usa curiosidad o emocion, no expliques el video.
- Formulas validas: "Tu cerebro...", "Nadie te dice...", "Esto explica por que...", "La trampa mental...", "Haces esto sin darte cuenta".

Reglas de hook_text:
- 1-4 palabras en MAYUSCULAS.
- Debe resumir el gancho visual del primer frame.

Reglas generales:
- Todo en espanol. Prohibido ingles.
- Sin markdown, sin comentarios, sin claves extra.
- Texto hablado total entre 300 y 900 caracteres.
{recent_block}
""".strip()


def validate_datos_es_metadata(title: str, description: str, line_texts: list[str]) -> None:
    if not has_emoji(title):
        raise ValueError("video_title must include at least one emoji")
    if looks_english(title) or looks_english(description):
        raise ValueError("Gemini returned English metadata; Spanish content required")
    for index, text in enumerate(line_texts):
        if looks_english(text):
            raise ValueError(f"Line {index} is not in Spanish")


def build_whatifvibe_prompt(recent_titles: list[str], content_type: str = "facts") -> str:
    recent_block = ""
    if recent_titles:
        joined = "\n".join(f"- {title}" for title in recent_titles)
        recent_block = f"""
Do not repeat these recent topics or titles:
{joined}
"""

    if content_type == "story":
        content_block = """
Content mode: IMMERSIVE SHORT STORY (30%).
Write a first-person creepy encounter or psychological dilemma with high suspense.
Keep cinematic pacing, visceral tension, and a disturbing final turn.
"""
    else:
        content_block = """
Content mode: WHAT IF FACTS (70%).
Write mind-bending "What happens if..." science and hypothetical scenarios.
Rotate sub-niches: human body limits, space/cosmic disasters, physics paradoxes, survival scenarios, psychology tricks, science anomalies.
"""

    return f"""
You are a viral YouTube Shorts scriptwriter for the US channel "WhatIfVibe".

Write a script in strict American English for a 40-50 second vertical Short.
Use 6-8 short spoken lines. Each line must hit hard and keep viewers watching.
{content_block}
BRUTAL HOOK RULE: Line 1 (lines[0].text) MUST be an aggressive psychological hook.
No greetings, no conversational intros, no filler like "hey guys" or "did you know".
It must grab attention within 2 seconds of reading.

Return ONLY valid JSON with this exact schema:
{{
  "video_title": "What If You Stop Blinking for 24 Hours?",
  "hook_text": "STOP BLINKING",
  "description": "2-3 sentences with 2-3 hashtags like #whatif #science #shorts",
  "tags": "what if,science,shorts,mind blowing,hypothetical",
  "lines": [
    {{"text": "What happens if you stopped blinking for 24 hours?", "search_keywords": "human eye close"}},
    {{"text": "Within minutes, your eyes would dry out and turn bloodshot.", "search_keywords": "red eye medical"}}
  ]
}}

Viral title rules:
- Max 50 characters, curiosity-driven.
- Emoji optional but encouraged (e.g. 🤯).
- Valid formulas: "What If You...", "What Happens If Earth...", "What If a Black Hole...".

hook_text rules:
- 1-4 words in UPPERCASE.
- Must summarize the visual hook of the first frame.

General rules:
- Strict American English only. No Spanish. Use US spellings.
- search_keywords: English, 2-4 words, Pexels-friendly nouns (e.g. "planet space", "brain scan").
- Pacing: escalation → twist → cliffhanger CTA at the end.
- No markdown, no comments, no extra keys.
- Total spoken text between 300 and 900 characters.
{recent_block}
""".strip()


def validate_whatifvibe_metadata(title: str, description: str, line_texts: list[str]) -> None:
    if looks_spanish(title) or looks_spanish(description):
        raise ValueError("Gemini returned Spanish metadata; American English required")
    for index, text in enumerate(line_texts):
        if looks_spanish(text):
            raise ValueError(f"Line {index} is not in American English")


def _resolve_channel_id(env_name: str, default: str = "") -> str:
    return os.environ.get(env_name, default).strip() or default


DATOS_ES = ChannelProfile(
    name="datos_es",
    display_name="Datos interesantes Español",
    youtube_handle="@Datosinteresantes-v7",
    channel_id="UCw272LClsZaAXko-DieXKKA",
    timezone="Europe/Madrid",
    language="es",
    voice="es-ES-AlvaroNeural",
    voice_fallbacks=[],
    gemini_model="gemini-2.5-flash-lite",
    gemini_fallback_models=[
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
    ],
    fallback_keywords=["paisaje naturaleza", "cerebro pensando", "ciudad noche"],
    hook_duration_seconds=2.5,
    hook_fontsize=84,
    hook_borderw=5,
    subtitle_style="yellow_black",
    thumbnail_style="purple_yellow",
    require_title_emoji=True,
    refresh_token_env="YT_REFRESH_TOKEN_DATOS_ES",
    channel_id_env="YT_TARGET_CHANNEL_ID_DATOS_ES",
    channel_description=(
        "Shorts diarios con datos asombrosos e insights psicológicos que te harán ver el mundo de otra forma.\n\n"
        "Cada video explora curiosidades sobre la mente humana, el comportamiento y hechos sorprendentes "
        "explicados de forma clara y directa.\n\n"
        "Nuevo Short cada día. Suscríbete para no perderte ninguno.\n\n"
        "#datoscuriosos #psicologia #shorts #mentehumana #hechosinteresantes"
    ),
    channel_keywords=(
        "datos curiosos, psicologia, shorts, cerebro, mente humana, hechos interesantes, "
        "insights psicologicos, neurociencia, comportamiento, aprendizaje"
    ),
    data_dir=ROOT_DIR / "data" / "datos_es",
    branding_dir=ROOT_DIR / "branding" / "datos_es",
    build_prompt=build_datos_es_prompt,
    validate_metadata=validate_datos_es_metadata,
)

WHATIFVIBE = ChannelProfile(
    name="whatifvibe",
    display_name="WhatIfVibe",
    youtube_handle="@WhatIfVibe-m5k",
    channel_id="",
    timezone="America/New_York",
    language="en",
    voice="en-US-ChristopherNeural",
    voice_fallbacks=["en-US-EricNeural"],
    gemini_model="gemini-2.5-flash-lite",
    gemini_fallback_models=[
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
    ],
    fallback_keywords=["space galaxy", "human body", "city night", "science lab", "ocean deep"],
    hook_duration_seconds=2.0,
    hook_fontsize=88,
    hook_borderw=6,
    subtitle_style="white_yellow",
    thumbnail_style="cyberpunk_cyan",
    require_title_emoji=False,
    refresh_token_env="YT_REFRESH_TOKEN_WHATIFVIBE",
    channel_id_env="YT_TARGET_CHANNEL_ID_WHATIFVIBE",
    channel_description=(
        "Welcome to WhatIfVibe. We explore the world's most mind-bending "
        "'What If' scenarios, science anomalies, and psychological mysteries. "
        "New Short every day."
    ),
    channel_keywords=(
        "what if, what happens if, science, hypothetical, mind blowing, "
        "shorts, psychology, space, facts, curiosity"
    ),
    data_dir=ROOT_DIR / "data" / "whatifvibe",
    branding_dir=ROOT_DIR / "branding" / "whatifvibe",
    build_prompt=build_whatifvibe_prompt,
    validate_metadata=validate_whatifvibe_metadata,
)

PROFILES: dict[str, ChannelProfile] = {
    "datos_es": DATOS_ES,
    "whatifvibe": WHATIFVIBE,
}


def load_channel_profile(name: str) -> ChannelProfile:
    key = name.strip().lower()
    if key not in PROFILES:
        valid = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown channel profile '{name}'. Valid profiles: {valid}")
    profile = PROFILES[key]
    resolved_id = _resolve_channel_id(profile.channel_id_env, profile.channel_id)
    if not resolved_id:
        raise ValueError(
            f"Channel ID for '{profile.name}' is not set. "
            f"Set environment variable {profile.channel_id_env}."
        )
    return ChannelProfile(
        **{**profile.__dict__, "channel_id": resolved_id}
    )


def resolve_profile_name() -> str:
    cli_channel = os.environ.get("_CLI_CHANNEL_PROFILE", "").strip()
    if cli_channel:
        return cli_channel
    env_channel = os.environ.get("CHANNEL_PROFILE", "").strip()
    if env_channel:
        return env_channel
    raise ValueError(
        "Channel profile is required. Use --channel datos_es|whatifvibe "
        "or set CHANNEL_PROFILE."
    )


def get_oauth_instructions(profile: ChannelProfile) -> str:
    if profile.name == "datos_es":
        return (
            f"1. Open https://www.youtube.com/channel/{profile.channel_id}\n"
            f"2. Make sure you are on '{profile.display_name}' ({profile.youtube_handle})\n"
            "   (profile icon top-right -> Switch account/channel)\n"
            "3. Then authorize in the browser that opens"
        )
    return (
        f"1. Open YouTube Studio for {profile.display_name} ({profile.youtube_handle})\n"
        f"2. Make sure you are on '{profile.display_name}'\n"
        "   (profile icon top-right -> Switch account/channel)\n"
        "3. Then authorize in the browser that opens"
    )


def subtitle_force_style(style: SubtitleStyle) -> str:
    if style == "yellow_black":
        return (
            "FontSize=22,"
            "PrimaryColour=&H00FFFF&,"
            "OutlineColour=&H000000&,"
            "BorderStyle=1,"
            "Outline=3,"
            "Shadow=0,"
            "Alignment=2,"
            "MarginV=90"
        )
    return (
        "FontSize=26,"
        "PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H00FFFF&,"
        "BorderStyle=1,"
        "Outline=4,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=100"
    )
