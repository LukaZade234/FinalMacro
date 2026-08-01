"""Tests for ConnectionRecovery driven through a RollContext (no engine)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from macro.config import MacroConfig
from macro.connection_recovery import ConnectionRecovery
from macro.roll_context import RollContext
from macro.state import AccountState


class _FakeActions:
    def __init__(self, send: object | None = None) -> None:
        self.drained = 0
        self.sent: list[tuple[str, str | None]] = []
        self._send = send

    def drain_queue(self) -> None:
        self.drained += 1

    async def send_command(self, command: str, *, prefix: str | None = None) -> int:
        self.sent.append((command, prefix))
        if callable(self._send):
            return self._send(len(self.sent))
        return 42


def _make_ctx(
    *,
    actions: _FakeActions | None = None,
    monitor: object | None = None,
    notification_mode: bool = False,
) -> tuple[RollContext, list[str], list[float]]:
    """Build a context with recording log/sleep stand-ins."""
    logs: list[str] = []
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    ctx = RollContext(
        actions=actions or _FakeActions(),
        config=MacroConfig(notification_mode=notification_mode),
        state=AccountState(),
        monitor=monitor if monitor is not None else SimpleNamespace(is_connected=True),
        log=logs.append,
        sleep=record_sleep,
    )
    return ctx, logs, sleeps


def _transient() -> Exception:
    return Exception("503 Service Unavailable: upstream connect error")


def test_recover_transient_reconnects_and_counts_up():
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    actions = _FakeActions()
    ctx, _logs, sleeps = _make_ctx(actions=actions, monitor=monitor)
    recovery = ConnectionRecovery(ctx)

    result = asyncio.run(
        recovery.recover_transient(_transient(), label="$us mode", recoveries=0)
    )

    assert result == 1
    monitor.force_reconnect.assert_awaited_once()
    assert actions.drained == 1
    # Settle wait went through the injected sleep, not a real one.
    assert sleeps == [2.0]


def test_recover_transient_gives_up_at_configured_limit():
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    ctx, logs, _sleeps = _make_ctx(monitor=monitor)
    recovery = ConnectionRecovery(ctx, max_transient_recoveries=2)

    result = asyncio.run(
        recovery.recover_transient(_transient(), label="$us mode", recoveries=2)
    )

    assert result is None
    monitor.force_reconnect.assert_not_called()
    assert any("exhausted (2/2)" in line for line in logs)


def test_recover_transient_ignores_fatal_and_unknown_errors():
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    ctx, logs, _sleeps = _make_ctx(monitor=monitor)
    recovery = ConnectionRecovery(ctx)

    async def run() -> None:
        fatal = await recovery.recover_transient(
            RuntimeError("Event loop is closed"), label="Roll", recoveries=0
        )
        unknown = await recovery.recover_transient(
            ValueError("bad character name"), label="Roll", recoveries=0
        )
        assert fatal is None
        assert unknown is None

    asyncio.run(run())
    monitor.force_reconnect.assert_not_called()
    assert any("fatal runtime error" in line for line in logs)


def test_recover_transient_aborts_when_reconnect_fails():
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=False))
    ctx, logs, _sleeps = _make_ctx(monitor=monitor)
    recovery = ConnectionRecovery(ctx)

    result = asyncio.run(
        recovery.recover_transient(_transient(), label="Roll", recoveries=0)
    )

    assert result is None
    assert any("reconnect failed" in line for line in logs)


def test_send_command_retries_once_after_transient_error():
    def flaky(attempt: int) -> int:
        if attempt == 1:
            raise _transient()
        return 99

    actions = _FakeActions(send=flaky)
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    ctx, _logs, sleeps = _make_ctx(actions=actions, monitor=monitor)
    recovery = ConnectionRecovery(ctx)

    message_id = asyncio.run(recovery.send_command_with_reconnect("wa", label="Roll 1"))

    assert message_id == 99
    assert [cmd for cmd, _ in actions.sent] == ["wa", "wa"]
    monitor.force_reconnect.assert_awaited_once()
    assert sleeps == [2.0]


def test_send_command_reraises_fatal_without_reconnecting():
    def fatal(_attempt: int) -> int:
        raise RuntimeError("Event loop is closed")

    actions = _FakeActions(send=fatal)
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    ctx, _logs, _sleeps = _make_ctx(actions=actions, monitor=monitor)
    recovery = ConnectionRecovery(ctx)

    with pytest.raises(RuntimeError):
        asyncio.run(recovery.send_command_with_reconnect("wa", label="Roll 1"))

    monitor.force_reconnect.assert_not_called()


def test_send_command_uses_live_prefix_after_config_swap():
    """update_config() replaces ctx.config; recovery must not cache the old one."""
    actions = _FakeActions()
    ctx, _logs, _sleeps = _make_ctx(actions=actions)
    recovery = ConnectionRecovery(ctx)

    asyncio.run(recovery.send_command_with_reconnect("tu", label="tu"))
    ctx.config = MacroConfig(prefix="!")
    asyncio.run(recovery.send_command_with_reconnect("tu", label="tu"))

    assert [prefix for _cmd, prefix in actions.sent] == ["$", "!"]


def test_notification_hooks_skipped_when_mode_disabled():
    disconnect = AsyncMock(return_value=True)
    ctx, _logs, _sleeps = _make_ctx(notification_mode=False)
    recovery = ConnectionRecovery(ctx, notification_disconnect=disconnect)

    assert asyncio.run(recovery.release_for_notifications()) is True
    disconnect.assert_not_called()


def test_notification_release_and_restore_track_connection_state():
    monitor = SimpleNamespace(is_connected=True)
    disconnect = AsyncMock(return_value=True)
    reconnect = AsyncMock(return_value=True)
    ctx, logs, _sleeps = _make_ctx(monitor=monitor, notification_mode=True)
    recovery = ConnectionRecovery(
        ctx,
        notification_disconnect=disconnect,
        notification_reconnect=reconnect,
    )

    async def run() -> None:
        assert await recovery.release_for_notifications() is True
        disconnect.assert_awaited_once()

        # Already connected — restoring is a no-op.
        assert await recovery.restore_for_notifications() is True
        reconnect.assert_not_called()

        monitor.is_connected = False
        assert await recovery.restore_for_notifications() is True
        reconnect.assert_awaited_once()

    asyncio.run(run())
    assert any("disconnecting" in line for line in logs)


def test_notification_hooks_accept_sync_callables():
    monitor = SimpleNamespace(is_connected=True)
    ctx, _logs, _sleeps = _make_ctx(monitor=monitor, notification_mode=True)
    recovery = ConnectionRecovery(ctx, notification_disconnect=lambda: True)

    assert asyncio.run(recovery.release_for_notifications()) is True


def test_force_reconnect_falls_back_to_notification_hooks():
    """Monitors without force_reconnect cycle the notification hooks instead."""
    monitor = SimpleNamespace(is_connected=True)
    calls: list[str] = []

    def disconnect() -> bool:
        calls.append("disconnect")
        monitor.is_connected = False
        return True

    def reconnect() -> bool:
        calls.append("reconnect")
        monitor.is_connected = True
        return True

    ctx, _logs, _sleeps = _make_ctx(monitor=monitor, notification_mode=True)
    recovery = ConnectionRecovery(
        ctx,
        notification_disconnect=disconnect,
        notification_reconnect=reconnect,
    )

    assert asyncio.run(recovery.force_reconnect()) is True
    assert calls == ["disconnect", "reconnect"]


def test_stop_event_short_circuits_every_reconnect_path():
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    ctx, _logs, _sleeps = _make_ctx(monitor=monitor, notification_mode=True)
    ctx.stop.set()
    recovery = ConnectionRecovery(
        ctx,
        notification_disconnect=AsyncMock(return_value=True),
        notification_reconnect=AsyncMock(return_value=True),
    )

    async def run() -> None:
        assert await recovery.force_reconnect() is False
        assert await recovery.release_for_notifications() is False
        assert await recovery.restore_for_notifications() is False

    asyncio.run(run())
    monitor.force_reconnect.assert_not_called()


def test_recoveries_are_isolated_per_account():
    """Two accounts each get their own recovery budget and monitor."""
    monitor_a = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    monitor_b = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    ctx_a, _la, _sa = _make_ctx(monitor=monitor_a)
    ctx_b, _lb, _sb = _make_ctx(monitor=monitor_b)
    ctx_a.account_id = "acc_a"
    ctx_b.account_id = "acc_b"
    recovery_a = ConnectionRecovery(ctx_a, max_transient_recoveries=1)
    recovery_b = ConnectionRecovery(ctx_b, max_transient_recoveries=3)

    async def run() -> None:
        assert await recovery_a.recover_transient(
            _transient(), label="A", recoveries=1
        ) is None
        assert await recovery_b.recover_transient(
            _transient(), label="B", recoveries=1
        ) == 2

    asyncio.run(run())
    monitor_a.force_reconnect.assert_not_called()
    monitor_b.force_reconnect.assert_awaited_once()
