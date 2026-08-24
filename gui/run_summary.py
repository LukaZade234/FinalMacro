"""Run-page summary: session haul, daily perk tallies and the last claim.

The Run designs show a "this session" panel (kakera / spheres / keys / claims)
plus perk 8 and perk 9 progress. Nothing tracked exactly that shape before, so
this assembles it from what the app already records:

* kakera / sphere / key totals come from the earning logs, filtered to entries
  recorded since the session started;
* claims come from the activity log, which is cleared per session — there is no
  dedicated claim log;
* perk 8 lives on the macro state (clicks used against the daily cap);
* perk 9 has no tracking of its own, so it is reported as today's sphere count,
  which is the tally the perk governs.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

# macro/post_roll.py logs claims as "Claimed {character} ({winner})".
_CLAIM_LINE = re.compile(r"^claimed\s+(.+?)(?:\s*\(([^)]*)\))?\s*$", re.IGNORECASE)


def _parse_iso(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _entry_time(entry: dict[str, Any]) -> dt.datetime | None:
    return _parse_iso(entry.get("recorded_at"))


def _in_window(
    entry: dict[str, Any],
    since: dt.datetime | None,
    date_key: str | None,
    *,
    unbounded: bool = False,
) -> bool:
    if date_key is not None and entry.get("date_key") != date_key:
        return False
    if since is None:
        # A missing start means no session has run yet, so nothing counts —
        # without this the "this session" figures would show all-time totals.
        return unbounded
    stamp = _entry_time(entry)
    # Entries with an unreadable timestamp are dropped rather than counted, so a
    # bad row cannot inflate the session total.
    return stamp is not None and stamp >= since


def _sum_amounts(
    events: list[dict[str, Any]],
    *,
    since: dt.datetime | None,
    date_key: str | None = None,
) -> int:
    total = 0
    unbounded = date_key is not None
    for entry in events:
        if not _in_window(entry, since, date_key, unbounded=unbounded):
            continue
        try:
            total += int(entry.get("amount") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _count_events(
    events: list[dict[str, Any]],
    *,
    since: dt.datetime | None,
    date_key: str | None = None,
) -> int:
    unbounded = date_key is not None
    return sum(
        1 for entry in events
        if _in_window(entry, since, date_key, unbounded=unbounded)
    )


def _claims_from_activity(activity_log: list[Any]) -> tuple[int, dict[str, str] | None]:
    """Count claims in the activity log and describe the most recent one."""
    count = 0
    last: dict[str, str] | None = None
    for entry in activity_log:
        to_dict = getattr(entry, "to_dict", None)
        data = to_dict() if callable(to_dict) else dict(entry)
        if data.get("severity") != "claim":
            continue
        match = _CLAIM_LINE.match(str(data.get("text") or "").strip())
        if not match:
            continue
        count += 1
        stamp = _parse_iso(data.get("ts"))
        last = {
            "character": match.group(1).strip(),
            "detail": (match.group(2) or "").strip(),
            "time": stamp.astimezone().strftime("%H:%M:%S") if stamp else "",
        }
    return count, last


def build_run_summary(
    state: Any,
    session_started_at: dt.datetime | None,
) -> dict[str, Any]:
    from mudae.kakera_log import get_kakera_events
    from mudae.key_log import get_key_events
    from mudae.sphere_log import get_sphere_events

    now = dt.datetime.now(dt.timezone.utc)
    today_key = now.strftime("%Y-%m-%d")

    kakera_events = get_kakera_events()
    sphere_events = get_sphere_events()
    key_events = get_key_events()

    claims, last_claim = _claims_from_activity(getattr(state, "activity_log", []) or [])

    perk8_max = getattr(state, "perk8_click_max", None)
    elapsed = int((now - session_started_at).total_seconds()) if session_started_at else 0

    return {
        "session": {
            "started_at": session_started_at.isoformat() if session_started_at else None,
            "elapsed_seconds": max(0, elapsed),
            "kakera": _sum_amounts(kakera_events, since=session_started_at),
            # Sphere entries store a kakera value, not a quantity, so the
            # headline "spheres" figure counts drops and the value is separate.
            "spheres": _count_events(sphere_events, since=session_started_at),
            "sphere_value": _sum_amounts(sphere_events, since=session_started_at),
            "keys": _sum_amounts(key_events, since=session_started_at),
            "claims": claims,
        },
        "today": {
            "kakera": _sum_amounts(kakera_events, since=None, date_key=today_key),
            "perk8_used": int(getattr(state, "kakera_clicks_today", 0) or 0),
            "perk8_max": int(perk8_max) if perk8_max else None,
            "perk8_mode": str(getattr(state, "perk8_priority_mode", "") or ""),
            "perk9_spheres": _count_events(sphere_events, since=None, date_key=today_key),
        },
        "last_claim": last_claim,
    }
