"""Configurable time windows for silent social-feed posts."""

import json
from datetime import datetime, time
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


CONFIG_FILE = Path("config/silent_times.json")
DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _load_config() -> dict:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        return config if isinstance(config, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _parse_time(value: object) -> Optional[time]:
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _day_matches(days: object, weekday: int) -> bool:
    if not isinstance(days, list):
        return False
    normalized_days = {str(day).lower() for day in days}
    if "everyday" in normalized_days or "daily" in normalized_days:
        return True
    return any(DAY_NAMES.get(day) == weekday for day in normalized_days)


def _window_matches(window: dict, current: datetime) -> bool:
    start = _parse_time(window.get("start"))
    end = _parse_time(window.get("end"))
    if start is None or end is None:
        return False

    current_time = current.time()
    if start < end:
        return _day_matches(window.get("days"), current.weekday()) and start <= current_time < end
    if start == end:
        return _day_matches(window.get("days"), current.weekday())

    if current_time >= start:
        return _day_matches(window.get("days"), current.weekday())
    previous_weekday = (current.weekday() - 1) % 7
    return current_time < end and _day_matches(window.get("days"), previous_weekday)


def silent_prefix(now: Optional[datetime] = None) -> str:
    """Return the configured silent prefix when the current time is covered."""
    config = _load_config()
    if not config.get("enabled", True):
        return ""
    prefix = str(config.get("prefix", "@silent")).strip()
    if not prefix or ZoneInfo is None:
        return ""

    windows = config.get("windows", [])
    if not isinstance(windows, list):
        return ""

    for window in windows:
        if not isinstance(window, dict):
            continue
        try:
            timezone = window.get("timezone", config.get("default_timezone", "UTC"))
            current = (now or datetime.now(ZoneInfo(timezone))).astimezone(ZoneInfo(timezone))
            if _window_matches(window, current):
                return prefix
        except Exception:
            continue
    return ""


def format_silent_post(content: str, now: Optional[datetime] = None) -> str:
    """Prefix content for Discord when the configured silent window is active."""
    prefix = silent_prefix(now)
    return f"{prefix} {content}" if prefix else content