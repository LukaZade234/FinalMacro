"""Tests for both wishlist capture routes (macro/wishlist_capture.py).

The DM route and the paged route reach the same result by different means, so
both are driven here against a fake ``DiscordActions``: what matters is that
each stops at the right moment and that a listing cut short comes back marked
incomplete rather than as a short wishlist.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from macro.wishlist_capture import (
    CHANNEL_COMMAND,
    DM_COMMAND,
    capture_via_dm,
    capture_via_pages,
    capture_wishlist,
)
from mudae.parsers.wishlist import parse_wishlist_page
from mudae.types import MessageKind, ParseResult

_HEADER = "someone's Wishlist - 4/10 $wl, 1/3 $sw"


def _rows(*names: str) -> str:
    return "\n".join(f"{name} ✅ 🔐 · 7,000 sp - 5 (x5), 6" for name in names)


def _parsed(content: str) -> ParseResult:
    return ParseResult(
        kind=MessageKind.WISHLIST,
        summary="$wl",
        fields=parse_wishlist_page(content),
        warnings=[],
    )


def _snapshot(content: str, *, message_id: int = 77, buttons=None):
    return SimpleNamespace(
        message_id=message_id,
        content=content,
        buttons=buttons if buttons is not None else [],
    )


class _FakeActions:
    """Replays a scripted list of replies through the real capture loops."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.sent: list[str] = []
        self.clicks: list[tuple[int, str]] = []

    async def send_command(self, command: str):
        self.sent.append(command)
        return 1

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        self.clicks.append((message_id, custom_id))
        return True

    async def wait_for(self, predicate, *, timeout: float = 0.0):
        while self._replies:
            snapshot, parsed = self._replies.pop(0)
            if predicate(snapshot, parsed):
                return snapshot, parsed
        return None


def _paging_buttons(disabled_back: bool = False):
    return [
        {"custom_id": "back", "kind": "other", "disabled": disabled_back, "emoji": "arrowL"},
        {"custom_id": "fwd", "kind": "other", "disabled": False, "emoji": "arrowR"},
    ]


# --- DM route ---------------------------------------------------------------


def test_dm_route_stops_once_the_header_count_is_reached():
    first = f"{_HEADER}\n" + _rows("Rem", "Emilia")
    second = _rows("Ram", "Beatrice")
    trailing = _rows("ShouldNotBeRead")
    actions = _FakeActions(
        [
            (_snapshot(first), _parsed(first)),
            (_snapshot(second), _parsed(second)),
            (_snapshot(trailing), _parsed(trailing)),
        ]
    )

    result = asyncio.run(capture_via_dm(actions))

    assert actions.sent == [DM_COMMAND]
    assert result.ok is True
    assert result.complete is True
    assert [e["name"] for e in result.entries] == ["Rem", "Emilia", "Ram", "Beatrice"]


def test_dm_route_reports_incomplete_when_parts_stop_early():
    first = f"{_HEADER}\n" + _rows("Rem", "Emilia")
    actions = _FakeActions([(_snapshot(first), _parsed(first))])

    result = asyncio.run(capture_via_dm(actions))

    assert result.ok is True
    assert result.complete is False  # header promised 4, only 2 arrived
    assert "stopped before" in result.reason


def test_dm_route_explains_a_silent_mailbox():
    actions = _FakeActions([])

    result = asyncio.run(capture_via_dm(actions))

    assert result.ok is False
    assert "Mudae direct messages" in result.reason


# --- Paged route ------------------------------------------------------------


def _page(number: int, total: int, *names: str, header: bool = False) -> str:
    body = (f"{_HEADER}\n" if header else "") + _rows(*names)
    return f"{body}\nPage {number} / {total}"


def test_paged_route_clicks_forward_through_every_page():
    pages = [
        _page(1, 3, "Rem", header=True),
        _page(2, 3, "Emilia"),
        _page(3, 3, "Ram"),
    ]
    actions = _FakeActions(
        [
            (_snapshot(text, buttons=_paging_buttons()), _parsed(text))
            for text in pages
        ]
    )

    result = asyncio.run(capture_via_pages(actions))

    assert actions.sent == [CHANNEL_COMMAND]
    assert actions.clicks == [(77, "fwd"), (77, "fwd")]  # 3 pages = 2 clicks
    assert [e["name"] for e in result.entries] == ["Rem", "Emilia", "Ram"]
    assert result.reason == ""


