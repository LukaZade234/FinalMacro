"""Tests for DiscordActions wait queue behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from macro.actions import DiscordActions
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


def _parsed(kind: MessageKind) -> ParseResult:
    return ParseResult(kind=kind, summary=kind.value, fields={})


async def _wait_kind(actions: DiscordActions, kind: MessageKind, *, timeout: float = 1.0):
    return await actions.wait_for(lambda _s, p: p.kind == kind, timeout=timeout)


def test_wait_for_preserves_non_matching_messages():
    actions = DiscordActions(SimpleNamespace())

    async def _run() -> None:
        actions.feed(_snapshot(1), _parsed(MessageKind.TU))
        actions.feed(_snapshot(2), _parsed(MessageKind.KAKERA_CLAIM))

        tu = await _wait_kind(actions, MessageKind.TU, timeout=0.5)
        assert tu is not None
        assert tu[0].message_id == 1

        claim = await _wait_kind(actions, MessageKind.KAKERA_CLAIM, timeout=0.5)
        assert claim is not None
        assert claim[0].message_id == 2

    asyncio.run(_run())


def test_wait_for_does_not_duplicate_skipped_messages():
    # Regression: skipped messages were re-queued twice on a successful match
    # (loop + finally), doubling the queue on every wait until timeouts hit.
    actions = DiscordActions(SimpleNamespace())

    async def _run() -> None:
        actions.feed(_snapshot(1), _parsed(MessageKind.KAKERA_CLAIM))
        actions.feed(_snapshot(2), _parsed(MessageKind.TU))

        # Successful wait that skips over message 1.
        tu = await _wait_kind(actions, MessageKind.TU, timeout=0.5)
        assert tu is not None
        assert actions._queue.qsize() == 1

        # Repeated successful waits must not grow the queue.
        for i in range(3, 8):
            actions.feed(_snapshot(i), _parsed(MessageKind.TU))
            assert await _wait_kind(actions, MessageKind.TU, timeout=0.5) is not None
            assert actions._queue.qsize() == 1

    asyncio.run(_run())


def test_feed_caps_queue_size_dropping_oldest():
    from macro.actions import _MAX_QUEUE_SIZE

    actions = DiscordActions(SimpleNamespace())

    async def _run() -> None:
        for i in range(_MAX_QUEUE_SIZE + 50):
            actions.feed(_snapshot(i), _parsed(MessageKind.TU))
        assert actions._queue.qsize() == _MAX_QUEUE_SIZE

        # Newest message survives; the oldest were dropped.
        newest = None
        while not actions._queue.empty():
            newest = actions._queue.get_nowait()
        assert newest is not None
        assert newest[0].message_id == _MAX_QUEUE_SIZE + 49

    asyncio.run(_run())
