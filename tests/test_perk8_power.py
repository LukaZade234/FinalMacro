"""Perk-8 reaction-power and ``$dk`` reservation."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import deque
from unittest.mock import patch

from macro.config import KakeraReactionRules, MacroConfig
from macro.kakera_reactor import KakeraReactor
from macro.perk8_power import (
    DEFAULT_DK_COOLDOWN_MINUTES,
    PowerSnapshot,
    burst_completes,
    chaos_click_cost,
    clamp_power_window_hours,
    dk_allowed_for_click,
    dk_cooldown_minutes_from_bonus,
    seconds_until_midnight,
    should_spend_paid_non_perk8,
    snapshot_from_state,
    power_save_status,
)
from macro.rule_eval import passes_kakera_reaction
from macro.state import AccountState
from macro.us_stop import us_kakera_power_exhausted
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_WINDOW = 4 * 3600
_FOURTEEN = dt.datetime(2026, 8, 25, 14, 0, tzinfo=dt.timezone.utc)
_SIXTEEN = dt.datetime(2026, 8, 25, 16, 0, tzinfo=dt.timezone.utc)
_TWENTY = dt.datetime(2026, 8, 25, 20, 0, tzinfo=dt.timezone.utc)
_PRE_MIDNIGHT = dt.datetime(2026, 8, 25, 23, 20, tzinfo=dt.timezone.utc)


def _snap(
    *,
    power: float,
    max_power: float = 155.0,
    dk_stock: int = 0,
    dk_next_sec: float | None = None,
    cooldown_hours: float = 20.0,
    base_cost: float = 30.0,
) -> PowerSnapshot:
    return PowerSnapshot(
        power=power,
        max_power=max_power,
        dk_stock=dk_stock,
        dk_next_sec=dk_next_sec,
        dk_cooldown_sec=cooldown_hours * 3600.0,
        perk8_cost=chaos_click_cost(perk8=True, base_cost=base_cost),
        normal_cost=chaos_click_cost(perk8=False, base_cost=base_cost),
    )


def _budget_rules(**overrides) -> KakeraReactionRules:
    data = dict(
        enabled=True,
        types_allowed=["kakeraR"],
        perk_8_budget_mode=True,
        perk_8_power_save=True,
        perk_8_power_window_hours=4.0,
        auto_use_dk=True,
    )
    data.update(overrides)
    return KakeraReactionRules(**data)


def _kakera_buttons(*emojis: str) -> list[dict]:
    return [
        {
            "is_kakera": True,
            "is_sphere": False,
            "disabled": False,
            "custom_id": f"cid-{i}-{emoji}",
            "emoji": emoji,
            "kind": "kakera",
        }
        for i, emoji in enumerate(emojis)
    ]


def _kakera_fields(*emojis: str, perk_8: bool | None = False) -> dict:
    return {
        "character_name": "Char",
        "buttons": _kakera_buttons(*emojis),
        "perk_8": perk_8,
        "spheres": None,
        "keys": [],
    }


def test_chaos_click_costs():
    assert chaos_click_cost(perk8=True) == 7.5
    assert chaos_click_cost(perk8=False) == 15.0


def test_clamp_and_default_dk_cooldown():
    assert clamp_power_window_hours(0) == 1.0
    assert clamp_power_window_hours(99) == 12.0
    assert clamp_power_window_hours(None) == 4.0
    assert dk_cooldown_minutes_from_bonus(None) == DEFAULT_DK_COOLDOWN_MINUTES
    assert dk_cooldown_minutes_from_bonus("20h") == 20 * 60
    assert dk_cooldown_minutes_from_bonus("10h") == 10 * 60
    assert dk_cooldown_minutes_from_bonus(20) == 20 * 60


def test_burst_155_needs_dk_for_40_in_4h():
    cost = chaos_click_cost(perk8=True)
    empty = _snap(power=155.0, max_power=155.0, dk_stock=0)
    assert not burst_completes(empty, clicks=40, cost=cost, horizon_sec=_WINDOW)
    filled = _snap(power=155.0, max_power=155.0, dk_stock=1)
    assert burst_completes(filled, clicks=40, cost=cost, horizon_sec=_WINDOW)


def test_burst_130_needs_dk_for_40_in_4h():
    cost = chaos_click_cost(perk8=True)
    empty = _snap(power=130.0, max_power=130.0, dk_stock=0)
    assert not burst_completes(empty, clicks=40, cost=cost, horizon_sec=_WINDOW)
    filled = _snap(power=130.0, max_power=130.0, dk_stock=1)
    assert burst_completes(filled, clicks=40, cost=cost, horizon_sec=_WINDOW)


def test_dk_20h_afternoon_normal_held_perk8_allowed():
    until = seconds_until_midnight(_FOURTEEN)
    snap = _snap(power=80.0, max_power=155.0, dk_stock=1, cooldown_hours=20)
    assert not dk_allowed_for_click(
        snap,
        perk8=False,
        remaining=0,
        window_sec=_WINDOW,
        until_midnight_sec=until,
    )
    assert dk_allowed_for_click(
        snap,
        perk8=True,
        remaining=20,
        window_sec=_WINDOW,
        until_midnight_sec=until,
    )


def test_dk_10h_afternoon_recycle_evening_hold():
    snap = _snap(power=80.0, max_power=155.0, dk_stock=1, cooldown_hours=10)
    assert dk_allowed_for_click(
        snap,
        perk8=False,
        remaining=0,
        window_sec=_WINDOW,
        until_midnight_sec=seconds_until_midnight(_FOURTEEN),
    )
    assert not dk_allowed_for_click(
        snap,
        perk8=False,
        remaining=0,
        window_sec=_WINDOW,
        until_midnight_sec=seconds_until_midnight(_TWENTY),
    )


def test_dk_pre_midnight_today_first():
    snap = _snap(power=100.0, max_power=155.0, dk_stock=1, cooldown_hours=20)
    assert dk_allowed_for_click(
        snap,
        perk8=True,
        remaining=40,
        window_sec=_WINDOW,
        until_midnight_sec=seconds_until_midnight(_PRE_MIDNIGHT),
    )
    assert not dk_allowed_for_click(
        snap,
        perk8=False,
        remaining=40,
        window_sec=_WINDOW,
        until_midnight_sec=seconds_until_midnight(_PRE_MIDNIGHT),
    )


def test_dk_midday_start_today_first():
    snap = _snap(power=100.0, max_power=130.0, dk_stock=1, cooldown_hours=20)
    until = seconds_until_midnight(_FOURTEEN)
    assert dk_allowed_for_click(
        snap,
        perk8=True,
        remaining=40,
        window_sec=_WINDOW,
        until_midnight_sec=until,
    )
    assert not dk_allowed_for_click(
        snap,
        perk8=False,
        remaining=40,
        window_sec=_WINDOW,
        until_midnight_sec=until,
    )


def test_after_budget_20h_dk_farm_chaos_but_hold_last_dk():
    until = seconds_until_midnight(_SIXTEEN)
    snap = _snap(power=80.0, max_power=130.0, dk_stock=1, cooldown_hours=20)
    assert should_spend_paid_non_perk8(
        snap,
        cost=snap.normal_cost,
        remaining=0,
        window_sec=_WINDOW,
        until_midnight_sec=until,
    )
    assert not dk_allowed_for_click(
        snap,
        perk8=False,
        remaining=0,
        window_sec=_WINDOW,
        until_midnight_sec=until,
    )


def test_paid_bypass_skipped_when_it_breaks_today_burst():
    now = _FOURTEEN
    rules = _budget_rules(
        perk_8_budget_bypass_types=["kakeraR"],
        auto_use_dk=False,
    )
    state = AccountState(
        power_percent=155.0,
        power_max_percent=155.0,
        dk_stock=0,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="active",
        perk8_click_max=40,
    )
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 9
    decision = passes_kakera_reaction(
        _kakera_fields("kakeraR"),
        rules,
        state,
        now=now,
    )
    assert decision.buttons == []
    assert "reserving power" in decision.reason


def test_purple_bypass_not_skipped_by_power_save():
    rules = _budget_rules(
        types_allowed=["kakeraP", "kakeraR"],
        perk_8_budget_bypass_types=["kakeraP"],
        auto_use_dk=False,
    )
    state = AccountState(
        power_percent=155.0,
        power_max_percent=155.0,
        dk_stock=0,
        perk8_priority_mode="active",
        perk8_click_max=40,
    )
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 9
    decision = passes_kakera_reaction(
        _kakera_fields("kakeraP", "kakeraR"),
        rules,
        state,
        now=_FOURTEEN,
    )
    assert [b.emoji for b in decision.buttons] == ["kakeraP"]


def test_perk8_click_not_held_before_midnight():
    rules = _budget_rules(auto_use_dk=False)
    state = AccountState(
        power_percent=100.0,
        power_max_percent=155.0,
        dk_stock=1,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="active",
        perk8_click_max=40,
    )
    state.rollover_kakera_budget_if_needed()
    decision = passes_kakera_reaction(
        _kakera_fields("kakeraR", perk_8=True),
        rules,
        state,
        now=_PRE_MIDNIGHT,
    )
    assert len(decision.buttons) == 1


def test_done_farm_allows_chaos_at_80_percent():
    rules = _budget_rules(auto_use_dk=False)
    state = AccountState(
        power_percent=80.0,
        power_max_percent=130.0,
        dk_stock=1,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="done",
        perk8_click_max=40,
        kakera_base_cost=30.0,
    )
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 40
    decision = passes_kakera_reaction(
        _kakera_fields("kakeraR"),
        rules,
        state,
        now=_SIXTEEN,
    )
    assert len(decision.buttons) == 1


class _FakeDkActions:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str | None]] = []
        self._dk = deque(
            [
                ParseResult(
                    kind=MessageKind.DK_CLAIM,
                    summary="$dk",
                    fields={"dk_used": True, "amount": 100, "dk_stock": 0},
                )
            ]
        )

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        self.sent.append((command, prefix))

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        return True

    async def wait_for(self, predicate, *, timeout: float = 8.0):
        del timeout
        outcome = ParseResult(
            kind=MessageKind.KAKERA_REACT_DENIED,
            summary="denied",
            fields={"kakera_cooldown_minutes": 5},
        )
        item = (
            MudaeMessageSnapshot(
                message_id=1,
                channel_id=1,
                channel_name="mudae",
                guild_id=1,
                guild_name="srv",
                author_id=1,
                author_name="Mudae",
                is_mudae=True,
                content="",
                embeds=[],
                buttons=[],
                created_at="12:00:00",
            ),
            outcome,
        )
        if predicate(*item):
            return item
        return None

    async def wait_for_kakera_outcome(self, *, timeout: float = 8.0):
        del timeout
        return ParseResult(
            kind=MessageKind.KAKERA_REACT_DENIED,
            summary="denied",
            fields={"kakera_cooldown_minutes": 5},
        )

    async def wait_for_dk_use(self, *, timeout: float = 12.0):
        return self._dk.popleft() if self._dk else None


async def _fast_sleep(_delay: float) -> None:
    return None


def test_reactor_holds_dk_for_tomorrow_after_budget():
    async def _case() -> None:
        state = AccountState(
            dk_stock=1,
            power_percent=5.0,
            power_max_percent=155.0,
            dk_cooldown_minutes=20 * 60,
            perk8_priority_mode="done",
            perk8_click_max=40,
        )
        state.rollover_kakera_budget_if_needed()
        state.kakera_clicks_today = 40
        config = MacroConfig(prefix="$", kakera_reaction=_budget_rules())
        actions = _FakeDkActions()
        reactor = KakeraReactor(
            actions=actions, config=config, state=state, log=lambda _m: None
        )
        with (
            patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep),
            patch("macro.perk8_power.utc_now", return_value=_FOURTEEN),
        ):
            await reactor.react(message_id=1, fields=_kakera_fields("kakeraR"))
        assert actions.sent == []

    asyncio.run(_case())


def test_reactor_uses_dk_for_perk8_while_remaining():
    async def _case() -> None:
        state = AccountState(
            dk_stock=1,
            power_percent=5.0,
            power_max_percent=155.0,
            dk_cooldown_minutes=20 * 60,
            perk8_priority_mode="active",
            perk8_click_max=40,
        )
        state.rollover_kakera_budget_if_needed()
        config = MacroConfig(prefix="$", kakera_reaction=_budget_rules())
        actions = _FakeDkActions()
        logs: list[str] = []
        reactor = KakeraReactor(
            actions=actions, config=config, state=state, log=logs.append
        )
        with (
            patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep),
            patch("macro.perk8_power.utc_now", return_value=_FOURTEEN),
        ):
            await reactor.react(
                message_id=1, fields=_kakera_fields("kakeraR", perk_8=True)
            )
        assert actions.sent == [("dk", "$")]

    asyncio.run(_case())


def test_us_stop_ignores_dk_held_for_tomorrow():
    rules = _budget_rules()
    state = AccountState(
        power_percent=5.0,
        power_max_percent=155.0,
        dk_stock=1,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="done",
        perk8_click_max=40,
    )
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 40
    with patch("macro.perk8_power.utc_now", return_value=_FOURTEEN):
        assert us_kakera_power_exhausted(state, rules)


def test_us_stop_counts_dk_owed_to_today():
    rules = _budget_rules()
    state = AccountState(
        power_percent=5.0,
        power_max_percent=155.0,
        dk_stock=1,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="active",
        perk8_click_max=40,
    )
    state.rollover_kakera_budget_if_needed()
    with patch("macro.perk8_power.utc_now", return_value=_FOURTEEN):
        assert not us_kakera_power_exhausted(state, rules)


def test_snapshot_missing_power_and_stock_are_zero():
    state = AccountState()
    snap = snapshot_from_state(state, now=_FOURTEEN)
    assert snap.power == 0.0
    assert snap.dk_stock == 0
    assert snap.dk_cooldown_sec == 20 * 3600


def test_power_save_status_hidden_when_toggle_off():
    state = AccountState(perk8_priority_mode="active", perk8_click_max=40)
    rules = KakeraReactionRules(enabled=True, perk_8_budget_mode=True, perk_8_power_save=False)
    assert power_save_status(state, rules, now=_FOURTEEN) is None
    rules = KakeraReactionRules(enabled=True, perk_8_budget_mode=False, perk_8_power_save=True)
    assert power_save_status(state, rules, now=_FOURTEEN) is None
    rules = KakeraReactionRules(
        enabled=True,
        perk_8_budget_mode=True,
        perk_8_priority=False,
        perk_8_power_save=True,
    )
    assert power_save_status(state, rules, now=_FOURTEEN) is None


def test_power_save_status_perk8_priority_limits_clicks():
    state = AccountState(
        power_percent=155.0,
        power_max_percent=155.0,
        dk_stock=1,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="active",
        perk8_click_max=40,
    )
    state.rollover_kakera_budget_if_needed()
    status = power_save_status(state, _budget_rules(), now=_FOURTEEN)
    assert status is not None
    assert status["perk8_priority"] is True
    assert status["normal_clicks"] is False
    assert status["kakera_free"] is False
    assert status["spendable_percent"] is not None


def test_power_save_status_done_farm_is_free_without_blocking():
    state = AccountState(
        power_percent=80.0,
        power_max_percent=130.0,
        dk_stock=1,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="done",
        perk8_click_max=40,
        kakera_base_cost=30.0,
    )
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 40
    status = power_save_status(state, _budget_rules(), now=_SIXTEEN)
    assert status is not None
    assert status["perk8_priority"] is False
    assert status["normal_clicks"] is True
    assert status["power_blocked"] is False
    assert status["kakera_free"] is True
    assert status["spendable_percent"] >= 15.0


def test_power_save_status_blocks_when_today_burst_would_fail():
    state = AccountState(
        power_percent=155.0,
        power_max_percent=155.0,
        dk_stock=0,
        dk_cooldown_minutes=20 * 60,
        perk8_priority_mode="active",
        perk8_click_max=40,
    )
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 9
    status = power_save_status(state, _budget_rules(), now=_FOURTEEN)
    assert status is not None
    assert status["perk8_priority"] is True
    assert status["power_blocked"] is True
    assert status["kakera_free"] is False
    assert status["spendable_percent"] < 15.0
