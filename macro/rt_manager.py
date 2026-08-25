"""Track and apply Mudae ``$rt`` (reset timer) availability."""

from __future__ import annotations

from typing import Any


def sync_rt_fields_from_tu(state: Any, fields: dict[str, Any]) -> None:
    """Update ``$rt`` availability / cooldown from a ``$tu`` (or combined) parse."""
    if fields.get("rt_available") is True:
        state.rt_available = True
        setter = getattr(state, "set_rt_reset", None)
        if callable(setter):
            setter(None)
        else:
            state.rt_next_minutes = None
    if fields.get("rt_next_minutes") is not None:
        setter = getattr(state, "set_rt_reset", None)
        if callable(setter):
            setter(int(fields["rt_next_minutes"]))
        else:
            state.rt_next_minutes = int(fields["rt_next_minutes"])
        state.rt_available = False
    elif fields.get("rt_available") is False:
        state.rt_available = False


def has_rt_available(state: Any) -> bool:
    return getattr(state, "rt_available", None) is True


def should_stop_after_wish_claim(state: Any) -> bool:
    """True when a wish was just claimed and neither claim nor ``$rt`` remains."""
    if getattr(state, "claim_available", None) is not False:
        return False
    return not has_rt_available(state)


def apply_rt_response(state: Any, fields: dict[str, Any]) -> bool:
    """Apply parsed fields after ``$rt``. Returns True when a claim slot was opened."""
    sync_rt_fields_from_tu(state, fields)
    if fields.get("claim_available") is True:
        state.claim_available = True
        setter = getattr(state, "set_claim_cooldown", None)
        if callable(setter):
            setter(None)
        else:
            state.claim_cooldown_minutes = None
    if fields.get("rt_used"):
        state.rt_available = False
    return fields.get("rt_used") is True or fields.get("claim_available") is True
