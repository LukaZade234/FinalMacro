"""Early-stop conditions during the roll loop (before normal end-of-run claim)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RollInterrupt:
    """Roll loop should stop and act on this roll immediately."""

    code: str
    reason: str


@dataclass
class RollInterruptContext:
    fields: dict[str, Any]
    own_user_ids: list[int]


RollInterruptCheck = Callable[[RollInterruptContext], RollInterrupt | None]


def check_wish_pinged_user(ctx: RollInterruptContext) -> RollInterrupt | None:
    """
    Wishlist drop that pings the running account.

    ``wished_by`` must include at least one of ``own_user_ids``. Pings for
  other users only are ignored.
    """
    wished_by = ctx.fields.get("wished_by")
    if not wished_by or not ctx.own_user_ids:
        return None
    try:
        wished_ids = {int(uid) for uid in wished_by}
    except (TypeError, ValueError):
        return None
    own_ids = {int(uid) for uid in ctx.own_user_ids}
    if wished_ids & own_ids:
        return RollInterrupt(
            code="wish_ping",
            reason="Wish rolled and pinged you",
        )
    return None


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
