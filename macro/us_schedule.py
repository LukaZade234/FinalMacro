"""Local-time window for scheduled ``$us`` drains.

Mudae dailies are UTC; this window is the machine's local clock, so a 04:00–06:00
slot is 4–6am on the computer running the app.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

_HHMM_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")


def local_now(now: dt.datetime | None = None) -> dt.datetime:
    """Timezone-aware now. A passed-in aware datetime is kept as-is (that clock
    *is* local for the caller); naive values get the host zone.
    """
    if now is None:
        return dt.datetime.now().astimezone()
    if now.tzinfo is None:
        return now.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return now


def normalize_hhmm(value: Any, default: str = "04:00") -> str:
    """Accept ``4``, ``4:00``, or ``04:00`` and return ``HH:MM``."""
    text = str(value or "").strip()
    match = _HHMM_RE.match(text)
    if not match:
        return default
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return default
    return f"{hour:02d}:{minute:02d}"


def hhmm_to_minutes(hhmm: str) -> int:
    normalized = normalize_hhmm(hhmm)
    hour, minute = normalized.split(":")
    return int(hour) * 60 + int(minute)


def minutes_since_midnight(now: dt.datetime) -> int:
    local = local_now(now)
    return local.hour * 60 + local.minute


def in_local_window(
    start_hhmm: str,
    end_hhmm: str,
    *,
    now: dt.datetime | None = None,
) -> bool:
    """True when local time is in ``[start, end)``. ``end < start`` wraps midnight."""
    start_m = hhmm_to_minutes(start_hhmm)
    end_m = hhmm_to_minutes(end_hhmm)
    current = minutes_since_midnight(local_now(now))
    if start_m == end_m:
        return True
    if start_m < end_m:
        return start_m <= current < end_m
    return current >= start_m or current < end_m


def _next_local_hhmm(now: dt.datetime, minutes: int) -> dt.datetime:
    local = local_now(now)
    candidate = local.replace(
        hour=minutes // 60,
        minute=minutes % 60,
        second=0,
        microsecond=0,
    )
    if candidate <= local:
        candidate += dt.timedelta(days=1)
    return candidate


def seconds_until_window_start(
    start_hhmm: str,
    end_hhmm: str,
    *,
    now: dt.datetime | None = None,
) -> float:
    """``0`` when already inside the window."""
    if in_local_window(start_hhmm, end_hhmm, now=now):
        return 0.0
    start_at = _next_local_hhmm(local_now(now), hhmm_to_minutes(start_hhmm))
    return max(0.0, (start_at - local_now(now)).total_seconds())


def seconds_until_window_end(
    start_hhmm: str,
    end_hhmm: str,
    *,
    now: dt.datetime | None = None,
) -> float | None:
    """``None`` when outside the window."""
    if not in_local_window(start_hhmm, end_hhmm, now=now):
        return None
    end_at = _next_local_hhmm(local_now(now), hhmm_to_minutes(end_hhmm))
    return max(0.0, (end_at - local_now(now)).total_seconds())


US_SCHEDULE_KEY = "us_schedule"


def containing_window_start(
    start_hhmm: str,
    end_hhmm: str,
    *,
    now: dt.datetime | None = None,
) -> dt.datetime | None:
    """Local start of the window that contains ``now``, or ``None`` if outside."""
    if not in_local_window(start_hhmm, end_hhmm, now=now):
        return None
    local = local_now(now)
    start_m = hhmm_to_minutes(start_hhmm)
    end_m = hhmm_to_minutes(end_hhmm)
    if start_m == end_m:
        return local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_today = local.replace(
        hour=start_m // 60,
        minute=start_m % 60,
        second=0,
        microsecond=0,
    )
    if start_m < end_m:
        return start_today
    if minutes_since_midnight(local) >= start_m:
        return start_today
    return start_today - dt.timedelta(days=1)


def containing_window_id(
    start_hhmm: str,
    end_hhmm: str,
    *,
    now: dt.datetime | None = None,
) -> str | None:
    """Stable id for the open window (local ``YYYY-MM-DDTHH:MM``)."""
    start_at = containing_window_start(start_hhmm, end_hhmm, now=now)
    if start_at is None:
        return None
    return start_at.strftime("%Y-%m-%dT%H:%M")


def load_consumed_window_id(daily_resets: dict[str, Any] | None) -> str:
    if not daily_resets:
        return ""
    raw = daily_resets.get(US_SCHEDULE_KEY)
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("consumed_id") or "")


def store_consumed_window_id(
    daily_resets: dict[str, Any] | None,
    window_id: str,
) -> dict[str, Any]:
    updated = dict(daily_resets or {})
    updated[US_SCHEDULE_KEY] = {"consumed_id": str(window_id or "")}
    return updated
