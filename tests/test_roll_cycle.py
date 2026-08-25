"""Tests for the normal (continuous hourly) macro loop."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from macro.config import CharacterClaimRules, KakeraReactionRules, MacroConfig
from macro.perk8_daily import PERK8_DAILY_KEY, Perk8DailyRecord
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState
from mudae.types import MessageKind, ParseResult


def _tu(rolls_left: int, reset_minutes: int, *, claim_available: bool = False) -> ParseResult:
    return ParseResult(
        kind=MessageKind.TU,
        summary="$tu",
        fields={
            "rolls_left": rolls_left,
            "rolls_reset_minutes": reset_minutes,
            "claim_available": claim_available,
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


def test_priority_pause_runs_before_tu_and_rolls():
    calls: list[str] = []

    async def pause() -> None:
        calls.append("pause")

    actions = _FakeActions(
        tu_script=[_tu(1, 30), _tu(0, 30)],
        roll_script=[_roll(1, 0)],
    )
    engine, _state = _make_engine(actions)
    engine._on_priority_pause = pause
    _run_normal(engine)
    assert calls, "expected $p/$daily priority pause before the roll loop"
    assert calls[0] == "pause"
    assert "tu" in [c for c, _ in actions.sent]
    assert "wa" in [c for c, _ in actions.sent]


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


class _ResendRollActions(_FakeActions):
    """Returns None for the first two embed waits, then a roll on the third."""

    def __init__(self) -> None:
        super().__init__(tu_script=[], roll_script=[_roll(1, 4)])
        self.roll_waits: list[float] = []

    async def wait_for_roll(self, *, roll_command: str, timeout: float = 20.0):
        self.roll_waits.append(timeout)
        if len(self.roll_waits) < 3:
            return None
        return self._rolls.popleft() if self._rolls else None


def test_perform_roll_resends_after_embed_timeouts():
    actions = _ResendRollActions()
    engine, state = _make_engine(actions)

    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        outcome = asyncio.run(
            engine._perform_roll("wa", 1, [], us_roll=False, stop_on_interrupt=True)
        )

    assert outcome.ok is True
    assert actions.roll_commands() == ["wa", "wa", "wa"]
    assert actions.roll_waits == [5.0, 10.0, 25.0]
    assert any("resending $wa" in entry.text for entry in state.activity_log)


def _wish_roll(message_id: int, rolls_left: int | None = None) -> tuple[SimpleNamespace, ParseResult]:
    """A roll that pings the running account's wishlist and is claimable."""
    snapshot = SimpleNamespace(message_id=message_id)
    fields: dict = {
        "character_name": f"Char{message_id}",
        "wished_by": [999],
        "can_claim": True,
        "claimed": False,
        "buttons": [{"label": "Claim", "custom_id": "1p2p3", "disabled": False}],
    }
    if rolls_left is not None:
        fields["rolls_left"] = rolls_left
    return snapshot, ParseResult(kind=MessageKind.ROLL, summary="$roll", fields=fields)


class _ClaimCapableActions(_FakeActions):
    """``_FakeActions`` plus the claim-button interaction methods."""

    async def wait_for_claim(self, *, timeout: float = 15.0):
        return ParseResult(
            kind=MessageKind.CLAIM,
            summary="claim",
            fields={"winner": "Tester", "character": "Char"},
        )

    async def fetch_message_snapshot(self, message_id: int):
        return None


def test_normal_macro_keeps_rolling_hour_after_wish_ping_claim():
    """A mid-hour wish-ping claim should not end the session while $rt remains."""
    actions = _ClaimCapableActions(
        tu_script=[_tu(5, 30, claim_available=True), _tu(0, 30)],
        roll_script=[
            _roll(1, 4),
            _wish_roll(2, 3),
            _roll(3, 2),
            _roll(4, 1),
            _roll(5, 0),
        ],
    )
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0.6,
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=True),
    )
    state = AccountState(own_user_ids=[999], claim_available=True, rt_available=True)
    monitor = SimpleNamespace(macro_active=False)
    engine = RollCycleEngine(actions, config, state, monitor)

    _run_normal(engine)

    # All 5 rolls of the hour still happen: wish claim spent the claim slot but
    # $rt is still available for another wish later in the hour.
    assert len(actions.roll_commands()) == 5
    assert any("claim now" in entry.text for entry in state.activity_log)
    assert any("continuing after claim" in entry.text for entry in state.activity_log)
    assert any("Macro finished" in entry.text for entry in state.activity_log)


