"""Claiming by reaction on servers/accounts with claim buttons switched off.

Mudae's claim buttons are not universal: `$togglebutton` (server) and the
user's own settings can turn them off, and an unclaimed roll then arrives with
no components at all — you claim it by *reacting* to the roll with any emoji.
Before this, `can_claim` was literally "has an enabled claim button", so on
those servers the macro considered every roll unclaimable and never claimed
anything.

The roll itself says which mode is live, so none of this needs `$settings`
parsed: a claim button under an unclaimed roll is button mode, and no claim
button at all is reaction mode. A *disabled* claim button is neither — that is
button mode with the window shut, and must not fall back to a react Mudae
would ignore.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from macro.config import CharacterClaimRules, MacroConfig
from macro.post_roll import PostRollHandler, RollRecord
from macro.rule_eval import passes_character_claim
from macro.state import AccountState
from mudae.buttons import claim_method_from_buttons
from mudae.constants import CLAIM_REACTION_EMOJI
from mudae.parsers.roll import parse_roll
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_EMBED = {
    "title": "",
    "author": "Spice Girl",
    "description": (
        "JoJo's Bizarre Adventure: Golden\n"
        "Wind\n"
        "Claims: #3,338\n"
        "Likes: #16,447\n"
        "**57**<:kakera:469835869059153940>"
    ),
    "footer": "",
    "image_url": "https://mudae.net/uploads/2511192/x.png",
}

_CLAIM_BUTTON = {
    "label": "",
    "emoji": "\U0001f496",
    "custom_id": "1506031651548037344p1473101129184186552p0",
    "kind": "other",
    "disabled": False,
}


def _snapshot(*, buttons: list[dict] | None = None, footer: str = "") -> MudaeMessageSnapshot:
    embed = dict(_EMBED)
    embed["footer"] = footer
    return MudaeMessageSnapshot(
        message_id=77,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=432618578496954900,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[embed],
        buttons=list(buttons or []),
        created_at="12:05:00",
    )


# --- reading the mode off the roll -----------------------------------------


def test_unclaimed_roll_with_no_buttons_is_claimable_by_reaction():
    result = parse_roll(_snapshot(buttons=[]))
    assert result.fields["claimed"] is False
    assert result.fields["claim_method"] == "reaction"
    # The whole point: the rest of the claim machinery gates on `can_claim`.
    assert result.fields["can_claim"] is True
    assert result.fields["has_claim_button"] is False


def test_unclaimed_roll_with_a_claim_button_still_uses_the_button():
    result = parse_roll(_snapshot(buttons=[_CLAIM_BUTTON]))
    assert result.fields["claim_method"] == "button"
    assert result.fields["can_claim"] is True


def test_disabled_claim_button_is_not_reaction_mode():
    """Button mode with the window shut — reacting there does nothing."""
    result = parse_roll(_snapshot(buttons=[{**_CLAIM_BUTTON, "disabled": True}]))
    assert result.fields["claim_method"] is None
    assert result.fields["can_claim"] is False


def test_claimed_roll_is_never_reaction_claimable():
    result = parse_roll(_snapshot(buttons=[], footer="Belongs to someone"))
    assert result.fields["claimed"] is True
    assert result.fields["claim_method"] is None
    assert result.fields["can_claim"] is False


def test_kakera_buttons_alone_still_read_as_reaction_mode():
    """A non-claim button is not a claim button — the roll is still react-only."""
    kakera = {"label": "", "emoji": "kakeraY", "kind": "kakera", "disabled": False}
    result = parse_roll(_snapshot(buttons=[kakera]))
    assert result.fields["claim_method"] == "reaction"


def test_claim_method_from_buttons_covers_the_three_cases():
    assert claim_method_from_buttons([]) == "reaction"
    assert claim_method_from_buttons([_CLAIM_BUTTON]) == "button"
    assert claim_method_from_buttons([{**_CLAIM_BUTTON, "disabled": True}]) == ""


def test_claim_rules_accept_a_reaction_only_roll():
    """`passes_character_claim` gated on `can_claim`, so this was the blocker."""
    fields = parse_roll(_snapshot(buttons=[])).fields
    decision = passes_character_claim(
        fields,
        CharacterClaimRules(enabled=True, min_kakera=1),
        AccountState(claim_available=True),
        final_hour=True,
        wished_pinged=False,
    )
    assert decision.reason != "claim window closed"
    assert decision.should_claim or decision.reason == "eligible at end of batch"


# --- claiming through a reaction -------------------------------------------


def _handler(actions) -> tuple[PostRollHandler, AccountState, list[str]]:
    config = MacroConfig(character_claim=CharacterClaimRules(enabled=True))
    state = AccountState()
    logs: list[str] = []
    return PostRollHandler(actions, config, state, log=logs.append), state, logs


def _react_record() -> RollRecord:
    return RollRecord(
        message_id=77,
        character_name="Spice Girl",
        fields=dict(parse_roll(_snapshot(buttons=[])).fields),
    )


def _claim_reply() -> ParseResult:
    return ParseResult(
        kind=MessageKind.CLAIM,
        summary="Claimed",
        fields={"winner": "lukazade234", "character": "Spice Girl"},
    )


def test_claim_record_reacts_when_the_roll_has_no_button():
    actions = AsyncMock()
    actions.click_button = AsyncMock(return_value=True)
    actions.add_reaction = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(return_value=_claim_reply())

    handler, state, logs = _handler(actions)
    record = _react_record()

    assert asyncio.run(handler.claim_record(record, reason="test")) is True

    actions.add_reaction.assert_awaited_once_with(77, CLAIM_REACTION_EMOJI)
    actions.click_button.assert_not_awaited()
    # Everything after the react is the shared claim path.
    assert record.fields["claimed"] is True
    assert state.claim_available is False
    assert any("Claimed Spice Girl" in line for line in logs)


def test_a_failed_reaction_does_not_count_as_a_claim():
    actions = AsyncMock()
    actions.add_reaction = AsyncMock(return_value=False)
    actions.wait_for_claim = AsyncMock(return_value=_claim_reply())

    handler, state, logs = _handler(actions)
    record = _react_record()

    asyncio.run(handler.claim_record(record, reason="test"))

    actions.wait_for_claim.assert_not_awaited()
    assert record.fields.get("claimed") is not True
    assert state.claim_available is not False
    assert any("reaction failed" in line.lower() for line in logs)


def test_button_rolls_are_still_clicked_not_reacted_to():
    actions = AsyncMock()
    actions.click_button = AsyncMock(return_value=True)
    actions.add_reaction = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(return_value=_claim_reply())

    handler, _state, _logs = _handler(actions)
    record = RollRecord(
        message_id=77,
        character_name="Spice Girl",
        fields=dict(parse_roll(_snapshot(buttons=[_CLAIM_BUTTON])).fields),
    )

    asyncio.run(handler.claim_record(record, reason="test"))

    actions.click_button.assert_awaited_once_with(77, _CLAIM_BUTTON["custom_id"])
    actions.add_reaction.assert_not_awaited()


def test_claim_best_reacts_for_the_batch_winner():
    """The end-of-batch picker goes through the same `_try_claim`."""
    actions = AsyncMock()
    actions.add_reaction = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(return_value=_claim_reply())

    handler, _state, _logs = _handler(actions)

    asyncio.run(handler.claim_best([_react_record()], final_hour=True))

    actions.add_reaction.assert_awaited_once_with(77, CLAIM_REACTION_EMOJI)


def test_records_without_a_claim_method_field_fall_back_to_their_buttons():
    """Records built outside the roll parser (chaos spawns) predate the field."""
    actions = AsyncMock()
    actions.click_button = AsyncMock(return_value=True)
    actions.add_reaction = AsyncMock(return_value=True)
    actions.wait_for_claim = AsyncMock(return_value=_claim_reply())

    handler, _state, _logs = _handler(actions)
    record = RollRecord(
        message_id=77,
        character_name="Spice Girl",
        fields={"can_claim": True, "claimed": False, "buttons": [_CLAIM_BUTTON]},
    )

    asyncio.run(handler.claim_record(record, reason="chaos wish spawn"))

    actions.click_button.assert_awaited_once_with(77, _CLAIM_BUTTON["custom_id"])
    actions.add_reaction.assert_not_awaited()


def test_add_reaction_is_a_no_op_on_a_monitor_that_cannot_react():
    from macro.actions import DiscordActions

    actions = DiscordActions(SimpleNamespace())
    assert asyncio.run(actions.add_reaction(1, CLAIM_REACTION_EMOJI)) is False
