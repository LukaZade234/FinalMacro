"""Meaning catalog for Mudae ``$ov`` — the *player's* settings sheet.

``$ov`` is the account-side twin of ``$settings``: same bullet shape, same
``($command)`` suffix, but describing the player rather than the server. Its own
last two lines say so — "For your unlocked bonuses, see **$bonus**. For the
server settings, see **$settings**."

**Why this is a catalog and not a suffix scrape.** ``$settings`` can key a field
on the command in its suffix, because every command appears once. ``$ov`` cannot:
``($rdmimg)`` ends *three* different lines — random images, GIF/WebP, and custom
images are three toggles under one command name. Keying on the suffix alone
would collapse them and the parser would report whichever it saw last. So the
identity of a field here is the **key** below, resolved from the command when
that is unambiguous and from the printed label when it is not.

One field the app actually needs: ``persrare``. It is the ``N`` in the `$bw`
sweep's reroll correction (see ``docs/MUDAE_LOGIC.md``), one of two inputs that
page was asking the user to supply by hand.

``$persrare`` is a **multiplier** and its lowest setting is one, which Mudae
prints as ``none`` rather than ``x1`` because multiplying by one changes
nothing. It is stored as the integer and rendered back to Mudae's own wording,
so ``none`` on the page still means the model is running at ``N = 1`` rather
than at no value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OvMeaning:
    """One printed line of the sheet."""

    key: str
    label: str
    command: str
    section: str
    value_type: str  # bool | int | flags | text
    description: str


OV_MEANINGS: tuple[OvMeaning, ...] = (
    OvMeaning(
        "player_premium",
        "Player Premium",
        "",
        "meta",
        "int",
        "Player Premium tier, from the header rather than a bullet",
    ),
    OvMeaning(
        "persrare",
        "Rarity for owned characters",
        "$persrare",
        "spawns",
        "int",
        "Rarity multiplier on characters you own — the $bw sweep's N",
    ),
    OvMeaning(
        "wishdm",
        "Private wishes",
        "$wishdm",
        "privacy",
        "flags",
        "Whether each wish kind is hidden from the channel",
    ),
    OvMeaning(
        "kakeradm",
        "Kakera badge notifications",
        "$kakeradm",
        "privacy",
        "bool",
        "Kakera badge notifications",
    ),
    OvMeaning(
        "hideinfodisable",
        "Emoji for disabled characters",
        "$hideinfodisable",
        "privacy",
        "bool",
        "Emoji notification for disabled characters",
    ),
    OvMeaning(
        "togglemovepage",
        "Others may move pages",
        "$togglemovepage",
        "privacy",
        "bool",
        "Whether other users can page through your listings",
    ),
    OvMeaning(
        "toggleletters",
        "Letters on kakera / sphere buttons",
        "$toggleletters",
        "privacy",
        "bool",
        "Letters added next to kakera or sphere buttons, for yourself",
    ),
    OvMeaning(
        "disablepins",
        "Mudapins from kakeraloots",
        "$disablepins",
        "privacy",
        "bool",
        "Whether kakeraloots still yield mudapins",
    ),
    OvMeaning(
        "setfooter",
        "Roll footer",
        "$setfooter",
        "display",
        "bool",
        "Footer information on rolls",
    ),
    # Three toggles, one command. The label is the only thing separating them.
    OvMeaning(
        "rdmimg_random",
        "Random images",
        "$rdmimg",
        "display",
        "bool",
        "Random images for rolls",
    ),
    OvMeaning(
        "rdmimg_gif_webp",
        "GIFs and WebP",
        "$rdmimg",
        "display",
        "bool",
        "GIFs and WebP displayed when you roll",
    ),
    OvMeaning(
        "rdmimg_custom",
        "Custom images",
        "$rdmimg",
        "display",
        "bool",
        "Custom images displayed when you roll",
    ),
    OvMeaning(
        "imglink",
        "Image links",
        "$imglink",
        "display",
        "bool",
        "Image links for rolls",
    ),
    OvMeaning(
        "perstogglebutton",
        "Buttons under rolls",
        "$perstogglebutton",
        "display",
        "text",
        "Personal override of the server's $togglebutton",
    ),
    OvMeaning(
        "rollsleft",
        "Rolls-left message",
        "$rollsleft",
        "display",
        "text",
        "Where the rolls-left message is drawn",
    ),
    OvMeaning(
        "displaykeys",
        "Keys shown on rolls",
        "$displaykeys",
        "display",
        "bool",
        "Keys displayed when you roll a character you do not own",
    ),
    OvMeaning(
        "limroul",
        "Character pool limits",
        "$limroul",
        "display",
        "text",
        "Pointer to $limroul; the sheet prints no value of its own",
    ),
)

OV_FIELD_KEYS: tuple[str, ...] = tuple(m.key for m in OV_MEANINGS)

OV_SECTION_ORDER: tuple[str, ...] = ("meta", "spawns", "privacy", "display")
OV_SECTION_TITLES: dict[str, str] = {
    "meta": "Account",
    "spawns": "Spawns",
    "privacy": "Wishes and notifications",
    "display": "Roll display",
}

MEANING_BY_KEY: dict[str, OvMeaning] = {m.key: m for m in OV_MEANINGS}

_WS_RE = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """Lowercased, whitespace-collapsed, trailing punctuation gone."""
    return _WS_RE.sub(" ", str(label or "").strip().lower()).rstrip(":.")


# The label Mudae prints, in the wording of the live sheet, back to a key. Used
# only to separate lines that share a command; an unknown label still resolves
# through the command when that command is unique.
MEANING_BY_LABEL: dict[str, OvMeaning] = {
    normalize_label("Increased rarity for owned characters"): MEANING_BY_KEY["persrare"],
    normalize_label("Private wishes"): MEANING_BY_KEY["wishdm"],
    normalize_label("Kakera badges notifications"): MEANING_BY_KEY["kakeradm"],
    normalize_label("Emoji notification for disabled characters"): MEANING_BY_KEY[
        "hideinfodisable"
    ],
    normalize_label("Allow other users to move pages"): MEANING_BY_KEY["togglemovepage"],
    normalize_label(
        "Letters added next to kakera or spheres buttons for yourself"
    ): MEANING_BY_KEY["toggleletters"],
    normalize_label("Obtaining mudapins from kakeraloots"): MEANING_BY_KEY["disablepins"],
    normalize_label("Footer informations for rolls"): MEANING_BY_KEY["setfooter"],
    normalize_label("Random images for rolls"): MEANING_BY_KEY["rdmimg_random"],
    normalize_label("GIFs and WebP displayed when you roll"): MEANING_BY_KEY[
        "rdmimg_gif_webp"
    ],
    normalize_label("Custom images displayed when you roll"): MEANING_BY_KEY[
        "rdmimg_custom"
    ],
    normalize_label("Image links for rolls"): MEANING_BY_KEY["imglink"],
    normalize_label("Buttons added under rolls"): MEANING_BY_KEY["perstogglebutton"],
    normalize_label("Rolls left message displayed"): MEANING_BY_KEY["rollsleft"],
    normalize_label(
        "Keys displayed when you roll a character you don't own"
    ): MEANING_BY_KEY["displaykeys"],
    normalize_label("Character pool limits"): MEANING_BY_KEY["limroul"],
}


def _by_command() -> dict[str, tuple[OvMeaning, ...]]:
    out: dict[str, list[OvMeaning]] = {}
    for meaning in OV_MEANINGS:
        if meaning.command:
            out.setdefault(meaning.command.lstrip("$"), []).append(meaning)
    return {key: tuple(value) for key, value in out.items()}


MEANINGS_BY_COMMAND: dict[str, tuple[OvMeaning, ...]] = _by_command()


def empty_ov_fields() -> dict[str, Any]:
    """Every key, unset — a line Mudae did not print stays ``None``."""
    return {key: None for key in OV_FIELD_KEYS}


def format_persrare(value: Any) -> str:
    """Back to Mudae's own wording: ``1`` reads ``none``, ``2`` reads ``x2``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    number = int(value)
    return "none" if number <= 1 else f"x{number}"


def format_ov_value(key: str, value: Any) -> str:
    if value is None:
        return "—"
    if key == "persrare":
        return format_persrare(value)
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    if key == "wishdm" and isinstance(value, (list, tuple)):
        return " ".join(str(part) for part in value)
    return str(value)


def fields_to_ov_display_dict(fields: dict[str, Any]) -> dict[str, Any]:
    """GUI rows for a stored ``$ov`` sheet (same shape as $settings / $bonus)."""
    data = dict(fields or {})
    by_section: dict[str, list[dict[str, Any]]] = {}
    filled = 0
    for meaning in OV_MEANINGS:
        value = data.get(meaning.key)
        has_value = value is not None
        if has_value:
            filled += 1
        by_section.setdefault(meaning.section, []).append({
            "field": meaning.key,
            "label": meaning.label,
            "command": meaning.command if has_value else "",
            "display": format_ov_value(meaning.key, value),
            "has_value": has_value,
            "value": value,
        })
    sections: list[dict[str, Any]] = []
    for section in OV_SECTION_ORDER:
        rows = by_section.get(section)
        if rows:
            sections.append({
                "id": section,
                "title": OV_SECTION_TITLES.get(section, section),
                "rows": rows,
            })
    return {"sections": sections, "field_count": filled}
