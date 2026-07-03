"""Track and apply Mudae ``$dk`` (daily kakera) stock."""

from __future__ import annotations

import time
from typing import Any

from macro.reaction_power import sync_reaction_power_fields


def sync_dk_fields_from_tu(state: Any, fields: dict[str, Any]) -> None:
    """Update ``$dk`` stock / recharge timer from a ``$tu`` (or combined) parse."""
    if "dk_stock" in fields and fields["dk_stock"] is not None:
        state.dk_stock = max(0, int(fields["dk_stock"]))
    if fields.get("dk_next_minutes") is not None:
        state.dk_next_minutes = int(fields["dk_next_minutes"])


def reset_reaction_power_to_max(state: Any, *, now: float | None = None) -> None:
    """``$dk`` refills reaction power to the account maximum."""
    stamp = now if now is not None else time.monotonic()
    state.power_percent = float(getattr(state, "power_max_percent", 155.0))
    state.power_tracked_at = stamp


def apply_dk_response(state: Any, fields: dict[str, Any], *, now: float | None = None) -> None:
    """Apply parsed fields after a successful ``$dk`` command."""
    stamp = now if now is not None else time.monotonic()
    if fields.get("dk_used") or "amount" in fields:
        if "dk_stock" in fields and fields["dk_stock"] is not None:
            state.dk_stock = max(0, int(fields["dk_stock"]))
        elif fields.get("dk_used"):
            if state.dk_stock is not None and state.dk_stock > 0:
                state.dk_stock = max(0, int(state.dk_stock) - 1)
            else:
                state.dk_stock = 0
        reset_reaction_power_to_max(state, now=stamp)
    sync_dk_fields_from_tu(state, fields)
    sync_reaction_power_fields(state, fields, now=stamp)


def has_dk_available(state: Any) -> bool:
    stock = getattr(state, "dk_stock", None)
    return stock is not None and int(stock) > 0
