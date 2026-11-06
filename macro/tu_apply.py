"""Apply a parsed ``$tu`` to one account's state.

Shared by the main's roll engine and the alts, so every account reads ``$tu``
the same way into its *own* ``AccountState``.
"""

from __future__ import annotations

from typing import Any

from macro.chaos_followup import merge_tu_hourly_rolls
from macro.dk_manager import sync_dk_fields_from_tu
from macro.reaction_power import sync_reaction_power_fields
from macro.rt_manager import sync_rt_fields_from_tu
from macro.state import AccountState


def apply_tu_fields(state: AccountState, fields: dict[str, Any]) -> None:
    if "rolls_left" in fields and fields["rolls_left"] is not None:
        merge_tu_hourly_rolls(state, int(fields["rolls_left"]))
    # Always refresh the $us bonus (None when $tu no longer reports one).
    us_bonus = fields.get("rolls_us_bonus")
    state.rolls_us_bonus = int(us_bonus) if us_bonus is not None else None
    if "claim_available" in fields:
        state.claim_available = fields["claim_available"]
        if fields["claim_available"]:
            state.set_claim_cooldown(None)
    if "claim_cooldown_minutes" in fields:
        state.set_claim_cooldown(fields["claim_cooldown_minutes"])
    sync_reaction_power_fields(state, fields)
    sync_dk_fields_from_tu(state, fields)
    sync_rt_fields_from_tu(state, fields)
    if "rolls_reset_minutes" in fields:
        state.set_rolls_reset(int(fields["rolls_reset_minutes"]))
    if "next_claim_reset_minutes" in fields and fields["next_claim_reset_minutes"] is not None:
        state.set_claim_reset(int(fields["next_claim_reset_minutes"]))
    for key in ("kakera_stock", "sphere_stock", "daily_available"):
        if fields.get(key) is not None:
            setattr(state, key, fields[key])
    if "oh_total" in fields:
        state.minigames_left = {g: int(fields.get(f"{g}_total") or 0) for g in ("oh", "oc", "oq", "ot")}
