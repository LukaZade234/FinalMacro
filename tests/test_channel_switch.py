"""Tests for live server/channel switching without a manual disconnect."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from macro.roll_cycle import RollCycleEngine
from macro.config import MacroConfig
from macro.state import AccountState
from mudae.discord_reader import ChannelMonitor


class _FakeActions:
    def drain_queue(self) -> None:
        return None


def test_switch_channel_updates_id_and_clears_cached_state():
    monitor = ChannelMonitor(token="token", channel_id=111)
    monitor._messages[1] = SimpleNamespace(message_id=1)
    monitor._pending_macro_command = "tu"
    monitor._connected = True
    monitor._client = SimpleNamespace(user=SimpleNamespace(name="Tester"))

    async def fake_label() -> str:
        return "#mudae (222)"

    with patch.object(monitor, "_resolve_channel_label", new=fake_label):
        with patch.object(monitor, "_emit_status") as emit:
            ok = asyncio.run(monitor.switch_channel(222))

    assert ok is True
    assert monitor.channel_id == 222
    assert monitor._messages == {}
    assert monitor._pending_macro_command is None
    emit.assert_called_once()
    assert "Switched" in emit.call_args.args[0]


def test_engine_update_run_target_rebinds_daily_store():
    store: dict[str, dict] = {"a": {"perk8": {}}, "b": {"perk8": {}}}
    engine = RollCycleEngine(
        _FakeActions(),
        MacroConfig(),
        AccountState(),
        SimpleNamespace(is_connected=True),
        daily_resets_get=lambda: store["a"],
        daily_resets_save=lambda daily: store.__setitem__("a", daily),
        account_id="acc-a",
    )

    engine.update_run_target(
        account_id="acc-b",
        daily_resets_get=lambda: store["b"],
        daily_resets_save=lambda daily: store.__setitem__("b", daily),
    )

    assert engine._ctx.account_id == "acc-b"
    engine._perk8.save_daily({"perk8": {"last_clicked": 3}})
    assert store["b"]["perk8"]["last_clicked"] == 3
    assert "perk8" not in store["a"] or store["a"].get("perk8") != {"last_clicked": 3}


def test_apply_run_target_switch_moves_monitor_without_token_change():
    from gui.bridge import AppBridge

    bridge = AppBridge()
    loop = asyncio.new_event_loop()
    bridge._loop = loop
    bridge._thread = SimpleNamespace(is_alive=lambda: True)
    bridge._run_token = "same-token"
    bridge._run_account_id = "acc-1"
    bridge._run_channel_profile_id = "ch-a"

    monitor = SimpleNamespace(
        channel_id=111,
        is_connected=True,
        get_own_usernames=lambda: ["Tester"],
        get_own_user_id=lambda: 42,
        switch_channel=AsyncMock(return_value=True),
        reconnect=AsyncMock(return_value=True),
    )
    bridge._monitor = monitor
    bridge._actions = _FakeActions()
    bridge._engine = RollCycleEngine(
        bridge._actions,
        MacroConfig(),
        bridge._macro_state,
        monitor,
        account_id="acc-1",
    )

    resolved = SimpleNamespace(
        token="same-token",
        discord_channel_id="222",
        macro_config=MacroConfig(),
        preset_id="default",
        account_id="acc-1",
        channel_profile_id="ch-b",
        label="Tester · Server · #mudae · default",
    )

    try:
        with patch.object(bridge, "_bind_run_target_metadata") as bind:
            with patch.object(bridge, "_on_connected"):
                with patch.object(bridge, "_on_macro_state"):
                    asyncio.run(bridge._apply_run_target_switch(resolved))
    finally:
        loop.close()

    monitor.switch_channel.assert_awaited_once_with(222)
    monitor.reconnect.assert_not_awaited()
    bind.assert_called_once_with(resolved)