def test_normal_macro_stops_after_wish_claim_without_claim_or_rt():
    """After a wish claim with no claim slot and no $rt, stop rolling entirely."""
    actions = _ClaimCapableActions(
        tu_script=[_tu(5, 30, claim_available=True)],
        roll_script=[
            _roll(1, 4),
            _wish_roll(2, 3),
            _roll(3, 2),
        ],
    )
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0.6,
        character_claim=CharacterClaimRules(
            enabled=False,
            claim_on_wish_ping=True,
            auto_use_rt=False,
        ),
    )
    state = AccountState(
        own_user_ids=[999],
        claim_available=True,
        rt_available=False,
    )
    monitor = SimpleNamespace(macro_active=False)
    engine = RollCycleEngine(actions, config, state, monitor)

    _run_normal(engine)

    assert len(actions.roll_commands()) == 2
    assert any("Wish claimed — no claim or $rt left" in entry.text for entry in state.activity_log)
    assert not any("continuing after claim" in entry.text for entry in state.activity_log)


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


def test_notification_mode_disconnects_during_hourly_wait():
    disconnects: list[str] = []
    reconnects: list[str] = []

    async def disconnect() -> bool:
        monitor.is_connected = False
        disconnects.append("disconnect")
        return True

    async def reconnect() -> bool:
        monitor.is_connected = True
        reconnects.append("reconnect")
        return True

    actions = _FakeActions(
        tu_script=[_tu(1, 30), _tu(0, 30)],
        roll_script=[_roll(1, 0)],
    )
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0.6,
        notification_mode=True,
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
    )
    state = AccountState()
    monitor = SimpleNamespace(macro_active=False, is_connected=True)
    engine = RollCycleEngine(
        actions,
        config,
        state,
        monitor,
        notification_disconnect=disconnect,
        notification_reconnect=reconnect,
    )
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._run_cycle())

    assert len(disconnects) >= 1
    assert len(reconnects) >= 1
    assert disconnects[0] == "disconnect"
    assert any("Notification mode: disconnecting" in entry.text for entry in state.activity_log)
    assert any("Notification mode: reconnecting" in entry.text for entry in state.activity_log)


def test_notification_mode_off_skips_connection_callbacks():
    disconnects: list[str] = []

    async def disconnect() -> bool:
        disconnects.append("disconnect")
        return True

    actions = _FakeActions(
        tu_script=[_tu(1, 30), _tu(0, 30)],
        roll_script=[_roll(1, 0)],
    )
    engine, state = _make_engine(actions)
    engine._config = MacroConfig(
        roll_command="wa",
        notification_mode=False,
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
    )
    engine._notification_disconnect = disconnect
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._run_cycle())

    assert disconnects == []


def test_notification_mode_stop_during_wait_skips_reconnect():
    disconnects: list[str] = []
    reconnects: list[str] = []

    async def disconnect() -> bool:
        monitor.is_connected = False
        disconnects.append("disconnect")
        return True

    async def reconnect() -> bool:
        reconnects.append("reconnect")
        return True

    actions = _FakeActions(
        tu_script=[_tu(1, 30), _tu(0, 30)],
        roll_script=[_roll(1, 0)],
    )
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0.6,
        notification_mode=True,
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
    )
    state = AccountState()
    monitor = SimpleNamespace(macro_active=False, is_connected=True)
    engine = RollCycleEngine(
        actions,
        config,
        state,
        monitor,
        notification_disconnect=disconnect,
        notification_reconnect=reconnect,
    )
    engine._stop.clear()

    async def stop_during_wait(_seconds: float) -> bool:
        engine.stop()
        return False

    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        with patch.object(engine, "_wait_for_scheduled_wake", side_effect=stop_during_wait):
            asyncio.run(engine._run_cycle())

    assert disconnects == ["disconnect"]
    assert reconnects == []


def test_notification_restore_skips_when_stop_requested():
    reconnects: list[str] = []

    async def reconnect() -> bool:
        reconnects.append("reconnect")
        return True

    engine, _state = _make_engine(
        _FakeActions(tu_script=[_tu(1, 30)], roll_script=[_roll(1, 0)])
    )
    engine._config = MacroConfig(notification_mode=True)
    engine._notification_reconnect = reconnect
    engine._stop.set()
    monitor = SimpleNamespace(is_connected=False)
    engine._monitor = monitor

    result = asyncio.run(engine._restore_connection_for_notifications())

    assert result is False
    assert reconnects == []


