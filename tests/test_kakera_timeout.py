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


def _fields(*, perk_8: bool = False) -> dict:
    return {
        "character_name": "TestChar",
        "perk_8": True if perk_8 else None,
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
            clicks = await reactor.react(
                message_id=4, fields=_fields(perk_8=True)
            )

        assert clicks == 0
        assert called == [True]
        assert any("click timeout" in line for line in logs)

    asyncio.run(_case())


def test_kakera_timeout_resyncs_on_a_normal_character_too():
    """An uncertain click desyncs the count whoever the character is.

    A paid click on an ordinary character still spends one of the daily 40
    unless it is a bypass colour, and the click may have landed even though the
    wait failed — so the count has to come from ``$ohu8``, not from us.

    This resync was unconditional until the click-result refactor in 9999ff3
    gated it on ``has_perk_8``. The symptom was the Run page showing 39/40
    while Mudae said 40/40: a purple on a non-perk-8 roll paid out, the wait
    timed out, nothing was recorded, and nothing reconciled it for the rest of
    the day. ``sphere_reactor`` resyncs on every timeout; so does this now.
    """

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
        called: list[bool] = []

        async def _resync() -> None:
            called.append(True)

        reactor = KakeraReactor(
            actions,
            config,
            state,
            log=lambda _m: None,
            on_click_timeout=_resync,
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            clicks = await reactor.react(message_id=5, fields=_fields())

        assert clicks == 0
        assert called == [True]

    asyncio.run(_case())


def test_kakera_perk8_timeout_resyncs_even_if_retry_succeeds():
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
        actions._outcomes.extend(
            [
                None,
                ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="ok", fields={}),
            ]
        )
        called: list[bool] = []

        async def _resync() -> None:
            called.append(True)

        reactor = KakeraReactor(
            actions,
            config,
            state,
            log=lambda _m: None,
            on_click_timeout=_resync,
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            clicks = await reactor.react(
                message_id=6, fields=_fields(perk_8=True)
            )

        assert clicks == 1
        assert called == [True]

    asyncio.run(_case())


def test_free_kakera_clicks_trigger_a_perk8_resync():
    """Chaos free kakera never pass through the budget accounting.

    ``_click_free_kakera`` is a separate path from ``react``, so
    ``counts_toward_perk8_budget`` / ``record_kakera_clicks`` never run for the
    buttons a chaos spawn grants on a character we own. Whether Mudae charges
    them against the daily 40 is not something the macro can tell from the
    click, so it asks ``$ohu8`` instead of guessing — otherwise the local count
    silently sits below Mudae's for the rest of the day.
    """

    async def _case() -> None:
        state = AccountState(power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(prefix="$", kakera_reaction=KakeraReactionRules(enabled=True))
        actions = _FakeActionsWithQueue()
        actions._outcomes.extend(
            [
                ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="ok", fields={}),
                ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="ok", fields={}),
            ]
        )
        called: list[bool] = []

        async def _resync() -> None:
            called.append(True)

        reactor = KakeraReactor(
            actions,
            config,
            state,
            log=lambda _m: None,
            on_click_timeout=_resync,
        )
        buttons = [
            {"custom_id": "free1", "emoji": "kakeraC"},
            {"custom_id": "free2", "emoji": "kakeraG"},
        ]
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            await reactor._click_free_kakera(7, buttons, character="Ariel")

        assert actions.clicks == ["free1", "free2"]
        # One resync for the burst, not one per button.
        assert called == [True]

    asyncio.run(_case())


def test_no_resync_when_there_were_no_free_kakera_to_click():
    async def _case() -> None:
        state = AccountState(power_percent=100.0, power_max_percent=155.0)
        config = MacroConfig(prefix="$", kakera_reaction=KakeraReactionRules(enabled=True))
        actions = _FakeActionsWithQueue()
        called: list[bool] = []

        async def _resync() -> None:
            called.append(True)

        reactor = KakeraReactor(
            actions, config, state, log=lambda _m: None, on_click_timeout=_resync
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            await reactor._click_free_kakera(7, [{"emoji": "kakeraC"}], character="X")

        assert actions.clicks == []
        assert called == []

    asyncio.run(_case())
