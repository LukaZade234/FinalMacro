"""Tests for kakera click timeout handling (stale drain + retry)."""

from __future__ import annotations

import asyncio
from collections import deque
from unittest.mock import patch

from macro.config import KakeraReactionRules, MacroConfig
from macro.kakera_reactor import (
    _KAKERA_CLICK_SETTLE_SEC,
    KakeraReactor,
)
from macro.actions import is_kakera_outcome_message
from macro.state import AccountState
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult


def _snapshot(message_id: int) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id,
        channel_id=1,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )


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


class _FakeActionsWithQueue:
    def __init__(self) -> None:
        self.clicks: list[str] = []
        self._outcomes: deque[ParseResult | None] = deque()
        self._queue: list[tuple[MudaeMessageSnapshot, ParseResult]] = []

    def feed(self, snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> None:
        self._queue.append((snapshot, parsed))

    def collect_queued(self, predicate):
        matches = [item for item in self._queue if predicate(*item)]
        self._queue = [item for item in self._queue if item not in matches]
        return matches

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        self.clicks.append(custom_id)
        return True

    async def wait_for(self, predicate, *, timeout: float = 8.0):
        del timeout
        if self._outcomes:
            outcome = self._outcomes.popleft()
            if outcome is None:
                return None
            item = (_snapshot(1), outcome)
            if predicate(*item):
                return item
        return None

    def count_queued_outcomes(self, predicate):
        matches = sum(1 for item in self._queue if predicate(*item))
        return len(self._queue), matches


async def _fast_sleep(_delay: float) -> None:
    return None


def test_kakera_drains_stale_outcomes_at_start():
    async def _case() -> None:
        state = AccountState(power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True,
                types_allowed=["kakeraR"],
            ),
        )
        actions = _FakeActionsWithQueue()
        actions.feed(_snapshot(99), ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="", fields={}))
        actions._outcomes.append(
            ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="ok", fields={"amount": 1})
        )
        logs: list[str] = []
        reactor = KakeraReactor(actions, config, state, log=logs.append)
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            clicks = await reactor.react(message_id=1, fields=_fields())

        assert clicks == 1
        assert any("cleared 1 stale response" in line for line in logs)

    asyncio.run(_case())


def test_kakera_retries_click_after_timeout():
    async def _case() -> None:
        state = AccountState(power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True,
                types_allowed=["kakeraR"],
            ),
        )
        actions = _FakeActionsWithQueue()
        actions._outcomes.extend([None, ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="ok", fields={})])
        logs: list[str] = []
        reactor = KakeraReactor(actions, config, state, log=logs.append)
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            clicks = await reactor.react(message_id=2, fields=_fields())

        assert clicks == 1
        assert actions.clicks == ["btn1", "btn1"]
        assert any("retrying click on TestChar" in line for line in logs)
        assert not any("click timeout" in line for line in logs)

    asyncio.run(_case())


def test_kakera_click_settle_runs_before_wait():
    sleeps: list[float] = []

    async def _record_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def _case() -> None:
        state = AccountState(power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True,
                types_allowed=["kakeraR"],
            ),
        )
        actions = _FakeActionsWithQueue()
        actions._outcomes.append(
            ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="ok", fields={})
        )
        reactor = KakeraReactor(actions, config, state, log=lambda _m: None)
        with patch("macro.kakera_reactor.asyncio.sleep", new=_record_sleep):
            await reactor.react(message_id=3, fields=_fields())

        assert _KAKERA_CLICK_SETTLE_SEC in sleeps

    asyncio.run(_case())


def test_kakera_timeout_calls_resync_hook():
    async def _case() -> None:
        state = AccountState(power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True,
                types_allowed=["kakeraR"],
            ),
        )
        actions = _FakeActionsWithQueue()
        actions._outcomes.extend([None, None])
        logs: list[str] = []
        called: list[bool] = []

        async def _resync() -> None:
            called.append(True)

        reactor = KakeraReactor(
            actions,
            config,
            state,
            log=logs.append,
            on_click_timeout=_resync,
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            clicks = await reactor.react(message_id=4, fields=_fields())

        assert clicks == 0
        assert called == [True]
        assert any("click timeout" in line for line in logs)

    asyncio.run(_case())
