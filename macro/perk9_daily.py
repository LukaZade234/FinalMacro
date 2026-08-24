"""Perk 9 daily sphere-button click budget (display + future $ohu9 sync)."""

from __future__ import annotations

from typing import Any

from mudae.constants import SPHERE_ROLL_FREE_EMOJIS
from mudae.sphere_log import get_sphere_events, normalize_source

# Until ``$bonus`` / ``$ohu9`` parsing lands, assume the default daily cap.
PERK9_CLICK_MAX_DEFAULT = 20


def is_perk9_sphere_click(sphere_type: str | None) -> bool:
    """True when a sphere-button click should consume perk 9 (not megasphere)."""
    if not sphere_type:
        return True
    key = str(sphere_type).strip()
    return key not in SPHERE_ROLL_FREE_EMOJIS and key.lower() not in {
        emoji.lower() for emoji in SPHERE_ROLL_FREE_EMOJIS
    }


def count_perk9_clicks(events: list[dict[str, Any]], *, date_key: str) -> int:
    """Count today's perk-9 sphere-button clicks from the earning log."""
    total = 0
    for entry in events:
        if entry.get("date_key") != date_key:
            continue
        if normalize_source(entry) != "sphere_click":
            continue
        if not is_perk9_sphere_click(entry.get("sphere_type")):
            continue
        total += 1
    return total


def sync_perk9_clicks_from_log(state: Any) -> None:
    """Raise ``state.perk9_clicks_today`` to match logged clicks for today."""
    from mudae.clock import utc_date_key

    rollover = getattr(state, "rollover_perk9_if_needed", None)
    if callable(rollover):
        rollover()
    today = utc_date_key()
    counted = count_perk9_clicks(get_sphere_events(), date_key=today)
    current = int(getattr(state, "perk9_clicks_today", 0) or 0)
    if counted > current:
        state.perk9_clicks_today = counted
        state.perk9_clicks_day = today
