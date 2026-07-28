"""Tests for Discord transport error classification and recovery."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mudae.discord_errors import is_fatal_runtime_error, is_transient_discord_error
from macro.roll_cycle import RollCycleEngine
from macro.config import CharacterClaimRules, MacroConfig
from macro.state import AccountState


def test_transient_discord_error_detects_503():
    exc = Exception(
        "503 Service Unavailable (error code: 0): upstream connect error or "
        "disconnect/reset before headers. reset reason: remote connection failure"
    )
    assert is_transient_discord_error(exc) is True
    assert is_fatal_runtime_error(exc) is False


def test_event_loop_closed_is_fatal_not_transient():
    exc = RuntimeError("Event loop is closed")
    assert is_fatal_runtime_error(exc) is True
    assert is_transient_discord_error(exc) is False


def test_send_command_retries_transient_errors():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    channel = SimpleNamespace(send=AsyncMock())
    calls = {"n": 0}

    async def flaky_send(_payload: str) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("503 Service Unavailable: upstream connect error")

    channel.send = flaky_send
    monitor._get_text_channel = AsyncMock(return_value=channel)  # type: ignore[method-assign]
    monitor._connected = True
    monitor._client = object()

    asyncio.run(monitor.send_command("wa", prefix="$"))
    assert calls["n"] == 3


def test_recover_transient_connection_reconnects():
    actions = SimpleNamespace(drain_queue=lambda: None)
    monitor = SimpleNamespace(
        force_reconnect=AsyncMock(return_value=True),
        is_connected=True,
        macro_active=False,
    )
    engine = RollCycleEngine(
        actions,  # type: ignore[arg-type]
        MacroConfig(character_claim=CharacterClaimRules(enabled=False)),
        AccountState(),
        monitor,
    )

    async def run() -> None:
        recovered = await engine._recover_transient_connection(
            Exception("503 Service Unavailable"),
            label="$us mode",
            recoveries=0,
        )
        assert recovered == 1
        monitor.force_reconnect.assert_awaited_once()

    asyncio.run(run())


def test_recover_transient_gives_up_after_max():
    actions = SimpleNamespace(drain_queue=lambda: None)
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    engine = RollCycleEngine(
        actions,  # type: ignore[arg-type]
        MacroConfig(character_claim=CharacterClaimRules(enabled=False)),
        AccountState(),
        monitor,
    )

    async def run() -> None:
        recovered = await engine._recover_transient_connection(
            Exception("503 Service Unavailable"),
            label="$us mode",
            recoveries=3,
        )
        assert recovered is None
        monitor.force_reconnect.assert_not_called()

    asyncio.run(run())
