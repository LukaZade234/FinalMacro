"""Classify Mudae messages before detailed parsing."""

from __future__ import annotations

import re

from mudae.buttons import is_claim_button, is_kakera_button
from mudae.commands import is_bonus_response, is_settings_response, is_tu_response
from mudae.parsers.claim_interval import is_claim_interval_message
from mudae.parsers.embed import is_character_embed, is_ownership_footer
from mudae.types import MessageKind, MudaeMessageSnapshot


def is_kakera_claim(content: str) -> bool:
    return bool(content and "+" in content and "($k)" in content.lower())


def is_marriage(content: str) -> bool:
    lower = content.lower()
    return "are now married" in lower or "casaram" in lower


def has_kakera_buttons(snapshot: MudaeMessageSnapshot) -> bool:
    return any(is_kakera_button(btn) for btn in snapshot.buttons)


def has_claim_buttons(snapshot: MudaeMessageSnapshot) -> bool:
    return any(is_claim_button(btn) for btn in snapshot.buttons)


def classify_message(snapshot: MudaeMessageSnapshot) -> MessageKind:
    content = snapshot.content or ""

    if snapshot.edited and snapshot.embeds:
        embed = snapshot.embeds[0]
        footer = (embed.get("footer") or "").lower()
        # Footer/key edits on a full roll embed are not a separate event.
        if is_ownership_footer(footer) and not is_character_embed(embed):
            return MessageKind.OWNERSHIP_UPDATE

    if is_bonus_response(content):
        return MessageKind.BONUS
    if is_settings_response(content):
        return MessageKind.SETTINGS
    if is_tu_response(content):
        return MessageKind.TU
    if is_kakera_claim(content):
        return MessageKind.KAKERA_CLAIM
    if is_marriage(content):
        return MessageKind.MARRIAGE
    if is_claim_interval_message(content):
        return MessageKind.CLAIM_INTERVAL

    if snapshot.embeds and is_character_embed(snapshot.embeds[0]):
        if has_kakera_buttons(snapshot):
            return MessageKind.KAKERA_BUTTONS
        if has_claim_buttons(snapshot):
            return MessageKind.CLAIM_BUTTONS
        return MessageKind.CHARACTER_EMBED

    if has_kakera_buttons(snapshot):
        return MessageKind.KAKERA_BUTTONS
    if has_claim_buttons(snapshot):
        return MessageKind.CLAIM_BUTTONS

    return MessageKind.UNKNOWN
