"""Rule evaluation for the three preset decision blocks.

Each helper inspects parsed roll fields against a rule block and returns a
structured decision + human-readable reason. The rest of the macro consumes
these decisions and is responsible for actually clicking buttons.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from macro.config import (
    CharacterClaimRules,
    KakeraReactionRules,
    SphereReactionRules,
)
from macro.perk8_daily import (
    PERK8_DAILY_CLICK_BUDGET,
    Perk8PriorityMode,
    perk8_budget_applies,
    perk8_requirements_relaxed,
)
from macro.perk8_power import (
    power_save_enabled,
    remaining_perk8_clicks,
    seconds_until_midnight,
    should_spend_paid_non_perk8,
    snapshot_from_state,
    window_sec_from_rules,
)
from macro.perk9_threshold import Perk9ThresholdContext
from macro.reaction_power import (
    can_afford_reaction,
    display_reaction_power,
    kakera_base_cost_from_state,
    reaction_power_cost,
    refresh_reaction_power,
)
from macro.rt_manager import has_rt_available
from macro.state import AccountState
from mudae.clock import utc_now
from mudae.constants import (
    SPHERE_ROLL_DEFAULT_EMOJI,
    SPHERE_ROLL_DEFAULT_FILTER_IDS,
    SPHERE_ROLL_FREE_EMOJIS,
    canonical_sphere_emoji,
)


@dataclass
class ClaimDecision:
    """Result of evaluating ``passes_character_claim``."""

    should_claim: bool
    immediate: bool  # True = interrupt loop and claim now
    reason: str


@dataclass
class ButtonChoice:
    """A specific button the macro should click."""

    custom_id: str
    message_id: int | None = None
    kind: str = ""
    label: str = ""
    emoji: str = ""


@dataclass
class ReactionDecision:
    """Result of evaluating a kakera or sphere reaction block."""

    buttons: list[ButtonChoice] = field(default_factory=list)
    reason: str = ""

    @property
    def should_click(self) -> bool:
        return bool(self.buttons)


# ---------------------------------------------------------------------------
# Helpers


def _has_chaos_key(fields: dict[str, Any]) -> bool:
    keys = fields.get("keys") or []
    if not isinstance(keys, Iterable):
        return False
    for entry in keys:
        if isinstance(entry, dict) and entry.get("type") == "chaos":
            return True
    return False


def _kakera_emoji(button: dict[str, Any]) -> str:
    emoji = button.get("emoji") or ""
    if isinstance(emoji, dict):
        return str(emoji.get("name") or "")
    return str(emoji or "")


def _sphere_emoji(button: dict[str, Any]) -> str:
    emoji = canonical_sphere_emoji(_kakera_emoji(button))
    if emoji == SPHERE_ROLL_DEFAULT_EMOJI:
        return emoji
    if emoji.startswith("sp") and len(emoji) >= 3:
        return emoji
    return ""


def _sphere_matches_filter(emoji: str, types_allowed: list[str]) -> bool:
    if not types_allowed:
        return True
    key = canonical_sphere_emoji(emoji)
    allowed = {canonical_sphere_emoji(item) for item in types_allowed}
    if key in allowed:
        return True
    if key == SPHERE_ROLL_DEFAULT_EMOJI:
        return bool(SPHERE_ROLL_DEFAULT_FILTER_IDS & allowed)
    return False


def _ranked_within(rank: Any, limit: int | None) -> bool:
    if limit is None:
        return True
    if rank is None:
        return False
    try:
        return int(rank) <= int(limit)
    except (TypeError, ValueError):
        return False


def _spheres_meets(actual: Any, minimum: int | None) -> bool:
    if minimum is None:
        return True
    if actual is None:
        return False
    try:
        return int(actual) >= int(minimum)
    except (TypeError, ValueError):
        return False


def _make_button_choice(message_id: int | None, button: dict[str, Any]) -> ButtonChoice:
    return ButtonChoice(
        custom_id=str(button.get("custom_id") or ""),
        message_id=message_id,
        kind=str(button.get("kind") or ""),
        label=str(button.get("label") or ""),
        emoji=_kakera_emoji(button),
    )


# ---------------------------------------------------------------------------
# Character claim


def passes_character_claim(
    fields: dict[str, Any],
    rules: CharacterClaimRules,
    state: AccountState,
    *,
    final_hour: bool,
    wished_pinged: bool,
) -> ClaimDecision:
    """Should the macro claim *this* character on a roll?

    ``immediate=True`` means interrupt the roll loop and claim now (wish ping or
    instant-trigger). ``immediate=False`` means defer to end-of-batch picker.
    """
    if not rules.enabled and not (rules.claim_on_wish_ping and wished_pinged):
        return ClaimDecision(False, False, "character claim block off")

    if fields.get("claimed"):
        return ClaimDecision(False, False, "character already claimed")
    if not fields.get("can_claim"):
        return ClaimDecision(False, False, "no enabled claim button")

    claim_blocked = state.claim_available is False
    if claim_blocked:
        if (
            rules.claim_on_wish_ping
            and wished_pinged
            and rules.auto_use_rt
            and has_rt_available(state)
        ):
            return ClaimDecision(True, True, "wish ping ($rt)")
        return ClaimDecision(False, False, "claim on cooldown")

    if rules.claim_on_wish_ping and wished_pinged:
        return ClaimDecision(True, True, "wish ping")

    if not rules.enabled:
        return ClaimDecision(False, False, "character claim disabled")

    kakera = fields.get("total_kakera")
    try:
        kakera_int = int(kakera) if kakera is not None else None
    except (TypeError, ValueError):
        kakera_int = None

    instant_triggers: list[str] = []
    if rules.min_kakera is not None and kakera_int is not None and kakera_int >= rules.min_kakera:
        instant_triggers.append(f"kakera {kakera_int} ≥ {rules.min_kakera}")
    if rules.max_claim_rank is not None and _ranked_within(
        fields.get("claim_rank"), rules.max_claim_rank
    ):
        instant_triggers.append(
            f"claim rank #{fields.get('claim_rank')} ≤ {rules.max_claim_rank}"
        )

    if instant_triggers:
        return ClaimDecision(True, True, " + ".join(instant_triggers))

    # No immediate trigger fired — defer to end-of-batch picker.
    if rules.only_final_hour and not final_hour:
        return ClaimDecision(False, False, "saving claim for final hour")

    # Eligible to be considered by end-of-batch picker.
    return ClaimDecision(False, False, "eligible at end of batch")


# ---------------------------------------------------------------------------
# Kakera reaction


def passes_kakera_reaction(
    fields: dict[str, Any],
    rules: KakeraReactionRules,
    state: AccountState,
    *,
    message_id: int | None = None,
    now: Any = None,
) -> ReactionDecision:
    """Which kakera buttons (if any) should be clicked on a roll?"""
    if not rules.enabled:
        return ReactionDecision(reason="kakera reaction off")

    buttons = fields.get("buttons") or []
    kakera_buttons = [
        b
        for b in buttons
        if isinstance(b, dict) and b.get("is_kakera") and not b.get("disabled")
    ]
    if not kakera_buttons:
        return ReactionDecision(reason="no kakera buttons")

    if (
        rules.require_perk_8
        and not fields.get("perk_8")
        and not perk8_requirements_relaxed(perk8_mode_from_state(state))
    ):
        return ReactionDecision(reason="needs perk 8")
    if not _spheres_meets(fields.get("spheres"), rules.min_spheres):
        return ReactionDecision(reason=f"needs ≥{rules.min_spheres} spheres")

    refresh_reaction_power(state)
    has_chaos = _has_chaos_key(fields)
    has_perk_8 = bool(fields.get("perk_8"))
    power_display = display_reaction_power(state.power_percent)

    # Perk-8 characters always use the perk-8 colour list (Reactions tab), even
    # after 40/40 and on $us rolls whose types_allowed is a narrower override.
    # Equal clicking only unblocks non-perk-8 rolls onto the main filter.
    saving = perk8_is_saving(state, rules)
    if rules.perk_8_budget_mode and bool(fields.get("perk_8")):
        types_allowed = list(rules.perk_8_types_allowed)
    else:
        types_allowed = list(rules.types_allowed)
    using_low_power = False
    if (
        rules.low_power
        and state.power_percent is not None
        and state.power_percent < rules.low_power.below_percent
    ):
        types_allowed = list(rules.low_power.types_allowed)
        using_low_power = True

    def matches_filter(button: dict[str, Any]) -> bool:
        if not types_allowed:
            return True
        return _kakera_emoji(button) in types_allowed

    selected = [b for b in kakera_buttons if matches_filter(b)]
    if not selected:
        filter_label = ",".join(types_allowed) if types_allowed else "any"
        return ReactionDecision(reason=f"no kakera button matched filter [{filter_label}]")

    if rules.require_chaos_key and not has_chaos:
        bypass = chaos_key_bypass_types(rules)
        chaos_ok = [b for b in selected if _kakera_emoji(b) in bypass]
        if not chaos_ok:
            return ReactionDecision(reason="needs chaos key")
        selected = chaos_ok

    affordable: list[dict[str, Any]] = []
    for button in selected:
        cost = reaction_power_cost(
            kakera_emoji=_kakera_emoji(button),
            has_chaos_key=has_chaos,
            has_perk_8=has_perk_8,
            base_cost=kakera_base_cost_from_state(state),
        )
        if can_afford_reaction(state, cost):
            affordable.append(button)
    if not affordable:
        if state.power_percent is None:
            return ReactionDecision(reason="reaction power unknown")
        return ReactionDecision(
            reason=f"insufficient reaction power ({power_display}%)"
        )
    selected = affordable

    # While clicks remain, skip non-perk-8 rolls except bypass types (purple by
    # default). Once the daily quota is used, fall through to equal clicking.
    if saving and not fields.get("perk_8"):
        bypass = perk8_budget_bypass_types(rules)
        bypass_selected = [b for b in selected if _kakera_emoji(b) in bypass]
        if bypass_selected:
            selected = bypass_selected
        else:
            return ReactionDecision(reason="saving perk-8 kakera budget")

    if power_save_enabled(rules):
        selected = _filter_perk8_power_reserve(
            selected,
            fields,
            rules,
            state,
            now=now,
        )
        if not selected:
            return ReactionDecision(reason="reserving power for perk-8 burst")

    choices = [_make_button_choice(message_id, b) for b in selected]
    reason_parts = [f"{len(choices)} kakera"]
    if using_low_power:
        reason_parts.append(
            f"low-power [{','.join(types_allowed) or 'all'}] @ {power_display}%"
        )
    elif types_allowed:
        reason_parts.append(f"filter [{','.join(types_allowed)}]")
    if saving:
        bypass = perk8_budget_bypass_types(rules)
        if not fields.get("perk_8") and any(
            _kakera_emoji(b) in bypass for b in (fields.get("buttons") or [])
        ):
            bypassed = sorted(
                {_kakera_emoji(b) for b in selected if _kakera_emoji(b) in bypass}
            )
            if bypassed:
                reason_parts.append(f"budget bypass [{','.join(bypassed)}]")
        reason_parts.append(
            f"budget {state.kakera_clicks_today}/{perk8_click_budget(state, rules)}"
        )

    return ReactionDecision(buttons=choices, reason=" · ".join(reason_parts))


def perk8_mode_from_state(state: AccountState) -> Perk8PriorityMode:
    try:
        return Perk8PriorityMode(state.perk8_priority_mode)
    except ValueError:
        return Perk8PriorityMode.INACTIVE


def perk8_is_saving(state: AccountState, rules: KakeraReactionRules) -> bool:
    """True while budget mode should hoard clicks for perk-8 characters.

    Off when ``perk_8_priority`` is False: perk-8 characters still use the
    perk-8 colour list, but other rolls click as they appear.
    """
    if not rules.perk8_priority_on():
        return False
    if not perk8_budget_applies(perk8_mode_from_state(state)):
        return False
    return state.remaining_kakera_budget(perk8_click_budget(state, rules)) > 0


def counts_toward_perk8_budget(
    *,
    emoji: str,
    perk8: bool,
    rules: KakeraReactionRules,
) -> bool:
    """Paid reacts that spend Mudae's perk-8 daily quota (or the local stand-in).

    Bypass types on *non*-perk-8 rolls are free of the quota. The same emoji on
    a perk-8 character still uses a daily click, so it must increment the count.
    """
    from macro.reaction_power import KAKERA_FREE_REACT_EMOJIS

    if (emoji or "") in KAKERA_FREE_REACT_EMOJIS:
        return False
    if perk8:
        return True
    return (emoji or "") not in perk8_budget_bypass_types(rules)


def slice_kakera_budget_candidates(
    candidates: list[ButtonChoice],
    *,
    remaining: int,
    perk8: bool,
    rules: KakeraReactionRules,
) -> list[ButtonChoice]:
    """Keep free clicks, then at most ``remaining`` clicks that use the 40.

    Bypass colours on a *non*-perk-8 roll do not use the daily quota (they
    still cost power, except purple). The same colours on a perk-8 character
    do use a slot, so they sit in the paid slice.
    """
    free: list[ButtonChoice] = []
    paid: list[ButtonChoice] = []
    for choice in candidates:
        if counts_toward_perk8_budget(
            emoji=choice.emoji or "",
            perk8=perk8,
            rules=rules,
        ):
            paid.append(choice)
        else:
            free.append(choice)
    return free + paid[: max(0, int(remaining))]


def _filter_perk8_power_reserve(
    selected: list[dict[str, Any]],
    fields: dict[str, Any],
    rules: KakeraReactionRules,
    state: AccountState,
    *,
    now: Any = None,
) -> list[dict[str, Any]]:
    """Drop paid non-perk-8 buttons that would break the perk-8 power floor."""
    if not selected or fields.get("perk_8"):
        return selected

    stamp = now if now is not None else utc_now()
    remaining = remaining_perk8_clicks(state)
    window_sec = window_sec_from_rules(rules)
    until_midnight = seconds_until_midnight(stamp)
    cap = perk8_click_budget(state, rules)
    bar = snapshot_from_state(state, now=stamp)
    kept: list[dict[str, Any]] = []
    for button in selected:
        cost = reaction_power_cost(
            kakera_emoji=_kakera_emoji(button),
            has_chaos_key=True,
            has_perk_8=False,
            base_cost=kakera_base_cost_from_state(state),
        )
        if cost <= 0:
            kept.append(button)
            continue
        if should_spend_paid_non_perk8(
            bar,
            cost=cost,
            remaining=remaining,
            window_sec=window_sec,
            until_midnight_sec=until_midnight,
            click_cap=cap,
        ):
            kept.append(button)
            bar = replace(bar, power=max(0.0, float(bar.power) - float(cost)))
    return kept


def perk8_click_budget(state: AccountState, rules: KakeraReactionRules) -> int:
    """Daily click cap: ``$ohu8``-reported max when known, otherwise 40."""
    del rules  # kept for call-site symmetry
    if state.perk8_click_max is not None:
        return max(1, int(state.perk8_click_max))
    return PERK8_DAILY_CLICK_BUDGET


def perk8_budget_bypass_types(rules: KakeraReactionRules) -> frozenset[str]:
    """Kakera emojis that ignore perk-8 daily budget saving."""
    if rules.perk_8_budget_bypass_types:
        return frozenset(rules.perk_8_budget_bypass_types)
    return frozenset({"kakeraP"})


def chaos_key_bypass_types(rules: KakeraReactionRules) -> frozenset[str]:
    """Kakera emojis that ignore the chaos-key requirement."""
    if rules.require_chaos_key_bypass_types:
        return frozenset(rules.require_chaos_key_bypass_types)
    return frozenset({"kakeraP"})


# ---------------------------------------------------------------------------
# Sphere reaction


def passes_sphere_reaction(
    fields: dict[str, Any],
    rules: SphereReactionRules,
    state: AccountState,
    *,
    message_id: int | None = None,
    threshold_ctx: Perk9ThresholdContext | None = None,
) -> ReactionDecision:
    """Which sphere buttons (if any) should be clicked on a roll?"""
    del state  # currently unused, kept for symmetry
    if not rules.enabled:
        return ReactionDecision(reason="sphere reaction off")

    buttons = fields.get("buttons") or []
    sphere_buttons = [
        b
        for b in buttons
        if isinstance(b, dict) and b.get("is_sphere") and not b.get("disabled")
    ]
    if not sphere_buttons:
        return ReactionDecision(reason="no sphere buttons")

    def matches_filter(button: dict[str, Any]) -> bool:
        emoji = _sphere_emoji(button)
        if emoji in SPHERE_ROLL_FREE_EMOJIS:
            return True
        return _sphere_matches_filter(emoji, rules.types_allowed)

    selected = [b for b in sphere_buttons if matches_filter(b)]
    if not selected:
        return ReactionDecision(
            reason=f"no sphere button matched filter [{','.join(rules.types_allowed)}]"
        )

    budget_ctx = threshold_ctx if rules.budget_aware else None
    if budget_ctx is not None:
        # Megasphere is free and never spends a perk-9 slot, so it skips the gate.
        kept = [
            b
            for b in selected
            if _sphere_emoji(b) in SPHERE_ROLL_FREE_EMOJIS
            or budget_ctx.should_click(_sphere_emoji(b))
        ]
        if not kept:
            bar = budget_ctx.threshold()
            return ReactionDecision(
                reason=(
                    f"perk9 budget: below EV bar {bar:.0f} "
                    f"({budget_ctx.clicks_left} clicks / "
                    f"{budget_ctx.opportunities_left} spawns left)"
                )
            )
        selected = kept

    choices = [_make_button_choice(message_id, b) for b in selected]
    reason = f"{len(choices)} sphere"
    if budget_ctx is not None:
        reason += (
            f" perk9 EV bar {budget_ctx.threshold():.0f}"
            f" ({budget_ctx.clicks_left} left)"
        )
    elif rules.types_allowed:
        reason += f" filter [{','.join(rules.types_allowed)}]"
    return ReactionDecision(buttons=choices, reason=reason)
