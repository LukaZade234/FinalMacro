"""Tests for mudae.key_log."""

from __future__ import annotations

import datetime as dt

import pytest

from macro.state import MacroPhase
from mudae.key_log import (
    build_stats,
    count_tier_keys_by_type,
    record_roll_key_events,
    reset_for_tests,
    roll_source_from_fields,
    should_record_roll_keys,
    total_omega_gain,
)
from mudae.parsers.kakera import parse_keys, parse_omega_keys
from mudae.types import MessageKind, MudaeMessageSnapshot


def _snapshot(**overrides) -> MudaeMessageSnapshot:
    base = dict(
        message_id=1,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=0,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )
    base.update(overrides)
    return MudaeMessageSnapshot(**base)


@pytest.fixture(autouse=True)
def _isolated_key_log():
    import mudae.key_log as key_log

    key_log.reset_for_tests()
    yield
    key_log.reset_for_tests()


def test_should_record_roll_keys_during_rolling():
    fields = {"character_name": "Miku", "keys": [{"type": "gold", "level": 3}]}
    assert should_record_roll_keys(
        MessageKind.ROLL,
        fields,
        own_usernames=["alice"],
        phase=MacroPhase.ROLLING,
    )


def test_should_not_record_without_keys():
    assert not should_record_roll_keys(
        MessageKind.ROLL,
        {},
        own_usernames=["alice"],
        phase=MacroPhase.ROLLING,
    )


def test_should_not_record_profile_embed_during_idle():
    pr_desc = (
        "Collection size: 1,617 (100%:female: 0% :male:)\n"
        "Pokédex: 293 Pokémon\n"
        "Keys: 3,154:bronzekey: 4,656:silverkey: 5,877:goldkey: 33,122:chaoskey:\n"
        "84 :omegakey:\n\n711 :sp:\n"
        "Mudapins: 2,347/2,347\n"
    )
    fields = {
        "character_name": "lukazade234",
        "is_profile": True,
        "omega_keys": parse_omega_keys(pr_desc),
    }
    assert parse_omega_keys(pr_desc) == []
    assert not should_record_roll_keys(
        MessageKind.CHARACTER_EMBED,
        fields,
        own_usernames=["lukazade234"],
        phase=MacroPhase.IDLE,
        macro_running=True,
    )


def test_should_not_record_username_author_outside_roll_phase():
    fields = {
        "character_name": "lukazade234",
        "omega_keys": [{"gain": 1}],
    }
    assert not should_record_roll_keys(
        MessageKind.CHARACTER_EMBED,
        fields,
        own_usernames=["lukazade234"],
        phase=MacroPhase.IDLE,
        macro_running=True,
    )


def test_count_tier_keys_one_line_one_gain():
    keys = parse_keys(":chaoskey: (18) +5% kakera value\n")
    assert count_tier_keys_by_type(keys) == {"chaos": [18]}


def test_log_kirby_one_chaos():
    keys = parse_keys(":chaoskey: (18) +5% kakera value\n")
    entries = record_roll_key_events(
        _snapshot(message_id=1),
        {"character_name": "Kirby", "keys": keys},
    )
    assert len(entries) == 1
    assert entries[0]["key_type"] == "chaos"
    assert entries[0]["amount"] == 1
    assert entries[0]["levels_after"] == [18]


def test_log_a2_two_chaos():
    desc = (
        ":chaoskey: (31) +5% kakera value\n"
        ":chaoskey: (32) +5% kakera value\n"
    )
    entries = record_roll_key_events(
        _snapshot(message_id=2),
        {"character_name": "A2", "keys": parse_keys(desc)},
    )
    assert len(entries) == 1
    assert entries[0]["amount"] == 2
    assert entries[0]["levels_after"] == [31, 32]


def test_log_marceline_one_bronze():
    entries = record_roll_key_events(
        _snapshot(message_id=3),
        {
            "character_name": "Marceline",
            "keys": parse_keys(":bronzekey: (2) +10% kakera value\n"),
        },
    )
    assert len(entries) == 1
    assert entries[0]["key_type"] == "bronze"
    assert entries[0]["amount"] == 1


def test_log_reze_comma_separated_chaos_keys():
    desc = (
        ":chaoskey: (1,004) +5% kakera value\n"
        ":chaoskey: (1,005) +5% kakera value\n"
    )
    keys = parse_keys(desc)
    assert keys == [
        {"type": "chaos", "level": 1004},
        {"type": "chaos", "level": 1005},
    ]


def test_log_reze_two_chaos():
    desc = (
        ":chaoskey: (714) +5% kakera value\n"
        ":chaoskey: (715) +5% kakera value\n"
    )
    entries = record_roll_key_events(
        _snapshot(message_id=4),
        {"character_name": "Reze", "keys": parse_keys(desc)},
    )
    assert len(entries) == 1
    assert entries[0]["amount"] == 2


def test_log_akame_perk6_two_chaos_six_omega():
    desc = (
        ":chaoskey: (109) +5% kakera value\n"
        ":chaoskey: (110) +5% kakera value\n"
        ":omegakey: +6\n"
    )
    entries = record_roll_key_events(
        _snapshot(message_id=5),
        {
            "character_name": "Akame",
            "is_perk_6_spawn": True,
            "keys": parse_keys(desc),
            "omega_keys": parse_omega_keys(desc),
        },
    )
    assert total_omega_gain(parse_omega_keys(desc)) == 6
    by_type = {entry["key_type"]: entry["amount"] for entry in entries}
    assert by_type == {"chaos": 2, "omega": 6}
    assert entries[0]["source"] == "perk6_spawn" or entries[1]["source"] == "perk6_spawn"


def test_log_miku_three_chaos_one_omega():
    desc = (
        ":chaoskey: (364) +5% kakera value\n"
        ":chaoskey: (365) +5% kakera value\n"
        ":chaoskey: (366) +5% kakera value\n"
        ":omegakey: +1\n"
    )
    entries = record_roll_key_events(
        _snapshot(message_id=6),
        {
            "character_name": "Hatsune Miku",
            "keys": parse_keys(desc),
            "omega_keys": parse_omega_keys(desc),
        },
    )
    by_type = {entry["key_type"]: entry["amount"] for entry in entries}
    assert by_type == {"chaos": 3, "omega": 1}


def test_message_dedup():
    fields = {
        "character_name": "Kirby",
        "keys": parse_keys(":chaoskey: (18) +5% kakera value\n"),
    }
    snap = _snapshot(message_id=99)
    first = record_roll_key_events(snap, fields)
    second = record_roll_key_events(snap, fields)
    assert len(first) == 1
    assert second == []


def test_perk6_spawn_source():
    assert roll_source_from_fields({"is_perk_6_spawn": True}) == "perk6_spawn"
    assert roll_source_from_fields({}) == "roll"


def test_build_stats_groups_by_type_and_source():
    now = dt.datetime(2026, 7, 6, 12, 0, tzinfo=dt.timezone.utc)
    entries = [
        {
            "amount": 2,
            "key_type": "chaos",
            "source": "roll",
            "recorded_at": now.isoformat(),
            "date_key": "2026-07-06",
        },
        {
            "amount": 6,
            "key_type": "omega",
            "source": "perk6_spawn",
            "recorded_at": now.isoformat(),
            "date_key": "2026-07-06",
        },
    ]
    stats = build_stats(entries, now=now)
    assert stats["totals_by_type"]["chaos"]["today"] == 2
    assert stats["totals_by_type"]["omega"]["today"] == 6
