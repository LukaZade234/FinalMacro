"""Local-time window math for scheduled ``$us`` drains."""

from __future__ import annotations

import datetime as dt

from macro.us_schedule import (
    containing_window_id,
    hhmm_to_minutes,
    in_local_window,
    load_consumed_window_id,
    normalize_hhmm,
    seconds_until_window_end,
    seconds_until_window_start,
    store_consumed_window_id,
)

_TZ = dt.timezone(dt.timedelta(hours=1))


def _at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 8, 25, hour, minute, tzinfo=_TZ)


def test_normalize_hhmm_accepts_short_forms():
    assert normalize_hhmm("4") == "04:00"
    assert normalize_hhmm("4:00") == "04:00"
    assert normalize_hhmm("04:00") == "04:00"
    assert normalize_hhmm("18:30") == "18:30"
    assert normalize_hhmm("99:00") == "04:00"
    assert hhmm_to_minutes("4:05") == 245


def test_same_day_window_is_half_open():
    assert in_local_window("04:00", "06:00", now=_at(4, 0))
    assert in_local_window("04:00", "06:00", now=_at(5, 59))
    assert not in_local_window("04:00", "06:00", now=_at(6, 0))
    assert not in_local_window("04:00", "06:00", now=_at(3, 59))
    assert not in_local_window("04:00", "06:00", now=_at(12, 0))


def test_overnight_window_wraps_midnight():
    assert in_local_window("22:00", "06:00", now=_at(22, 0))
    assert in_local_window("22:00", "06:00", now=_at(23, 30))
    assert in_local_window("22:00", "06:00", now=_at(0, 10))
    assert in_local_window("22:00", "06:00", now=_at(5, 59))
    assert not in_local_window("22:00", "06:00", now=_at(6, 0))
    assert not in_local_window("22:00", "06:00", now=_at(12, 0))


def test_seconds_until_start_and_end():
    assert seconds_until_window_start("04:00", "06:00", now=_at(5, 0)) == 0.0
    until_start = seconds_until_window_start("04:00", "06:00", now=_at(3, 0))
    assert 3600 - 1 <= until_start <= 3600
    until_end = seconds_until_window_end("04:00", "06:00", now=_at(5, 0))
    assert until_end is not None
    assert 3600 - 1 <= until_end <= 3600
    assert seconds_until_window_end("04:00", "06:00", now=_at(7, 0)) is None


def test_after_window_waits_until_tomorrow():
    until_start = seconds_until_window_start("04:00", "06:00", now=_at(7, 0))
    # 21 hours from 07:00 to 04:00 next day.
    assert 21 * 3600 - 1 <= until_start <= 21 * 3600


def test_containing_window_id_same_day():
    assert containing_window_id("04:00", "06:00", now=_at(5, 0)) == "2026-08-25T04:00"
    assert containing_window_id("04:00", "06:00", now=_at(3, 0)) is None
    assert containing_window_id("04:00", "06:00", now=_at(6, 0)) is None


def test_containing_window_id_overnight():
    assert containing_window_id("22:00", "06:00", now=_at(23, 0)) == "2026-08-25T22:00"
    assert containing_window_id("22:00", "06:00", now=_at(1, 0)) == "2026-08-24T22:00"
    assert containing_window_id("22:00", "06:00", now=_at(12, 0)) is None


def test_consumed_window_id_roundtrip():
    stored = store_consumed_window_id({}, "2026-08-25T04:00")
    assert load_consumed_window_id(stored) == "2026-08-25T04:00"
    assert load_consumed_window_id({}) == ""
