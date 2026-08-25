"""Wall-clock deadlines so the GUI can tick reset timers and power regen.

``$tu`` gives minutes remaining. Those go stale the moment they are stored.
ISO deadlines plus the last power-anchor time let the Run page count down (and
regenerate reaction power) every second without another ``$tu``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from macro.perk8_daily import parse_iso
from macro.reaction_power import DEFAULT_MAX_REACTION_POWER, apply_passive_regen
from mudae.clock import utc_now


def iso_deadline(minutes: int | None, *, now: dt.datetime | None = None) -> str:
    """UTC ISO timestamp ``minutes`` from now, or ``""`` when unknown."""
    if minutes is None:
        return ""
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    stamp = now or utc_now()
    return (stamp + dt.timedelta(minutes=value)).isoformat()


def remaining_minutes(deadline_iso: str, *, now: dt.datetime | None = None) -> int | None:
    """Whole minutes until ``deadline_iso``, ``0`` once it has passed."""
    if not deadline_iso:
        return None
    deadline = parse_iso(deadline_iso)
    if deadline is None:
        return None
    stamp = now or utc_now()
    delta = (deadline - stamp).total_seconds()
    if delta <= 0:
        return 0
    return max(1, int(delta // 60))


def apply_countdown(
    state: Any,
    minutes_attr: str,
    at_attr: str,
    minutes: int | None,
    *,
    now: dt.datetime | None = None,
) -> None:
    """Write a minute countdown and its absolute deadline onto ``state``."""
    if minutes is None:
        setattr(state, minutes_attr, None)
        setattr(state, at_attr, "")
        return
    value = int(minutes)
    setattr(state, minutes_attr, value)
    setattr(state, at_attr, iso_deadline(value, now=now))


def stamp_power_updated(state: Any, *, now: dt.datetime | None = None) -> None:
    """Record when ``power_percent`` was last known, for GUI regen."""
    state.power_updated_at = (now or utc_now()).isoformat()


def live_power_percent(state: Any, *, now: dt.datetime | None = None) -> float | None:
    """Anchored power plus passive regen since ``power_updated_at``."""
    raw = getattr(state, "power_percent", None)
    if raw is None:
        return None
    anchor = parse_iso(str(getattr(state, "power_updated_at", "") or ""))
    if anchor is None:
        return float(raw)
    elapsed = ((now or utc_now()) - anchor).total_seconds()
    max_power = float(
        getattr(state, "power_max_percent", None) or DEFAULT_MAX_REACTION_POWER
    )
    return apply_passive_regen(float(raw), elapsed, max_power=max_power)
