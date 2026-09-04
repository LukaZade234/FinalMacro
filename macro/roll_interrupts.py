"""Early-stop conditions during the roll loop (before normal end-of-run claim).

Wish ping is preserved as a discrete check; preset rule blocks now drive the
"instant claim trigger" path through :func:`macro.rule_eval.passes_character_claim`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from macro.config import CharacterClaimRules
from macro.rule_eval import passes_character_claim
from macro.state import AccountState
from macro.wishlist import match_wishlist


@dataclass(frozen=True)
class RollInterrupt:
    """Roll loop should stop and act on this roll immediately."""

    code: str
    reason: str


@dataclass
class RollInterruptContext:
    fields: dict[str, Any]
    own_user_ids: list[int]
    wishlist_characters: list[str] = field(default_factory=list)
    wishlist_series: list[str] = field(default_factory=list)


RollInterruptCheck = Callable[[RollInterruptContext], RollInterrupt | None]


def _wished_pinged(fields: dict[str, Any], own_user_ids: list[int]) -> bool:
    wished_by = fields.get("wished_by")
    if not wished_by or not own_user_ids:
        return False
    try:
        wished_ids = {int(uid) for uid in wished_by}
    except (TypeError, ValueError):
        return False
    own_ids = {int(uid) for uid in own_user_ids}
    return bool(wished_ids & own_ids)


def check_wish_pinged_user(ctx: RollInterruptContext) -> RollInterrupt | None:
    """
    Wishlist drop that pings the running account.

    ``wished_by`` must include at least one of ``own_user_ids``. Pings for
    other users only are ignored.
    """
    if _wished_pinged(ctx.fields, ctx.own_user_ids):
        return RollInterrupt(
            code="wish_ping",
            reason="Wish rolled and pinged you",
        )
    return None


def check_app_wishlist_match(ctx: RollInterruptContext) -> RollInterrupt | None:
    """A roll matches the app-only character/series wishlist.

    Same ``code="wish_ping"`` as a real Mudae ping, so the roll loop's `$rt`
    spend and "stop after wish claim" logic (both keyed on that code) apply
    unchanged. Unlike :func:`check_wish_pinged_user` this guards
    ``claimed``/``can_claim`` itself — Mudae only ever pings a wish on a roll
    that is genuinely claimable, but an app-side name/series match has no
    such guarantee (an edited message reprocessed, say), so it must not
    fire a claim attempt at a roll that is already gone.
    """
    if ctx.fields.get("claimed") or not ctx.fields.get("can_claim"):
        return None
    reason = match_wishlist(ctx.fields, ctx.wishlist_characters, ctx.wishlist_series)
    if reason is None:
        return None
    return RollInterrupt(code="wish_ping", reason=f"Wishlist match — {reason}")


# Register new checks here (order = priority).
ROLL_INTERRUPT_CHECKS: tuple[RollInterruptCheck, ...] = (
    check_wish_pinged_user,
)


def evaluate_roll_interrupts(ctx: RollInterruptContext) -> RollInterrupt | None:
    """First matching interrupt wins."""
    for check in ROLL_INTERRUPT_CHECKS:
        hit = check(ctx)
        if hit is not None:
            return hit
    return None


def evaluate_claim_trigger(
    ctx: RollInterruptContext,
    rules: CharacterClaimRules,
    state: AccountState,
    *,
    final_hour: bool,
) -> RollInterrupt | None:
    """Bridge legacy ``evaluate_roll_interrupts`` to the new rule block.

    Returns a ``RollInterrupt`` only when the rules say *claim now*. Defer /
    eligible / skip decisions are *not* interrupts and stay on the deferred path.
    """
    legacy = evaluate_roll_interrupts(ctx)
    if legacy is not None:
        return legacy

    # Gated on the same toggle a real wish ping uses, unlike the Mudae-side
    # check above: that one bypasses ``rules`` entirely (Mudae's own ping is
    # unconditional today), but there is no reason a fresh app feature should
    # inherit that rather than just respecting "claim on wish ping".
    if rules.claim_on_wish_ping:
        wishlist_hit = check_app_wishlist_match(ctx)
        if wishlist_hit is not None:
            return wishlist_hit

    wished = _wished_pinged(ctx.fields, ctx.own_user_ids)
    decision = passes_character_claim(
        ctx.fields,
        rules,
        state,
        final_hour=final_hour,
        wished_pinged=wished,
    )
    if decision.should_claim and decision.immediate:
        return RollInterrupt(code="rule_trigger", reason=decision.reason)
    return None
