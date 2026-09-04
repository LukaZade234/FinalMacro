"""Tests for the opt-in Mudae DM capture path (`ChannelMonitor`).

The gateway is the whole account, so DMs arrive whether we want them or not.
These pin the gate that decides they are dropped, and the narrowness of what
happens when they are not: parsed and handed to waiters, never mirrored into
the Run feed and never touching the channel-keyed trackers.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mudae.constants import TARGET_BOT_ID
from mudae.discord_reader import ChannelMonitor

_RUN_CHANNEL = 111
_DM_CHANNEL = 999


def _message(
    *,
    channel_id: int,
    guild: object | None,
    author_id: int = TARGET_BOT_ID,
    content: str = "Wishlist size: 42",
):
    """Enough of a ``discord.Message`` for the reader's own code paths."""
    return SimpleNamespace(
        id=5000 + channel_id,
        channel=SimpleNamespace(id=channel_id, name="dm" if guild is None else "mudae"),
        guild=guild,
        author=SimpleNamespace(id=author_id, name="Mudae", display_name="Mudae"),
        content=content,
        embeds=[],
        components=[],
        created_at=SimpleNamespace(strftime=lambda _fmt: "12:00:00"),
    )


def _monitor(*, allow_mudae_dms: bool):
    parsed: list[tuple] = []
    entries: list[dict] = []
    monitor = ChannelMonitor(
        token="t",
        channel_id=_RUN_CHANNEL,
        on_entry=entries.append,
        on_parsed=lambda snapshot, result: parsed.append((snapshot, result)),
        allow_mudae_dms=allow_mudae_dms,
    )
    return monitor, parsed, entries


def test_dm_is_dropped_when_the_toggle_is_off():
    monitor, parsed, entries = _monitor(allow_mudae_dms=False)
    message = _message(channel_id=_DM_CHANNEL, guild=None)

    asyncio.run(monitor._handle_message(message, edited=False))

    assert parsed == []
    assert entries == []


def test_mudae_dm_is_parsed_when_the_toggle_is_on():
    monitor, parsed, entries = _monitor(allow_mudae_dms=True)
    message = _message(channel_id=_DM_CHANNEL, guild=None)

    asyncio.run(monitor._handle_message(message, edited=False))

    assert len(parsed) == 1
    snapshot, _result = parsed[0]
    assert snapshot.is_mudae is True
    assert snapshot.guild_id is None
    assert snapshot.content == "Wishlist size: 42"
    # Never mirrored: the Run feed is channel text, and a DM is not in it.
    assert entries == []


def test_dm_from_anyone_but_mudae_is_ignored_even_with_the_toggle_on():
    monitor, parsed, entries = _monitor(allow_mudae_dms=True)
    message = _message(channel_id=_DM_CHANNEL, guild=None, author_id=424242)
    message.author.name = "SomeoneElse"

    asyncio.run(monitor._handle_message(message, edited=False))

    assert parsed == []
    assert entries == []


def test_another_guild_channel_is_still_ignored_with_the_toggle_on():
    """The toggle opens DMs, not every channel the account can see."""
    monitor, parsed, entries = _monitor(allow_mudae_dms=True)
    other_guild = SimpleNamespace(id=7, name="Somewhere else")
    message = _message(channel_id=222, guild=other_guild)

    asyncio.run(monitor._handle_message(message, edited=False))

    assert parsed == []
    assert entries == []


def test_dm_does_not_touch_the_channel_keyed_trackers():
    monitor, _parsed, _entries = _monitor(allow_mudae_dms=True)
    monitor._pending_macro_command = "wlsz"
    message = _message(channel_id=_DM_CHANNEL, guild=None)

    asyncio.run(monitor._handle_message(message, edited=False))

    # Still pending: the DM path must not consume a channel command's slot,
    # and must not cache the message for button clicks either.
    assert monitor._pending_macro_command == "wlsz"
    assert monitor._messages == {}


def test_toggle_flips_live_without_a_reconnect():
    monitor, parsed, _entries = _monitor(allow_mudae_dms=False)
    message = _message(channel_id=_DM_CHANNEL, guild=None)

    asyncio.run(monitor._handle_message(message, edited=False))
    assert parsed == []

    monitor.allow_mudae_dms = True
    asyncio.run(monitor._handle_message(message, edited=False))
    assert len(parsed) == 1

    monitor.allow_mudae_dms = False
    asyncio.run(monitor._handle_message(message, edited=False))
    assert len(parsed) == 1


def test_bridge_persists_the_toggle_and_pushes_it_to_a_live_monitor(
    tmp_path, monkeypatch
):
    import json

    path = tmp_path / "settings.json"
    monkeypatch.setattr("gui.settings.SETTINGS_PATH", path)

    from gui.bridge import AppBridge

    bridge = AppBridge()
    assert bridge.allowMudaeDms is False  # off unless asked for

    live = SimpleNamespace(allow_mudae_dms=False)
    bridge._monitor = live

    bridge.setAllowMudaeDms(True)
    assert bridge.allowMudaeDms is True
    assert live.allow_mudae_dms is True
    assert json.loads(path.read_text())["allow_mudae_dms"] is True

    bridge.setAllowMudaeDms(False)
    assert live.allow_mudae_dms is False

    bridge.setAllowMudaeDms(True)
    assert AppBridge().allowMudaeDms is True


# --- Page edits must survive the roll-edit filter ---------------------------


def test_wishlist_page_edit_is_not_dropped_as_a_roll_edit():
    """Every page after the first arrives as an *edit* of the same message.

    ``_handle_message`` drops edited Mudae messages whose embed looks like a
    character embed unless they are ownership confirmations — and a listing
    embed does look like one (an author line and a body). That silently ate
    every page click, so the capture could never scroll.
    """
    import json
    import pathlib

    import mudae.discord_reader as reader
    from macro.wishlist_capture import _is_wishlist

    raw = json.loads(
        (
            pathlib.Path(__file__).parent / "fixtures" / "wlz_channel_page.json"
        ).read_text(encoding="utf-8")
    )
    embed = dict(raw["embeds"][0])
    embed["footer"] = "Page 2 / 8"

    def fake_snapshot(message, *, edited=False):
        return SimpleNamespace(
            message_id=100000000000000001,
            channel_id=_RUN_CHANNEL,
            channel_name="mudae-w",
            guild_id=1,
            guild_name="g",
            author_id=TARGET_BOT_ID,
            author_name="Mudae",
            is_mudae=True,
            content="",
            embeds=[embed],
            buttons=raw["buttons"],
            created_at="17:11:40",
            edited=edited,
            components=raw["components"],
        )

    original = reader.snapshot_from_message
    reader.snapshot_from_message = fake_snapshot
    try:
        parsed: list = []
        monitor = ChannelMonitor(
            token="t",
            channel_id=_RUN_CHANNEL,
            on_parsed=lambda snapshot, result: parsed.append((snapshot, result)),
        )
        message = _message(channel_id=_RUN_CHANNEL, guild=SimpleNamespace(id=1, name="g"))
        asyncio.run(monitor._handle_message(message, edited=True))
    finally:
        reader.snapshot_from_message = original

    assert len(parsed) == 1, "the page edit was dropped before reaching a parser"
    _snapshot, result = parsed[0]
    assert result.fields["page"] == 2
    assert len(result.fields["entries"]) == 20
    assert _is_wishlist(result) is True
