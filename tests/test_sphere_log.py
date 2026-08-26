"""Sphere earnings log and stats."""

from __future__ import annotations

import datetime as dt

from gui.accounts import AccountProfile
from mudae.sphere_log import (
    MINIGAME_IDS,
    build_stats,
    client_payload,
    minigame_source,
    record_minigame_earning,
    record_sphere_earning,
    set_recording_account,
    should_record_sphere_click,
    source_label,
)
from mudae.types import MessageKind, MudaeMessageSnapshot


def test_minigame_source_ids():
    assert minigame_source("oh") == "minigame_oh"
    assert source_label("minigame_oc") == "$oc minigame"
    assert source_label("perk10") == "Perk 10 (invested spheres)"
    assert "oc" in MINIGAME_IDS


def test_should_record_sphere_click():
    fields = {"amount": 72, "claimed_by": "me"}
    assert should_record_sphere_click(MessageKind.SPHERE_CLICK, fields, ["me"])
    assert not should_record_sphere_click(MessageKind.KAKERA_CLAIM, fields, ["me"])


def test_record_sphere_sources(tmp_path, monkeypatch):
    import mudae.sphere_log as sphere_log

    sphere_log._events.clear()
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
    record_sphere_earning(
        snapshot,
        {"amount": 46, "claimed_by": "me", "sphere_type": "spB"},
        source="sphere_click",
        now=now,
    )
    record_sphere_earning(
        snapshot,
        {"amount": 12, "claimed_by": "me"},
        source="kakera_bonus",
        now=now,
    )
    record_minigame_earning(
        game="oh",
        amount=1273,
        clicks=5,
        channel_id=99,
        channel_name="mudae",
        guild_id=42,
        guild_name="Guild",
        now=now,
    )
    record_sphere_earning(
        snapshot,
        {"amount": 5600},
        source="perk10",
        now=now,
    )

    store = type("S", (), {"accounts": [AccountProfile(id="acc1", name="Main", type="Main")]})()
    payload = client_payload(store)
    assert "entries" not in payload
    assert payload["totals"]["all_time"] == 46 + 12 + 1273 + 5600
    sources = {row["id"]: row["amount"] for row in payload["by_source"]}
    assert sources["sphere_click"] == 46
    assert sources["kakera_bonus"] == 12
    assert sources["minigame_oh"] == 1273
    assert sources["perk10"] == 5600


def test_record_sphere_click_colorblind_type_is_base_colour(tmp_path, monkeypatch):
    import mudae.sphere_log as sphere_log

    sphere_log._events.clear()
    set_recording_account("acc1", "Main")
    now = dt.datetime(2026, 7, 3, 14, 30, tzinfo=dt.timezone.utc)
    snapshot = MudaeMessageSnapshot(
        message_id=2,
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
    entry = record_sphere_earning(
        snapshot,
        {"amount": 72, "claimed_by": "me", "sphere_type": "spT2"},
        source="sphere_click",
        now=now,
    )
    assert entry["sphere_type"] == "spT"


def test_build_stats_by_source():
    entries = [
        {
            "amount": 10,
            "source": "sphere_click",
            "source_label": source_label("sphere_click"),
            "date_key": "2026-07-03",
            "recorded_at": "2026-07-03T10:00:00+00:00",
        },
        {
            "amount": 500,
            "source": "minigame_oh",
            "source_label": source_label("minigame_oh"),
            "date_key": "2026-07-03",
            "recorded_at": "2026-07-03T11:00:00+00:00",
        },
    ]
    stats = build_stats(entries, now=dt.datetime(2026, 7, 3, tzinfo=dt.timezone.utc))
    assert stats["totals"]["all_time"] == 510
    assert len(stats["by_source"]) == 2
