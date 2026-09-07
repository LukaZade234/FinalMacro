"""When to distrust the perk-8 count and ask Mudae again.

The macro's perk-8 tally is a **belief**. It is set by ``$ohu8`` and then moved
only by the macro's own clicks, and `macro/rule_eval.py` spends that belief:
while it says clicks remain, every paid non-perk-8 roll is skipped so the slots
are saved for perk-8 characters, which are half price.

`macro/perk8_daily.should_query_ohu8_on_refill` re-asks only when the record is
**exhausted** or the refill has **passed**. Neither covers a belief that is
simply wrong, which is how this was reported on 2026-09-07:

    last_clicked: 38 / 40   clicks_exhausted: false
    refill_at:  2026-09-08T00:00Z   updated_at: 2026-09-07T03:01Z

Mudae was at 40/40. Two clicks the macro never counted left it holding slots
that no longer existed, and nothing in the gate above could notice for the ~21
hours until midnight. Power pinned at the cap, ``$dk`` went unspent, and no
paid kakera was clicked all night.

The three reasons below are what a wrong belief actually looks like from
inside the macro. Each is a reason to *ask*, never an answer: they all end in
one ``$ohu8`` and Mudae's number wins.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from mudae.clock import utc_now

# A perk-8 character is a minority of rolls, so a quiet stretch is normal — but
# not this quiet. At a typical pool a two-hour silence while the macro still
# believes slots remain is far outside what the spawn rate explains.
PERK8_SILENCE_SEC = 2 * 60 * 60

# The bar refuses to grow past its cap, so every minute pinned is regen thrown
# away. Long enough not to fire on the moment before a click lands.
POWER_PINNED_SEC = 10 * 60


@dataclass(frozen=True)
class RecheckReason:
    """Why an ``$ohu8`` is worth spending, phrased for the run log."""

    key: str
    detail: str


def _parse(stamp: Any) -> dt.datetime | None:
    text = str(stamp or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _elapsed(stamp: Any, now: dt.datetime) -> float | None:
    parsed = _parse(stamp)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds())


def perk8_recheck_reason(
    state: Any,
    *,
    remaining: int,
    power_pinned: bool,
    now: dt.datetime | None = None,
    silence_sec: float = PERK8_SILENCE_SEC,
    pinned_sec: float = POWER_PINNED_SEC,
) -> RecheckReason | None:
    """The first reason to re-query ``$ohu8``, or ``None`` to keep the cache.

    ``remaining`` is what the macro currently believes is left. Two of the three
    reasons only make sense while that is above zero — a belief of zero is the
    safe direction to be wrong in, because it spends rather than hoards.
    """
    stamp = now or utc_now()

    # Mudae said so itself. Cheapest and most certain, so it goes first, and it
    # holds even at a believed zero: confirming is how the flag gets cleared.
    if getattr(state, "perk8_final_notice", False):
        return RecheckReason(
            "final_notice",
            "Mudae announced the day's last perk-8 click",
        )

    if int(remaining) <= 0:
        return None

    quiet = _elapsed(getattr(state, "perk8_last_seen_at", ""), stamp)
    if quiet is not None and quiet >= silence_sec:
        return RecheckReason(
            "perk8_silence",
            f"no perk-8 character in {quiet / 3600:.1f}h "
            f"while {int(remaining)} click(s) are believed left",
        )

    if power_pinned:
        pinned = _elapsed(getattr(state, "power_pinned_since", ""), stamp)
        if pinned is not None and pinned >= pinned_sec:
            return RecheckReason(
                "power_pinned",
                f"power has been at its cap for {pinned / 60:.0f}m "
                f"while {int(remaining)} perk-8 click(s) are believed left",
            )

    return None


def note_perk8_seen(state: Any, *, now: dt.datetime | None = None) -> None:
    """A perk-8 character spawned or was clicked — the belief is fresh again."""
    state.perk8_last_seen_at = (now or utc_now()).isoformat()


def note_power_level(
    state: Any,
    *,
    pinned: bool,
    now: dt.datetime | None = None,
) -> None:
    """Track how long the bar has been at its cap.

    Only the *first* pinned observation sets the clock; spending below the cap
    clears it, so the elapsed time always means "pinned continuously since".
    """
    if not pinned:
        state.power_pinned_since = ""
        return
    if not getattr(state, "power_pinned_since", ""):
        state.power_pinned_since = (now or utc_now()).isoformat()


def note_perk8_final_notice(state: Any) -> None:
    """Mudae printed ``($op 8) … for today`` on a kakera claim."""
    state.perk8_final_notice = True


def clear_recheck_flags(state: Any, *, now: dt.datetime | None = None) -> None:
    """Called once ``$ohu8`` has answered, whatever it said.

    ``perk8_last_seen_at`` is restamped rather than blanked: the count is
    verified as of now, so the silence clock restarts from the answer instead of
    firing again on the next poll.
    """
    state.perk8_final_notice = False
    state.perk8_last_seen_at = (now or utc_now()).isoformat()