def test_paged_route_reports_the_pages_a_timeout_lost():
    """The user's worry: a slow page truncating a long list, visibly."""
    first = _page(1, 4, "Rem", header=True)
    actions = _FakeActions(
        [(_snapshot(first, buttons=_paging_buttons()), _parsed(first))]
    )

    result = asyncio.run(capture_via_pages(actions))

    assert result.ok is True
    assert result.complete is False
    assert "Missing page(s) [2, 3, 4]" in result.reason


def test_paged_route_handles_a_single_page_listing():
    only = _page(1, 1, "Rem", header=True)
    actions = _FakeActions([(_snapshot(only, buttons=_paging_buttons()), _parsed(only))])

    result = asyncio.run(capture_via_pages(actions))

    assert result.ok is True
    assert actions.clicks == []
    assert [e["name"] for e in result.entries] == ["Rem"]


def test_paged_route_needs_two_buttons_to_page():
    text = _page(1, 3, "Rem", header=True)
    one_button = [{"custom_id": "fwd", "kind": "other", "disabled": False}]
    actions = _FakeActions([(_snapshot(text, buttons=one_button), _parsed(text))])

    result = asyncio.run(capture_via_pages(actions))

    assert result.ok is False
    assert "No page-forward button" in result.reason
    assert [e["name"] for e in result.entries] == ["Rem"]


def test_paged_route_pages_even_though_the_arrows_look_like_claim_buttons():
    """Mudae's real arrows classify as ``claim`` — kind cannot be the filter.

    Their custom ids have the same ``<id>p<id>p<id>`` shape a claim button
    has, so ``classify_button_kind`` calls both arrows ``claim``. The forward
    arrow is found by its ``wright`` emoji instead.
    """
    text = _page(1, 2, "Rem", header=True)
    buttons = [
        {"custom_id": "back", "kind": "claim", "disabled": False, "emoji": "wleft"},
        {"custom_id": "fwd", "kind": "claim", "disabled": False, "emoji": "wright"},
    ]
    second = _page(2, 2, "Emilia")
    actions = _FakeActions(
        [
            (_snapshot(text, buttons=buttons), _parsed(text)),
            (_snapshot(second, buttons=buttons), _parsed(second)),
        ]
    )

    result = asyncio.run(capture_via_pages(actions))

    assert actions.clicks == [(77, "fwd")]
    assert [e["name"] for e in result.entries] == ["Rem", "Emilia"]


# --- Route choice -----------------------------------------------------------


def test_route_follows_the_dm_setting():
    dm_text = f"{_HEADER}\n" + _rows("Rem", "Emilia", "Ram", "Beatrice")
    dm_actions = _FakeActions([(_snapshot(dm_text), _parsed(dm_text))])
    assert asyncio.run(capture_wishlist(dm_actions, allow_dms=True)).route == "dm"
    assert dm_actions.sent == [DM_COMMAND]

    page_text = _page(1, 1, "Rem", header=True)
    page_actions = _FakeActions(
        [(_snapshot(page_text, buttons=_paging_buttons()), _parsed(page_text))]
    )
    result = asyncio.run(capture_wishlist(page_actions, allow_dms=False))
    assert result.route == "pages"
    # With DMs off the paged route is the supported path, not a fallback after
    # a failed DM attempt — the DM command is never sent.
    assert page_actions.sent == [CHANNEL_COMMAND]


