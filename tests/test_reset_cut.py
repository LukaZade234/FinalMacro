"""A batch still rolling at the hourly reset stops there and starts the new hour over."""

from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import patch

from macro.roll_scheduler import seconds_until_rolls_reset_estimate
from tests.test_chaos import _fast_sleep, _noop_claim_best, _segment_engine

UTC = dt.timezone.utc


def test_estimate_snaps_tu_rounded_up_minutes_to_the_real_reset():
    # $tu at 12:45:17 said "15m": the reset is 13:00, not 13:00:17.
    read = dt.datetime(2026, 11, 6, 12, 45, 17, tzinfo=UTC)
    reset_at = (read + dt.timedelta(minutes=15)).isoformat()
    now = dt.datetime(2026, 11, 6, 12, 59, 50, tzinfo=UTC)
    assert seconds_until_rolls_reset_estimate(reset_at, now=now) == 10.0
    after = dt.datetime(2026, 11, 6, 13, 0, 5, tzinfo=UTC)
    assert seconds_until_rolls_reset_estimate(reset_at, now=after) == -5.0
    assert seconds_until_rolls_reset_estimate("", now=now) is None


def _reset_in(seconds: float) -> str:
    return (dt.datetime.now(UTC) + dt.timedelta(seconds=seconds)).replace(
        second=0, microsecond=0
    ).isoformat()


def _run_segment(engine, rolls: int) -> int:
    async def _case() -> int:
        engine._claim_best_at_session_end = _noop_claim_best
        engine._stop.clear()
        with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
            done, _c, _i = await engine._roll_hourly_normal_segment(
                "wa", [], 0, normal_rolls=rolls
            )
        return done

    return asyncio.run(_case())


def test_batch_stops_when_the_reset_is_due():
    engine, state, actions = _segment_engine(grant_on=0, grant=0)
    state.rolls_left = 50
    state.rolls_reset_at = (dt.datetime.now(UTC) - dt.timedelta(seconds=1)).isoformat()
    assert _run_segment(engine, 50) == 0
    assert actions.rolls_served == 0
    assert engine._batch_cut_at_reset is True


def test_batch_rolls_on_when_the_reset_is_far():
    engine, state, actions = _segment_engine(grant_on=0, grant=0)
    state.rolls_left = 5
    state.rolls_reset_at = _reset_in(30 * 60)
    assert _run_segment(engine, 5) == 5
    assert engine._batch_cut_at_reset is False


def test_final_hour_cuts_earlier_so_the_claim_lands_before_the_reset():
    engine, state, _actions = _segment_engine(grant_on=0, grant=0)
    state.rolls_reset_at = "set"
    with patch("macro.roll_cycle.seconds_until_rolls_reset_estimate", return_value=10.0):
        engine._final_roll_session = False
        assert engine._rolls_reset_due() is False
        engine._final_roll_session = True
        assert engine._rolls_reset_due() is True


def test_cycle_restarts_from_tu_after_a_cut():
    """The new hour goes through $tu (and the steps after it), not the stale count."""
    from tests.test_roll_cycle import _FakeActions, _make_engine, _roll, _run_normal, _tu

    actions = _FakeActions(
        tu_script=[_tu(10, 30), _tu(0, 30)],
        roll_script=[_roll(i, None) for i in range(1, 11)],
    )
    engine, state = _make_engine(actions)
    checks = {"n": 0}

    def _due() -> bool:
        checks["n"] += 1
        return checks["n"] > 2  # the reset arrives after two rolls

    async def _past_reset() -> bool:
        return True

    engine._rolls_reset_due = _due
    engine._wait_past_reset_after_cut = _past_reset
    _run_normal(engine)
    cmds = [c for c, _ in actions.sent]
    assert cmds[:4] == ["tu", "wa", "wa", "tu"]
    assert any("Rolls reset is due" in e.text for e in state.activity_log)
