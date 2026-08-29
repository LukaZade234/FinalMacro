"""Run-page summary: session haul, daily perk tallies and the last claim.

The Run designs show a "this session" panel (kakera / spheres / keys / claims)
plus perk 8 and perk 9 progress. Nothing tracked exactly that shape before, so
this assembles it from what the app already records:

* kakera / sphere / key totals come from the earning logs, filtered to entries
  recorded since the session started;
* claims come from the activity log, which is cleared per session — there is no
  dedicated claim log;
* perk 8 lives on the macro state (clicks used against the daily cap);
* perk 9 counts sphere-button clicks today (excluding megasphere), also on
  macro state — bootstrapped from ``sphere_click`` log entries on connect.
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
    *,
    kakera_rules: Any = None,
) -> dict[str, Any]:
    from macro.perk8_power import power_save_status
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
    perk8_cap = int(perk8_max) if perk8_max else None
    perk8_used = int(getattr(state, "kakera_clicks_today", 0) or 0)
    if perk8_cap is not None and perk8_cap > 0:
        perk8_used = min(perk8_used, perk8_cap)
    elapsed = int((now - session_started_at).total_seconds()) if session_started_at else 0
    sphere_sp = _sum_amounts(sphere_events, since=session_started_at)

    return {
        "session": {
            "started_at": session_started_at.isoformat() if session_started_at else None,
            "elapsed_seconds": max(0, elapsed),
            "kakera": _sum_amounts(kakera_events, since=session_started_at),
            # Same unit as kakera / keys: sum of logged SP, not the drop count.
            "spheres": sphere_sp,
            "sphere_value": sphere_sp,
            "keys": _sum_amounts(key_events, since=session_started_at),
            "claims": claims,
        },
        "today": {
            "kakera": _sum_amounts(kakera_events, since=None, date_key=today_key),
            "perk8_used": perk8_used,
            "perk8_max": perk8_cap,
            "perk8_mode": str(getattr(state, "perk8_priority_mode", "") or ""),
            "perk9_used": int(getattr(state, "perk9_clicks_today", 0) or 0),
            "perk9_max": int(getattr(state, "perk9_click_max", 0) or 0) or None,
            # Legacy key — kept so older QML bindings do not break mid-session.
            "perk9_spheres": int(getattr(state, "perk9_clicks_today", 0) or 0),
        },
        "last_claim": last_claim,
        "power_save": power_save_status(state, kakera_rules),
    }
