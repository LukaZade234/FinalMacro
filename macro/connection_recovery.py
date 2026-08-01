"""Discord transport recovery: reconnects and transient-error retries.

Pure transport concern — nothing here knows about Mudae, rolls, or presets. One
instance per running account, built from that account's :class:`RollContext`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from macro.roll_context import RollContext
from mudae.discord_errors import is_fatal_runtime_error, is_transient_discord_error

# How many Discord 503 / disconnect recoveries to attempt before giving up.
MAX_TRANSIENT_RECOVERIES = 3
# Pause after a reconnect so the gateway settles before the next command.
RECONNECT_SETTLE_SEC = 2.0

# Returns bool or an awaitable of bool; supplied by the GUI bridge.
ConnectionHook = Callable[[], Any]


async def _resolve(result: Any) -> bool:
    if asyncio.iscoroutine(result):
        return bool(await result)
    return bool(result)


class ConnectionRecovery:
    def __init__(
        self,
        ctx: RollContext,
        *,
        notification_disconnect: ConnectionHook | None = None,
        notification_reconnect: ConnectionHook | None = None,
        max_transient_recoveries: int = MAX_TRANSIENT_RECOVERIES,
        settle_sec: float = RECONNECT_SETTLE_SEC,
    ) -> None:
        self._ctx = ctx
        self._notification_disconnect = notification_disconnect
        self._notification_reconnect = notification_reconnect
        self._max_recoveries = max_transient_recoveries
        self._settle_sec = settle_sec

    async def release_for_notifications(self) -> bool:
        """Disconnect between hourly sessions when notification mode is enabled."""
        ctx = self._ctx
        if ctx.stop_requested:
            return False
        if not ctx.config.notification_mode:
            return True
        if self._notification_disconnect is None:
            return True
        if not ctx.monitor_connected:
            return True
        ctx.log("Notification mode: disconnecting until next roll session")
        return await _resolve(self._notification_disconnect())

    async def restore_for_notifications(self) -> bool:
        """Reconnect before the next hourly roll session when needed."""
        ctx = self._ctx
        if ctx.stop_requested:
            return False
        if not ctx.config.notification_mode:
            return True
        if self._notification_reconnect is None:
            return True
        if ctx.monitor_connected:
            return True
        ctx.log("Notification mode: reconnecting for roll session")
        return await _resolve(self._notification_reconnect())

    async def force_reconnect(self) -> bool:
        """Force a fresh Discord gateway after a transport failure."""
        ctx = self._ctx
        if ctx.stop_requested:
            return False
        reconnect = getattr(ctx.monitor, "force_reconnect", None)
        if reconnect is None:
            # Fall back to notification-mode reconnect hooks when available.
            if not await self.release_for_notifications():
                return False
            return await self.restore_for_notifications()
        return await _resolve(reconnect())

    async def recover_transient(
        self,
        exc: BaseException,
        *,
        label: str,
        recoveries: int,
    ) -> int | None:
        """Reconnect after a transient Discord error.

        Returns the new recovery count on success, or ``None`` when the caller
        should abort (fatal / too many failures / reconnect failed).
        """
        ctx = self._ctx
        if is_fatal_runtime_error(exc):
            ctx.log(f"{label}: fatal runtime error — {exc}")
            return None
        if not is_transient_discord_error(exc):
            return None
        recoveries += 1
        if recoveries > self._max_recoveries:
            ctx.log(
                f"{label}: connection errors exhausted "
                f"({recoveries - 1}/{self._max_recoveries}) — stopping"
            )
            return None
        ctx.log(
            f"{label}: connection error ({exc}) — reconnecting "
            f"({recoveries}/{self._max_recoveries})"
        )
        if not await self.force_reconnect():
            ctx.log(f"{label}: reconnect failed — stopping")
            return None
        ctx.actions.drain_queue()
        await ctx.sleep(self._settle_sec)
        return recoveries

    async def send_command_with_reconnect(
        self,
        command: str,
        *,
        label: str,
    ) -> int | None:
        """Send a command; reconnect once on a transient Discord transport error."""
        ctx = self._ctx
        try:
            return await ctx.actions.send_command(command, prefix=ctx.config.prefix)
        except Exception as exc:
            if is_fatal_runtime_error(exc) or not is_transient_discord_error(exc):
                raise
            ctx.log(f"{label}: connection error ({exc}) — reconnecting")
            if not await self.force_reconnect():
                ctx.log(f"{label}: reconnect failed")
                raise
            ctx.actions.drain_queue()
            await ctx.sleep(self._settle_sec)
            return await ctx.actions.send_command(command, prefix=ctx.config.prefix)
