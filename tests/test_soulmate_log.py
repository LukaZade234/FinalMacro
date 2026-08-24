"""Soulmate log account enrichment and recording."""

from __future__ import annotations

from dataclasses import dataclass

from gui.accounts import AccountProfile
from mudae.account_context import main_account_defaults
from mudae import event_log
from mudae.soulmate_log import (
    clear_recording_account,
    enrich_entry,
    events_for_client,
    record_new_soulmate,
    set_recording_account,
)
from mudae.types import MudaeMessageSnapshot


def _set_soulmate_events(rows: list[dict]) -> None:
    import mudae.soulmate_log as soulmate_log

    event_log.replace("soulmate", rows)
    soulmate_log._bind_events()


@dataclass
class _FakeStore:
    accounts: list[AccountProfile]
    active_account_id: str = ""


def test_events_for_client_uses_active_account_for_legacy_rows(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    _set_soulmate_events([{"character_name": "Legacy", "time": "01:00:00"}])
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
    _set_soulmate_events([
        {"character_name": "First", "time": "01:00:00"},
        {"character_name": "Second", "time": "02:00:00", "account_id": "main1"},
    ])
    store = _FakeStore(accounts=[AccountProfile(id="main1", name="Primary", type="Main")])
    rows = events_for_client(store)
    assert rows[0]["character_name"] == "Second"
    assert rows[1]["character_name"] == "First"
    assert rows[1]["account_name"] == "Primary"
    assert rows[1]["account_inferred"] is True


def test_legacy_soulmate_gets_account_from_owner(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    _set_soulmate_events([
        {
            "character_name": "Senzawa",
            "owner": "lukazade234",
            "time": "23:29:21",
        }
    ])
    store = _FakeStore(
        accounts=[
            AccountProfile(id="dup", name="Default", type="Main"),
            AccountProfile(id="real", name="lukazade234", type="Main"),
        ],
        active_account_id="real",
    )
    updated = soulmate_log.persist_legacy_account_ids(store)
    assert updated == 1
    assert soulmate_log._events[0]["account_id"] == "real"
    assert soulmate_log._events[0]["account_name"] == "lukazade234"

    rows = events_for_client(store)
    assert rows[0]["account_id"] == "real"
    assert rows[0]["account_name"] == "lukazade234"


def test_backfill_account_name_from_owner_skips_named_rows():
    import mudae.soulmate_log as soulmate_log

    _set_soulmate_events([
        {"owner": "lukazade234", "account_name": "kleinam0n"},
        {"owner": "lukazade234"},
        {"owner": "lukazade234", "account_name": "Default"},
    ])
    assert soulmate_log._backfill_account_name_from_owner() is True
    assert soulmate_log._events[0]["account_name"] == "kleinam0n"
    assert soulmate_log._events[1]["account_name"] == "lukazade234"
    assert soulmate_log._events[2]["account_name"] == "lukazade234"


def _sample_snapshot(**overrides) -> MudaeMessageSnapshot:
    base = dict(
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
    base.update(overrides)
    return MudaeMessageSnapshot(**base)


def test_record_new_soulmate_dedupes_same_message(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    snapshot = _sample_snapshot(message_id=777)
    fields = {"character_name": "Alice", "series": "Test"}

    first = record_new_soulmate(snapshot, fields)
    second = record_new_soulmate(snapshot, fields)

    assert first is not second
    assert first == second
    assert len(soulmate_log._events) == 1


def test_record_new_soulmate_dedupes_same_character_per_guild(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    fields = {"character_name": "Alice", "series": "Test"}

    first = record_new_soulmate(_sample_snapshot(message_id=1), fields)
    second = record_new_soulmate(_sample_snapshot(message_id=2), fields)

    assert first["character_name"] == "Alice"
    assert second["message_id"] == first["message_id"]
    assert len(soulmate_log._events) == 1


def test_record_new_soulmate_allows_same_character_on_other_guilds(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    fields = {"character_name": "Alice", "series": "Test"}

    record_new_soulmate(_sample_snapshot(message_id=1, guild_id=10), fields)
    record_new_soulmate(_sample_snapshot(message_id=2, guild_id=20), fields)

    assert len(soulmate_log._events) == 2


def test_dedupe_stored_events(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")
    _set_soulmate_events([
        {
            "guild_id": 1,
            "character_name": "Alice",
            "message_id": 100,
            "time": "01:00:00",
        },
        {
            "guild_id": 1,
            "character_name": "Alice",
            "message_id": 100,
            "time": "01:00:00",
        },
        {
            "guild_id": 1,
            "character_name": "Bob",
            "message_id": 101,
            "time": "02:00:00",
        },
    ])
    removed = soulmate_log.dedupe_stored_events()
    assert removed == 1
    assert len(soulmate_log._events) == 2


def test_parse_roll_skips_soulmate_log_on_embed_edit(tmp_path, monkeypatch):
    import mudae.soulmate_log as soulmate_log
    from mudae.parsers.roll import parse_roll

    monkeypatch.setattr(soulmate_log, "_LOG_PATH", tmp_path / "soulmate_log.json")

    description = (
        "**Series** · 100 <:kakera:123> (**100**)\n"
        ":chaoskey: (10) +5% kakera value\n"
        "Now your **SOULMATE**!"
    )
    snapshot = _sample_snapshot(
        message_id=99,
        edited=True,
        embeds=[{
            "author": "Alice",
            "description": description,
            "footer": "(🔑10) · Belongs to **Tester**",
        }],
    )

    result = parse_roll(snapshot)

    assert result.fields["new_soulmate"] is True
    assert soulmate_log._events == []
