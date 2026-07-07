import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
GITHUB_ENV_PATH = os.environ.get("GITHUB_ENV")

HOUR_TO_SLOT = {
    10: "morning",
    14: "afternoon",
    18: "evening",
}

SLOT_TO_HOUR = {slot: hour for hour, slot in HOUR_TO_SLOT.items()}

CRON_SLOT_MAP: dict[str, dict[str, str]] = {
    "datos_es": {
        "17 8 * * *": "morning",
        "37 8 * * *": "morning",
        "57 8 * * *": "morning",
        "17 9 * * *": "morning",
        "17 12 * * *": "afternoon",
        "37 12 * * *": "afternoon",
        "57 12 * * *": "afternoon",
        "17 13 * * *": "afternoon",
        "17 16 * * *": "evening",
        "37 16 * * *": "evening",
        "57 16 * * *": "evening",
        "17 17 * * *": "evening",
    },
    "whatifvibe": {
        "23 14 * * *": "morning",
        "43 14 * * *": "morning",
        "3 15 * * *": "morning",
        "23 15 * * *": "morning",
        "23 18 * * *": "afternoon",
        "43 18 * * *": "afternoon",
        "3 19 * * *": "afternoon",
        "23 19 * * *": "afternoon",
        "23 22 * * *": "evening",
        "43 22 * * *": "evening",
        "3 23 * * *": "evening",
        "23 23 * * *": "evening",
    },
}


def recent_topics_path() -> Path:
    profile = os.environ.get("CHANNEL_PROFILE", "datos_es").strip() or "datos_es"
    return ROOT / "data" / profile / "recent_topics.json"


def load_recent_topics() -> list[dict]:
    path = recent_topics_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    except json.JSONDecodeError:
        return []
    return []


def slot_already_ran_today(slot: str, today: str) -> bool:
    return any(
        entry.get("date") == today and entry.get("slot") == slot
        for entry in load_recent_topics()
    )


def write_github_env(key: str, value: str) -> None:
    if not GITHUB_ENV_PATH:
        return
    with open(GITHUB_ENV_PATH, "a", encoding="utf-8") as env_file:
        env_file.write(f"{key}={value}\n")


def resolve_slot_from_schedule(profile: str, schedule: str) -> tuple[str, int] | None:
    slot = CRON_SLOT_MAP.get(profile, {}).get(schedule.strip())
    if not slot:
        print(f"Skip: unknown schedule cron '{schedule}' for profile '{profile}'.")
        return None
    return slot, SLOT_TO_HOUR[slot]


def resolve_slot(timezone_name: str, forced_slot: str) -> tuple[str, int] | None:
    if forced_slot in {"morning", "afternoon", "evening"}:
        return forced_slot, SLOT_TO_HOUR[forced_slot]

    now = datetime.now(ZoneInfo(timezone_name))
    slot = HOUR_TO_SLOT.get(now.hour)
    if not slot:
        print(f"Skip: local hour {now.hour} is outside upload windows.")
        return None
    return slot, now.hour


def main() -> None:
    profile = os.environ.get("CHANNEL_PROFILE", "datos_es").strip() or "datos_es"
    timezone_name = os.environ.get("UPLOAD_TIMEZONE", "Europe/Madrid").strip() or "Europe/Madrid"
    forced_slot = os.environ.get("FORCE_UPLOAD_SLOT", "").strip().lower()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()

    event_schedule = os.environ.get("GITHUB_EVENT_SCHEDULE", "").strip()

    if event_name == "schedule" and event_schedule:
        resolved = resolve_slot_from_schedule(profile, event_schedule)
    elif event_name == "workflow_dispatch" and forced_slot:
        resolved = resolve_slot(timezone_name, forced_slot)
    else:
        resolved = resolve_slot(timezone_name, "")

    if not resolved:
        sys.exit(1)

    slot, hour = resolved
    today = datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")

    if slot_already_ran_today(slot, today) and event_name != "workflow_dispatch":
        print(f"Skip: slot '{slot}' already completed for {today} ({profile}).")
        sys.exit(1)

    work_dir = f"work/{profile}/{today}_{slot}"
    print(f"Run approved: profile={profile}, slot={slot}, hour={hour}, work_dir={work_dir}")
    write_github_env("UPLOAD_SLOT", slot)
    write_github_env("WORK_DIR", work_dir)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Gate error: {exc}", file=sys.stderr)
        sys.exit(1)
