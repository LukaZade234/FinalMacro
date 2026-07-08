"""Tests for DiscordActions wait queue behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from macro.actions import DiscordActions, is_kakera_outcome_message
from mudae.parsers.classify import classify_message
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


def test_kakera_outcome_matches_embed_only_claim():
    from macro.actions import is_kakera_outcome_message

    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=1,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[{"description": "**user +123** ($k)", "title": "", "footer": "", "author": ""}],
        buttons=[],
        created_at="12:00:00",
    )
    parsed = ParseResult(kind=MessageKind.CHARACTER_EMBED, summary="", fields={})
    assert is_kakera_outcome_message(snapshot, parsed)
    assert classify_message(snapshot) == MessageKind.KAKERA_CLAIM


def test_wait_for_kakera_outcome_finds_misclassified_claim():
    actions = DiscordActions(SimpleNamespace())

    async def _run() -> None:
        snapshot = MudaeMessageSnapshot(
            message_id=2,
            channel_id=1,
            channel_name="mudae",
            guild_id=1,
            guild_name="srv",
            author_id=1,
            author_name="Mudae",
            is_mudae=True,
            content="",
            embeds=[{"description": "**user +50** ($k)", "title": "", "footer": "", "author": ""}],
            buttons=[],
            created_at="12:00:00",
        )
        parsed = ParseResult(kind=MessageKind.UNKNOWN, summary="", fields={})
        actions.feed(snapshot, parsed)

        result = await actions.wait_for_kakera_outcome(timeout=0.5)
        assert result is not None
        assert result.kind == MessageKind.KAKERA_CLAIM
        assert result.fields.get("amount") == 50

    asyncio.run(_run())

    actions = DiscordActions(SimpleNamespace())

    async def _run() -> None:
        actions.feed(_snapshot(1), _parsed(MessageKind.TU))
        actions.feed(_snapshot(2), _parsed(MessageKind.KAKERA_CLAIM))

        matches = actions.collect_queued(
            lambda _s, p: p.kind == MessageKind.KAKERA_CLAIM
        )
        assert len(matches) == 1
        assert matches[0][0].message_id == 2
        assert actions._queue.qsize() == 1

        tu = await _wait_kind(actions, MessageKind.TU, timeout=0.5)
        assert tu is not None
        assert tu[0].message_id == 1

    asyncio.run(_run())
