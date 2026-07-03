"""Tests for ``$dk`` auto-use timing and kakera retry in :class:`KakeraReactor`."""

from __future__ import annotations

import asyncio
from collections import deque
from unittest.mock import patch

from macro.config import KakeraReactionRules, MacroConfig
from macro.kakera_reactor import (
    _DK_PAUSE_AFTER_SEC,
    _DK_PAUSE_BEFORE_SEC,
    _DK_RETRY_PAUSE_AFTER_SEC,
    _DK_RETRY_PAUSE_BEFORE_SEC,
    KakeraReactor,
)
from macro.state import AccountState
from mudae.types import MessageKind, ParseResult


class _FakeActions:
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

    async def wait_for_kakera_outcome(self, *, timeout: float = 8.0):
        return ParseResult(
            kind=MessageKind.KAKERA_REACT_DENIED,
            summary="denied",
            fields={"kakera_cooldown_minutes": 5},
        )

    async def wait_for_dk_use(self, *, timeout: float = 12.0):
        return self._dk.popleft() if self._dk else None


async def _fast_sleep(_delay: float) -> None:
    return None


def _fields() -> dict:
    return {
        "character_name": "TestChar",
        "buttons": [
            {
                "kind": "kakera",
                "is_kakera": True,
                "custom_id": "btn1",
                "emoji": "kakeraR",
            }
        ],
    }


def test_dk_waits_before_and_after_send_and_retries_kakera():
    async def _case() -> None:
        state = AccountState(dk_stock=1, power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True,
                types_allowed=["kakeraR"],
                auto_use_dk=True,
            ),
        )
        actions = _FakeActions()
        logs: list[str] = []
        reactor = KakeraReactor(
            actions=actions,
            config=config,
            state=state,
            log=logs.append,
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            await reactor.react(message_id=1, fields=_fields(), roll_index=3)

        assert actions.sent == [("dk", "$")]
        assert any("waiting 1s before send" in line for line in logs)
        assert any("sent $dk" in line for line in logs)
        assert any("waiting 1s for Mudae to settle" in line for line in logs)
        assert any("retrying TestChar after $dk refill" in line for line in logs)

    asyncio.run(_case())


def test_dk_retry_uses_longer_pauses():
    sleeps: list[float] = []

    async def _record_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def _case() -> None:
        state = AccountState(dk_stock=2, power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True,
                types_allowed=["kakeraR"],
                auto_use_dk=True,
            ),
        )
        actions = _FakeActions()
        actions._dk = deque(
            [
                ParseResult(
                    kind=MessageKind.DK_CLAIM,
                    summary="$dk",
                    fields={"dk_used": True, "amount": 50, "dk_stock": 1},
                ),
                ParseResult(
                    kind=MessageKind.DK_CLAIM,
                    summary="$dk",
                    fields={"dk_used": True, "amount": 50, "dk_stock": 0},
                ),
            ]
        )
        logs: list[str] = []
        reactor = KakeraReactor(actions, config, state, log=logs.append)
        with patch("macro.kakera_reactor.asyncio.sleep", new=_record_sleep):
            await reactor.react(message_id=2, fields=_fields(), roll_index=1)

        assert _DK_PAUSE_BEFORE_SEC in sleeps
        assert _DK_PAUSE_AFTER_SEC in sleeps
        assert _DK_RETRY_PAUSE_BEFORE_SEC in sleeps
        assert _DK_RETRY_PAUSE_AFTER_SEC in sleeps
        assert actions.sent == [("dk", "$"), ("dk", "$")]

    asyncio.run(_case())


def test_dk_writes_rule_trace():
    async def _case() -> None:
        state = AccountState(dk_stock=1, power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(
            kakera_reaction=KakeraReactionRules(
                enabled=True,
                types_allowed=["kakeraR"],
                auto_use_dk=True,
            ),
        )
        actions = _FakeActions()
        reactor = KakeraReactor(actions, config, state, log=lambda _m: None)
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            await reactor.react(message_id=5, fields=_fields(), roll_index=7)

        dk_traces = [t for t in state.rule_trace if t.block == "dk"]
        assert dk_traces
        assert any(t.decision == "wait" for t in dk_traces)
        assert any(t.decision == "use" for t in dk_traces)

    asyncio.run(_case())
