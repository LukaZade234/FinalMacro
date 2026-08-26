"""Convert discord.py messages into parser-friendly snapshots."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import discord

from mudae.buttons import button_styles_from_raw, classify_button_kind, normalize_button_style
from mudae.constants import BOT_NAME, MUDAE_BOT_IDS
from mudae.message_text import flatten_component_text
from mudae.types import MudaeMessageSnapshot

# discord.Message is slotted and has no ``__weakref__``, so we cannot stash
# Components V2 payloads on the instance. Key by snowflake; cap the map so
# overnight sessions do not grow without bound.
_RAW_COMPONENTS_BY_ID: OrderedDict[int, list[Any]] = OrderedDict()
_RAW_COMPONENTS_MAX = 400


def remember_raw_components(message_id: int, data: Any) -> None:
    payload = list(data) if data else []
    _RAW_COMPONENTS_BY_ID[int(message_id)] = payload
    _RAW_COMPONENTS_BY_ID.move_to_end(int(message_id))
    while len(_RAW_COMPONENTS_BY_ID) > _RAW_COMPONENTS_MAX:
        _RAW_COMPONENTS_BY_ID.popitem(last=False)


def raw_components_for(message: Any) -> list[Any]:
    cached = getattr(message, "_raw_components", None)
    if cached:
        return list(cached)
    message_id = getattr(message, "id", None)
    if message_id is None:
        return []
    return list(_RAW_COMPONENTS_BY_ID.get(int(message_id), []))


def _install_raw_component_capture() -> None:
    """Keep Components V2 payloads that discord.py-self 2.1 otherwise drops."""
    original = discord.Message._handle_components
    if getattr(original, "_finalmacro_keeps_raw", False):
        return

    def _keep_raw(self: discord.Message, data: Any) -> None:
        try:
            remember_raw_components(int(self.id), data)
        except Exception:
            pass
        original(self, data)

    _keep_raw._finalmacro_keeps_raw = True  # type: ignore[attr-defined]
    discord.Message._handle_components = _keep_raw  # type: ignore[method-assign]


_install_raw_component_capture()


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


def _components_to_buttons(
    message: discord.Message,
    raw_components: Any = None,
) -> list[dict[str, Any]]:
    raw_styles = button_styles_from_raw(raw_components)
    buttons: list[dict[str, Any]] = []
    for row in message.components or []:
        if not isinstance(row, discord.ActionRow):
            continue
        for child in row.children:
            if not isinstance(child, discord.Button):
                continue
            emoji = child.emoji
            custom_id = child.custom_id or ""
            style = normalize_button_style(getattr(child, "style", None))
            if custom_id and raw_styles.get(custom_id):
                style = raw_styles[custom_id]
            buttons.append(
                {
                    "label": child.label or "",
                    "emoji": getattr(emoji, "name", None) or (str(emoji) if emoji else ""),
                    "custom_id": custom_id,
                    "kind": _button_kind(child),
                    "disabled": child.disabled,
                    "style": style,
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
    raw_components = raw_components_for(message)
    component_text = flatten_component_text(raw_components)
    content = (message.content or "").strip()
    if component_text and component_text not in content:
        content = f"{content}\n{component_text}".strip() if content else component_text
    return MudaeMessageSnapshot(
        message_id=message.id,
        channel_id=message.channel.id,
        channel_name=channel_name,
        guild_id=guild.id if guild else None,
        guild_name=guild.name if guild else None,
        author_id=author_id,
        author_name=author_name,
        is_mudae=mudae,
        content=content,
        embeds=[_embed_to_dict(e) for e in message.embeds],
        buttons=_components_to_buttons(message, raw_components),
        created_at=message.created_at.strftime("%H:%M:%S"),
        edited=edited,
        components=raw_components,
    )


def is_mudae_message(message: discord.Message) -> bool:
    author = message.author
    if author is None:
        return False
    if author.id in MUDAE_BOT_IDS:
        return True
    name = (getattr(author, "name", None) or "").lower()
    return name == BOT_NAME.lower()
