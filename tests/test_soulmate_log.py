"""Soulmate log account enrichment and recording."""

from __future__ import annotations

from dataclasses import dataclass

from gui.accounts import AccountProfile
from mudae.account_context import main_account_defaults
from mudae.soulmate_log import (
    clear_recording_account,
    enrich_entry,
    events_for_client,
    record_new_soulmate,
    set_recording_account,
)
from mudae.types import MudaeMessageSnapshot


@dataclass
class _FakeStore:
    accounts: list[AccountProfile]
    active_account_id: str = ""


def test_events_for_client_uses_active_account_for_legacy_rows(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    soulmate_log._events = [{"character_name": "Legacy", "time": "01:00:00"}]
    store = _FakeStore(
        accounts=[
            AccountProfile(id="default", name="Default", type="Main"),
            AccountProfile(id="active", name="lukazade234", type="Main"),
        ],
        active_account_id="active",
    )
    rows = events_for_client(store)
    assert rows[0]["account_name"] == "lukazade234"
    assert rows[0]["account_id"] == "active"
    assert rows[0]["account_inferred"] is True


def test_main_account_defaults_prefers_main_type():
    store = _FakeStore(
        accounts=[
            AccountProfile(id="alt1", name="Alt One", type="Alt"),
            AccountProfile(id="main1", name="Primary", type="Main"),
        ]
    )
    assert main_account_defaults(store.accounts) == ("main1", "Primary")


def test_main_account_defaults_falls_back_to_first():
    store = _FakeStore(
        accounts=[AccountProfile(id="only", name="Solo", type="Alt")]
    )
    assert main_account_defaults(store.accounts) == ("only", "Solo")


def test_legacy_entry_assumes_main_account():
    store = _FakeStore(
        accounts=[AccountProfile(id="main1", name="Primary", type="Main")]
    )
    enriched = enrich_entry(
        {"guild_name": "Guild A", "character_name": "Alice"},
        account_by_id={acc.id: acc for acc in store.accounts},
        main_account_id="main1",
        main_account_name="Primary",
    )
    assert enriched["account_id"] == "main1"
    assert enriched["account_name"] == "Primary"
    assert enriched["account_inferred"] is True


def test_record_new_soulmate_uses_recording_account(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    soulmate_log._events = []
    set_recording_account("acc42", "Roller")

    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=99,
        channel_name="mudae",
        guild_id=42,
        guild_name="Test Guild",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )
    entry = record_new_soulmate(snapshot, {"character_name": "Bob", "series": "Test"})
    assert entry["account_id"] == "acc42"
    assert entry["account_name"] == "Roller"
    clear_recording_account()


def test_events_for_client_newest_first(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    soulmate_log._events = [
        {"character_name": "First", "time": "01:00:00"},
        {"character_name": "Second", "time": "02:00:00", "account_id": "main1"},
    ]
    store = _FakeStore(accounts=[AccountProfile(id="main1", name="Primary", type="Main")])
    rows = events_for_client(store)
    assert rows[0]["character_name"] == "Second"
    assert rows[1]["character_name"] == "First"
    assert rows[1]["account_name"] == "Primary"
    assert rows[1]["account_inferred"] is True
