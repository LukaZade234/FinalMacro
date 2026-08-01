"""Per-account runtime context shared by roll-cycle subsystems.

One :class:`RollContext` per running account. Nothing here is module-level or
global, so a coordinator can drive several accounts concurrently by building one
context each (see ``docs/MULTI_ACCOUNT.md``).

Subsystems must read ``ctx.config`` and ``ctx.state`` through the context on every
use rather than caching them at construction: :meth:`RollCycleEngine.update_config`
swaps ``config`` when a live preset is edited mid-session.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from macro.config import MacroConfig
from macro.state import AccountState


async def default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _drop_text(_text: str) -> None:
    return None


def _do_nothing() -> None:
    return None


@dataclass
class RollContext:
    """Dependencies one account's roll subsystems need.

    ``actions`` and ``monitor`` are duck-typed so tests can pass stand-ins without
    a Discord connection.
    """

    actions: Any
    config: MacroConfig
    state: AccountState
    monitor: Any
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    # Empty while a single target runs; set once a coordinator drives several.
    account_id: str = ""
    log: Callable[[str], None] = _drop_text
    log_debug: Callable[[str], None] = _drop_text
    notify: Callable[[], None] = _do_nothing
    # Injectable so tests skip real waits, jitter can wrap every delay in one
    # place, and a coordinator can stagger accounts off the same tick.
    sleep: Callable[[float], Awaitable[None]] = default_sleep

    @property
    def stop_requested(self) -> bool:
        return self.stop.is_set()

    @property
    def monitor_connected(self) -> bool:
        return bool(getattr(self.monitor, "is_connected", False))

    @property
    def commands_blocked(self) -> bool:
        """True when notification mode dropped the gateway, so no sends are possible."""
        return self.config.notification_mode and not self.monitor_connected
