import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from main import require_env

VIDEO_ID = "hG6zPOINoX0"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def build_manage_client():
    credentials = Credentials(
        None,
        refresh_token=require_env("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=require_env("YT_CLIENT_ID"),
        client_secret=require_env("YT_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=credentials)


def main() -> None:
    youtube = build_manage_client()
    try:
        youtube.videos().delete(id=VIDEO_ID).execute()
        print(f"Deleted video: https://www.youtube.com/watch?v={VIDEO_ID}")
    except HttpError as exc:
        print(f"Delete failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
