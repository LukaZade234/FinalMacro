"""Kakera earnings log and stats."""

from __future__ import annotations

import datetime as dt

from gui.accounts import AccountProfile
from macro.state import MacroPhase
from mudae.kakera_log import (
    build_stats,
    client_payload,
    earn_method_label,
    enrich_entry,
    record_kakera_earning,
    record_roll_bku_earning,
    set_recording_account,
    should_record_earning,
    should_record_roll_bku,
    username_matches_own,
)
from mudae.types import MessageKind, MudaeMessageSnapshot


def test_username_matches_own():
    assert username_matches_own("PlayerOne", ["PlayerOne", "Alt"])
    assert not username_matches_own("Other", ["PlayerOne"])


def test_should_record_kakera_claim():
    fields = {"amount": 500, "claimed_by": "me", "earn_method": "kakera_click"}
    assert should_record_earning(MessageKind.KAKERA_CLAIM, fields, ["me"])
    assert not should_record_earning(MessageKind.KAKERA_CLAIM, fields, ["other"])


def test_should_record_roll_bku_during_rolling():
    fields = {"bku": 197, "owner": None, "claimed": False}
    assert should_record_roll_bku(fields, ["me"], MacroPhase.ROLLING)
    assert not should_record_roll_bku(fields, ["me"], MacroPhase.IDLE)
    assert should_record_roll_bku(
        {"bku": 197, "owner": "other", "claimed": True},
        ["me"],
        MacroPhase.ROLLING,
    )
    assert not should_record_roll_bku(
        {"bku": 197, "owner": "other", "claimed": True},
        ["me"],
        MacroPhase.IDLE,
    )


def test_should_record_roll_bku_idle_owned_character():
    set_recording_account("acc1", "lukazade234")
    fields = {"bku": 197, "owner": "lukazade234", "claimed": True}
    assert should_record_roll_bku(fields, [], MacroPhase.IDLE)
    assert should_record_roll_bku(fields, ["someone"], MacroPhase.IDLE)


def test_record_and_stats(tmp_path, monkeypatch):
    import mudae.kakera_log as kakera_log

    kakera_log._events.clear()
    set_recording_account("acc1", "Main")

    now = dt.datetime(2026, 7, 3, 14, 30, tzinfo=dt.timezone.utc)
    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=99,
        channel_name="mudae",
        guild_id=42,
        guild_name="Guild",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[],
        buttons=[],
        created_at="14:30:00",
    )
    record_kakera_earning(
        snapshot,
        {"amount": 1200, "claimed_by": "me", "kakera_type": "kakeraY", "earn_method": "kakera_click"},
        earn_method="kakera_click",
        now=now,
    )
    record_roll_bku_earning(
        snapshot,
        {"bku": 500, "bku_reset": True, "character_name": "Alice", "starwish": True},
        now=now,
    )

    store = type("S", (), {"accounts": [AccountProfile(id="acc1", name="Main", type="Main")]})()
    payload = client_payload(store)
    assert "entries" not in payload
    assert payload["totals"]["all_time"] == 1700
    assert payload["event_count"] == 2
    assert len(payload["recent"]) == 2
    assert len(payload["by_method"]) == 2
    assert payload["recent"][0]["earn_method_label"] == earn_method_label("bku_reset")
    assert payload["recent"][0]["starwish"] is True
    assert payload["recent"][1]["earn_method_label"] == earn_method_label("kakera_click")
    assert payload["recent"][1]["starwish"] is False


def test_build_stats_by_method():
    entries = [
        enrich_entry(
            {"amount": 100, "earn_method": "kakera_click", "date_key": "2026-07-03", "recorded_at": "2026-07-03T10:00:00+00:00"},
            account_by_id={},
            main_account_id="m",
            main_account_name="Main",
        ),
        enrich_entry(
            {"amount": 250, "earn_method": "bku_reset", "date_key": "2026-07-03", "recorded_at": "2026-07-03T11:00:00+00:00"},
            account_by_id={},
            main_account_id="m",
            main_account_name="Main",
        ),
    ]
    stats = build_stats(entries, now=dt.datetime(2026, 7, 3, tzinfo=dt.timezone.utc))
    assert stats["totals"]["all_time"] == 350
    methods = {row["id"]: row["amount"] for row in stats["by_method"]}
    assert methods["bku_reset"] == 250
    assert methods["kakera_click"] == 100
