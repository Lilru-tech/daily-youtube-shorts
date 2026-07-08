import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT", "")

PROFILE_TIMEZONES = {
    "datos_es": "Europe/Madrid",
    "whatifvibe": "America/New_York",
}

VALID_SLOTS = {"morning", "afternoon", "evening"}


def write_output(key: str, value: str) -> None:
    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a", encoding="utf-8") as handle:
            handle.write(f"{key}={value}\n")


def slot_completed_today(profile: str, slot: str, today: str) -> bool:
    path = ROOT / "data" / profile / "recent_topics.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, list):
        return False
    return any(
        isinstance(entry, dict) and entry.get("date") == today and entry.get("slot") == slot
        for entry in payload
    )


def main() -> None:
    profile = os.environ.get("CHANNEL_PROFILE", "").strip()
    slot = os.environ.get("WATCHDOG_SLOT", "").strip().lower()

    if profile not in PROFILE_TIMEZONES:
        print(f"Invalid channel profile: {profile}", file=sys.stderr)
        sys.exit(1)
    if slot not in VALID_SLOTS:
        print(f"Invalid slot: {slot}", file=sys.stderr)
        sys.exit(1)

    timezone_name = PROFILE_TIMEZONES[profile]
    today = datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")

    if slot_completed_today(profile, slot, today):
        print(f"Skip: {profile} slot '{slot}' already completed for {today}.")
        write_output("needs_trigger", "false")
        sys.exit(0)

    print(f"Trigger needed: {profile} slot '{slot}' missing for {today}.")
    write_output("needs_trigger", "true")
    sys.exit(0)


if __name__ == "__main__":
    main()
