import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_SECRET = ROOT / "client_secret.json"
GET_TOKEN = ROOT / "get_token.py"
CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials/oauthclient?project=_"


def main() -> None:
    print("YouTube OAuth setup")
    print("=" * 50)

    if CLIENT_SECRET.exists():
        print(f"Found {CLIENT_SECRET.name} — running get_token.py ...\n")
        subprocess.run([sys.executable, str(GET_TOKEN)], cwd=ROOT, check=True)
        return

    print("No client_secret.json found.")
    print("\nOpening Google Cloud Console in your browser...")
    print("Create credentials with these settings:")
    print("  - Type: Desktop app (Aplicación de escritorio)")
    print("  - Download JSON")
    print(f"  - Save as: {CLIENT_SECRET}\n")

    webbrowser.open(CREDENTIALS_URL)

    print("Waiting for client_secret.json (up to 10 minutes)...")
    for _ in range(600):
        if CLIENT_SECRET.exists():
            print(f"\nDetected {CLIENT_SECRET.name} — starting OAuth flow...\n")
            subprocess.run([sys.executable, str(GET_TOKEN)], cwd=ROOT, check=True)
            return
        time.sleep(1)

    print("\nTimeout: client_secret.json was not created.")
    print("Download the OAuth JSON from Google Cloud and save it as client_secret.json")
    sys.exit(1)


if __name__ == "__main__":
    main()
