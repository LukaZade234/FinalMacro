"""Tests for ``$us`` mode stop conditions."""

import datetime as dt

from macro.config import KakeraReactionRules, MacroConfig
from macro.state import AccountState
from macro.us_stop import (
    UsModeStopOptions,
    overlay_legacy_us_options,
    us_kakera_power_exhausted,
    us_stop_can_pause,
    us_stop_from_config,
    us_stop_reason,
)

_TODAY = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def test_us_stop_roll_limit():
    opts = UsModeStopOptions(stop_after_rolls_enabled=True, stop_after_rolls=100)
    rules = KakeraReactionRules(enabled=False)
    reason = us_stop_reason(
        options=opts,
        state=AccountState(),
        rules=rules,
        us_rolls_done=99,
    )
    assert reason is None
    reason = us_stop_reason(
        options=opts,
        state=AccountState(),
        rules=rules,
        us_rolls_done=100,
    )
    assert reason == "roll limit (100) reached"


def test_us_stop_power_with_dk_available():
    rules = KakeraReactionRules(enabled=True, auto_use_dk=True)
    state = AccountState(power_percent=5.0, dk_stock=1)
    assert not us_kakera_power_exhausted(state, rules)


def test_us_stop_power_without_dk():
    rules = KakeraReactionRules(enabled=True, auto_use_dk=True)
    state = AccountState(power_percent=5.0, dk_stock=0)
    assert us_kakera_power_exhausted(state, rules)


def test_us_stop_power_disabled_kakera():
    rules = KakeraReactionRules(enabled=False)
    state = AccountState(power_percent=0.0, dk_stock=0)
    assert not us_kakera_power_exhausted(state, rules)


def test_us_stop_power_ignores_free_kakera_in_type_list():
    """Purple is free — stop threshold must use paid colors only."""
    rules = KakeraReactionRules(
        enabled=True,
        auto_use_dk=False,
        types_allowed=["kakeraP", "kakeraW"],
    )
    state = AccountState(power_percent=5.0, dk_stock=0)
    assert us_kakera_power_exhausted(state, rules)


def test_us_stop_power_only_free_kakera_never_stops():
    rules = KakeraReactionRules(
        enabled=True,
        auto_use_dk=False,
        types_allowed=["kakeraP"],
    )
    state = AccountState(power_percent=0.0, dk_stock=0)
    assert not us_kakera_power_exhausted(state, rules)


def test_us_stop_power_perk8_budget_done_uses_15_percent():
    rules = KakeraReactionRules(
        enabled=True,
        auto_use_dk=False,
        perk_8_budget_mode=True,
        types_allowed=["kakeraP", "kakeraW"],
    )
    state = AccountState(
        power_percent=10.0,
        dk_stock=0,
        perk8_priority_mode="done",
        kakera_clicks_today=40,
        kakera_clicks_day=_TODAY,
        perk8_click_max=40,
    )
    assert us_kakera_power_exhausted(state, rules)
    state.power_percent = 20.0
    assert not us_kakera_power_exhausted(state, rules)


def test_us_stop_power_perk8_budget_active_uses_7_5_percent():
    rules = KakeraReactionRules(
        enabled=True,
        auto_use_dk=False,
        perk_8_budget_mode=True,
        types_allowed=["kakeraP", "kakeraW"],
    )
    state = AccountState(
        power_percent=10.0,
        dk_stock=0,
        perk8_priority_mode="active",
        kakera_clicks_today=10,
        kakera_clicks_day=_TODAY,
        perk8_click_max=40,
    )
    assert not us_kakera_power_exhausted(state, rules)
    state.power_percent = 5.0
    assert us_kakera_power_exhausted(state, rules)


def test_keep_draining_does_not_watch_power_unless_toggled():
    opts = UsModeStopOptions(keep_draining=True)
    rules = KakeraReactionRules(enabled=True, auto_use_dk=True)
    reason = us_stop_reason(
        options=opts,
        state=AccountState(power_percent=0.0, dk_stock=0),
        rules=rules,
        us_rolls_done=0,
    )
    assert reason is None


def test_keep_draining_pauses_when_power_stop_is_on():
    opts = UsModeStopOptions(keep_draining=True, stop_on_power_exhausted=True)
    rules = KakeraReactionRules(enabled=True, auto_use_dk=True)
    reason = us_stop_reason(
        options=opts,
        state=AccountState(power_percent=0.0, dk_stock=0),
        rules=rules,
        us_rolls_done=0,
    )
    assert reason is not None
    assert reason.startswith("reaction power exhausted")
    assert us_stop_can_pause(reason)


def test_roll_limit_is_not_pausable():
    assert not us_stop_can_pause("roll limit (100) reached")
    assert us_stop_can_pause("reaction power exhausted (no usable $dk left)")


def test_us_stop_from_config_maps_preset_fields():
    opts = us_stop_from_config(
        MacroConfig(
            us_keep_draining=True,
            us_stop_on_power_exhausted=True,
            us_stop_after_rolls_enabled=True,
            us_stop_after_rolls=25,
            us_schedule_enabled=True,
            us_schedule_start="4:00",
            us_schedule_end="6:00",
        )
    )
    assert opts.keep_draining is True
    assert opts.stop_on_power_exhausted is True
    assert opts.stop_after_rolls_enabled is True
    assert opts.stop_after_rolls == 25
    assert opts.schedule_enabled is True
    assert opts.schedule_start == "04:00"
    assert opts.schedule_end == "06:00"


def test_us_stop_from_config_can_ignore_schedule():
    opts = us_stop_from_config(
        MacroConfig(us_schedule_enabled=True, us_schedule_start="4:00"),
        apply_schedule=False,
    )
    assert opts.schedule_enabled is False
    assert opts.schedule_start == "04:00"


def test_overlay_legacy_copies_classic_stops():
    stored = {"us_batch_size": 15}
    legacy = UsModeStopOptions(
        stop_on_power_exhausted=True,
        stop_after_rolls_enabled=True,
        stop_after_rolls=40,
    )
    out = overlay_legacy_us_options(stored, legacy)
    assert out["us_keep_draining"] is False
    assert out["us_stop_on_power_exhausted"] is True
    assert out["us_stop_after_rolls_enabled"] is True
    assert out["us_stop_after_rolls"] == 40
    assert stored == {"us_batch_size": 15}


def test_overlay_legacy_skips_when_preset_has_keys():
    stored = {"us_keep_draining": True, "us_stop_on_power_exhausted": False}
    legacy = UsModeStopOptions(stop_on_power_exhausted=True)
    assert overlay_legacy_us_options(stored, legacy) is stored
