"""Detect Mudae's acknowledgement reaction on user command messages."""

from __future__ import annotations

import inspect

from mudae.constants import MUDAE_BOT_IDS

# Mudae reacts with a checkmark on accepted $commands (including ``$us N``).
_MUDAE_ACK_UNICODE = frozenset({
    "\u2714",  # heavy check mark
    "\u2705",  # white heavy check mark
})
_MUDAE_ACK_NAMES = frozenset({
    "white_check_mark",
    "heavy_check_mark",
    "mudatick",
    "muda_tick",
    "tick",
})


def mudae_ack_emoji_key(emoji: object) -> str:
    """Normalize a Discord emoji object to a comparable key."""
    if emoji is None:
        return ""
    name = getattr(emoji, "name", None)
    if name:
        return str(name).strip()
    return str(emoji).strip()


def is_mudae_command_ack_emoji(emoji: object) -> bool:
    """True when ``emoji`` is one of Mudae's command-acknowledgement marks."""
    key = mudae_ack_emoji_key(emoji)
    if not key:
        return False
    if key in _MUDAE_ACK_UNICODE:
        return True
    return key.lower() in _MUDAE_ACK_NAMES


def reaction_is_mudae_command_ack(reaction: object, user_id: int | None) -> bool:
    """True when Mudae added an acknowledgement reaction."""
    if user_id not in MUDAE_BOT_IDS:
        return False
    return is_mudae_command_ack_emoji(getattr(reaction, "emoji", None))


async def _reaction_has_mudae_user(reaction: object) -> bool:
    """True when a tick reaction on a command message came from Mudae."""
    users = getattr(reaction, "users", None)
    if users is None:
        return int(getattr(reaction, "count", 0) or 0) > 0
    if callable(users):
        users = users()
    if inspect.isawaitable(users):
        users = await users
    try:
        async for user in users:
            if getattr(user, "id", None) in MUDAE_BOT_IDS:
                return True
    except TypeError:
        for user in users:
            if getattr(user, "id", None) in MUDAE_BOT_IDS:
                return True
    return False


async def message_has_mudae_command_ack(message: object) -> bool:
    """True when a message already has Mudae's tick reaction."""
    reactions = getattr(message, "reactions", None) or []
    for reaction in reactions:
        if not is_mudae_command_ack_emoji(getattr(reaction, "emoji", None)):
            continue
        if await _reaction_has_mudae_user(reaction):
            return True
    return False
