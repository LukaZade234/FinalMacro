"""Tests for ``$dk`` parsing and auto-use tracking."""

from __future__ import annotations

import time

from macro.config import KakeraReactionRules
from macro.dk_manager import apply_dk_response, has_dk_available, sync_dk_fields_from_tu
from macro.state import AccountState
from mudae.parsers.classify import classify_message
from mudae.parsers.dk import extract_dk_fields, is_dk_claim, parse_dk
from mudae.parsers.tu import parse_tu
from mudae.types import MessageKind, MudaeMessageSnapshot


def test_parse_dk_standalone_with_stock_left():
    content = (
        "Nice, **+389**<:kakera:469835869059153940>added to your kakera collection! "
        "(**85,995** total). **1** $dk left. +**30** <:sp:1437140700604137554>"
    )
    assert is_dk_claim(content) is True
    result = parse_dk(content)
    assert result.kind == MessageKind.DK_CLAIM
    assert result.fields["amount"] == 389
    assert result.fields["total_kakera"] == 85995
    assert result.fields["dk_stock"] == 1
    assert result.fields["spheres"] == 30


def test_parse_dk_no_stock_left():
    content = (
        "**+309**<:kakera:469835869059153940>added to your kakera collection! "
        "(**88,959** total). +**30** <:sp:1437140700604137554>"
    )
    fields = extract_dk_fields(content)
    assert fields["amount"] == 309
    assert fields["dk_stock"] == 0


def test_parse_tu_next_dk_timer_sets_zero_stock():
    content = (
        "**User**, you __can__ claim right now! "
        "You have **0** rolls left. Next rolls reset in **49** min.\n"
        "Power: **115%**\n\n"
        "$rt is available!\n"
        "Next $dk in **9h 57** min."
    )
    result = parse_tu(content)
    assert result.fields["dk_stock"] == 0
    assert result.fields["dk_next_minutes"] == 9 * 60 + 57
    assert result.fields["power_percent"] == 115


def test_parse_tu_combined_dk_and_status():
    content = (
        "**+309**<:kakera:469835869059153940>added to your kakera collection! "
        "(**88,959** total). +**30** <:sp:1437140700604137554>\n\n"
        "**User**, you __can__ claim right now! The next claim reset is in **49** min.\n"
        "You have **0** rolls (+**0** $mk) left. Next rolls reset in **49** min.\n"
        "Power: **115%**\n\n"
        "$rt is available!\n"
        "Next $dk in **9h 57** min."
    )
    result = parse_tu(content)
    assert result.fields["amount"] == 309
    assert result.fields["dk_used"] is True
    assert result.fields["dk_stock"] == 0
    assert result.fields["dk_next_minutes"] == 9 * 60 + 57
    assert result.fields["power_percent"] == 115


def test_sync_dk_from_tu_and_apply_dk_response():
    state = AccountState(dk_stock=2, power_percent=12.0, power_tracked_at=time.monotonic())
    sync_dk_fields_from_tu(state, {"dk_stock": 2, "dk_next_minutes": 517})
    assert state.dk_stock == 2
    assert state.dk_next_minutes == 517

    apply_dk_response(
        state,
        {"dk_used": True, "amount": 389, "dk_stock": 1, "power_percent": 115},
    )
    assert state.power_percent == 115.0
    assert state.dk_stock == 1


def test_has_dk_available():
    assert has_dk_available(AccountState(dk_stock=2)) is True
    assert has_dk_available(AccountState(dk_stock=0)) is False
    assert has_dk_available(AccountState(dk_stock=None)) is False


def test_classify_dk_claim():
    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=2,
        channel_name="c",
        guild_id=3,
        guild_name="g",
        author_id=4,
        author_name="Mudae",
        is_mudae=True,
        content="Nice, **+100**<:kakera:1>added to your kakera collection! (**1** total).",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )
    assert classify_message(snapshot) == MessageKind.DK_CLAIM


def test_kakera_rules_auto_use_dk_default_off():
    rules = KakeraReactionRules.from_dict({})
    assert rules.auto_use_dk is False
    restored = KakeraReactionRules.from_dict({"auto_use_dk": True})
    assert restored.auto_use_dk is True
