"""Tests for local kakera reaction power tracking."""

from __future__ import annotations

import time

import pytest

from macro.reaction_power import (
    BASE_REACTION_COST,
    apply_passive_regen,
    can_afford_reaction,
    estimate_power_from_cooldown,
    kakera_base_cost_from_state,
    reaction_power_cost,
    refresh_reaction_power,
    spend_reaction_power,
    sync_reaction_power_fields,
    sync_reaction_power_from_denial,
)
from macro.rule_eval import passes_kakera_reaction
from macro.config import KakeraReactionRules, LowPowerOverride
from macro.state import AccountState
from mudae.parsers.reaction_power import (
    is_kakera_react_denied,
    is_ku_response,
    parse_kakera_react_denied,
    parse_ku,
)
from mudae.parsers.classify import classify_message
from mudae.types import MessageKind, MudaeMessageSnapshot


class _State:
    power_percent: float | None = None
    power_max_percent: float = 155.0
    power_tracked_at: float = 0.0


def test_reaction_power_cost_purple_free():
    assert reaction_power_cost(kakera_emoji="kakeraP", has_chaos_key=False, has_perk_8=False) == 0


def test_reaction_power_cost_chaos_and_perk8():
    assert reaction_power_cost(kakera_emoji="kakeraR", has_chaos_key=True, has_perk_8=False) == 15
    assert reaction_power_cost(kakera_emoji="kakeraR", has_chaos_key=True, has_perk_8=True) == 7.5
    assert reaction_power_cost(kakera_emoji="kakeraR", has_chaos_key=False, has_perk_8=False) == 30


def test_reaction_power_cost_uses_bonus_base():
    assert (
        reaction_power_cost(
            kakera_emoji="kakeraR",
            has_chaos_key=False,
            has_perk_8=False,
            base_cost=20,
        )
        == 20
    )
    assert (
        reaction_power_cost(
            kakera_emoji="kakeraR",
            has_chaos_key=True,
            has_perk_8=True,
            base_cost=20,
        )
        == 5
    )
    assert kakera_base_cost_from_state(AccountState(kakera_base_cost=20)) == 20
    assert kakera_base_cost_from_state(AccountState()) == BASE_REACTION_COST
    assert kakera_base_cost_from_state(None) == BASE_REACTION_COST


def test_passive_regen_one_percent_per_three_minutes():
    assert apply_passive_regen(50.0, 180.0) == 51.0
    assert apply_passive_regen(154.0, 180.0, max_power=155.0) == 155.0


def test_spend_and_regen():
    state = _State()
    state.power_percent = 40.0
    state.power_tracked_at = 1000.0
    assert spend_reaction_power(state, 30.0, now=1000.0) is True
    assert state.power_percent == 10.0
    refreshed = refresh_reaction_power(state, now=1180.0)
    assert refreshed == pytest.approx(11.0)


def test_sync_from_tu_fields():
    state = _State()
    sync_reaction_power_fields(state, {"power_percent": 88}, now=500.0)
    assert state.power_percent == 88.0
    assert state.power_tracked_at == 500.0


def test_estimate_power_from_denial_cooldown():
    # Need 30% to react; Mudae says wait 11 min (~3.67% regen) → ~26.3% now.
    estimated = estimate_power_from_cooldown(11, cost=BASE_REACTION_COST)
    assert estimated == pytest.approx(26.333, rel=1e-3)


def test_sync_from_denial():
    state = _State()
    sync_reaction_power_from_denial(state, cooldown_minutes=11, cost=30.0, now=1.0)
    assert state.power_percent == pytest.approx(26.333, rel=1e-3)


def test_parse_ku_response():
    content = (
        "**User**, Power: **92%**\n"
        "You __can__ react to kakera! ($ku)"
    )
    assert is_ku_response(content) is True
    result = parse_ku(content)
    assert result.fields["power_percent"] == 92
    assert result.fields["kakera_react_available"] is True


def test_parse_kakera_react_denied_message():
    content = "**lukazade234**, You can't react to kakera for **11** min. ($ku)"
    assert is_kakera_react_denied(content) is True
    result = parse_kakera_react_denied(content)
    assert result.kind == MessageKind.KAKERA_REACT_DENIED
    assert result.fields["kakera_cooldown_minutes"] == 11
    assert result.fields["claimed_by"] == "lukazade234"


def test_classify_kakera_react_denied():
    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=2,
        channel_name="c",
        guild_id=3,
        guild_name="g",
        author_id=4,
        author_name="Mudae",
        is_mudae=True,
        content="**user**, You can't react to kakera for **5** min. ($ku)",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )
    assert classify_message(snapshot) == MessageKind.KAKERA_REACT_DENIED


def test_rule_eval_skips_when_power_too_low():
    fields = {
        "buttons": [
            {
                "emoji": "kakeraR",
                "custom_id": "x",
                "is_kakera": True,
                "disabled": False,
            }
        ],
        "keys": [],
        "spheres": 0,
    }
    state = AccountState(power_percent=10.0, power_tracked_at=time.monotonic())
    rules = KakeraReactionRules(enabled=True, types_allowed=["kakeraR"])
    decision = passes_kakera_reaction(fields, rules, state)
    assert decision.buttons == []
    assert "insufficient reaction power" in decision.reason


def test_rule_eval_low_power_override_uses_tracked_power():
    fields = {
        "buttons": [
            {"emoji": "kakeraW", "custom_id": "w", "is_kakera": True, "disabled": False},
            {"emoji": "kakeraR", "custom_id": "r", "is_kakera": True, "disabled": False},
        ],
        "keys": [{"type": "chaos", "level": 1}],
        "spheres": 0,
    }
    state = AccountState(power_percent=20.0, power_tracked_at=time.monotonic())
    rules = KakeraReactionRules(
        enabled=True,
        types_allowed=["kakeraR", "kakeraW"],
        low_power=LowPowerOverride(below_percent=30, types_allowed=["kakeraW"]),
    )
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1
    assert decision.buttons[0].emoji == "kakeraW"
    assert "low-power" in decision.reason
