"""Minigame session log: board, clicks, win, base SP."""

from __future__ import annotations

import datetime as dt
import json

from gui.accounts import AccountProfile
from macro.minigame_board import build_session, classify_oh_click, make_click
from mudae.minigame_log import (
    build_stats,
    client_payload,
    log_path,
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
    click = make_click(3, "spB2", paid=True)
    assert click["emoji"] == "spB"
    assert click["base_sp"] == 10
    click = make_click(4, "spT2", paid=True)
    assert click["emoji"] == "spT"
    assert click["base_sp"] == 20


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
    five = classify_oh_click(
        clicked_emoji="spL",
        reward_types=["spB", "spB", "spB", "spT", "spB"],
    )
    five_click = make_click(
        21,
        five["emoji"],
        paid=True,
        resolved=five["resolved"],
    )
    assert five_click["resolved"] == ["spB", "spB", "spB", "spT", "spB"]
    assert five_click["base_sp"] == 60
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
    assert session["oc_spawn"] == 0


def test_oh_final_reveal_counts_leftover_hidden_as_oc_spawn():
    board = ["spB"] * 24 + ["spU"]
    session = build_session(
        "oh",
        [make_click(0, "spB", paid=True)],
        board,
        clicks_paid=5,
        clicks_budget=5,
        reason="done",
    )
    assert session["oc_spawn"] == 1
    assert session["oc_bonus"] == 0
    stats = build_stats([session])
    spawn = {row["emoji"]: row["count"] for row in stats["spawn"]}
    assert spawn["spB"] == 24
    assert spawn["spU"] == 1
    assert spawn["spU"] / sum(spawn.values()) == 1 / 25
    labels = {row["emoji"]: row["label"] for row in stats["spawn"]}
    assert labels["spU"] == "Hidden ($oc)"


def test_oh_midgame_hidden_is_not_oc_spawn():
    session = build_session(
        "oh",
        [make_click(0, "spB", paid=True)],
        ["spB"] + ["spU"] * 24,
        clicks_paid=1,
        clicks_budget=5,
        reason="done",
    )
    assert session["oc_spawn"] == 0
    stats = build_stats([session])
    spawn = {row["emoji"]: row["count"] for row in stats["spawn"]}
    assert spawn == {"spB": 1}


def test_oq_leftover_hidden_is_not_oc_spawn():
    board = ["spB"] * 24 + ["spU"]
    session = build_session(
        "oq",
        [make_click(0, "spB", paid=True)],
        board,
        clicks_paid=1,
        clicks_budget=7,
        reason="done",
    )
    assert session.get("oc_spawn", 0) == 0
    stats = build_stats([session])
    spawn = {row["emoji"]: row["count"] for row in stats["spawn"]}
    assert spawn == {"spB": 24}


def test_oh_perk10_grants_on_session():
    session = build_session(
        "oh",
        [make_click(0, "spY", paid=True)],
        ["spY"] + ["spU"] * 24,
        clicks_paid=1,
        clicks_budget=5,
        reason="done",
        oq_bonus=2,
        ot_bonus=1,
        spheres_bonus=5600,
    )
    assert session["oq_bonus"] == 2
    assert session["ot_bonus"] == 1
    assert session["spheres_bonus"] == 5600
    stats = build_stats([session])
    assert stats["totals"]["oq_grants"] == 2
    assert stats["totals"]["ot_grants"] == 1
    by_id = {row["id"]: row for row in stats["by_game"]}
    assert by_id["oh"]["oq_bonus"] == 2
    assert by_id["oh"]["ot_bonus"] == 1


def test_oh_does_not_affect_win_rate():
    oh = build_session(
        "oh",
        [make_click(0, "spD", paid=True, resolved=["spR"])],
        ["spD"] + ["spU"] * 24,
        clicks_paid=1,
        clicks_budget=5,
        reason="done",
    )
    oq = build_session(
        "oq",
        [make_click(15, "spT", paid=True)],
        ["spU"] * 25,
        clicks_paid=1,
        clicks_budget=7,
        reason="done",
    )
    assert oh["won"] is True
    assert oq["won"] is False
    stats = build_stats([oh, oq])
    assert stats["totals"]["games"] == 2
    assert stats["totals"]["scored_games"] == 1
    assert stats["totals"]["wins"] == 0
    assert stats["totals"]["win_rate"] == 0.0
    by_id = {row["id"]: row for row in stats["by_game"]}
    assert by_id["oh"]["has_win"] is False
    assert by_id["oh"]["wins"] == 0
    assert by_id["oq"]["has_win"] is True


def test_log_path_is_under_data():
    path = log_path()
    assert path.name == "minigame_log.json"
    assert path.parent.name == "data"


def test_record_minigame_session_skips_no_grid(tmp_path, monkeypatch):
    import mudae.minigame_log as minigame_log

    monkeypatch.setattr(minigame_log, "_LOG_PATH", tmp_path / "minigame_log.json")
    minigame_log._events = []
    assert record_minigame_session({"reason": "no grid", "game": "oh"}, channel_id=1) is None
    assert record_minigame_session(
        {"reason": "exhausted", "game": "oh", "refill_minutes": 188},
        channel_id=1,
    ) is None
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


def test_payload_reloads_when_file_changes(tmp_path, monkeypatch):
    import mudae.minigame_log as minigame_log

    path = tmp_path / "minigame_log.json"
    monkeypatch.setattr(minigame_log, "_LOG_PATH", path)
    minigame_log._events = []
    minigame_log._disk_sig = None
    path.write_text(
        json.dumps(
            [
                {
                    "game": "oh",
                    "won": False,
                    "base_value": 10,
                    "board": ["spB"] * 25,
                    "clicks": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    store = type("S", (), {"accounts": [AccountProfile(id="acc1", name="Main", type="Main")]})()
    payload = client_payload(store)
    assert payload["totals"]["games"] == 1
    assert payload["totals"]["base_value"] == 10
