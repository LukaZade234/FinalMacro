"""Perk-9 adaptive click/skip threshold."""

from __future__ import annotations

import datetime as dt

from macro.config import SphereReactionRules
from macro.perk9_threshold import (
    COLBLITZ_SPHERE_BASE_SP,
    COLBLITZ_SPHERE_FREQUENCY,
    MAX_TABLE_OPPORTUNITIES,
    Perk9ThresholdContext,
    best_static_strategy,
    build_ev_table,
    build_perk9_threshold_context,
    build_value_table,
    click_threshold,
    estimate_opportunities_left,
    estimate_sphere_colour_frequency,
    normalize_frequency,
    sphere_ev,
)
from macro.rule_eval import passes_sphere_reaction
from macro.state import AccountState
from mudae.parsers.ohu import parse_ohu, parse_perk9_rolled_pool

# Colblitz p9calc's own example account: OP9 10, 34% double, +18 flat.
_DOUBLE = 34.0
_FLAT = 18.0
_SHOP9 = 100.0
_PUBLISHED_EV = {
    "spW": 1376.0,
    "spR": 438.0,
    "spD": 316.1,
    "spO": 277.2,
    "spL": 239.4,
    "spY": 183.4,
    "spG": 129.8,
    "spT": 89.6,
    "spB": 62.8,
}
_NOON = dt.datetime(2026, 8, 29, 12, 0, tzinfo=dt.timezone.utc)


def _sphere_button(emoji: str, custom_id: str = "cmd s0") -> dict:
    return {
        "custom_id": custom_id,
        "is_sphere": True,
        "disabled": False,
        "emoji": {"name": emoji},
    }


def _rules(**overrides) -> SphereReactionRules:
    base = {"enabled": True, "budget_aware": True}
    base.update(overrides)
    return SphereReactionRules(**base)


def _context(spawns: int, clicks: int) -> Perk9ThresholdContext:
    ctx = build_perk9_threshold_context(
        opportunities_left=spawns,
        clicks_left=clicks,
        double_chance_pct=_DOUBLE,
        additional_spheres=_FLAT,
        shop9_bonus_pct=_SHOP9,
    )
    assert ctx is not None
    return ctx


def test_sphere_ev_matches_every_published_row():
    """The formula must reproduce Colblitz's whole EV column, not just one row."""
    for emoji, expected in _PUBLISHED_EV.items():
        got = sphere_ev(
            COLBLITZ_SPHERE_BASE_SP[emoji],
            double_chance_pct=_DOUBLE,
            additional_spheres=_FLAT,
            shop9_bonus_pct=_SHOP9,
        )
        assert abs(got - expected) < 0.05, emoji


def test_sphere_ev_without_bonuses_is_base_sp():
    assert sphere_ev(150.0) == 150.0


def test_default_frequency_sums_to_one():
    assert abs(sum(COLBLITZ_SPHERE_FREQUENCY.values()) - 1.0) < 1e-9


def test_normalize_frequency_rescales_user_percentages():
    freq = normalize_frequency(
        {emoji: 0.0 for emoji in COLBLITZ_SPHERE_FREQUENCY}
        | {"spB": 60.0, "spT": 25.0, "spR": 15.0}
    )
    assert abs(sum(freq.values()) - 1.0) < 1e-9
    assert abs(freq["spB"] - 0.6) < 1e-9


def test_partial_frequency_edit_keeps_the_other_colours():
    """Presets stores only edited colours, so the rest must stay at defaults."""
    freq = normalize_frequency({"spB": 50.0})
    assert set(freq) == set(COLBLITZ_SPHERE_FREQUENCY)
    assert freq["spW"] > 0


def test_partial_value_edit_keeps_the_other_colours():
    ev = build_ev_table({"spB": 12.0})
    assert set(ev) == set(COLBLITZ_SPHERE_BASE_SP)
    assert ev["spB"] == 12.0
    assert ev["spW"] == 500.0


def test_zero_frequency_drops_a_colour():
    freq = normalize_frequency({"spW": 0.0})
    assert "spW" not in freq


def test_normalize_frequency_falls_back_when_everything_is_zero():
    zeroed = {emoji: 0.0 for emoji in COLBLITZ_SPHERE_FREQUENCY}
    assert normalize_frequency(zeroed) == COLBLITZ_SPHERE_FREQUENCY


def test_value_table_single_click_is_expected_value():
    """V(1,1) is just the mean EV of one click — the DP's base case."""
    ev = {"spB": 10.0, "spR": 150.0}
    freq = {"spB": 0.9, "spR": 0.1}
    table = build_value_table(1, 1, ev, freq)
    assert abs(table[1][1] - (0.9 * 10.0 + 0.1 * 150.0)) < 1e-9


