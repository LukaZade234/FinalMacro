"""Apply parsed chaos-kakera extras to runtime state.

Discord clicks (free kakera, wish claim) stay in ``KakeraReactor``. This
module is the pure arithmetic: extra hourly rolls and discounted power cost.
"""

from __future__ import annotations

from typing import Any

from mudae.commands import is_roll_command
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_SPAWN_KINDS = frozenset(
    {
        MessageKind.ROLL,
        MessageKind.CHARACTER_EMBED,
        MessageKind.KAKERA_BUTTONS,
        MessageKind.CLAIM_BUTTONS,
    }
)


def discounted_reaction_cost(cost: float, discount_pct: float | None) -> float:
    """``cost`` after a chaos ``N% kakera power discount`` line."""
    if cost <= 0:
        return 0.0
    pct = float(discount_pct or 0.0)
    if pct <= 0:
        return float(cost)
    paid = float(cost) * (1.0 - min(pct, 100.0) / 100.0)
    return max(0.0, paid)


def apply_chaos_hourly_rolls(state: Any, extra: int) -> int:
    """Add ``+N rolls this hour`` to the ordinary hourly pool. Returns new total."""
    added = max(0, int(extra))
    pending = int(getattr(state, "chaos_rolls_left", 0) or 0)
    if added > 0:
        pending += added
        state.chaos_rolls_left = pending
        current = getattr(state, "rolls_left", None)
        if current is None:
            state.rolls_left = added
        else:
            state.rolls_left = int(current) + added
    current = getattr(state, "rolls_left", None)
    return 0 if current is None else int(current)


def chaos_extra_rolls(state: Any) -> int:
    return max(0, int(getattr(state, "chaos_rolls_left", 0) or 0))


def original_hourly_rolls(state: Any) -> int:
    """Hourly pool remaining. Chaos extras are ordinary rolls in ``rolls_left``."""
    return max(0, int(getattr(state, "rolls_left", 0) or 0))


def merge_tu_hourly_rolls(state: Any, tu_rolls: int) -> None:
    """Apply ``$tu`` rolls, folding unspent chaos extras into the ordinary pool.

    ``$tu`` usually already includes ``+N rolls this hour``. When it is smaller
    than the tagged extras (footer omitted them), add extras on top. Either way
    the result is one hourly pool — stop-at-2 runs on the combined count.
    """
    extras = chaos_extra_rolls(state)
    tu = int(tu_rolls)
    if extras > 0 and tu < extras:
        state.rolls_left = tu + extras
        return
    state.rolls_left = tu
    state.chaos_rolls_left = 0


def is_chaos_followup_embed(
    snapshot: MudaeMessageSnapshot,
    parsed: ParseResult,
    clicked_message_id: int,
) -> bool:
    """True for a chaos free-kakera / wish spawn, not the clicked roll or perk 6."""
    if snapshot.message_id == clicked_message_id:
        return False
    if snapshot.edited:
        return False
    fields = parsed.fields or {}
    if fields.get("perk_6") or fields.get("is_perk_6_spawn"):
        return False
    parser = str(fields.get("parser_command") or "").strip().lower()
    command = str(fields.get("command") or "").strip().lower()
    if parser == "roll" or (command and is_roll_command(command)):
        return False
    return parsed.kind in _SPAWN_KINDS
