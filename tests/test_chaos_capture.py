"""Raw chaos-kakera follow-up capture (no outcome parser yet)."""

from __future__ import annotations

import json
import time

import pytest

from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult


def _snapshot(message_id: int, *, content: str = "", edited: bool = False) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id,
        channel_id=99,
        channel_name="mudae",
        guild_id=42,
        guild_name="Guild",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content=content,
        embeds=[{"author": "Asuna", "description": "wish", "footer": "", "title": "", "image_url": ""}],
        buttons=[{"emoji": "kakeraP", "label": "", "custom_id": "p", "kind": "kakera", "disabled": False}],
        created_at="14:27:32",
        edited=edited,
    )


@pytest.fixture
def chaos(tmp_path, monkeypatch):
    import mudae.chaos_capture as mod

    monkeypatch.setattr(mod, "_LOG_PATH", tmp_path / "chaos_log.json")
    mod._events = []
    mod._open = None
    yield mod
    mod._cancel_idle_timer()
    mod._events = []
    mod._open = None
    mod._writer.cancel_pending()
    mod.bind_notify(None, None)


def test_keeps_follow_ups_until_commanded_roll(chaos):
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    claim = ParseResult(
        kind=MessageKind.KAKERA_CLAIM,
        summary="+$k 200",
        fields={"amount": 200, "character_name": "Rem"},
    )
    kl = ParseResult(kind=MessageKind.UNKNOWN, summary="$kl 10", fields={})
    spawn = ParseResult(
        kind=MessageKind.CHARACTER_EMBED,
        summary="Asuna",
        fields={"character_name": "Asuna"},
    )
    nxt = ParseResult(
        kind=MessageKind.ROLL,
        summary="Maki",
        fields={"character_name": "Maki", "parser_command": "roll", "command": "wa"},
    )

    assert chaos.note_parsed(_snapshot(11, content="+$k"), claim) is None
    assert chaos.note_parsed(_snapshot(12, content="$kl 10"), kl) is None
    assert chaos.note_parsed(_snapshot(13), spawn) is None
    closed = chaos.note_parsed(_snapshot(14), nxt)

    assert closed is not None
    assert closed["closed_reason"] == "next_roll"
    assert closed["kind"] == "unparsed"
    assert closed["character_name"] == "Rem"
    kinds = [row["kind"] for row in closed["messages"]]
    assert kinds == ["kakera_claim", "unknown", "character_embed"]
    assert all(row["message_id"] != 14 for row in closed["messages"])
    assert chaos.open_window() is None
    assert chaos.log_path().is_file()


def test_perk6_spawn_does_not_close_window(chaos):
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    chaos.note_parsed(
        _snapshot(11),
        ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="+$k", fields={"amount": 1}),
    )
    perk6 = ParseResult(
        kind=MessageKind.ROLL,
        summary="spawn",
        fields={
            "character_name": "Kid",
            "parser_command": "roll",
            "command": "wa",
            "perk_6": True,
        },
    )
    assert chaos.note_parsed(_snapshot(12), perk6) is None
    assert chaos.open_window() is not None
    assert chaos.open_window()["messages"][-1]["fields"]["perk_6"] is True


def test_command_response_roll_closes_without_including_it(chaos):
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    chaos.note_parsed(
        _snapshot(11, content="+$k"),
        ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="+$k", fields={"amount": 1}),
    )
    closed = chaos.note_parsed(
        _snapshot(12),
        ParseResult(
            kind=MessageKind.COMMAND_RESPONSE,
            summary="$wa response",
            fields={
                "character_name": "Maki",
                "parser_command": "roll",
                "command": "wa",
            },
        ),
    )
    assert closed is not None
    assert closed["closed_reason"] == "next_roll"
    assert closed["messages"][-1]["kind"] == "kakera_claim"


def test_empty_unconfirmed_click_is_not_saved(chaos):
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    assert chaos.close_open_window("click_unconfirmed") is None
    assert chaos._events == []


def test_next_chaos_flushes_previous_window(chaos):
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    chaos.note_parsed(
        _snapshot(11, content="+$k"),
        ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="+$k", fields={"amount": 1}),
    )
    chaos.begin_window(clicked_message_id=20, character_name="Maki")
    assert len(chaos._events) == 1
    assert chaos._events[0]["closed_reason"] == "next_chaos"
    assert chaos._events[0]["clicked_message_id"] == 10
    assert chaos.open_window()["clicked_message_id"] == 20


def test_first_follow_up_writes_log_file(chaos):
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    chaos.note_parsed(
        _snapshot(11, content="+$k"),
        ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="+$k", fields={"amount": 1}),
    )
    path = chaos.log_path()
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload[0]["closed_reason"] == "open"
    assert payload[0]["messages"][0]["kind"] == "kakera_claim"


def test_idle_silence_closes_window(chaos, monkeypatch):
    monkeypatch.setattr(chaos, "_IDLE_SEC", 0.05)
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    chaos.note_parsed(
        _snapshot(11, content="+$k"),
        ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="+$k", fields={"amount": 1}),
    )
    assert chaos.open_window() is not None
    deadline = time.monotonic() + 1.0
    while chaos.open_window() is not None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert chaos.open_window() is None
    assert chaos._events[-1]["closed_reason"] == "idle"
    payload = json.loads(chaos.log_path().read_text(encoding="utf-8"))
    assert payload[-1]["closed_reason"] == "idle"


def test_idle_timer_resets_on_new_message(chaos, monkeypatch):
    monkeypatch.setattr(chaos, "_IDLE_SEC", 0.12)
    chaos.begin_window(clicked_message_id=10, character_name="Rem")
    chaos.note_parsed(
        _snapshot(11, content="+$k"),
        ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="+$k", fields={"amount": 1}),
    )
    time.sleep(0.06)
    chaos.note_parsed(
        _snapshot(12, content="$kl 10"),
        ParseResult(kind=MessageKind.UNKNOWN, summary="$kl 10", fields={}),
    )
    time.sleep(0.06)
    assert chaos.open_window() is not None
    deadline = time.monotonic() + 1.0
    while chaos.open_window() is not None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert chaos.open_window() is None
    kinds = [row["kind"] for row in chaos._events[-1]["messages"]]
    assert kinds == ["kakera_claim", "unknown"]
