"""Tests for Mudae command acknowledgement reactions."""

from __future__ import annotations

from types import SimpleNamespace

from mudae.command_ack import (
    is_mudae_command_ack_emoji,
    message_has_mudae_command_ack,
    reaction_is_mudae_command_ack,
)
from mudae.constants import TARGET_BOT_ID


def test_is_mudae_command_ack_emoji_accepts_checkmarks():
    assert is_mudae_command_ack_emoji("\u2705") is True
    assert is_mudae_command_ack_emoji(SimpleNamespace(name="white_check_mark")) is True


def test_reaction_is_mudae_command_ack_requires_mudae_user():
    reaction = SimpleNamespace(emoji="\u2705")
    assert reaction_is_mudae_command_ack(reaction, TARGET_BOT_ID) is True
    assert reaction_is_mudae_command_ack(reaction, 123456789) is False


def test_message_has_mudae_command_ack():
    users = [SimpleNamespace(id=TARGET_BOT_ID)]
    reaction = SimpleNamespace(emoji="\u2705", users=users)
    message = SimpleNamespace(reactions=[reaction])
    assert message_has_mudae_command_ack(message) is True
