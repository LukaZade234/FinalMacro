"""Tests for roll-loop timing math and wait loops (no engine, no real clock)."""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

from macro.config import MacroConfig
from macro.perk8_daily import Perk8DailyRecord
from macro.roll_context import RollContext
from macro.roll_scheduler import (
    ROLLS_RESET_BUFFER_SEC,
    STOP_CHECK_SEC,
    next_wake_step,
    seconds_until_perk8_refill,
    seconds_until_rolls_reset,
    sleep_interruptible,
    wait_for_scheduled_wake,
)
from macro.state import AccountState


def _at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 8, 1, hour, minute, tzinfo=dt.timezone.utc)


# --- hourly rolls reset -------------------------------------------------------


def test_seconds_until_rolls_reset_adds_buffer():
    assert seconds_until_rolls_reset(30) == 30 * 60 + ROLLS_RESET_BUFFER_SEC


def test_seconds_until_rolls_reset_unknown_returns_zero():
    """No parsed reset time means re-check now rather than sleep blind."""
    assert seconds_until_rolls_reset(None) == 0.0


def test_seconds_until_rolls_reset_never_negative():
    assert seconds_until_rolls_reset(0) == ROLLS_RESET_BUFFER_SEC
    assert seconds_until_rolls_reset(-10, buffer_sec=0.0) == 0.0


# --- perk-8 refill boundary ---------------------------------------------------


def _exhausted_at(refill_at: dt.datetime) -> Perk8DailyRecord:
    return Perk8DailyRecord(clicks_exhausted=True, refill_at=refill_at.isoformat())


def test_perk8_refill_returns_remaining_seconds():
    record = _exhausted_at(_at(3))
    assert seconds_until_perk8_refill(record, now=_at(2, 59)) == 60.0


def test_perk8_refill_zero_once_deadline_passed():
    record = _exhausted_at(_at(3))
    assert seconds_until_perk8_refill(record, now=_at(3, 1)) == 0.0
    assert seconds_until_perk8_refill(record, now=_at(3)) == 0.0


def test_perk8_refill_none_when_clicks_not_exhausted():
    """No timed wake needed — a long sleep must not be interrupted."""
    record = Perk8DailyRecord(clicks_exhausted=False, refill_at=_at(3).isoformat())
    assert seconds_until_perk8_refill(record, now=_at(1)) is None


def test_perk8_refill_none_without_recorded_deadline():
    assert seconds_until_perk8_refill(Perk8DailyRecord(clicks_exhausted=True)) is None


def test_perk8_refill_none_on_corrupt_timestamp():
    record = Perk8DailyRecord(clicks_exhausted=True, refill_at="not-a-timestamp")
    assert seconds_until_perk8_refill(record, now=_at(1)) is None


def test_perk8_refill_handles_zulu_and_naive_timestamps():
    """Stored values have used both forms; neither may raise on comparison."""
    zulu = Perk8DailyRecord(clicks_exhausted=True, refill_at="2026-08-01T03:00:00Z")
    naive = Perk8DailyRecord(clicks_exhausted=True, refill_at="2026-08-01T03:00:00")

    assert seconds_until_perk8_refill(zulu, now=_at(2)) == 3600.0
    assert seconds_until_perk8_refill(naive, now=_at(2)) == 3600.0


# --- wake slicing -------------------------------------------------------------


def test_wake_step_capped_so_stop_stays_responsive():
    assert next_wake_step(600.0, wake_seconds=None) == STOP_CHECK_SEC


def test_wake_step_never_overshoots_remaining():
    assert next_wake_step(0.25, wake_seconds=None) == 0.25
    assert next_wake_step(0.0, wake_seconds=None) == 0.0
    assert next_wake_step(-5.0, wake_seconds=None) == 0.0


def test_wake_step_shortens_for_imminent_perk8_refill():
    assert next_wake_step(600.0, wake_seconds=0.3) == 0.3


def test_wake_step_ignores_distant_or_passed_perk8_refill():
    # Further away than the stop-check slice — no need to shorten.
    assert next_wake_step(600.0, wake_seconds=90.0) == STOP_CHECK_SEC
    # Already due (0.0) is handled by the caller, not by shortening to zero.
    assert next_wake_step(600.0, wake_seconds=0.0) == STOP_CHECK_SEC


