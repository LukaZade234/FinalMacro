"""Tests for ``$rt`` parsing, state sync, and auto-use before claims."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from macro.config import CharacterClaimRules, MacroConfig
from macro.post_roll import PostRollHandler, RollRecord
from macro.rt_manager import apply_rt_response, has_rt_available, should_stop_after_wish_claim, sync_rt_fields_from_tu
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


def test_has_rt_available():
    state = AccountState(rt_available=True)
    assert has_rt_available(state) is True
    state.rt_available = False
    assert has_rt_available(state) is False


def test_should_stop_after_wish_claim():
    assert should_stop_after_wish_claim(
        AccountState(claim_available=False, rt_available=False)
    ) is True
    assert should_stop_after_wish_claim(
        AccountState(claim_available=False, rt_available=True)
    ) is False
    assert should_stop_after_wish_claim(
        AccountState(claim_available=True, rt_available=False)
    ) is False


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


def _rt_record() -> RollRecord:
    return RollRecord(
        message_id=1,
        character_name="Char",
        fields={
            "can_claim": True,
            "claimed": False,
            "buttons": [{"label": "Claim", "custom_id": "123p456p789"}],
        },
    )


def _rt_handler(actions, logs: list[str]) -> tuple[PostRollHandler, AccountState]:
    state = AccountState(claim_available=False, rt_available=True)
    config = MacroConfig(
        character_claim=CharacterClaimRules(
            claim_on_wish_ping=True,
            auto_use_rt=True,
        )
    )
    return PostRollHandler(actions, config, state, log=logs.append), state


def test_post_roll_rt_without_tick_asks_tu_and_gives_up_when_still_on_cooldown():
    """A lost tick is not proof the reset was missed — $tu is asked, and believed."""
    actions = AsyncMock()
    actions.send_command = AsyncMock(return_value=12345)
    actions.wait_for_mudae_tick = AsyncMock(return_value=False)
    actions.wait_for_tu = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.TU,
            summary="$tu",
            fields={"claim_available": False, "claim_cooldown_minutes": 42},
        )
    )
    logs: list[str] = []
    handler, _state = _rt_handler(actions, logs)

    claimed = asyncio.run(
        handler.claim_record(_rt_record(), reason="Wish rolled and pinged you", allow_rt=True)
    )

    assert claimed is False
    actions.click_button.assert_not_called()
    assert any("no Mudae tick" in line for line in logs)
    assert any("still on cooldown" in line for line in logs)


def test_post_roll_rt_claims_on_the_tick_alone():
    """The tick is Mudae's whole answer to $rt — nothing else is waited for.

    The macro used to sit for 12s waiting for a reply message that Mudae never
    sends, then cancel the claim when it did not arrive, losing the wish and the
    reset together.
    """
    actions = AsyncMock()
    actions.send_command = AsyncMock(return_value=12345)
    actions.wait_for_mudae_tick = AsyncMock(return_value=True)
    actions.fetch_message_snapshot = AsyncMock(return_value=None)
    logs: list[str] = []
    handler, state = _rt_handler(actions, logs)

    claimed = asyncio.run(
        handler.claim_record(_rt_record(), reason="Wish rolled and pinged you", allow_rt=True)
    )

    assert claimed is True
    actions.click_button.assert_awaited_once()
    actions.wait_for_tu.assert_not_called()  # no confirmation needed after a tick
    actions.send_command.assert_awaited_once_with("rt", prefix="$")
    assert state.rt_available is False
    assert any("confirmed by tick" in line for line in logs)


def test_post_roll_rt_lost_tick_is_recovered_by_tu():
    """A tick is a gateway event and can be lost; $tu is the only other evidence."""
    actions = AsyncMock()
    actions.send_command = AsyncMock(return_value=12345)
    actions.wait_for_mudae_tick = AsyncMock(return_value=False)
    actions.wait_for_tu = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.TU,
            summary="$tu",
            fields={"claim_available": True, "rt_next_minutes": 1200},
        )
    )
    actions.fetch_message_snapshot = AsyncMock(return_value=None)
    logs: list[str] = []
    handler, state = _rt_handler(actions, logs)

    claimed = asyncio.run(
        handler.claim_record(_rt_record(), reason="Wish rolled and pinged you", allow_rt=True)
    )

    assert claimed is True
    actions.click_button.assert_awaited_once()
    assert state.rt_available is False
    assert any("$tu confirms" in line for line in logs)


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


# --- what $rt buys stays bought for the character it was bought for ---------
#
# Reported 2026-09-07: a wish series rolled, the macro spent `$rt` for it, and
# then claimed the highest-kakera character of the batch instead. Both halves
# below are that report: `$rt` was spent on a claim that could not land, and the
# slot it opened was then spent by the end-of-batch picker.


def _rt_actions(*, sniped: bool = False):
    actions = AsyncMock()
    actions.send_command = AsyncMock(return_value=12345)
    actions.wait_for_mudae_tick = AsyncMock(return_value=True)
    actions.fetch_message_snapshot = AsyncMock(
        return_value=object() if sniped else None
    )
    actions.click_button = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.CLAIM,
            summary="claim",
            fields={"winner": "Tester", "character": "Big Kakera Guy"},
        )
    )
    return actions


def _wish_config():
    return MacroConfig(
        character_claim=CharacterClaimRules(
            enabled=True,
            claim_on_wish_ping=True,
            auto_use_rt=True,
            only_final_hour=False,
        )
    )


def _record(message_id, name, kakera, **fields):
    base = {
        "can_claim": True,
        "claimed": False,
        "total_kakera": kakera,
        "claim_method": "button",
        "buttons": [{"label": "Claim", "custom_id": f"{message_id}p2p3"}],
    }
    base.update(fields)
    return RollRecord(message_id=message_id, character_name=name, fields=base)


def test_a_wish_bought_rt_slot_is_not_spent_on_the_batchs_best():
    """The reported bug, end to end at the claim layer."""
    state = AccountState(claim_available=False, rt_available=True)
    actions = _rt_actions(sniped=True)
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    wish = _record(1, "Wished Series Char", 120)
    big = _record(2, "Big Kakera Guy", 9000)

    with patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.ROLL_OWNERSHIP,
            summary="claimed",
            fields={
                "character_name": "Wished Series Char",
                "claimed": True,
                "owner": "Sniper",
            },
        ),
    ):
        claimed = asyncio.run(
            handler.claim_record(wish, reason="Wish rolled", allow_rt=True)
        )

    # $rt was spent and the wish was sniped during the round trip, so the slot
    # is open — but it belongs to the wish, not to the batch.
    assert claimed is False
    assert state.claim_available is True
    assert state.rt_claim_slot_for == "Wished Series Char"

    asyncio.run(handler.claim_best([wish, big], context="batch end", final_hour=False))

    actions.click_button.assert_not_called()
    assert not any("Claimed Big Kakera Guy" in line for line in logs)
    assert any("keeping it for a wish" in line for line in logs)


def test_an_ordinary_open_slot_still_claims_the_batchs_best():
    """The guard is about a slot `$rt` bought, not about claiming in general."""
    state = AccountState(claim_available=True, rt_available=True)
    actions = _rt_actions()
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    asyncio.run(
        handler.claim_best(
            [_record(1, "Small", 100), _record(2, "Big Kakera Guy", 9000)],
            context="batch end",
            final_hour=False,
        )
    )

    actions.click_button.assert_awaited_once()
    assert any("Best this batch: Big Kakera Guy" in line for line in logs)


def test_a_landed_wish_claim_releases_the_reservation():
    state = AccountState(claim_available=False, rt_available=True)
    actions = _rt_actions()
    actions.wait_for_claim = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.CLAIM,
            summary="claim",
            fields={"winner": "Tester", "character": "Wished Series Char"},
        )
    )
    handler = PostRollHandler(actions, _wish_config(), state, log=lambda _: None)

    claimed = asyncio.run(
        handler.claim_record(
            _record(1, "Wished Series Char", 120), reason="Wish rolled", allow_rt=True
        )
    )

    assert claimed is True
    # The slot was used for what it was bought for, so nothing is held back.
    assert state.rt_claim_slot_for == ""
    assert state.claim_available is False


def test_rt_is_not_spent_on_a_roll_that_is_already_gone():
    """These three were only checked *after* `$rt` had been sent, so each cost a
    reset to discover."""
    for fields, expected in (
        ({"claimed": True, "owner": "Sniper"}, "already claimed"),
        ({"can_claim": False}, "not claimable"),
    ):
        state = AccountState(claim_available=False, rt_available=True)
        actions = _rt_actions()
        logs: list[str] = []
        handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)
        record = _record(1, "Char", 100, **fields)

        claimed = asyncio.run(
            handler.claim_record(record, reason="Wish rolled", allow_rt=True)
        )

        assert claimed is False
        actions.send_command.assert_not_called()
        assert state.rt_available is True
        assert any(expected in line for line in logs)


def test_rt_is_not_spent_when_the_claim_timer_has_already_run_out():
    import time as _time

    state = AccountState(claim_available=False, rt_available=True, claim_expire_sec=45)
    actions = _rt_actions()
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)
    stale = _record(1, "Char", 100)
    stale.rolled_at = _time.monotonic() - 60

    claimed = asyncio.run(
        handler.claim_record(stale, reason="Wish rolled", allow_rt=True)
    )

    assert claimed is False
    actions.send_command.assert_not_called()
    assert any("claim timer expired" in line for line in logs)


def test_rt_is_not_spent_when_the_timer_would_die_mid_round_trip():
    """A reset bought with 2s left on a 45s button is a guaranteed loss: the
    round trip cannot finish before Mudae disables it."""
    import time as _time

    state = AccountState(claim_available=False, rt_available=True, claim_expire_sec=45)
    actions = _rt_actions()
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)
    nearly_gone = _record(1, "Char", 100)
    nearly_gone.rolled_at = _time.monotonic() - 43

    claimed = asyncio.run(
        handler.claim_record(nearly_gone, reason="Wish rolled", allow_rt=True)
    )

    assert claimed is False
    actions.send_command.assert_not_called()
    assert state.rt_available is True
    assert any("expire mid-round-trip" in line for line in logs)


def test_a_fresh_roll_still_gets_its_rt():
    """The headroom guard must not refuse a roll that just landed."""
    import time as _time

    state = AccountState(claim_available=False, rt_available=True, claim_expire_sec=45)
    actions = _rt_actions()
    handler = PostRollHandler(actions, _wish_config(), state, log=lambda _: None)
    fresh = _record(1, "Char", 100)
    fresh.rolled_at = _time.monotonic() - 2

    claimed = asyncio.run(
        handler.claim_record(fresh, reason="Wish rolled", allow_rt=True)
    )

    assert claimed is True
    actions.send_command.assert_awaited_once_with("rt", prefix="$")


def test_the_banked_slot_goes_to_the_next_wish():
    """The point of holding it back: the reset stays available for what it was
    bought for, instead of the next wish finding no slot and no `$rt`."""
    state = AccountState(claim_available=False, rt_available=True)
    actions = _rt_actions(sniped=True)
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    with patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.ROLL_OWNERSHIP,
            summary="claimed",
            fields={"character_name": "First Wish", "claimed": True, "owner": "Sniper"},
        ),
    ):
        asyncio.run(
            handler.claim_record(
                _record(1, "First Wish", 120), reason="Wish rolled", allow_rt=True
            )
        )
    assert state.rt_claim_slot_for == "First Wish"
    assert state.rt_available is False  # spent, and there is no second one

    actions.wait_for_claim = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.CLAIM,
            summary="claim",
            fields={"winner": "Tester", "character": "Second Wish"},
        )
    )
    claimed = asyncio.run(
        handler.claim_record(
            _record(2, "Second Wish", 300), reason="Wish rolled", allow_rt=True
        )
    )

    assert claimed is True
    assert any("Claimed Second Wish" in line for line in logs)
    # One $rt sent in total — the second wish rode the slot the first bought.
    assert actions.send_command.await_count == 1
    assert state.rt_claim_slot_for == ""


# --- claim retry ------------------------------------------------------------
#
# A wish is claimed a second or two after it spawns, so a claim that does not
# land is a lost click or a lost reply — not an expired window. Giving up on the
# first silence is what left the $rt slot open for the batch picker.


def _claim_reply(character="Wished Series Char"):
    return ParseResult(
        kind=MessageKind.CLAIM,
        summary="claim",
        fields={"winner": "Tester", "character": character},
    )


def test_a_timed_out_claim_is_retried_and_lands():
    state = AccountState(claim_available=True, own_usernames=["Tester"])
    actions = _rt_actions()
    # First attempt gets no reply; the roll re-reads as still claimable.
    actions.wait_for_claim = AsyncMock(side_effect=[None, _claim_reply()])
    actions.fetch_message_snapshot = AsyncMock(return_value=object())
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)
    record = _record(1, "Wished Series Char", 120)

    with patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.CLAIM_BUTTONS,
            summary="roll",
            fields={
                "character_name": "Wished Series Char",
                "claimed": False,
                "can_claim": True,
                "claim_method": "button",
                "buttons": [{"label": "Claim", "custom_id": "1p2p3"}],
            },
        ),
    ):
        asyncio.run(handler.claim_record(record, reason="Wish rolled"))

    assert actions.click_button.await_count == 2
    assert any("Retrying claim on Wished Series Char" in line for line in logs)
    assert any("Claimed Wished Series Char" in line for line in logs)
    assert state.claim_available is False


def test_a_claim_whose_reply_was_lost_is_recognised_not_reclaimed():
    """The `$ot` lesson: a silent click may well have landed and paid out, so
    the roll is re-read before anything is retried."""
    state = AccountState(claim_available=True, own_usernames=["Tester"])
    actions = _rt_actions()
    actions.wait_for_claim = AsyncMock(return_value=None)
    actions.fetch_message_snapshot = AsyncMock(return_value=object())
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    with patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.ROLL_OWNERSHIP,
            summary="ours",
            fields={
                "character_name": "Wished Series Char",
                "claimed": True,
                "owner": "Tester",
            },
        ),
    ):
        asyncio.run(
            handler.claim_record(_record(1, "Wished Series Char", 120), reason="Wish")
        )

    assert actions.click_button.await_count == 1  # not clicked a second time
    assert any("Claim confirmed" in line for line in logs)
    # The slot really was spent, so nothing else in the batch may claim on it.
    assert state.claim_available is False
    assert state.rt_claim_slot_for == ""


def test_a_sniped_roll_is_not_retried():
    state = AccountState(claim_available=True, own_usernames=["Tester"])
    actions = _rt_actions()
    actions.wait_for_claim = AsyncMock(return_value=None)
    actions.fetch_message_snapshot = AsyncMock(return_value=object())
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    with patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.ROLL_OWNERSHIP,
            summary="theirs",
            fields={
                "character_name": "Wished Series Char",
                "claimed": True,
                "owner": "Sniper",
            },
        ),
    ):
        asyncio.run(
            handler.claim_record(_record(1, "Wished Series Char", 120), reason="Wish")
        )

    assert actions.click_button.await_count == 1
    assert any("claimed by Sniper — nothing to retry" in line for line in logs)


def test_retry_gaps_escalate_and_the_first_attempt_is_never_delayed():
    """A wish is claimed the instant it spawns, so only *retries* back off."""
    from macro.post_roll import _CLAIM_ATTEMPTS, _CLAIM_RETRY_PAUSES_SEC

    assert _CLAIM_RETRY_PAUSES_SEC == (1.0, 3.0, 5.0)
    assert _CLAIM_ATTEMPTS == 4

    state = AccountState(claim_available=True, own_usernames=["Tester"])
    actions = _rt_actions()
    actions.wait_for_claim = AsyncMock(return_value=None)
    actions.fetch_message_snapshot = AsyncMock(return_value=object())
    slept: list[float] = []
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    async def _record_sleep(seconds):
        slept.append(seconds)

    with patch("macro.post_roll.asyncio.sleep", _record_sleep), patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.CLAIM_BUTTONS,
            summary="roll",
            fields={
                "character_name": "Wished Series Char",
                "claimed": False,
                "can_claim": True,
                "claim_method": "button",
                "buttons": [{"label": "Claim", "custom_id": "1p2p3"}],
            },
        ),
    ):
        asyncio.run(
            handler.claim_record(_record(1, "Wished Series Char", 120), reason="Wish")
        )

    assert slept == [1.0, 3.0, 5.0]
    assert actions.click_button.await_count == 4
    assert any("Retrying claim on Wished Series Char in 1s" in x for x in logs)
    assert any("in 5s (4/4)" in x for x in logs)


def test_retries_stop_at_the_attempt_limit():
    state = AccountState(claim_available=True, own_usernames=["Tester"])
    actions = _rt_actions()
    actions.wait_for_claim = AsyncMock(return_value=None)
    actions.fetch_message_snapshot = AsyncMock(return_value=object())
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    with patch(
        "mudae.parsers.pipeline.parse_mudae_message",
        return_value=ParseResult(
            kind=MessageKind.CLAIM_BUTTONS,
            summary="roll",
            fields={
                "character_name": "Wished Series Char",
                "claimed": False,
                "can_claim": True,
                "claim_method": "button",
                "buttons": [{"label": "Claim", "custom_id": "1p2p3"}],
            },
        ),
    ):
        asyncio.run(
            handler.claim_record(_record(1, "Wished Series Char", 120), reason="Wish")
        )

    assert actions.click_button.await_count == 4
    assert any("Gave up claiming" in line for line in logs)
    # Never silently reported as claimed.
    assert state.claim_available is True


def test_a_failed_click_is_retried_too():
    """`click_button` reporting failure is exactly the case that can still have
    reached Mudae, so it re-reads and tries again rather than giving up."""
    state = AccountState(claim_available=True, own_usernames=["Tester"])
    actions = _rt_actions()
    actions.click_button = AsyncMock(side_effect=[False, True])
    actions.wait_for_claim = AsyncMock(return_value=_claim_reply())
    actions.fetch_message_snapshot = AsyncMock(return_value=None)
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    asyncio.run(
        handler.claim_record(_record(1, "Wished Series Char", 120), reason="Wish")
    )

    assert actions.click_button.await_count == 2
    assert any("Claimed Wished Series Char" in line for line in logs)


def test_a_claim_interval_rejection_is_final():
    """Not a transport failure — the server said no, so retrying just clicks
    into the same wall."""
    state = AccountState(claim_available=True, own_usernames=["Tester"])
    actions = _rt_actions()
    actions.wait_for_claim = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.CLAIM_INTERVAL,
            summary="interval",
            fields={"next_interval_minutes": 90},
        )
    )
    logs: list[str] = []
    handler = PostRollHandler(actions, _wish_config(), state, log=logs.append)

    asyncio.run(
        handler.claim_record(_record(1, "Wished Series Char", 120), reason="Wish")
    )

    assert actions.click_button.await_count == 1
    assert state.claim_available is False
    assert any("claim interval" in line for line in logs)
