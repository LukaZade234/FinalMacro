"""UTC calendar for Mudae dailies; local clock only for display.

Mudae resets at 00:00 UTC. Log ``date_key`` values and stats buckets use that
day. The in-app live feed converts stored UTC ISO timestamps to local time.
"""

from __future__ import annotations

import datetime as dt
from typing import Any


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def as_utc(stamp: dt.datetime) -> dt.datetime:
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=dt.UTC)
    return stamp.astimezone(dt.UTC)


def utc_date_key(now: dt.datetime | None = None) -> str:
    """YYYY-MM-DD of the Mudae daily (UTC)."""
    return as_utc(now or utc_now()).strftime("%Y-%m-%d")


def parse_iso_datetime(raw: str) -> dt.datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed


def local_hhmmss(iso_ts: str) -> str:
    """Clock time in the local timezone for a stored UTC ISO timestamp."""
    parsed = parse_iso_datetime(iso_ts)
    if parsed is None:
        return ""
    return parsed.astimezone().strftime("%H:%M:%S")


# Discord ids embed the millisecond they were minted, counted from this epoch.
# That makes a message id a usable timestamp for any row that stored the id but
# not the date — see ``mudae.soulmate_log.backfill_dates``.
DISCORD_EPOCH_MS = 1420070400000


def snowflake_datetime(snowflake: Any) -> dt.datetime | None:
    """UTC time a Discord snowflake was created, or ``None`` if unusable."""
    try:
        value = int(snowflake)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    millis = (value >> 22) + DISCORD_EPOCH_MS
    try:
        return dt.datetime.fromtimestamp(millis / 1000, dt.UTC)
    except (OverflowError, OSError, ValueError):
        return None
