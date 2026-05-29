"""Rule evaluation for the three preset decision blocks.

Each helper inspects parsed roll fields against a rule block and returns a
structured decision + human-readable reason. The rest of the macro consumes
these decisions and is responsible for actually clicking buttons.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from macro.config import (
    CharacterClaimRules,
    KakeraReactionRules,
    SphereReactionRules,
)
from macro.state import AccountState


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
    emoji = _kakera_emoji(button)
    if emoji.startswith("sp") and len(emoji) >= 3:
        return emoji
    return ""


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
    if state.claim_available is False:
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

    if rules.require_chaos_key and not _has_chaos_key(fields):
        return ReactionDecision(reason="needs chaos key")
    if rules.require_perk_8 and not fields.get("perk_8"):
        return ReactionDecision(reason="needs perk 8")
    if not _spheres_meets(fields.get("spheres"), rules.min_spheres):
        return ReactionDecision(reason=f"needs ≥{rules.min_spheres} spheres")

    # Determine which color filter applies. low_power override wins below threshold.
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

    # Perk-8 budget mode: don't click when over budget unless this is a perk-8 character.
    if rules.perk_8_budget_mode and not fields.get("perk_8"):
        remaining = state.remaining_kakera_budget(rules.daily_click_budget)
        if remaining <= 0:
            return ReactionDecision(reason="daily kakera budget exhausted (perk-8 only)")

    choices = [_make_button_choice(message_id, b) for b in selected]
    reason_parts = [f"{len(choices)} kakera"]
    if using_low_power:
        reason_parts.append(
            f"low-power [{','.join(types_allowed) or 'all'}] @ {state.power_percent}%"
        )
    elif types_allowed:
        reason_parts.append(f"filter [{','.join(types_allowed)}]")
    if rules.perk_8_budget_mode:
        reason_parts.append(
            f"budget {state.kakera_clicks_today}/{rules.daily_click_budget}"
        )

    return ReactionDecision(buttons=choices, reason=" · ".join(reason_parts))


# ---------------------------------------------------------------------------
# Sphere reaction


def passes_sphere_reaction(
    fields: dict[str, Any],
    rules: SphereReactionRules,
    state: AccountState,
    *,
    message_id: int | None = None,
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
        if not rules.types_allowed:
            return True
        return _sphere_emoji(button) in rules.types_allowed

    selected = [b for b in sphere_buttons if matches_filter(b)]
    if not selected:
        return ReactionDecision(
            reason=f"no sphere button matched filter [{','.join(rules.types_allowed)}]"
        )

    choices = [_make_button_choice(message_id, b) for b in selected]
    return ReactionDecision(
        buttons=choices,
        reason=f"{len(choices)} sphere"
        + (f" filter [{','.join(rules.types_allowed)}]" if rules.types_allowed else ""),
    )
