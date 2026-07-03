"""Classify Mudae messages before detailed parsing."""

from __future__ import annotations

import re

from mudae.buttons import is_claim_button, is_kakera_button
from mudae.commands import is_bonus_response, is_settings_response, is_tu_response
from mudae.parsers.claim import is_custom_claim, is_marriage_claim
from mudae.parsers.claim_interval import is_claim_interval_message
from mudae.parsers.dk import is_dk_claim
from mudae.parsers.reaction_power import is_kakera_react_denied
from mudae.parsers.sphere import is_sphere_click_message
from mudae.parsers.embed import (
    is_character_embed,
    is_ownership_footer,
    is_ownership_update_footer,
)
from mudae.types import MessageKind, MudaeMessageSnapshot


def is_kakera_claim(content: str) -> bool:
    return bool(content and "+" in content and "($k)" in content.lower())


def has_kakera_buttons(snapshot: MudaeMessageSnapshot) -> bool:
    return any(is_kakera_button(btn) for btn in snapshot.buttons)


def has_claim_buttons(snapshot: MudaeMessageSnapshot) -> bool:
    return any(is_claim_button(btn) for btn in snapshot.buttons)


def classify_message(snapshot: MudaeMessageSnapshot) -> MessageKind:
    content = snapshot.content or ""

    if snapshot.edited and snapshot.embeds:
        embed = snapshot.embeds[0]
        footer = embed.get("footer") or ""
        # A bare "Belongs to X" footer is a claim-confirmation edit; footers
        # with a prefix (key/sphere counts) are rolls of already-owned chars.
        if is_character_embed(embed) and is_ownership_update_footer(footer):
            return MessageKind.ROLL_OWNERSHIP
        if is_ownership_footer(footer) and not is_character_embed(embed):
            return MessageKind.OWNERSHIP_UPDATE

    if is_bonus_response(content):
        return MessageKind.BONUS
    if is_settings_response(content):
        return MessageKind.SETTINGS
    if is_tu_response(content):
        return MessageKind.TU
    if is_kakera_react_denied(content):
        return MessageKind.KAKERA_REACT_DENIED
    if is_dk_claim(content):
        return MessageKind.DK_CLAIM
    if is_kakera_claim(content):
        return MessageKind.KAKERA_CLAIM
    if is_sphere_click_message(content):
        return MessageKind.SPHERE_CLICK
    if is_marriage_claim(content):
        return MessageKind.MARRIAGE
    if is_custom_claim(content):
        return MessageKind.CLAIM
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
