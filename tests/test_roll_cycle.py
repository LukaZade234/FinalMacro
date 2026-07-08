"""Tests for the normal (continuous hourly) macro loop."""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

from macro.config import CharacterClaimRules, KakeraReactionRules, MacroConfig
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState
from mudae.types import MessageKind, ParseResult


def _tu(rolls_left: int, reset_minutes: int) -> ParseResult:
    return ParseResult(
        kind=MessageKind.TU,
        summary="$tu",
        fields={
            "rolls_left": rolls_left,
            "rolls_reset_minutes": reset_minutes,
            "claim_available": False,
        },
    )


def _roll(message_id: int, rolls_left: int | None = None) -> tuple[SimpleNamespace, ParseResult]:
    snapshot = SimpleNamespace(message_id=message_id)
    fields: dict = {"character_name": f"Char{message_id}", "wished_by": None}
    if rolls_left is not None:
        fields["rolls_left"] = rolls_left
    return snapshot, ParseResult(
        kind=MessageKind.ROLL,
        summary="$roll",
        fields=fields,
    )


def _roll_limit(reset_minutes: int = 34) -> tuple[SimpleNamespace, ParseResult]:
    from mudae.parsers.roll_limit import parse_roll_limit

    content = (
        "lukazade234, the roulette is limited to 30 uses per hour. "
        f"{reset_minutes} min left."
    )
    return SimpleNamespace(message_id=999), parse_roll_limit(content)


class _FakeActions:
    def __init__(self, tu_script: list, roll_script: list) -> None:
        self._tu = deque(tu_script)
        self._rolls = deque(roll_script)
        self.sent: list[tuple[str, str | None]] = []

    def drain_queue(self) -> None:
        pass

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        self.sent.append((command, prefix))

    async def wait_for_tu(self, *, timeout: float = 12.0):
        return self._tu.popleft() if self._tu else None

    async def wait_for_roll(self, *, roll_command: str, timeout: float = 20.0):
        return self._rolls.popleft() if self._rolls else None

    async def wait_for_perk6_spawn(self, *, parent_character: str, timeout: float = 5.0):
        return None

    async def wait_for(self, predicate, *, timeout: float = 15.0):
        return None

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        return True

    def roll_commands(self) -> list[str]:
        return [c for c, _ in self.sent if c == "wa"]


def _make_engine(actions: _FakeActions) -> tuple[RollCycleEngine, AccountState]:
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0.6,
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
    )
    state = AccountState()
    monitor = SimpleNamespace(macro_active=False)
    engine = RollCycleEngine(actions, config, state, monitor)
    return engine, state


async def _fast_sleep(*_a, **_k) -> None:
    return None


def _run_normal(engine: RollCycleEngine) -> None:
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._run_cycle())


def test_normal_macro_rolls_one_hour_then_stops_when_tu_exhausted():
    actions = _FakeActions(
        tu_script=[_tu(5, 30), _tu(0, 30)],
        roll_script=[
            _roll(1, 4),
            _roll(2, 3),
            _roll(3, 2),
            _roll(4, 1),
            _roll(5, 0),
        ],
    )
    engine, state = _make_engine(actions)

    _run_normal(engine)

    assert len(actions.roll_commands()) == 5
    assert any("waiting 30m until hourly refill" in entry.text for entry in state.activity_log)


def test_normal_macro_caps_rolls_at_tu_count():
    actions = _FakeActions(
        tu_script=[_tu(1, 34), _tu(0, 34)],
        roll_script=[_roll(1, 0), _roll(2, 0)],
    )
    engine, state = _make_engine(actions)

    _run_normal(engine)

    assert len(actions.roll_commands()) == 1


def test_normal_macro_stops_on_roll_limit_message():
    actions = _FakeActions(
        tu_script=[_tu(2, 34), _tu(0, 34)],
        roll_script=[_roll(1, 1), _roll_limit(34)],
    )
    engine, state = _make_engine(actions)

    _run_normal(engine)

    assert len(actions.roll_commands()) == 2
    assert state.rolls_left == 0
    assert state.rolls_reset_minutes == 34
    assert any("Hourly roll limit reached" in entry.text for entry in state.activity_log)


def test_normal_macro_waits_and_rolls_next_hour():
    actions = _FakeActions(
        tu_script=[_tu(5, 30), _tu(0, 30), _tu(8, 55)],
        roll_script=[
            _roll(1, 4),
            _roll(2, 3),
            _roll(3, 2),
            _roll(4, 1),
            _roll(5, 0),
            _roll(6, 7),
            _roll(7, 6),
            _roll(8, 5),
            _roll(9, 4),
            _roll(10, 3),
            _roll(11, 2),
            _roll(12, 1),
            _roll(13, 0),
        ],
    )
    engine, state = _make_engine(actions)

    _run_normal(engine)

    assert len(actions.roll_commands()) == 13
    assert any("Hourly rolls available" in entry.text for entry in state.activity_log)


def test_seconds_until_perk8_refresh_none_while_active():
    config = MacroConfig(
        kakera_reaction=KakeraReactionRules(
            enabled=True,
            perk_8_budget_mode=True,
        )
    )
    engine = RollCycleEngine(
        SimpleNamespace(),
        config,
        AccountState(perk8_priority_mode="active"),
        SimpleNamespace(),
        daily_resets_get=lambda: {"perk8": {"clicks_exhausted": False}},
    )
    assert engine._seconds_until_perk8_refresh() is None
