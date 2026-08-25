"""Reaction-power and perk-9 caps from stored ``$bonus`` / ``$shop``."""

from types import SimpleNamespace

from macro.perk9_daily import PERK9_CLICK_MAX_DEFAULT
from macro.reaction_power import DEFAULT_MAX_REACTION_POWER
from macro.sheet_caps import (
    apply_sheet_caps,
    perk9_max_from_shop,
    power_max_from_bonus,
    rolls_max_from_sheets,
)


def test_power_max_from_bonus_uses_sheet_or_default():
    assert power_max_from_bonus(None) == DEFAULT_MAX_REACTION_POWER
    assert power_max_from_bonus({}) == DEFAULT_MAX_REACTION_POWER
    assert power_max_from_bonus({"kakera_max_power": 175}) == 175.0
    assert power_max_from_bonus({"kakera_max_power": "0"}) == DEFAULT_MAX_REACTION_POWER


def test_perk9_max_from_shop_uses_sheet_or_default():
    assert perk9_max_from_shop(None) == PERK9_CLICK_MAX_DEFAULT
    assert perk9_max_from_shop({}) == PERK9_CLICK_MAX_DEFAULT
    assert perk9_max_from_shop({"perk9_click_max": 15}) == 15
    assert perk9_max_from_shop({"perk9_click_max": -1}) == PERK9_CLICK_MAX_DEFAULT


def test_apply_sheet_caps_clamps_current_power():
    state = SimpleNamespace(power_percent=160.0, power_max_percent=155.0, perk9_click_max=20)
    apply_sheet_caps(state, bonus={"kakera_max_power": 150}, shop={"perk9_click_max": 12})
    assert state.power_max_percent == 150.0
    assert state.power_percent == 150.0
    assert state.perk9_click_max == 12


def test_rolls_max_from_sheets_prefers_bonus_net_over_setrolls():
    assert rolls_max_from_sheets(None, None) is None
    assert rolls_max_from_sheets({}, {"setrolls": 21}) == 21
    assert (
        rolls_max_from_sheets(
            {"rolls_per_hour": {"net": 62, "base": 21}},
            {"setrolls": 21},
        )
        == 62
    )
    assert rolls_max_from_sheets({"rolls_per_hour": {"net": 0}}, {"setrolls": 21}) == 21
    assert rolls_max_from_sheets({"rolls_per_hour": "62"}, {"setrolls": 21}) == 21