def test_paged_route_end_to_end_on_the_real_captured_reply():
    """Drives the real loop with the real embed + arrows from a live capture.

    Both channel-route bugs are covered here at once: the body is an embed
    with no message content, and the paging arrows classify as ``claim``.
    """
    import json
    import pathlib

    from mudae.parsers.pipeline import parse_message

    raw = json.loads(
        (pathlib.Path(__file__).parent / "fixtures" / "wlz_channel_page.json").read_text(
            encoding="utf-8"
        )
    )

    def snapshot_for(page: int):
        embed = dict(raw["embeds"][0])
        embed["footer"] = f"Page {page} / 2"
        if page == 2:
            embed["author"] = ""  # only page 1 carries the header
            embed["description"] = "Kurisu Makise ✅ 🔐 · 7,000 sp - 5 (x5), 6"
        return SimpleNamespace(
            message_id=100000000000000001,
            channel_id=1,
            channel_name="mudae-w",
            guild_id=1,
            guild_name="g",
            author_id=1,
            author_name="Mudae",
            is_mudae=True,
            content="",
            embeds=[embed],
            buttons=raw["buttons"],
            created_at="16:51:02",
            edited=page > 1,
            components=raw["components"],
        )

    # Page 1 arrives *paired with the command the macro just sent*, which is
    # the case that failed: the pipeline labels such a reply COMMAND_RESPONSE,
    # not WISHLIST. Page 2 arrives as an edit, unpaired.
    first = snapshot_for(1)
    second = snapshot_for(2)
    replies = [
        (first, parse_message(first, reply_to_command="wlz")),
        (second, parse_message(second)),
    ]

    actions = _FakeActions(replies)
    result = asyncio.run(capture_via_pages(actions))

    assert actions.sent == [CHANNEL_COMMAND]
    # Clicked the wright arrow, not the wleft one.
    forward = next(b["custom_id"] for b in raw["buttons"] if b["emoji"] == "wright")
    assert actions.clicks == [(100000000000000001, forward)]
    assert result.ok is True
    assert result.reason == ""
    names = [entry["name"] for entry in result.entries]
    assert len(names) == 21  # 20 on page 1, plus Ado on page 2
    assert names[0] == "Rebecca"
    assert names[-1] == "Kurisu Makise"


def test_the_macros_own_command_reply_is_recognised():
    """Regression: the capture sent $wlz+z! and then sat there doing nothing.

    A reply paired with the command that was just sent never reaches
    ``classify_message`` — it is routed by command name and returned as
    ``COMMAND_RESPONSE``. Matching only ``MessageKind.WISHLIST`` therefore
    missed the very first reply, so the wait timed out.
    """
    import json
    import pathlib

    from mudae.parsers.pipeline import parse_message
    from mudae.types import MessageKind

    from macro.wishlist_capture import _is_wishlist

    raw = json.loads(
        (pathlib.Path(__file__).parent / "fixtures" / "wlz_channel_page.json").read_text(
            encoding="utf-8"
        )
    )
    snap = SimpleNamespace(
        message_id=100000000000000001,
        channel_id=1,
        channel_name="mudae-w",
        guild_id=1,
        guild_name="g",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=raw["embeds"],
        buttons=raw["buttons"],
        created_at="16:51:02",
        edited=False,
        components=raw["components"],
    )

    for spelling in ("wlz", "wlsz", "wl"):
        parsed = parse_message(snap, reply_to_command=spelling)
        assert parsed.kind == MessageKind.COMMAND_RESPONSE, spelling
        assert parsed.fields["parser_command"] == "wishlist", spelling
        assert len(parsed.fields["entries"]) == 20, spelling
        # No "Typed $wlz but response matches $roll" any more.
        assert parsed.warnings == [], spelling
        assert _is_wishlist(parsed) is True, spelling


def test_the_macros_flagged_command_resolves_like_the_bare_one():
    """Regression: the macro records what it sent, flags and all.

    ``send_command("wlz+z!")`` sets the pending command to ``wlz+z!``, while
    the tracker watching what the *user* types has already stripped the flags
    to ``wlz``. Only the second hit the alias table, so the identical message
    parsed correctly when hand-typed and as a **roll** when the macro sent it.
    """
    from mudae.commands import normalize_command

    for flagged in ("wlz+z!", "wlsz+z!", "wl", "wlz"):
        assert normalize_command(flagged) == "wishlist", flagged

    # Exact names that merely contain digits are untouched by the fallback.
    for unchanged in ("ohu8", "ohu9", "ohu", "tu"):
        assert normalize_command(unchanged) == unchanged, unchanged
