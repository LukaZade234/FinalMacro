"""Tests for ``$us`` mode stop conditions."""

from macro.config import KakeraReactionRules
from macro.state import AccountState
from macro.us_stop import UsModeStopOptions, us_kakera_power_exhausted, us_stop_reason


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
