"""Wall-clock reset deadlines and GUI power regen."""

from __future__ import annotations

import datetime as dt

from macro.live_clock import (
    apply_countdown,
    iso_deadline,
    live_power_percent,
    remaining_minutes,
    stamp_power_updated,
)
from macro.state import AccountState


def _utc(y, m, d, h, mi=0) -> dt.datetime:
    return dt.datetime(y, m, d, h, mi, tzinfo=dt.timezone.utc)


def test_iso_deadline_and_remaining_minutes():
    now = _utc(2026, 8, 25, 12, 10)
    stamp = iso_deadline(30, now=now)
    assert remaining_minutes(stamp, now=now) == 30
    assert remaining_minutes(stamp, now=_utc(2026, 8, 25, 12, 25)) == 15
    assert remaining_minutes(stamp, now=_utc(2026, 8, 25, 12, 40)) == 0
    assert iso_deadline(None, now=now) == ""
    assert remaining_minutes("") is None


def test_apply_countdown_writes_deadline():
    state = AccountState()
    now = _utc(2026, 8, 25, 12, 0)
    apply_countdown(state, "rolls_reset_minutes", "rolls_reset_at", 20, now=now)
    assert state.rolls_reset_minutes == 20
    assert remaining_minutes(state.rolls_reset_at, now=_utc(2026, 8, 25, 12, 10)) == 10
    apply_countdown(state, "rolls_reset_minutes", "rolls_reset_at", None)
    assert state.rolls_reset_minutes is None
    assert state.rolls_reset_at == ""


def test_live_power_percent_regens_from_wall_clock():
    state = AccountState(power_percent=50.0, power_max_percent=155.0)
    stamp_power_updated(state, now=_utc(2026, 8, 25, 12, 0))
    live = live_power_percent(state, now=_utc(2026, 8, 25, 12, 9))
    assert live == 53.0
    capped = AccountState(power_percent=154.0, power_max_percent=155.0)
    stamp_power_updated(capped, now=_utc(2026, 8, 25, 12, 0))
    assert live_power_percent(capped, now=_utc(2026, 8, 25, 12, 9)) == 155.0
