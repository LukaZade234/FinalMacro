"""Tests for the per-server "once per interval" claim rejection.

Before this, ``wait_for_claim`` only recognized ``CLAIM``/``MARRIAGE``, so a
``CLAIM_INTERVAL`` rejection (a real, fast reply — "For this server, you can
claim once per interval of Xh. The next interval begins in **N** min.") was
invisible to it: the call burned its full 8s timeout and logged a plain
"Claim timeout", and nothing synced ``claim_available``/``claim_cooldown``
from it, so the very next roll in the same batch clicked into the same wall
again. It is the *same* claim slot ``$tu`` reports as "you can't claim for
another N min" — this denial just reveals it more precisely than the last
``$tu`` did, so the fix syncs it the same way ``$tu`` parsing already does.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from macro.actions import DiscordActions
from macro.config import CharacterClaimRules, MacroConfig
from macro.post_roll import PostRollHandler, RollRecord
from macro.state import AccountState
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult


def _snapshot(message_id: int) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id,
        channel_id=1,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )


def _claim_interval_result() -> ParseResult:
    return ParseResult(
        kind=MessageKind.CLAIM_INTERVAL,
        summary="Claim interval",
        fields={"next_interval_minutes": 90, "interval_hours": 12},
    )


def _record() -> RollRecord:
    return RollRecord(
        message_id=1,
        character_name="Char",
        fields={
            "can_claim": True,
            "claimed": False,
            "buttons": [{"label": "Claim", "custom_id": "123p456p789"}],
        },
    )


def _handler(actions) -> tuple[PostRollHandler, AccountState, list[str]]:
    config = MacroConfig(character_claim=CharacterClaimRules(enabled=True))
    state = AccountState()
    logs: list[str] = []
    return PostRollHandler(actions, config, state, log=logs.append), state, logs


def test_wait_for_claim_resolves_on_claim_interval_rejection():
    actions = DiscordActions(SimpleNamespace())

    async def _run() -> None:
        actions.feed(_snapshot(1), _claim_interval_result())
        parsed = await actions.wait_for_claim(timeout=0.5)
        assert parsed is not None
        assert parsed.kind == MessageKind.CLAIM_INTERVAL

    asyncio.run(_run())


def test_try_claim_syncs_claim_available_instead_of_timing_out():
    actions = AsyncMock()
    actions.click_button = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(return_value=_claim_interval_result())

    handler, state, logs = _handler(actions)
    record = _record()

    asyncio.run(handler.claim_record(record, reason="test"))

    assert any("claim interval" in line.lower() for line in logs)
    assert not any("timeout" in line.lower() for line in logs)
    # Same resource $tu reports via claim_available/claim_cooldown_minutes —
    # the existing guards elsewhere now see it as unavailable immediately.
    assert state.claim_available is False
    assert state.claim_cooldown_minutes == 90
    assert record.fields.get("claimed") is not True


def test_claim_record_skips_immediately_once_synced_unavailable():
    actions = AsyncMock()
    actions.click_button = AsyncMock(return_value=True)

    handler, state, logs = _handler(actions)
    state.claim_available = False
    state.set_claim_cooldown(90)

    claimed = asyncio.run(handler.claim_record(_record(), reason="test"))

    assert claimed is False
    actions.click_button.assert_not_awaited()
    assert any("cooldown" in line.lower() for line in logs)


def test_claim_best_skips_immediately_once_synced_unavailable():
    actions = AsyncMock()
    actions.click_button = AsyncMock(return_value=True)

    handler, state, logs = _handler(actions)
    state.claim_available = False
    state.set_claim_cooldown(90)

    asyncio.run(handler.claim_best([_record()], final_hour=True))

    actions.click_button.assert_not_awaited()
    assert any("cooldown" in line.lower() for line in logs)


def test_claim_interval_rejection_without_a_parsed_minutes_field():
    """The wait/reason parsing still resolves even if the minutes regex misses."""
    actions = AsyncMock()
    actions.click_button = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(
        return_value=ParseResult(
            kind=MessageKind.CLAIM_INTERVAL,
            summary="Claim interval",
            fields={},
        )
    )

    handler, state, logs = _handler(actions)

    asyncio.run(handler.claim_record(_record(), reason="test"))

    assert state.claim_available is False
    assert state.claim_cooldown_minutes is None
    assert any("claim interval" in line.lower() for line in logs)
