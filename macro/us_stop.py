"""Runtime stop / pause conditions for ``$us`` roll mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from macro.config import KakeraReactionRules, MacroConfig
from macro.dk_manager import has_dk_available
from macro.perk8_daily import perk8_budget_applies
from macro.perk8_power import (
    dk_allowed_for_state,
    power_save_enabled,
    remaining_perk8_clicks,
)
from macro.reaction_power import (
    KAKERA_FREE_REACT_EMOJIS,
    can_afford_reaction,
    kakera_base_cost_from_state,
    reaction_power_cost,
    refresh_reaction_power,
)
from macro.rule_eval import perk8_click_budget, perk8_mode_from_state
from macro.us_schedule import normalize_hhmm


_POWER_EXHAUSTED_PREFIX = "reaction power exhausted"
KEY_LIMIT_PREFIX = "hourly key limit reached"


def _clamp_stop_after_rolls(value: Any, default: int = 100) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


@dataclass
class UsModeStopOptions:
    """User-selected limits applied when starting ``$us`` roll mode."""

    keep_draining: bool = False
    stop_on_power_exhausted: bool = False
    stop_on_key_limit: bool = False
    stop_after_rolls_enabled: bool = False
    stop_after_rolls: int = 100
    schedule_enabled: bool = False
    schedule_start: str = "04:00"
    schedule_end: str = "06:00"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> UsModeStopOptions:
        if not data:
            return cls()
        return cls(
            keep_draining=bool(data.get("keep_draining", False)),
            stop_on_power_exhausted=bool(data.get("stop_on_power_exhausted", False)),
            stop_on_key_limit=bool(data.get("stop_on_key_limit", False)),
            stop_after_rolls_enabled=bool(data.get("stop_after_rolls_enabled", False)),
            stop_after_rolls=_clamp_stop_after_rolls(data.get("stop_after_rolls", 100)),
            schedule_enabled=bool(data.get("schedule_enabled", False)),
            schedule_start=normalize_hhmm(data.get("schedule_start"), "04:00"),
            schedule_end=normalize_hhmm(data.get("schedule_end"), "06:00"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "keep_draining": self.keep_draining,
            "stop_on_power_exhausted": self.stop_on_power_exhausted,
            "stop_on_key_limit": self.stop_on_key_limit,
            "stop_after_rolls_enabled": self.stop_after_rolls_enabled,
            "stop_after_rolls": max(1, int(self.stop_after_rolls)),
            "schedule_enabled": self.schedule_enabled,
            "schedule_start": normalize_hhmm(self.schedule_start, "04:00"),
            "schedule_end": normalize_hhmm(self.schedule_end, "06:00"),
        }


def us_stop_from_config(
    config: MacroConfig,
    *,
    apply_schedule: bool = True,
) -> UsModeStopOptions:
    """Build session options from the preset ``$us`` drain policy.

    ``apply_schedule=False`` is the Run-page Roll ``$us`` button: same stops,
    but the local window is ignored so a later schedule does not delay it.
    """
    return UsModeStopOptions(
        keep_draining=bool(config.us_keep_draining),
        stop_on_power_exhausted=bool(config.us_stop_on_power_exhausted),
        stop_on_key_limit=bool(config.us_stop_on_key_limit),
        stop_after_rolls_enabled=bool(config.us_stop_after_rolls_enabled),
        stop_after_rolls=max(1, int(config.us_stop_after_rolls)),
        schedule_enabled=bool(config.us_schedule_enabled) if apply_schedule else False,
        schedule_start=normalize_hhmm(config.us_schedule_start, "04:00"),
        schedule_end=normalize_hhmm(config.us_schedule_end, "06:00"),
    )


def overlay_legacy_us_options(
    stored: dict[str, Any],
    legacy: UsModeStopOptions,
) -> dict[str, Any]:
    """Copy Classic app-global ``$us`` stops onto a preset that predates them."""
    if "us_keep_draining" in stored or "us_stop_on_power_exhausted" in stored:
        return stored
    out = dict(stored)
    out["us_keep_draining"] = False
    out["us_stop_on_power_exhausted"] = legacy.stop_on_power_exhausted
    out["us_stop_after_rolls_enabled"] = legacy.stop_after_rolls_enabled
    out["us_stop_after_rolls"] = legacy.stop_after_rolls
    return out


def us_stop_can_pause(reason: str | None) -> bool:
    """True when keep-draining should wait instead of quitting.

    Reaction power may never come back inside one session — it needs ``$dk`` or
    hours of regen — so waiting on it is opt-in behind keep-draining. The key
    cap is not in this class; see :func:`us_stop_is_key_limit`.
    """
    return bool(reason) and reason.startswith(_POWER_EXHAUSTED_PREFIX)


def us_stop_is_key_limit(reason: str | None) -> bool:
    """True for the hourly key cap, which always waits rather than quitting.

    Unlike reaction power this always comes back, and soon: it lifts at the
    hourly rolls reset, which the ``$us`` loop already waits out for everyone
    (``_wait_for_rolls_reset``). So enabling the toggle *is* the opt-in, and it
    does not additionally require keep-draining — leaving the stack alone for
    the rest of the hour and resuming is the whole point of it.
    """
    return bool(reason) and reason.startswith(KEY_LIMIT_PREFIX)


def _perk8_half_cost_applies(state: Any, rules: KakeraReactionRules) -> bool:
    """True when the next paid kakera clicks are likely at perk-8 half cost."""
    if not rules.perk_8_budget_mode:
        return False
    mode = perk8_mode_from_state(state)
    if not perk8_budget_applies(mode):
        return False
    budget = perk8_click_budget(state, rules)
    return state.remaining_kakera_budget(budget) > 0


def _minimum_kakera_cost(state: Any, rules: KakeraReactionRules) -> float:
    """Lowest non-free reaction cost among kakera types this preset could click."""
    has_perk_8 = _perk8_half_cost_applies(state, rules)
    base_cost = kakera_base_cost_from_state(state)
    types = list(rules.types_allowed)
    if not types:
        return reaction_power_cost(
            kakera_emoji="kakeraW",
            has_chaos_key=True,
            has_perk_8=has_perk_8,
            base_cost=base_cost,
        )
    costs = [
        reaction_power_cost(
            kakera_emoji=emoji,
            has_chaos_key=True,
            has_perk_8=has_perk_8,
            base_cost=base_cost,
        )
        for emoji in types
        if emoji not in KAKERA_FREE_REACT_EMOJIS
    ]
    if not costs:
        return 0.0
    return min(costs)


def us_kakera_power_exhausted(state: Any, rules: KakeraReactionRules) -> bool:
    """True when kakera clicks are enabled but power and ``$dk`` cannot cover them."""
    if not rules.enabled:
        return False

    types = list(rules.types_allowed)
    paid_types = [t for t in types if t not in KAKERA_FREE_REACT_EMOJIS]
    if types and not paid_types:
        return False

    refresh_reaction_power(state)
    if state.power_percent is None:
        # Same call as `can_afford_reaction`: unknown power means "not
        # exhausted yet" rather than "stop now". The first click after this
        # (if any) resolves the unknown one way or the other — either it
        # spends power that turns out to be there, or Mudae's denial message
        # re-anchors `power_percent` to the real value — so this check is
        # accurate again on the very next roll either way.
        return False

    if rules.auto_use_dk and has_dk_available(state):
        held_for_tomorrow = (
            power_save_enabled(rules)
            and remaining_perk8_clicks(state) <= 0
            and not dk_allowed_for_state(state, rules, perk8=False)
        )
        if not held_for_tomorrow:
            return False

    min_cost = _minimum_kakera_cost(state, rules)
    if min_cost <= 0:
        return False
    return not can_afford_reaction(state, min_cost)


def us_key_limit_reached(state: Any) -> int | None:
    """Mudae's hourly key cap, once a roll has reported it."""
    limit = getattr(state, "key_limit_hit", None)
    if limit is None:
        return None
    try:
        return int(limit)
    except (TypeError, ValueError):
        return None


def us_stop_reason(
    *,
    options: UsModeStopOptions,
    state: Any,
    rules: KakeraReactionRules,
    us_rolls_done: int,
) -> str | None:
    if options.stop_after_rolls_enabled and us_rolls_done >= options.stop_after_rolls:
        return f"roll limit ({options.stop_after_rolls}) reached"
    if options.stop_on_key_limit:
        limit = us_key_limit_reached(state)
        if limit is not None:
            return f"{KEY_LIMIT_PREFIX} ({limit:,} keys/h)"
    if options.stop_on_power_exhausted and us_kakera_power_exhausted(state, rules):
        return "reaction power exhausted (no usable $dk left)"
    return None
