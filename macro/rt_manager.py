"""Track and apply Mudae ``$rt`` (reset timer) availability."""

from __future__ import annotations

from typing import Any


def sync_rt_fields_from_tu(state: Any, fields: dict[str, Any]) -> None:
    """Update ``$rt`` availability / cooldown from a ``$tu`` (or combined) parse."""
    if fields.get("rt_available") is True:
        state.rt_available = True
        state.rt_next_minutes = None
    if fields.get("rt_next_minutes") is not None:
        state.rt_next_minutes = int(fields["rt_next_minutes"])
        state.rt_available = False
    elif fields.get("rt_available") is False:
        state.rt_available = False


def has_rt_available(state: Any) -> bool:
    return getattr(state, "rt_available", None) is True


def apply_rt_response(state: Any, fields: dict[str, Any]) -> bool:
    """Apply parsed fields after ``$rt``. Returns True when a claim slot was opened."""
    sync_rt_fields_from_tu(state, fields)
    if fields.get("claim_available") is True:
        state.claim_available = True
        state.claim_cooldown_minutes = None
    if fields.get("rt_used"):
        state.rt_available = False
    return fields.get("rt_used") is True or fields.get("claim_available") is True
