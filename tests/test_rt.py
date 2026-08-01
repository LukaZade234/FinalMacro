"""Tests for ``$rt`` parsing, state sync, and auto-use before claims."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from macro.config import CharacterClaimRules, MacroConfig
from macro.post_roll import PostRollHandler, RollRecord
from macro.rt_manager import apply_rt_response, has_rt_available, sync_rt_fields_from_tu
from macro.rule_eval import passes_character_claim
from macro.state import AccountState
from mudae.parsers.rt import extract_rt_fields, parse_rt
from mudae.parsers.tu import parse_tu
from mudae.types import MessageKind, ParseResult


def test_parse_tu_rt_available():
    content = (
        "**User**, you __can__ claim right now! "
        "You have **3** rolls left.\n"
        "$rt is available!\n"
        "Next $dk in **9h 57** min."
    )
    result = parse_tu(content)
    assert result.fields["rt_available"] is True
    assert "rt_next_minutes" not in result.fields


def test_parse_tu_rt_cooldown_replaces_available():
    content = (
        "**User**, you can't claim for another **45** min. "
        "You have **3** rolls left.\n"
        "Next $rt in **5h 30** min.\n"
        "Next $dk in **9h 57** min."
    )
    result = parse_tu(content)
    assert result.fields["rt_available"] is False
    assert result.fields["rt_next_minutes"] == 5 * 60 + 30
    assert "rt next 5h 30m" in result.summary


def test_parse_rt_success_from_tu_response():
    content = (
        "**User**, you __can__ claim right now! "
        "You have **0** rolls left.\n"
        "Next $rt in **20h 0** min."
    )
    result = parse_rt(content)
    assert result.fields["rt_used"] is True
    assert result.fields["claim_available"] is True
    assert result.fields["rt_next_minutes"] == 20 * 60


def test_sync_and_apply_rt_response():
    state = AccountState(claim_available=False, rt_available=True)
    sync_rt_fields_from_tu(state, {"rt_available": True})
    assert has_rt_available(state) is True

    ok = apply_rt_response(
        state,
        {
            "rt_used": True,
            "claim_available": True,
            "rt_next_minutes": 1200,
            "rt_available": False,
        },
    )
    assert ok is True
    assert state.claim_available is True
    assert state.rt_available is False
    assert state.rt_next_minutes == 1200


def test_wish_ping_allows_rt_on_cooldown():
    rules = CharacterClaimRules(claim_on_wish_ping=True, auto_use_rt=True)
    state = AccountState(claim_available=False, rt_available=True)
    decision = passes_character_claim(
        {"can_claim": True, "claimed": False},
        rules,
        state,
        final_hour=False,
        wished_pinged=True,
    )
    assert decision.should_claim is True
    assert decision.immediate is True
    assert "$rt" in decision.reason


def test_wish_ping_still_blocked_without_rt():
    rules = CharacterClaimRules(claim_on_wish_ping=True, auto_use_rt=False)
    state = AccountState(claim_available=False, rt_available=True)
    decision = passes_character_claim(
        {"can_claim": True, "claimed": False},
        rules,
        state,
        final_hour=False,
        wished_pinged=True,
    )
    assert decision.should_claim is False
    assert "cooldown" in decision.reason


def test_post_roll_uses_rt_before_wish_claim():
    state = AccountState(claim_available=False, rt_available=True)
    config = MacroConfig(
        character_claim=CharacterClaimRules(
            enabled=False,
            claim_on_wish_ping=True,
            auto_use_rt=True,
        )
    )
    actions = AsyncMock()
    actions.send_command = AsyncMock(return_value=12345)
    actions.wait_for_mudae_tick = AsyncMock(return_value=True)
    actions.wait_for_rt_use = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.TU,
            summary="$rt",
            fields={"rt_used": True, "claim_available": True},
        )
    )
    actions.fetch_message_snapshot = AsyncMock(return_value=None)
    actions.click_button = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.CLAIM,
            summary="claim",
            fields={"winner": "Tester", "character": "Char"},
        )
    )

    logs: list[str] = []
    handler = PostRollHandler(actions, config, state, log=logs.append)
    record = RollRecord(
        message_id=1,
        character_name="Char",
        fields={
            "can_claim": True,
            "claimed": False,
            "buttons": [{"label": "Claim", "custom_id": "123p456p789"}],
        },
    )

    claimed = asyncio.run(handler.claim_record(record, reason="Wish rolled and pinged you", allow_rt=True))

    assert claimed is True
    actions.send_command.assert_awaited_once_with("rt", prefix="$")
    actions.click_button.assert_awaited_once()
    assert state.claim_available is False  # spent after claim
    assert any("$rt OK" in line for line in logs)
    actions.wait_for_mudae_tick.assert_awaited_once_with(12345, timeout=8.0)


def test_post_roll_rt_then_someone_else_claimed_first():
    """If a claim slot opens via $rt but another user claimed it meanwhile, skip cleanly."""
    state = AccountState(claim_available=False, rt_available=True)
    config = MacroConfig(
        character_claim=CharacterClaimRules(
            enabled=False,
            claim_on_wish_ping=True,
            auto_use_rt=True,
        )
    )
    actions = AsyncMock()
    actions.send_command = AsyncMock(return_value=12345)
    actions.wait_for_mudae_tick = AsyncMock(return_value=True)
    actions.wait_for_rt_use = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.TU,
            summary="$rt",
            fields={"rt_used": True, "claim_available": True},
        )
    )
    fresh_snapshot = object()
    actions.fetch_message_snapshot = AsyncMock(return_value=fresh_snapshot)

    logs: list[str] = []
    handler = PostRollHandler(actions, config, state, log=logs.append)
    record = RollRecord(
        message_id=1,
        character_name="Char",
        fields={
            "can_claim": True,
            "claimed": False,
            "buttons": [{"label": "Claim", "custom_id": "123p456p789"}],
        },
    )

    with patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.ROLL_OWNERSHIP,
            summary="Roll claimed",
            fields={"character_name": "Char", "claimed": True, "owner": "RivalUser"},
        ),
    ):
        claimed = asyncio.run(
            handler.claim_record(record, reason="Wish rolled and pinged you", allow_rt=True)
        )

    assert claimed is False
    actions.click_button.assert_not_called()
    assert any("already claimed by RivalUser" in line for line in logs)


def test_post_roll_rt_aborts_without_tick():
    state = AccountState(claim_available=False, rt_available=True)
    config = MacroConfig(
        character_claim=CharacterClaimRules(
            claim_on_wish_ping=True,
            auto_use_rt=True,
        )
    )
    actions = AsyncMock()
    actions.send_command = AsyncMock(return_value=12345)
    actions.wait_for_mudae_tick = AsyncMock(return_value=False)
    logs: list[str] = []
    handler = PostRollHandler(actions, config, state, log=logs.append)
    record = RollRecord(
        message_id=1,
        character_name="Char",
        fields={"can_claim": True, "claimed": False, "buttons": [{"custom_id": "123p456p789"}]},
    )

    claimed = asyncio.run(
        handler.claim_record(record, reason="Wish rolled and pinged you", allow_rt=True)
    )

    assert claimed is False
    actions.wait_for_rt_use.assert_not_called()
    assert any("no Mudae tick" in line for line in logs)


def test_instant_trigger_does_not_use_rt_on_cooldown():
    rules = CharacterClaimRules(
        enabled=True,
        claim_on_wish_ping=False,
        auto_use_rt=True,
        min_kakera=500,
    )
    state = AccountState(claim_available=False, rt_available=True)
    decision = passes_character_claim(
        {"can_claim": True, "claimed": False, "total_kakera": 900},
        rules,
        state,
        final_hour=False,
        wished_pinged=False,
    )
    assert decision.should_claim is False
    assert "cooldown" in decision.reason


def test_claim_best_skips_rt_on_cooldown():
    state = AccountState(claim_available=False, rt_available=True)
    config = MacroConfig(
        character_claim=CharacterClaimRules(enabled=True, auto_use_rt=True),
    )
    actions = AsyncMock()
    actions.send_command = AsyncMock()
    logs: list[str] = []
    handler = PostRollHandler(actions, config, state, log=logs.append)
    record = RollRecord(
        message_id=1,
        character_name="Char",
        fields={"can_claim": True, "claimed": False, "total_kakera": 500},
    )

    asyncio.run(handler.claim_best([record], final_hour=True))

    actions.send_command.assert_not_awaited()
    assert any("claim on cooldown" in line for line in logs)


def test_character_claim_rules_auto_use_rt_default_off():
    rules = CharacterClaimRules.from_dict({})
    assert rules.auto_use_rt is False
    restored = CharacterClaimRules.from_dict({"auto_use_rt": True})
    assert restored.auto_use_rt is True
