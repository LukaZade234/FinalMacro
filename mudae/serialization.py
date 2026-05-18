"""Convert discord.py messages into parser-friendly snapshots."""

from __future__ import annotations

from typing import Any

import discord

from mudae.buttons import classify_button_kind
from mudae.constants import BOT_NAME, MUDAE_BOT_IDS
from mudae.types import MudaeMessageSnapshot


def _embed_to_dict(embed: discord.Embed) -> dict[str, Any]:
    return {
        "title": embed.title or "",
        "author": (embed.author.name if embed.author else "") or "",
        "description": embed.description or "",
        "footer": (embed.footer.text if embed.footer else "") or "",
        "image_url": (embed.image.url if embed.image else "") or "",
    }


def _button_kind(button: discord.Button) -> str:
    emoji = button.emoji
    emoji_key = ""
    if emoji:
        emoji_key = getattr(emoji, "name", None) or str(emoji)
    return classify_button_kind(
        emoji=emoji_key,
        label=button.label or "",
        custom_id=button.custom_id or "",
    )


def _components_to_buttons(message: discord.Message) -> list[dict[str, Any]]:
    buttons: list[dict[str, Any]] = []
    for row in message.components or []:
        if not isinstance(row, discord.ActionRow):
            continue
        for child in row.children:
            if not isinstance(child, discord.Button):
                continue
            emoji = child.emoji
            buttons.append(
                {
                    "label": child.label or "",
                    "emoji": getattr(emoji, "name", None) or (str(emoji) if emoji else ""),
                    "custom_id": child.custom_id or "",
                    "kind": _button_kind(child),
                    "disabled": child.disabled,
                }
            )
    return buttons


def snapshot_from_message(
    message: discord.Message,
    *,
    edited: bool = False,
) -> MudaeMessageSnapshot:
    guild = message.guild
    channel = message.channel
    channel_name = getattr(channel, "name", str(message.channel.id))
    author = message.author
    author_id = author.id if author else 0
    author_name = getattr(author, "display_name", None) or getattr(author, "name", "?") or "?"
    mudae = is_mudae_message(message)
    return MudaeMessageSnapshot(
        message_id=message.id,
        channel_id=message.channel.id,
        channel_name=channel_name,
        guild_id=guild.id if guild else None,
        guild_name=guild.name if guild else None,
        author_id=author_id,
        author_name=author_name,
        is_mudae=mudae,
        content=message.content or "",
        embeds=[_embed_to_dict(e) for e in message.embeds],
        buttons=_components_to_buttons(message),
        created_at=message.created_at.strftime("%H:%M:%S"),
        edited=edited,
    )


def is_mudae_message(message: discord.Message) -> bool:
    author = message.author
    if author is None:
        return False
    if author.id in MUDAE_BOT_IDS:
        return True
    name = (getattr(author, "name", None) or "").lower()
    return name == BOT_NAME.lower()
