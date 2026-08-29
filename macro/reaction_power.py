"""Track Mudae kakera reaction power without polling ``$tu`` / ``$ku`` every roll.

Power is seeded from ``$tu`` (or ``$ku``) at session start, passively regenerates
at 1% every 3 minutes, and is spent on successful kakera button clicks. Purple
(``kakeraP``) costs nothing. Chaos keys halve the cost; perk 8 halves it again.
"""

from __future__ import annotations

import time
from typing import Any

# Temporary default when ``$bonus`` has not been fetched for the run channel.
DEFAULT_MAX_REACTION_POWER = 155.0
REGEN_PERCENT_PER_3MIN = 1.0
REGEN_INTERVAL_SEC = 180.0
BASE_REACTION_COST = 30.0
KAKERA_FREE_REACT_EMOJIS = frozenset({"kakeraP"})


def kakera_base_cost_from_state(state: Any | None) -> float:
    """Paid-kakera % cost from the run channel's ``$bonus``, else 30.

    Caps live on ``AccountState.kakera_base_cost``, which is rewritten from
    the *current* run channel's stored sheet (never a leftover from another
    account or server).
    """
    if state is None:
        return BASE_REACTION_COST
    raw = getattr(state, "kakera_base_cost", None)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return BASE_REACTION_COST
    return value if value > 0 else BASE_REACTION_COST


def reaction_power_cost(
    *,
    kakera_emoji: str,
    has_chaos_key: bool,
    has_perk_8: bool,
    base_cost: float | None = None,
) -> float:
    """Percent of reaction power consumed by one kakera click."""
    emoji = (kakera_emoji or "").strip()
    if emoji in KAKERA_FREE_REACT_EMOJIS:
        return 0.0
    cost = BASE_REACTION_COST
    if base_cost is not None:
        try:
            parsed = float(base_cost)
        except (TypeError, ValueError):
            parsed = 0.0
        if parsed > 0:
            cost = parsed
    if has_chaos_key:
        cost /= 2.0
    if has_perk_8:
        cost /= 2.0
    return cost


def apply_passive_regen(
    power: float,
    elapsed_sec: float,
    *,
    max_power: float = DEFAULT_MAX_REACTION_POWER,
) -> float:
    if elapsed_sec <= 0:
        return power
    gained = (elapsed_sec / REGEN_INTERVAL_SEC) * REGEN_PERCENT_PER_3MIN
    return min(max_power, power + gained)


def estimate_power_from_cooldown(cooldown_minutes: int, *, cost: float) -> float:
    """Back-calculate current power from Mudae's 'wait N min' denial message."""
    if cooldown_minutes <= 0:
        return 0.0
    regen_during_wait = (cooldown_minutes / 3.0) * REGEN_PERCENT_PER_3MIN
    return max(0.0, cost - regen_during_wait)


def display_reaction_power(power: float | None) -> int:
    if power is None:
        return -1
    return int(round(power))


def sync_reaction_power_fields(state: Any, fields: dict[str, Any], *, now: float | None = None) -> None:
    """Apply parsed ``$tu`` / ``$ku`` reaction-power fields to runtime state."""
    stamp = now if now is not None else time.monotonic()
    if "power_percent" in fields and fields["power_percent"] is not None:
        state.power_percent = float(fields["power_percent"])
        state.power_tracked_at = stamp
        from macro.live_clock import stamp_power_updated

        stamp_power_updated(state)
    if fields.get("power_max_percent") is not None:
        state.power_max_percent = float(fields["power_max_percent"])


def refresh_reaction_power(state: Any, *, now: float | None = None) -> float | None:
    """Apply passive regen since the last anchor and return current power."""
    if state.power_percent is None:
        return None
    stamp = now if now is not None else time.monotonic()
    tracked_at = float(getattr(state, "power_tracked_at", 0.0) or 0.0)
    if tracked_at > 0:
        elapsed = stamp - tracked_at
        if elapsed > 0:
            max_power = float(getattr(state, "power_max_percent", DEFAULT_MAX_REACTION_POWER))
            state.power_percent = apply_passive_regen(
                float(state.power_percent),
                elapsed,
                max_power=max_power,
            )
            state.power_tracked_at = stamp
    return state.power_percent


def can_afford_reaction(state: Any, cost: float, *, now: float | None = None) -> bool:
    refresh_reaction_power(state, now=now)
    if cost <= 0:
        return True
    if state.power_percent is None:
        return True
    return float(state.power_percent) >= cost


def spend_reaction_power(state: Any, cost: float, *, now: float | None = None) -> bool:
    """Deduct ``cost`` after a confirmed kakera claim. Returns False if too low."""
    refresh_reaction_power(state, now=now)
    if cost <= 0:
        return True
    if state.power_percent is None:
        return True
    if float(state.power_percent) < cost:
        return False
    state.power_percent = float(state.power_percent) - cost
    state.power_tracked_at = now if now is not None else time.monotonic()
    from macro.live_clock import stamp_power_updated

    stamp_power_updated(state)
    return True


def sync_reaction_power_from_denial(
    state: Any,
    *,
    cooldown_minutes: int,
    cost: float,
    now: float | None = None,
) -> None:
    """Re-anchor power when Mudae rejects a kakera click for insufficient power."""
    state.power_percent = estimate_power_from_cooldown(cooldown_minutes, cost=cost)
    state.power_tracked_at = now if now is not None else time.monotonic()
    from macro.live_clock import stamp_power_updated

    stamp_power_updated(state)