@pytest.mark.slow
def test_wait_for_scheduled_wake_defers_ohu8_when_disconnected():
    """A refill landing mid-wait, while notification mode holds the gateway down.

    The wait loop must not try to send ``$ohu8`` with no connection, and must
    leave a note so the query happens once the macro reconnects.
    """
    now = dt.datetime.now(dt.timezone.utc)
    store = {
        "value": {
            PERK8_DAILY_KEY: Perk8DailyRecord(
                clicks_exhausted=True,
                refill_at=(now + dt.timedelta(seconds=0.02)).isoformat(),
                updated_at=now.isoformat(),
                last_clicked=40,
                last_click_max=40,
            ).to_dict()
        }
    }
    actions = _FakeActions(tu_script=[_tu(1, 30)], roll_script=[_roll(1, 0)])
    config = MacroConfig(
        notification_mode=True,
        kakera_reaction=KakeraReactionRules(enabled=False, perk_8_budget_mode=True),
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
    )
    monitor = SimpleNamespace(is_connected=False, macro_active=False)
    engine = RollCycleEngine(
        actions,
        config,
        AccountState(),
        monitor,
        daily_resets_get=lambda: store["value"],
        daily_resets_save=lambda daily: store.__setitem__("value", daily),
    )
    engine._stop.clear()
    engine._pending_perk8_refresh = False

    async def run() -> None:
        ok = await engine._wait_for_scheduled_wake(0.05)
        assert ok is True
        assert engine._pending_perk8_refresh is True
        assert [c for c, _ in actions.sent if c == "ohu8"] == []

    asyncio.run(run())


def test_maybe_refresh_perk8_defers_without_connection():
    actions = _FakeActions(tu_script=[_tu(1, 30)], roll_script=[_roll(1, 0)])

    async def fail_send(*_args, **_kwargs):
        raise RuntimeError("Not connected")

    actions.send_command = fail_send  # type: ignore[method-assign]

    config = MacroConfig(
        notification_mode=True,
        kakera_reaction=KakeraReactionRules(enabled=False, perk_8_budget_mode=True),
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
    )
    monitor = SimpleNamespace(is_connected=False, macro_active=False)
    engine = RollCycleEngine(
        actions,
        config,
        AccountState(),
        monitor,
        daily_resets_get=lambda: {
            "perk8": {
                "clicks_exhausted": True,
                "refill_at": "2000-01-01T00:00:00+00:00",
                "last_clicked": 40,
                "last_click_max": 40,
            }
        },
    )

    async def run() -> None:
        await engine._maybe_refresh_perk8_status()

    asyncio.run(run())
    assert engine._pending_perk8_refresh is True


def test_normal_macro_skips_initial_tu_when_persisted_state_valid():
    saved = dt.datetime(2026, 8, 4, 12, 0, tzinfo=dt.timezone.utc)
    reset_at = (saved + dt.timedelta(minutes=45)).isoformat()
    daily = {
        "macro_runtime": {
            "saved_at": saved.isoformat(),
            "rolls_left": 6,
            "rolls_us_bonus": 0,
            "claim_available": True,
            "power_percent": 70.0,
            "power_max_percent": 155.0,
            "power_updated_at": saved.isoformat(),
            "rolls_reset_at": reset_at,
        }
    }
    actions = _FakeActions(
        tu_script=[_tu(0, 45)],
        roll_script=[_roll(1, 5), _roll(2, 4), _roll(3, 3), _roll(4, 2), _roll(5, 1), _roll(6, 0)],
    )
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0.6,
        character_claim=CharacterClaimRules(
            enabled=False,
            claim_on_wish_ping=False,
            persist_tu_state=True,
        ),
    )
    state = AccountState()
    monitor = SimpleNamespace(macro_active=False)
    engine = RollCycleEngine(
        actions,
        config,
        state,
        monitor,
        daily_resets_get=lambda: daily,
        daily_resets_save=lambda d: daily.update(d),
    )
    now = saved + dt.timedelta(minutes=5)

    with patch("macro.runtime_store._utc_now", return_value=now):
        with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
            engine._stop.clear()
            asyncio.run(engine._run_cycle())

    assert not any(cmd == "tu" for cmd, _ in actions.sent[:1])
    assert len(actions.roll_commands()) == 6
    assert any("Using saved $tu state" in entry.text for entry in state.activity_log)
