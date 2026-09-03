"""Text-only Discord/Mudae mirror for the Run live feed.

The Run tab should read like the channel: Mudae's follow-up lines (``+$k``,
sphere clicks, claims) beneath the character cards the roll cycle logs as it
rolls them. Macro skip / filter / budget chatter stays out, and so does
everything else in the channel — a minigame someone plays by hand while the
macro is connected is not part of the run.

The message *kind* is not enough to decide that, because classification runs
on loose content heuristics: two bold names anywhere make a "claim", and a
sphere emoji beside an ``(n/m)`` fraction makes a "sphere click". Mudae prose
trips both — a ``$ou`` upgrade panel and a ``Syntax: $kakeracopy …`` reply
were mirrored into the feed dozens of times while the user was typing
commands by hand. So a follow-up is mirrored only when it **names the
connected account** (:func:`mudae.account_context.username_matches_own`),
which is the same test the statistics logs already apply before recording a
row, and edits are never mirrored at all: Mudae posts real follow-ups as new
messages, while an edit is a panel or a board being re-rendered, which is how
one manual upgrade session printed the same line twenty times.

Roll cards are the one line nobody is named on, so they cannot be attributed
this way at all, and they are not mirrored here. :func:`format_roll_line` is
called by the roll cycle for each card it rolls itself, after a button refresh
so the reacts are complete. A card the mirror would have added is therefore
either a duplicate of that one or a roll made by hand while the macro sat idle
— which is the same "the macro is not why Mudae said this" the account check
exists to catch.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from mudae.account_context import username_matches_own
from mudae.buttons import is_kakera_button, is_sphere_button
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Follow-up kinds are always channel text. Rolls are formatted from embed
# fields (Discord's character card), not from ``parsed.summary``.
#
# The value is the parsed field carrying the account name for that kind, and
# every one of these kinds has one: Mudae names the account in each line that
# is genuinely about it. Prose that names nobody has no such field, which is
# exactly what keeps it out of the feed.
_OWNER_FIELDS: dict[MessageKind, str] = {
    MessageKind.KAKERA_CLAIM: "claimed_by",
    MessageKind.SPHERE_CLICK: "claimed_by",
    MessageKind.KAKERA_REACT_DENIED: "claimed_by",
    MessageKind.CLAIM: "winner",
    MessageKind.MARRIAGE: "winner",
}
_CONTENT_KINDS = frozenset(_OWNER_FIELDS)


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


def names_own_account(
    parsed: ParseResult,
    own_usernames: Sequence[str],
) -> bool:
    """Whether a mirrored follow-up is about the connected account."""
    field = _OWNER_FIELDS.get(parsed.kind)
    if field is None:
        return False
    return username_matches_own(str(parsed.fields.get(field) or ""), own_usernames)


def format_live_feed(
    snapshot: MudaeMessageSnapshot,
    parsed: ParseResult,
    *,
    own_usernames: Sequence[str] = (),
) -> tuple[str, str] | None:
    """Return ``(text, severity)`` for the Run feed, or ``None`` to skip.

    ``own_usernames`` are the connected account's Discord names. Without them
    nothing is mirrored at all: an unattributable line is left out rather than
    printed on the chance that it belongs to us.
    """
    if snapshot.edited:
        # An edit is a re-render — a roll's ownership footer, a minigame board,
        # an upgrade panel being clicked through — never a new event. Mirroring
        # them reprinted one message once per click.
        return None
    if parsed.kind not in _CONTENT_KINDS:
        return None
    if not names_own_account(parsed, own_usernames):
        # Mudae did not name us, so either someone else did this or the message
        # is not the event it was classified as. Both are noise in a feed that
        # is meant to mirror our own run.
        return None
    if parsed.kind in {MessageKind.CLAIM, MessageKind.MARRIAGE} and not parsed.fields.get(
        "character"
    ):
        # A claim with no character in it is not a claim we recognised — the
        # bold-name heuristic also fires on Mudae's character-info embeds.
        return None
    # Only real channel text is mirrored. ``parsed.summary`` is macro-side
    # prose, so falling back to it printed lines like "Claim · ? → ?" for
    # messages whose text lives somewhere the parser never read.
    text = flatten_discord_text(snapshot.content or "")
    if not text:
        return None
    return text, _severity_for(parsed.kind)
