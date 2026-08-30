"""Reconnect / overlap holes: who owns ``macro_active``, and who may start.

Three defects motivated these, all of which only show up overnight when the
hourly loop, a manual minigame, and a gateway drop can land on top of one
another:

1. ``macro_active`` was a boolean saved and restored by each owner, so two
   overlapping owners either cleared it early (Mudae's replies to our own
   commands get attributed to the user's last typed command) or left it
   stuck true (``CommandContextTracker.observe`` silenced for the rest of
   the connection);
2. ``_clear_channel_state`` dropped the flag for the whole reconnect;
3. the hourly loop came out of its refill wait straight into ``$tu`` even
   while a manually started minigame was mid-board.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from macro.config import CharacterClaimRules, MacroConfig
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState
from mudae.macro_activity import (
    enter_macro_activity,
    exit_macro_activity,
    macro_activity,
    macro_activity_depth,
)


def _monitor() -> SimpleNamespace:
    return SimpleNamespace(macro_active=False, is_connected=True)


def _engine(monitor, **kwargs) -> RollCycleEngine:
    return RollCycleEngine(
        SimpleNamespace(drain_queue=lambda: None),  # type: ignore[arg-type]
        MacroConfig(character_claim=CharacterClaimRules(enabled=False)),
        AccountState(),
        monitor,
        **kwargs,
    )


# --- the depth count --------------------------------------------------------


def test_nested_owners_keep_the_flag_until_the_last_one_leaves():
    monitor = _monitor()
    enter_macro_activity(monitor)
    enter_macro_activity(monitor)
    assert monitor.macro_active is True
    exit_macro_activity(monitor)
    assert monitor.macro_active is True, "an inner owner must not clear the flag"
    exit_macro_activity(monitor)
    assert monitor.macro_active is False
    assert macro_activity_depth(monitor) == 0


def test_owners_may_finish_out_of_order():
    """The roll cycle can stop while a manual minigame is still clicking."""
    monitor = _monitor()
    enter_macro_activity(monitor)  # roll cycle
    enter_macro_activity(monitor)  # manual $oh, started during the refill wait
    exit_macro_activity(monitor)  # user hits Stop; the cycle's finally runs
    assert monitor.macro_active is True, "the minigame still owns the channel"
    exit_macro_activity(monitor)  # the board finishes
    assert monitor.macro_active is False, "no stale flag once nothing is running"


def test_exit_without_enter_does_not_go_negative():
    monitor = _monitor()
    exit_macro_activity(monitor)
    assert macro_activity_depth(monitor) == 0
    assert monitor.macro_active is False
    enter_macro_activity(monitor)
    assert monitor.macro_active is True


def test_context_manager_releases_on_error():
    monitor = _monitor()
    try:
        with macro_activity(monitor):
            raise RuntimeError("board timed out")
    except RuntimeError:
        pass
    assert monitor.macro_active is False


# --- the reader keeps the flag across a reconnect ---------------------------


def test_clear_channel_state_leaves_macro_active_alone():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    enter_macro_activity(monitor)
    monitor._clear_channel_state()
    assert monitor.macro_active is True
    assert monitor._pending_macro_command is None


def test_reconnect_never_exposes_a_window_with_the_flag_down():
    """The old code cleared the flag and restored it only after the gateway was
    back — up to 30 seconds during which arriving messages were mis-attributed.
    """
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    enter_macro_activity(monitor)
    seen: list[bool] = []

    async def _slow_start() -> bool:
        seen.append(monitor.macro_active)
        return True

    monitor.stop_background = AsyncMock()  # type: ignore[method-assign]
    monitor.start_background = _slow_start  # type: ignore[method-assign]

    asyncio.run(monitor.force_reconnect())
    assert seen == [True]
    assert monitor.macro_active is True


def test_switch_channel_keeps_the_flag_for_a_running_macro():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    enter_macro_activity(monitor)
    asyncio.run(monitor.switch_channel(456))
    assert monitor.macro_active is True
    assert monitor.channel_id == 456


# --- the hourly loop yields to a manual minigame ----------------------------


def test_wait_for_minigame_returns_immediately_when_idle():
    engine = _engine(_monitor(), minigames_busy=lambda: False)
    assert asyncio.run(engine._wait_for_minigame_to_finish("Hourly refill")) is True


def test_wait_for_minigame_blocks_until_the_board_finishes():
    busy = {"value": True}
    slept: list[float] = []

    async def _sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) >= 3:
            busy["value"] = False

    engine = _engine(_monitor(), minigames_busy=lambda: busy["value"])
    engine._ctx.sleep = _sleep

    assert asyncio.run(engine._wait_for_minigame_to_finish("Hourly refill")) is True
    assert len(slept) == 3


def test_wait_for_minigame_gives_up_on_a_stuck_board():
    """A board that never ends must not wedge the hourly loop forever."""

    async def _sleep(_seconds: float) -> None:
        return None

    engine = _engine(_monitor(), minigames_busy=lambda: True)
    engine._ctx.sleep = _sleep

    assert asyncio.run(engine._wait_for_minigame_to_finish("Hourly refill")) is False


def test_wait_for_minigame_aborts_on_stop():
    async def _sleep(_seconds: float) -> None:
        engine._stop.set()

    engine = _engine(_monitor(), minigames_busy=lambda: True)
    engine._ctx.sleep = _sleep

    assert asyncio.run(engine._wait_for_minigame_to_finish("Hourly refill")) is False


def test_scheduled_wake_does_not_run_work_during_a_minigame():
    """$p / $daily / perk-8 / play-all all send commands — none may interleave."""
    ran: list[str] = []

    async def _sleep(_seconds: float) -> None:
        return None

    engine = _engine(
        _monitor(),
        minigames_busy=lambda: True,
        on_priority_pause=lambda: ran.append("priority"),
        play_daily_minigames=lambda: ran.append("play-all"),
    )
    engine._ctx.sleep = _sleep

    asyncio.run(engine._on_scheduled_wake())
    assert ran == []


# --- starting a session on top of a minigame --------------------------------


def test_start_refuses_while_a_minigame_runs():
    engine = _engine(_monitor(), minigames_busy=lambda: True)
    engine.start()
    assert engine.is_running is False


def test_start_us_mode_refuses_while_a_minigame_runs():
    engine = _engine(_monitor(), minigames_busy=lambda: True)
    engine.start_us_mode()
    assert engine.is_running is False


def test_start_is_unaffected_when_no_hook_is_wired():
    engine = _engine(_monitor())
    assert engine._minigame_start_blocked("hourly macro") is False
