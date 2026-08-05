"""Tests for persisted $tu runtime snapshots."""

from __future__ import annotations

import datetime as dt

from macro.runtime_store import (
    MACRO_RUNTIME_KEY,
    MacroRuntimeRecord,
    apply_power_with_regen,
    apply_to_state,
    can_skip_initial_tu,
    load_runtime_record,
    save_runtime_record,
    snapshot_from_state,
)
from macro.state import AccountState


def _utc(y, m, d, h, mi=0) -> dt.datetime:
    return dt.datetime(y, m, d, h, mi, tzinfo=dt.timezone.utc)


def test_snapshot_and_load_round_trip():
    state = AccountState(
        rolls_left=8,
        rolls_us_bonus=2,
        claim_available=False,
        claim_cooldown_minutes=40,
        power_percent=50.0,
        power_max_percent=155.0,
        rolls_reset_minutes=25,
        next_claim_reset_minutes=120,
        dk_stock=1,
        rt_available=False,
        rt_next_minutes=30,
    )
    now = _utc(2026, 8, 4, 12, 0)
    settings = {"setrolls": 10, "setclaim": 180, "setinterval": 0, "shifthour": 0}
    record = snapshot_from_state(state, now=now, settings=settings)
    daily = save_runtime_record({}, record)
    loaded = load_runtime_record(daily)
    assert loaded.rolls_left == 8
    assert loaded.power_percent == 50.0
    assert loaded.rolls_reset_at != ""
    assert loaded.setrolls == 10
    assert loaded.setclaim == 180
    assert MACRO_RUNTIME_KEY in daily


def test_restore_extrapolates_timers_and_power_regen():
    saved = _utc(2026, 8, 4, 12, 0)
    record = MacroRuntimeRecord(
        saved_at=saved.isoformat(),
        rolls_left=5,
        rolls_us_bonus=0,
        claim_available=False,
        claim_cooldown_minutes=40,
        next_claim_reset_minutes=90,
        power_percent=40.0,
        power_max_percent=155.0,
        power_updated_at=saved.isoformat(),
        rolls_reset_at=(_utc(2026, 8, 4, 12, 20)).isoformat(),
        claim_reset_at=(_utc(2026, 8, 4, 13, 30)).isoformat(),
        setrolls=10,
        setclaim=180,
    )
    now = _utc(2026, 8, 4, 12, 10)
    state = AccountState()
    result = apply_to_state(state, record, now=now)
    assert result.applied is True
    assert result.needs_tu is False
    assert can_skip_initial_tu(result)
    assert state.rolls_left == 5
    assert state.rolls_reset_minutes == 10
    assert state.claim_cooldown_minutes == 30
    # 10 minutes of passive regen → +3.33%
    assert state.power_percent == 43.333333333333336


def test_restore_refills_rolls_after_hourly_reset_passed():
    saved = _utc(2026, 8, 4, 12, 0)
    record = MacroRuntimeRecord(
        saved_at=saved.isoformat(),
        rolls_left=0,
        rolls_us_bonus=3,
        rolls_reset_at=(_utc(2026, 8, 4, 12, 15)).isoformat(),
        power_percent=80.0,
        power_updated_at=saved.isoformat(),
        setrolls=21,
    )
    now = _utc(2026, 8, 4, 12, 20)
    state = AccountState()
    result = apply_to_state(state, record, now=now)
    assert result.applied is True
    assert result.needs_tu is False
    assert can_skip_initial_tu(result)
    assert state.rolls_left == 21
    assert state.rolls_us_bonus == 0
    assert "roll reset" in result.message


def test_restore_applies_multiple_hourly_resets():
    saved = _utc(2026, 8, 4, 10, 0)
    record = MacroRuntimeRecord(
        saved_at=saved.isoformat(),
        rolls_left=2,
        rolls_reset_at=(_utc(2026, 8, 4, 10, 30)).isoformat(),
        setrolls=10,
    )
    now = _utc(2026, 8, 4, 13, 0)
    state = AccountState()
    result = apply_to_state(state, record, now=now)
    assert result.applied is True
    assert state.rolls_left == 10
    assert "3 roll reset" in result.message


def test_restore_claim_reset_and_cooldown_tick():
    saved = _utc(2026, 8, 4, 12, 0)
    record = MacroRuntimeRecord(
        saved_at=saved.isoformat(),
        rolls_left=5,
        rolls_reset_at=(_utc(2026, 8, 4, 13, 0)).isoformat(),
        claim_available=False,
        claim_cooldown_minutes=25,
        claim_reset_at=(_utc(2026, 8, 4, 13, 0)).isoformat(),
        setrolls=10,
        setclaim=60,
    )
    now = _utc(2026, 8, 4, 12, 10)
    state = AccountState()
    result = apply_to_state(state, record, now=now)
    assert result.applied is True
    assert state.claim_available is False
    assert state.claim_cooldown_minutes == 15

    record2 = MacroRuntimeRecord(
        saved_at=saved.isoformat(),
        rolls_left=5,
        rolls_reset_at=(_utc(2026, 8, 4, 13, 0)).isoformat(),
        claim_available=False,
        claim_cooldown_minutes=25,
        claim_reset_at=(_utc(2026, 8, 4, 12, 30)).isoformat(),
        setrolls=10,
        setclaim=60,
    )
    now2 = _utc(2026, 8, 4, 12, 45)
    state2 = AccountState()
    result2 = apply_to_state(state2, record2, now=now2)
    assert result2.applied is True
    assert state2.claim_available is True
    assert state2.claim_cooldown_minutes == 0
    assert "claim reset" in result2.message


def test_apply_power_with_regen_from_iso():
    state = AccountState()
    record = MacroRuntimeRecord(
        power_percent=100.0,
        power_max_percent=155.0,
        power_updated_at=_utc(2026, 8, 4, 12, 0).isoformat(),
    )
    apply_power_with_regen(state, record, now=_utc(2026, 8, 4, 12, 6))
    assert state.power_percent == 102.0
