"""Notification mode keeps the gateway up when the rolls reset is close.

Seen live: the $p wake at 16:00:00 landed 28 s before the rolls reset, so
after $p the wake dropped the connection only for the refill to reconnect it
20 s later.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from macro.config import MacroConfig
from macro.roll_cycle import NOTIFICATION_STAY_CONNECTED_SEC, RollCycleEngine
from macro.state import AccountState


def _engine(seconds_to_reset: float):
    config = MacroConfig(roll_command="wa", roll_delay_sec=0)
    state = AccountState()
    state.rolls_reset_minutes = max(1, int(seconds_to_reset // 60))
    engine = RollCycleEngine(
        SimpleNamespace(drain_queue=lambda: None),
        config,
        state,
        SimpleNamespace(macro_active=False),
    )
    engine._seconds_until_rolls_reset = lambda: seconds_to_reset
    released: list[bool] = []

    async def release():
        released.append(True)
        return True

    async def nothing(*_a, **_k):
        return True

    engine._release_connection_for_notifications = release
    engine._restore_connection_for_notifications = nothing
    engine._run_priority_pause = nothing
    engine._maybe_refresh_perk8_status = nothing
    engine._maybe_play_daily_minigames = nothing
    engine._maybe_auto_kakera_loot = nothing
    engine._waiting_for_hourly_refill = True
    return engine, released


def test_wake_just_before_the_reset_stays_connected():
    engine, released = _engine(28)
    asyncio.run(engine._on_scheduled_wake())
    assert released == []


def test_wake_well_before_the_reset_disconnects_again():
    engine, released = _engine(NOTIFICATION_STAY_CONNECTED_SEC + 600)
    asyncio.run(engine._on_scheduled_wake())
    assert released == [True]
