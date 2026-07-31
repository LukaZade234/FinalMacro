"""Runtime stop conditions for ``$us`` roll mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from macro.config import KakeraReactionRules
from macro.dk_manager import has_dk_available
from macro.reaction_power import (
    BASE_REACTION_COST,
    KAKERA_FREE_REACT_EMOJIS,
    can_afford_reaction,
    reaction_power_cost,
    refresh_reaction_power,
)


@dataclass
class UsModeStopOptions:
    """User-selected limits applied when starting ``$us`` roll mode."""

    stop_on_power_exhausted: bool = False
    stop_after_rolls_enabled: bool = False
    stop_after_rolls: int = 100

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> UsModeStopOptions:
        if not data:
            return cls()
        return cls(
            stop_on_power_exhausted=bool(data.get("stop_on_power_exhausted", False)),
            stop_after_rolls_enabled=bool(data.get("stop_after_rolls_enabled", False)),
            stop_after_rolls=max(1, int(data.get("stop_after_rolls", 100))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stop_on_power_exhausted": self.stop_on_power_exhausted,
            "stop_after_rolls_enabled": self.stop_after_rolls_enabled,
            "stop_after_rolls": max(1, int(self.stop_after_rolls)),
        }


def _minimum_kakera_cost(rules: KakeraReactionRules) -> float:
    """Lowest reaction cost among kakera types this preset could click."""
    types = list(rules.types_allowed)
    if not types:
        return BASE_REACTION_COST
    costs = [
        reaction_power_cost(
            kakera_emoji=emoji,
            has_chaos_key=True,
            has_perk_8=True,
        )
        for emoji in types
    ]
    return min(costs) if costs else BASE_REACTION_COST


def us_kakera_power_exhausted(state: Any, rules: KakeraReactionRules) -> bool:
    """True when kakera clicks are enabled but power and ``$dk`` cannot cover them."""
    if not rules.enabled:
        return False

    types = list(rules.types_allowed)
    if types and all(t in KAKERA_FREE_REACT_EMOJIS for t in types):
        return False

    refresh_reaction_power(state)
    if state.power_percent is None:
        return False

    if rules.auto_use_dk and has_dk_available(state):
        return False

    min_cost = _minimum_kakera_cost(rules)
    if min_cost <= 0:
        return False
    return not can_afford_reaction(state, min_cost)


def us_stop_reason(
    *,
    options: UsModeStopOptions,
    state: Any,
    rules: KakeraReactionRules,
    us_rolls_done: int,
) -> str | None:
    if options.stop_after_rolls_enabled and us_rolls_done >= options.stop_after_rolls:
        return f"roll limit ({options.stop_after_rolls}) reached"
    if options.stop_on_power_exhausted and us_kakera_power_exhausted(state, rules):
        return "reaction power exhausted (no usable $dk left)"
    return None
