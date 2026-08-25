"""Timing math for the roll loops, plus the wait loops built on it.

The arithmetic is pure so it is testable without a clock or an event loop, and
the loops take their sleep from ``RollContext`` rather than calling
``asyncio.sleep`` directly — so tests inject a fake clock instead of patching a
module global, and each account waits on its own.

Nothing here knows what a caller wants to wake up early *for*; that arrives as a
``wake_hint`` callback, so perk-8 is one caller rather than something baked in.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable

from macro.perk8_daily import Perk8DailyRecord, parse_iso
from macro.roll_context import RollContext

# Seconds until something wants an early wake; ``None`` when nothing is scheduled.
WakeHint = Callable[[], float | None]
WakeCallback = Callable[[], Awaitable[object]]

# Pad after the parsed reset time before re-checking ``$tu``, so a slightly fast
# local clock does not ask Mudae before the rolls actually land.
ROLLS_RESET_BUFFER_SEC = 5.0
# Wake interval during long waits so Stop stays responsive.
STOP_CHECK_SEC = 1.0


def seconds_until_rolls_reset(
    reset_minutes: int | None,
    *,
    buffer_sec: float = ROLLS_RESET_BUFFER_SEC,
) -> float:
    """Seconds until the next hourly rolls reset reported by the last ``$tu``.

    Returns ``0.0`` when the reset time is unknown, so the caller re-checks
    rather than sleeping blind.
    """
    if reset_minutes is None:
        return 0.0
    return max(0.0, reset_minutes * 60.0 + buffer_sec)


def seconds_until_perk8_refill(
    record: Perk8DailyRecord,
    *,
    now: dt.datetime | None = None,
) -> float | None:
    """Seconds until perk-8 daily clicks return, or ``0.0`` if that already passed.

    ``None`` means no timed wake is needed — clicks are not exhausted, or no
    refill deadline was ever recorded — so a long sleep must not be interrupted
    to re-query ``$ohu8``.
    """
    if not record.clicks_exhausted or not record.refill_at:
        return None
    refill_at = parse_iso(record.refill_at)
    if refill_at is None:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    if now >= refill_at:
        return 0.0
    return (refill_at - now).total_seconds()


def next_wake_step(
    remaining: float,
    *,
    wake_seconds: float | None,
    stop_check_sec: float = STOP_CHECK_SEC,
) -> float:
    """How long the next slice of a long wait should be.

    Capped at ``stop_check_sec`` so Stop stays responsive, and shortened further
    when an early wake lands sooner than that.
    """
    step = min(max(0.0, remaining), stop_check_sec)
    if wake_seconds is not None and 0 < wake_seconds < step:
        step = wake_seconds
    return step


def earliest_wake_seconds(*hints: WakeHint | None) -> WakeHint:
    """Combine wake hints; the soonest deadline wins. ``None`` hints are ignored."""

    def combined() -> float | None:
        values: list[float] = []
        for hint in hints:
            if hint is None:
                continue
            value = hint()
            if value is not None:
                values.append(value)
        return min(values) if values else None

    return combined


async def sleep_interruptible(
    seconds: float,
    *,
    ctx: RollContext,
    stop_check_sec: float = STOP_CHECK_SEC,
) -> bool:
    """Sleep up to ``seconds``. Returns False as soon as a stop is requested."""
    remaining = max(0.0, seconds)
    while remaining > 0:
        if ctx.stop_requested:
            return False
        step = min(remaining, stop_check_sec)
        await ctx.sleep(step)
        remaining -= step
    return True


async def wait_for_scheduled_wake(
    seconds: float,
    *,
    ctx: RollContext,
    wake_hint: WakeHint | None = None,
    on_wake: WakeCallback | None = None,
    stop_check_sec: float = STOP_CHECK_SEC,
) -> bool:
    """Sleep toward a deadline, running ``on_wake`` when ``wake_hint`` comes due.

    ``wake_hint`` is re-read each slice, so a hint that appears or moves partway
    through a long wait is still honoured. Returns False if stopped.
    """
    remaining = max(0.0, seconds)
    while remaining > 0:
        if ctx.stop_requested:
            return False
        hint = wake_hint() if wake_hint is not None else None
        if on_wake is not None and hint is not None and hint <= 0:
            await on_wake()
        step = next_wake_step(
            remaining,
            wake_seconds=hint,
            stop_check_sec=stop_check_sec,
        )
        await ctx.sleep(step)
        remaining -= step
        # The step above was shortened to land on the hint, so it is due now.
        if on_wake is not None and hint is not None and 0 < hint <= step:
            await on_wake()
    return True
