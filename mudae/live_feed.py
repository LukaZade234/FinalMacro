"""Text-only Discord/Mudae mirror for the Run live feed.

The Run tab should read like the channel: character cards with the reacts
that are actually on the embed, then Mudae's follow-up lines (``+$k``,
sphere clicks, claims). Macro skip / filter / budget chatter stays out.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.buttons import is_kakera_button, is_sphere_button
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Follow-up kinds are always channel text. Rolls are formatted from embed
# fields (Discord's character card), not from ``parsed.summary``.
_CONTENT_KINDS = frozenset(
    {
        MessageKind.KAKERA_CLAIM,
        MessageKind.SPHERE_CLICK,
        MessageKind.CLAIM,
        MessageKind.MARRIAGE,
        MessageKind.KAKERA_REACT_DENIED,
    }
)


def flatten_discord_text(text: str) -> str:
    """``<:kakeraT:123> **user +546** ($k)`` → ``:kakeraT: user +546 ($k)``."""
    if not text:
        return ""
    flat = _CUSTOM_EMOJI_RE.sub(r":\1:", text)
    flat = strip_markdown(flat)
    return _WHITESPACE_RE.sub(" ", flat).strip()


def _button_emoji(btn: dict[str, Any]) -> str:
    emoji = btn.get("emoji") or ""
    if isinstance(emoji, dict):
        return str(emoji.get("name") or "").strip()
    return str(emoji or "").strip()


def _emoji_token(emoji: str) -> str:
    emoji = (emoji or "").strip()
    if not emoji:
        return ""
    if emoji.startswith(":") and emoji.endswith(":"):
        return emoji
    if emoji.replace("_", "").isalnum():
        return f":{emoji}:"
    return emoji


def _button_tokens(fields: dict[str, Any], *, kakera: bool) -> list[str]:
    tokens: list[str] = []
    for btn in fields.get("buttons") or []:
        if not isinstance(btn, dict):
            continue
        emoji = _button_emoji(btn)
        classified = dict(btn)
        classified["emoji"] = emoji
        match = is_kakera_button(classified) if kakera else is_sphere_button(classified)
        if not match:
            continue
        token = _emoji_token(emoji)
        if token:
            tokens.append(token)
    return tokens


def _key_token(kind: str) -> str:
    name = str(kind or "key").strip().lower()
    if not name.endswith("key"):
        name = f"{name}key"
    return f":{name}:"


def _format_keys(keys: list[Any]) -> str:
    bits: list[str] = []
    for entry in keys:
        if not isinstance(entry, dict):
            continue
        token = _key_token(str(entry.get("type") or "key"))
        level = entry.get("level")
        if level is not None:
            bits.append(f"{token} {level}")
        else:
            bits.append(token)
    return " · ".join(bits)


def format_roll_line(fields: dict[str, Any]) -> str:
    """One-line character card: name, series, kakera, reacts, owner."""
    name = str(fields.get("character_name") or "Unknown")
    parts: list[str] = [name]
    series = fields.get("series")
    if series:
        parts.append(str(series))
    ka = fields.get("total_kakera")
    if ka is not None:
        try:
            parts.append(f"{int(ka):,} ka")
        except (TypeError, ValueError):
            parts.append(f"{ka} ka")
    kakera = _button_tokens(fields, kakera=True)
    spheres = _button_tokens(fields, kakera=False)
    if kakera:
        parts.append(" ".join(kakera))
    if spheres:
        parts.append(" ".join(spheres))
    if fields.get("can_claim"):
        parts.append("unclaimed")
    elif fields.get("claimed") and fields.get("owner"):
        parts.append(f"belongs to {fields['owner']}")
    keys = fields.get("keys") or []
    if keys:
        key_text = _format_keys(keys)
        if key_text:
            parts.append(key_text)
    omega = fields.get("omega_keys") or []
    if omega:
        total = 0
        for entry in omega:
            if isinstance(entry, dict):
                try:
                    total += int(entry.get("gain") or 0)
                except (TypeError, ValueError):
                    continue
        if total:
            parts.append(f":omegakey: +{total}")
    limit = fields.get("key_limit")
    if limit is not None:
        try:
            parts.append(f"❌ key limit {int(limit):,}/h")
        except (TypeError, ValueError):
            parts.append("❌ key limit reached")
    if fields.get("starwish"):
        parts.append(":starwish:")
    if fields.get("bku_reset"):
        try:
            parts.append(f":bku: +{int(fields.get('bku')):,}")
        except (TypeError, ValueError):
            parts.append(":bku:")
    elif fields.get("bku") is not None:
        parts.append(":bku:")
    wished = fields.get("wished_by")
    if wished:
        parts.append(f"wish×{len(wished)}")
    if fields.get("perk_6"):
        spawner = fields.get("spawned_by") or "?"
        parts.append(f"spawned by {spawner}")
    return " · ".join(parts)


def _severity_for(kind: MessageKind) -> str:
    if kind in {MessageKind.CLAIM, MessageKind.MARRIAGE}:
        return "claim"
    if kind in {MessageKind.KAKERA_CLAIM, MessageKind.SPHERE_CLICK}:
        return "click"
    if kind == MessageKind.KAKERA_REACT_DENIED:
        return "error"
    return "info"


def format_live_feed(
    snapshot: MudaeMessageSnapshot,
    parsed: ParseResult,
) -> tuple[str, str] | None:
    """Return ``(text, severity)`` for the Run feed, or ``None`` to skip.

    Edited roll embeds (ownership footer updates) are skipped so a claim does
    not reprint the character card.
    """
    if parsed.kind == MessageKind.ROLL:
        if snapshot.edited:
            return None
        text = format_roll_line(parsed.fields)
        if not text:
            return None
        return text, _severity_for(parsed.kind)
    if parsed.kind not in _CONTENT_KINDS:
        return None
    text = flatten_discord_text(snapshot.content or "")
    if not text:
        text = (parsed.summary or "").strip()
    if not text:
        return None
    return text, _severity_for(parsed.kind)