def test_value_table_two_spawns_one_click_prefers_waiting_for_red():
    """With a spare spawn, a 10 SP blue is skipped in the hope of a 150 SP red."""
    ev = {"spB": 10.0, "spR": 150.0}
    freq = {"spB": 0.9, "spR": 0.1}
    table = build_value_table(2, 1, ev, freq)
    one = 0.9 * 10.0 + 0.1 * 150.0
    expected = 0.9 * max(10.0, one) + 0.1 * max(150.0, one)
    assert abs(table[2][1] - expected) < 1e-9
    assert click_threshold(table, 2, 1) == one


def test_threshold_is_non_increasing_as_the_day_drains():
    ev = build_ev_table()
    freq = normalize_frequency(None)
    table = build_value_table(300, 10, ev, freq)
    bars = [click_threshold(table, left, 10) for left in range(300, 0, -1)]
    assert all(a >= b - 1e-9 for a, b in zip(bars, bars[1:]))


def test_threshold_reaches_zero_when_spawns_match_budget():
    """Unused clicks expire, so the last spawns are worth taking at any colour."""
    ev = build_ev_table()
    freq = normalize_frequency(None)
    table = build_value_table(60, 10, ev, freq)
    assert click_threshold(table, 10, 10) == 0.0
    assert click_threshold(table, 60, 10) > 0.0


def test_context_skips_cheap_colour_when_spawns_are_plentiful():
    ctx = _context(250, 20)
    assert not ctx.should_click("spB")
    assert not ctx.should_click("spT")
    assert ctx.should_click("spR")
    assert ctx.should_click("spW")


def test_context_clicks_everything_once_spawns_run_out():
    ctx = _context(12, 20)
    assert ctx.should_click("spB")


def test_context_refuses_when_budget_is_spent():
    ctx = _context(100, 20)
    spent = Perk9ThresholdContext(
        ev_by_emoji=ctx.ev_by_emoji,
        value_table=ctx.value_table,
        opportunities_left=100,
        clicks_left=0,
    )
    assert not spent.should_click("spW")


def test_context_is_none_without_clicks_or_spawns():
    assert build_perk9_threshold_context(opportunities_left=100, clicks_left=0) is None
    assert build_perk9_threshold_context(opportunities_left=0, clicks_left=20) is None


def test_bare_sp_is_treated_as_red():
    ctx = _context(250, 20)
    assert ctx.ev_for("sp") == ctx.ev_for("spR")
    assert ctx.should_click("sp")


def test_colourblind_variant_folds_to_base_colour():
    ctx = _context(250, 20)
    assert ctx.ev_for("spB2") == ctx.ev_for("spB")


def test_unknown_colour_is_clicked_rather_than_dropped():
    """It already cleared the user's allow-list; we just cannot score it."""
    ctx = _context(250, 20)
    assert ctx.should_click("spZ")


def test_context_caps_a_runaway_opportunity_estimate():
    ctx = _context(50_000, 20)
    assert ctx.opportunities_left == MAX_TABLE_OPPORTUNITIES


def test_best_static_never_beats_the_adaptive_table():
    ev = build_ev_table(
        double_chance_pct=_DOUBLE, additional_spheres=_FLAT, shop9_bonus_pct=_SHOP9
    )
    freq = normalize_frequency(None)
    for spawns in (30, 60, 120, 250):
        table = build_value_table(spawns, 20, ev, freq)
        _picks, static = best_static_strategy(spawns, 20, ev, freq)
        assert table[spawns][20] >= static


def test_best_static_clicks_everything_when_spawns_are_scarce():
    ev = build_ev_table()
    freq = normalize_frequency(None)
    picks, _ = best_static_strategy(5, 20, ev, freq)
    assert set(picks) == set(freq)


def test_estimate_frequency_needs_a_big_enough_sample():
    events = [
        {"source": "sphere_click", "sphere_type": "spB"},
        {"source": "sphere_click", "sphere_type": "spT"},
    ]
    assert estimate_sphere_colour_frequency(events, min_samples=500) is None
    got = estimate_sphere_colour_frequency(events, min_samples=2)
    assert got == {"spB": 0.5, "spT": 0.5}


def test_estimate_frequency_ignores_non_click_sources():
    events = [
        {"source": "sphere_click", "sphere_type": "spB"},
        {"source": "perk10", "sphere_type": "spW"},
        {"source": "minigame_oh", "sphere_type": "spR"},
    ]
    assert estimate_sphere_colour_frequency(events, min_samples=1) == {"spB": 1.0}


def test_parse_perk9_rolled_pool():
    assert parse_perk9_rolled_pool("(Perk 9) Rolled today: **44**/154") == (44, 154)
    assert parse_perk9_rolled_pool("(Perk 9) Rolled today: 7/20") == (7, 20)


def test_parse_perk9_rolled_pool_ignores_the_perk8_line():
    assert parse_perk9_rolled_pool("(Perk 8) Rolled today: **12**/99") is None


def test_parse_ohu_exposes_the_perk9_pool():
    content = (
        "4 $oh left for today, 2 $oc, 1 $oq and 0 $ot.\n"
        "3h 20 min before the refill. 6/20 buttons clicked.\n"
        "(Perk 9) Rolled today: **44**/154"
    )
    fields = parse_ohu(content).fields
    assert fields["perk9_rolled_today"] == 44
    assert fields["perk9_roll_pool"] == 154


