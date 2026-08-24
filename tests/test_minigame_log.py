"""Minigame session log: board, clicks, win, base SP."""

from __future__ import annotations

import datetime as dt

from gui.accounts import AccountProfile
from macro.minigame_board import build_session, classify_oh_click, make_click
from mudae.minigame_log import (
    build_stats,
    client_payload,
    record_minigame_session,
    set_recording_account,
)


def test_make_click_uses_base_sp_not_chat_amount():
    click = make_click(7, "spB", paid=True)
    assert click["base_sp"] == 10
    click = make_click(0, "spP", paid=False)
    assert click["base_sp"] == 5
    click = make_click(15, "spR", paid=True)
    assert click["base_sp"] == 150


def test_session_won_on_red_click():
    clicks = [
        make_click(7, "spT", paid=True),
        make_click(12, "spP", paid=False),
        make_click(15, "spR", paid=True),
    ]
    board = ["spU"] * 25
    board[7] = "spT"
    board[12] = "spP"
    board[15] = "spR"
    session = build_session(
        "oq", clicks, board, clicks_paid=2, clicks_budget=7, reason="done"
    )
    assert session["won"] is True
    assert session["base_value"] == 20 + 5 + 150


def test_light_click_keeps_identity_and_sums_fragments():
    classified = classify_oh_click(
        clicked_emoji="spL",
        reward_types=["spB", "spT", "spG"],
    )
    click = make_click(
        0,
        classified["emoji"],
        paid=True,
        resolved=classified["resolved"],
    )
    assert click["emoji"] == "spL"
    assert click["resolved"] == ["spB", "spT", "spG"]
    assert click["base_sp"] == 10 + 20 + 35
    board = ["spL"] + ["spU"] * 24
    session = build_session(
        "oh", [click], board, clicks_paid=1, clicks_budget=5, reason="done"
    )
    stats = build_stats([session])
    spawn = {row["emoji"]: row["count"] for row in stats["spawn"]}
    clicked = {row["emoji"]: row["count"] for row in stats["clicked"]}
    assert spawn == {"spL": 1}
    assert clicked == {"spL": 1}


def test_dark_click_keeps_identity_value_from_transform():
    classified = classify_oh_click(
        clicked_emoji="spD",
        reward_types=["spP", "spP"],
    )
    click = make_click(
        3,
        classified["emoji"],
        paid=True,
        resolved=classified["resolved"],
    )
    assert click["emoji"] == "spD"
    assert click["resolved"] == ["spP"]
    assert click["base_sp"] == 5
    yellow = classify_oh_click(clicked_emoji="spD", reward_types=["spY"])
    assert yellow["resolved"] == ["spY"]
    dark_red = make_click(4, "spD", paid=True, resolved=["spR"])
    session = build_session(
        "oh",
        [dark_red],
        ["spD"] + ["spU"] * 24,
        clicks_paid=1,
        clicks_budget=5,
        reason="done",
    )
    assert session["won"] is True
    assert session["base_value"] == 150


def test_light_spawn_keeps_identity_when_board_shows_fragment():
    click = make_click(0, "spL", paid=True, resolved=["spB", "spT", "spG"])
    board = ["spB"] + ["spU"] * 24
    session = build_session(
        "oh", [click], board, clicks_paid=1, clicks_budget=5, reason="done"
    )
    assert session["board"][0] == "spL"
    stats = build_stats([session])
    spawn = {row["emoji"]: row["count"] for row in stats["spawn"]}
    clicked = {row["emoji"]: row["count"] for row in stats["clicked"]}
    assert spawn == {"spL": 1}
    assert clicked == {"spL": 1}


def test_dark_spawn_keeps_identity_when_board_shows_transform():
    click = make_click(3, "spD", paid=True, resolved=["spY"])
    board = ["spU"] * 25
    board[3] = "spY"
    session = build_session(
        "oh", [click], board, clicks_paid=1, clicks_budget=5, reason="done"
    )
    assert session["board"][3] == "spD"
    stats = build_stats([session])
    spawn = {row["emoji"]: row["count"] for row in stats["spawn"]}
    clicked = {row["emoji"]: row["count"] for row in stats["clicked"]}
    assert spawn == {"spD": 1}
    assert clicked == {"spD": 1}


def test_hidden_oh_click_grants_oc_not_sp():
    classified = classify_oh_click(
        clicked_emoji="spU",
        reward_types=["spU"],
    )
    click = make_click(
        12,
        classified["emoji"],
        paid=True,
        oc_bonus=classified["oc_bonus"],
    )
    assert click["emoji"] == "spU"
    assert click["base_sp"] == 0
    assert click["oc_bonus"] == 1
    session = build_session(
        "oh",
        [click],
        ["spU"] * 25,
        clicks_paid=1,
        clicks_budget=5,
        reason="done",
    )
    assert session["oc_bonus"] == 1
    assert session["base_value"] == 0
    stats = build_stats([session])
    clicked = {row["emoji"]: row["count"] for row in stats["clicked"]}
    assert clicked == {"spU": 1}
    assert stats["totals"]["oc_grants"] == 1
    assert stats["spawn"] == []


def test_record_minigame_session_skips_no_grid(tmp_path, monkeypatch):
    import mudae.minigame_log as minigame_log

    monkeypatch.setattr(minigame_log, "_LOG_PATH", tmp_path / "minigame_log.json")
    minigame_log._events = []
    assert record_minigame_session({"reason": "no grid", "game": "oh"}, channel_id=1) is None
    assert minigame_log._events == []


def test_record_and_stats(tmp_path, monkeypatch):
    import mudae.minigame_log as minigame_log

    monkeypatch.setattr(minigame_log, "_LOG_PATH", tmp_path / "minigame_log.json")
    minigame_log._events = []
    set_recording_account("acc1", "Main")
    now = dt.datetime(2026, 8, 24, 12, 0, tzinfo=dt.timezone.utc)
    board = ["spB"] * 20 + ["spR"] + ["spP"] * 4
    session = {
        "game": "oq",
        "won": True,
        "base_value": 175,
        "clicks": [make_click(20, "spR", paid=True)],
        "board": board,
        "clicks_paid": 7,
        "clicks_budget": 7,
        "reason": "done",
    }
    record_minigame_session(
        session,
        channel_id=99,
        channel_name="mudae",
        guild_id=42,
        guild_name="Guild",
        now=now,
    )
    store = type("S", (), {"accounts": [AccountProfile(id="acc1", name="Main", type="Main")]})()
    payload = client_payload(store)
    assert payload["totals"]["games"] == 1
    assert payload["totals"]["wins"] == 1
    assert payload["totals"]["base_value"] == 175
    spawn = {row["emoji"]: row["count"] for row in payload["spawn"]}
    assert spawn["spB"] == 20
    assert spawn["spR"] == 1
    stats = build_stats(payload["entries"])
    assert stats["by_game"][0]["id"] == "oq"
