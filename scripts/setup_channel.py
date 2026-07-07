import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "create_branding.py"), "--channel", "datos_es", "--update-youtube"],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
