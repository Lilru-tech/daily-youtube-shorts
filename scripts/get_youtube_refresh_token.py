import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = Path("client_secret.json")


def main() -> None:
    if not CLIENT_SECRET_FILE.exists():
        print(
            "Download your OAuth client JSON from Google Cloud Console and save it as "
            f"'{CLIENT_SECRET_FILE}' in the project root.",
            file=sys.stderr,
        )
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    credentials = flow.run_local_server(port=0)

    output = {
        "YT_CLIENT_ID": credentials.client_id,
        "YT_CLIENT_SECRET": credentials.client_secret,
        "YT_REFRESH_TOKEN": credentials.refresh_token,
    }

    print("\nAdd these values as GitHub Secrets:\n")
    for key, value in output.items():
        print(f"{key}={value}")

    secrets_path = Path("youtube_secrets.json")
    secrets_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nAlso saved to {secrets_path} (do not commit this file).")


if __name__ == "__main__":
    main()