# --- wait loops ---------------------------------------------------------------


def _ctx(*, stopped: bool = False) -> tuple[RollContext, list[float]]:
    """A context whose sleep is a recorder, so waits are instant and inspectable."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    stop = asyncio.Event()
    if stopped:
        stop.set()
    ctx = RollContext(
        actions=SimpleNamespace(),
        config=MacroConfig(),
        state=AccountState(),
        monitor=SimpleNamespace(is_connected=True),
        stop=stop,
        sleep=fake_sleep,
    )
    return ctx, slept


def test_sleep_interruptible_covers_the_full_duration():
    ctx, slept = _ctx()

    assert asyncio.run(sleep_interruptible(3.0, ctx=ctx)) is True
    assert sum(slept) == 3.0
    assert max(slept) <= STOP_CHECK_SEC


def test_sleep_interruptible_returns_false_when_already_stopped():
    ctx, slept = _ctx(stopped=True)

    assert asyncio.run(sleep_interruptible(3.0, ctx=ctx)) is False
    assert slept == []


def test_sleep_interruptible_bails_partway_through():
    """Stop pressed mid-wait: the loop gives up instead of serving out the hour."""
    ctx, slept = _ctx()

    async def stop_on_third_slice(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 3:
            ctx.stop.set()

    ctx.sleep = stop_on_third_slice

    assert asyncio.run(sleep_interruptible(3600.0, ctx=ctx)) is False
    assert len(slept) == 3


def test_scheduled_wake_without_a_hint_just_sleeps():
    ctx, slept = _ctx()
    calls: list[int] = []

    async def on_wake() -> None:
        calls.append(1)

    assert asyncio.run(
        wait_for_scheduled_wake(3.0, ctx=ctx, wake_hint=lambda: None, on_wake=on_wake)
    ) is True
    assert sum(slept) == 3.0
    assert calls == []


def test_scheduled_wake_fires_when_the_hint_comes_due():
    """The slice is shortened to land on the hint, then the callback runs."""
    ctx, slept = _ctx()
    calls: list[int] = []

    async def on_wake() -> None:
        calls.append(1)
        hint[0] = None  # the refresh happened; nothing pending now

    hint: list[float | None] = [0.4]

    assert asyncio.run(
        wait_for_scheduled_wake(3.0, ctx=ctx, wake_hint=lambda: hint[0], on_wake=on_wake)
    ) is True
    assert calls == [1]
    assert 0.4 in slept
    assert sum(slept) == 3.0


def test_scheduled_wake_fires_immediately_for_an_overdue_hint():
    ctx, _slept = _ctx()
    calls: list[int] = []
    hint: list[float | None] = [0.0]

    async def on_wake() -> None:
        calls.append(1)
        hint[0] = None

    asyncio.run(
        wait_for_scheduled_wake(2.0, ctx=ctx, wake_hint=lambda: hint[0], on_wake=on_wake)
    )

    assert calls == [1]


def test_scheduled_wake_rereads_a_hint_that_appears_mid_wait():
    """Nothing scheduled at first; a refill deadline shows up partway through."""
    ctx, _slept = _ctx()
    calls: list[int] = []
    elapsed = {"slices": 0}

    def wake_hint() -> float | None:
        elapsed["slices"] += 1
        return 0.5 if elapsed["slices"] > 2 and not calls else None

    async def on_wake() -> None:
        calls.append(1)

    asyncio.run(
        wait_for_scheduled_wake(5.0, ctx=ctx, wake_hint=wake_hint, on_wake=on_wake)
    )

    assert calls == [1]


def test_scheduled_wake_stops_without_running_the_callback():
    ctx, slept = _ctx(stopped=True)
    calls: list[int] = []

    async def on_wake() -> None:
        calls.append(1)

    assert asyncio.run(
        wait_for_scheduled_wake(5.0, ctx=ctx, wake_hint=lambda: 0.0, on_wake=on_wake)
    ) is False
    assert calls == []
    assert slept == []