def test_estimate_opportunities_prefers_the_unrolled_pool():
    state = AccountState()
    state.perk9_rolled_today = 44
    state.perk9_roll_pool = 154
    assert estimate_opportunities_left(state, rolls_per_hour=None, now=_NOON) == 110


def test_estimate_opportunities_is_capped_by_rolls_left_in_the_day():
    """The rolls-left arm is a spawn forecast, not a raw roll count.

    It used to return the 120 rolls themselves, which counted every roll as if
    it were a perk-9 spawn — roughly 50× too many, so the arm never bound and
    the pool ceiling alone drove the bar. Scaling by the account's own measured
    arrival rate is what makes it a real forecast.
    """
    state = AccountState()
    state.perk9_rolled_today = 0
    state.perk9_roll_pool = 900
    state.rolls_left = 0
    state.perk9_hazard = 0.37
    # 12h to the UTC reset at 10 rolls/hour is 120 rolls; at 0.37 spawns per
    # roll against a barely-touched 900 pool that is ~43 spawns, not 900.
    assert estimate_opportunities_left(state, rolls_per_hour=10, now=_NOON) == 43


def test_estimate_opportunities_keeps_the_pool_ceiling_without_a_learned_rate():
    """Cold start is the old behaviour, never some other account's constant."""
    state = AccountState()
    state.perk9_rolled_today = 0
    state.perk9_roll_pool = 900
    state.rolls_left = 0
    assert state.perk9_hazard is None
    assert estimate_opportunities_left(state, rolls_per_hour=10, now=_NOON) == 900


def test_estimate_opportunities_honours_the_manual_override():
    state = AccountState()
    assert estimate_opportunities_left(state, manual_override=77, now=_NOON) == 77


def test_estimate_opportunities_is_none_without_any_signal():
    assert estimate_opportunities_left(AccountState(), now=_NOON) is None


def test_reaction_skips_cheap_colour_when_spawns_are_plentiful():
    fields = {"buttons": [_sphere_button("spB")]}
    decision = passes_sphere_reaction(
        fields, _rules(), AccountState(), threshold_ctx=_context(250, 20)
    )
    assert not decision.should_click
    assert "perk9 budget" in decision.reason


def test_reaction_clicks_the_same_colour_when_spawns_are_scarce():
    fields = {"buttons": [_sphere_button("spB")]}
    decision = passes_sphere_reaction(
        fields, _rules(), AccountState(), threshold_ctx=_context(12, 20)
    )
    assert decision.should_click


def test_reaction_keeps_megasphere_below_the_bar():
    """Megasphere is free and spends no perk-9 slot, so the gate must not eat it."""
    fields = {"buttons": [_sphere_button("spM")]}
    decision = passes_sphere_reaction(
        fields, _rules(), AccountState(), threshold_ctx=_context(250, 20)
    )
    assert decision.should_click


def test_reaction_ignores_the_context_when_budget_mode_is_off():
    fields = {"buttons": [_sphere_button("spB")]}
    rules = SphereReactionRules(enabled=True, budget_aware=False)
    decision = passes_sphere_reaction(
        fields, rules, AccountState(), threshold_ctx=_context(250, 20)
    )
    assert decision.should_click


def test_budget_mode_replaces_the_static_filter_rather_than_narrowing_it():
    """In budget mode the EV bar is the only gate, so it can widen the list.

    Filtering first is what let clicks expire: ``types_allowed`` is typically
    missing blue and teal, five spawns in six, so almost every button the bar
    would have cleared at the end of the day never reached it.
    """
    fields = {"buttons": [_sphere_button("spR")]}
    rules = _rules(types_allowed=["spW"])
    decision = passes_sphere_reaction(
        fields, rules, AccountState(), threshold_ctx=_context(12, 20)
    )
    assert decision.should_click


def test_the_static_filter_still_rules_when_budget_mode_is_off():
    fields = {"buttons": [_sphere_button("spR")]}
    rules = SphereReactionRules(enabled=True, budget_aware=False, types_allowed=["spW"])
    decision = passes_sphere_reaction(
        fields, rules, AccountState(), threshold_ctx=_context(12, 20)
    )
    assert not decision.should_click


def test_config_round_trip_keeps_the_new_fields():
    rules = SphereReactionRules(
        enabled=True,
        budget_aware=True,
        sphere_frequency={"spB": 60.0},
        sphere_values={"spB": 11.0},
        expected_daily_opportunities=140,
    )
    restored = SphereReactionRules.from_dict(rules.to_dict())
    assert restored == rules


def test_config_defaults_keep_todays_behaviour():
    rules = SphereReactionRules.from_dict({})
    assert rules.budget_aware is False
    assert rules.sphere_frequency == {}
    assert rules.expected_daily_opportunities == 0
