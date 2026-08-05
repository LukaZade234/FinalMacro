"""Tests for Mudae reset schedule extrapolation."""

from __future__ import annotations

import datetime as dt

from macro.reset_schedule import (
    MudaeResetSchedule,
    advance_periodic_deadline,
    count_hourly_resets_between,
    next_hourly_reset_at,
)


def _utc(y, m, d, h, mi=0) -> dt.datetime:
    return dt.datetime(y, m, d, h, mi, tzinfo=dt.timezone.utc)


def test_next_hourly_reset_respects_shift():
    schedule = MudaeResetSchedule(setinterval=0, shifthour=15)
    now = _utc(2026, 8, 4, 12, 10)
    nxt = next_hourly_reset_at(now, schedule)
    assert nxt == _utc(2026, 8, 4, 12, 15)


def test_advance_periodic_deadline_counts_crossings():
    deadline = _utc(2026, 8, 4, 12, 0).isoformat()
    now = _utc(2026, 8, 4, 13, 30)
    advance = advance_periodic_deadline(deadline, 60, now)
    assert advance.periods_crossed == 2
    assert advance.minutes_remaining == 30


def test_count_hourly_resets_between():
    schedule = MudaeResetSchedule(setinterval=0, shifthour=0)
    start = _utc(2026, 8, 4, 10, 30)
    end = _utc(2026, 8, 4, 12, 30)
    assert count_hourly_resets_between(start, end, schedule) == 2
