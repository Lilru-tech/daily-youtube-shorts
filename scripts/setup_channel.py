import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from main import require_env

TARGET_CHANNEL_ID = "UCw272LClsZaAXko-DieXKKA"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CHANNEL_DESCRIPTION = """Shorts diarios con datos asombrosos e insights psicológicos que te harán ver el mundo de otra forma.

Cada video explora curiosidades sobre la mente humana, el comportamiento y hechos sorprendentes explicados de forma clara y directa.

Nuevo Short cada día. Suscríbete para no perderte ninguno.

#datoscuriosos #psicologia #shorts #mentehumana #hechosinteresantes"""

CHANNEL_KEYWORDS = (
    "datos curiosos, psicologia, shorts, cerebro, mente humana, hechos interesantes, "
    "insights psicologicos, neurociencia, comportamiento, aprendizaje"
)


def build_client():
    credentials = Credentials(
        None,
        refresh_token=require_env("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=require_env("YT_CLIENT_ID"),
        client_secret=require_env("YT_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=credentials)


def get_authenticated_channel_id(youtube) -> str:
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])
    if not items:
        raise RuntimeError("No channel found for this token")
    channel_id = items[0]["id"]
    title = items[0]["snippet"]["title"]
    print(f"Authenticated channel: {title} ({channel_id})")
    return channel_id


def main() -> None:
    youtube = build_client()
    channel_id = get_authenticated_channel_id(youtube)

    if channel_id != TARGET_CHANNEL_ID:
        print(
            f"\nERROR: Token is for {channel_id}, not {TARGET_CHANNEL_ID}.\n"
            "Switch to 'Datos interesantes Español' in YouTube, then run get_token.py again.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    current = youtube.channels().list(part="brandingSettings", id=channel_id).execute()
    branding = current["items"][0].get("brandingSettings", {})
    channel_branding = branding.get("channel", {})

    channel_branding["description"] = CHANNEL_DESCRIPTION
    channel_branding["keywords"] = CHANNEL_KEYWORDS
    channel_branding["defaultLanguage"] = "es"

    youtube.channels().update(
        part="brandingSettings",
        body={
            "id": channel_id,
            "brandingSettings": {
                "channel": channel_branding,
            },
        },
    ).execute()

    print("Channel branding updated successfully.")
    print("Profile picture and banner must be uploaded manually in YouTube Studio.")


if __name__ == "__main__":
    main()
