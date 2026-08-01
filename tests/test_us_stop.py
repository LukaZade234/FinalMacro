"""Tests for ``$us`` mode stop conditions."""

import datetime as dt

from macro.config import KakeraReactionRules
from macro.state import AccountState
from macro.us_stop import UsModeStopOptions, us_kakera_power_exhausted, us_stop_reason

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
