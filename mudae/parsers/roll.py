"""Parse Mudae roll command responses (character embeds)."""

from __future__ import annotations

import re
from typing import Any

from mudae.buttons import format_button, is_claim_button, is_sphere_button
from mudae.parsers.embed import (
    get_character_owner,
    has_claim_option,
    is_character_embed,
    is_ownership_footer,
)
from mudae.parsers.kakera import parse_keys, parse_omega_keys
from mudae.soulmate_log import record_new_soulmate
from mudae.parsers.utils import strip_discord_emojis, strip_markdown
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_SERIES_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*\s*·")
_CLAIMS_RANK_RE = re.compile(r"Claims:\s*#([\d,]+)", re.IGNORECASE)
_LIKES_RANK_RE = re.compile(r"Likes:\s*#([\d,]+)", re.IGNORECASE)
_STARWISH_RE = re.compile(r"<:sw:", re.IGNORECASE)
_NEW_SOULMATE_RE = re.compile(
    r"now your\s+\*{0,2}soulmate\*{0,2}!?",
    re.IGNORECASE,
)
_SPAWNED_BY_RE = re.compile(r"\[SPAWNED BY\s+([^\]]+)\]", re.IGNORECASE)
_PERK8_HEAD_DIGIT_RE = re.compile(r"^\d")
_PERK8_HALF_RE = re.compile(r"/\s*2(?:\s|\u200b|$)")
_MENTION_RE = re.compile(r"<@!?(\d+)>")
_ROLLS_LEFT_WARNING_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*|\d+)\s+rolls?\s+left",
    re.IGNORECASE,
)
_BELONGS_SPLIT_RE = re.compile(
    r"\s*·\s*(?=belongs to|pertence a)",
    re.IGNORECASE,
)
_FOOTER_SPHERE_PREFIX_RE = re.compile(r"^(\d{1,3}(?:,\d{3})*|\d+)")
_SPHERE_VALUE_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*|\d+)\s*<:sp:",
    re.IGNORECASE,
)
_BKU_RESET_AMOUNT_RE = re.compile(r"\*\*\+([\d,]+)\*\*")

# Fields exposed for roll part 1 (stats only — no raw embed blobs).
ROLL_FIELD_KEYS: tuple[str, ...] = (
    "character_name",
    "series",
    "starwish",
    "new_soulmate",
    "bku",
    "bku_reset",
    "total_kakera",
    "spheres",
    "perk_8",
    "perk_6",
    "spawned_by",
    "rolls_left",
    "wished_by",
    "has_sphere_button",
    "keys",
    "omega_keys",
    "claimed",
    "owner",
    "can_claim",
    "claim_rank",
    "like_rank",
    "has_claim_button",
    "buttons",
)

OWNERSHIP_FIELD_KEYS: tuple[str, ...] = (
    "character_name",
    "claimed",
    "owner",
)


def _empty_roll_fields() -> dict[str, Any]:
    return {key: None for key in ROLL_FIELD_KEYS}


def _parse_series(description: str) -> str | None:
    """First description line is the series (may match character name on some rolls)."""
    lines = [line for line in description.splitlines() if line.strip()]
    if not lines:
        return None

    first = lines[0]
    series_bold = _SERIES_BOLD_RE.match(first)
    if series_bold:
        return series_bold.group(1).strip()

    plain = strip_discord_emojis(strip_markdown(first)).strip()
    return plain or None


def _parse_rank(description: str, label: str) -> int | None:
    if label == "Claims":
        match = _CLAIMS_RANK_RE.search(description)
    elif label == "Likes":
        match = _LIKES_RANK_RE.search(description)
    else:
        match = None
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _is_starwish(description: str) -> bool:
    return bool(_STARWISH_RE.search(description))


def _is_new_soulmate(description: str) -> bool:
    """True when chaos keys just hit 10 — ``Now your **SOULMATE**!`` on this roll."""
    return bool(_NEW_SOULMATE_RE.search(description))


def _is_profile_embed(description: str) -> bool:
    """``$pr`` profile embed — inventory totals, not a roll."""
    lower = (description or "").lower()
    return "collection size:" in lower or "mudapins:" in lower


def _parse_perk_6_spawn(description: str) -> tuple[bool, str | None]:
    """Perk 6 extra spawn — ``[SPAWNED BY Name]`` in description (often after ``<:spG:...>``)."""
    match = _SPAWNED_BY_RE.search(description)
    if not match:
        return False, None
    spawner = strip_markdown(match.group(1)).strip()
    return True, spawner or None


def normalize_character_name(name: str | None) -> str:
    """Case-insensitive compare helper for roll / spawn names."""
    if not name:
        return ""
    return strip_markdown(str(name)).strip().lower()


def perk6_spawner_matches(spawned_by: str | None, parent_name: str | None) -> bool:
    """True when ``spawned_by`` refers to the character that was just rolled."""
    spawned = normalize_character_name(spawned_by)
    parent = normalize_character_name(parent_name)
    return bool(spawned and parent and spawned == parent)


def _has_perk_8(footer: str) -> bool:
    """Perk 8: half-power kakera — footer shows ``💎/2`` before belongs."""
    if not footer:
        return False
    head = footer[:24]
    if _PERK8_HEAD_DIGIT_RE.match(head):
        return False
    return bool(_PERK8_HALF_RE.search(head))


def _parse_wished_by(content: str) -> list[int]:
    """User IDs pinged after ``Wished by`` when a wishlist character drops."""
    if not content:
        return []
    idx = content.lower().find("wished by")
    if idx < 0:
        return []
    chunk = content[idx:]
    ids: list[int] = []
    seen: set[int] = set()
    for match in _MENTION_RE.finditer(chunk):
        user_id = int(match.group(1))
        if user_id not in seen:
            seen.add(user_id)
            ids.append(user_id)
    return ids


def _parse_rolls_left_warning(footer: str) -> int | None:
    """Low-roll warning in footer, e.g. ``⚠️ 2 ROLLS LEFT ⚠️``."""
    if not footer:
        return None
    match = _ROLLS_LEFT_WARNING_RE.search(footer)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _parse_spheres_from_footer(footer: str) -> int | None:
    """Custom footers often lead with sphere count, e.g. ``23🔴 ☑️ · Belongs to ...``."""
    if not footer or _has_perk_8(footer):
        return None

    prefix = footer
    belongs_split = _BELONGS_SPLIT_RE.split(footer, maxsplit=1)
    if len(belongs_split) > 1:
        prefix = belongs_split[0].strip()

    match = _FOOTER_SPHERE_PREFIX_RE.match(prefix)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _parse_spheres(description: str, footer: str = "") -> int | None:
    """Sphere value on roll — description ``9<:sp:...>`` or leading digits in footer."""
    for text in (description, footer):
        if not text:
            continue
        match = _SPHERE_VALUE_RE.search(text)
        if match:
            return int(match.group(1).replace(",", ""))

    return _parse_spheres_from_footer(footer)


_KAKERA_LINE_RE = re.compile(
    r"\*\*(\+?)([\d,]+)\*\*\s*(?:<:kakera:|:kakera:|kakera)",
    re.IGNORECASE,
)


def _parse_roll_kakera(
    description: str,
) -> tuple[int | None, int | None, bool]:
    """Parse bku gain, character total, and whether $bku completed + reset fired.

    - Reset: ``$bku completed`` block with ``**+17,760**`` (bku payout); total is the
      final plain ``**13,781**`` line after claims/likes.
    - No reset: character kakera shows as ``**+197**`` (gained from remaining bku pool).
    """
    lower = description.lower()
    bku_reset = "$bku completed" in lower

    plus_amounts: list[int] = []
    plain_amounts: list[int] = []
    for match in _KAKERA_LINE_RE.finditer(description):
        amount = int(match.group(2).replace(",", ""))
        if match.group(1) == "+":
            plus_amounts.append(amount)
        else:
            plain_amounts.append(amount)

    bku: int | None = None
    if bku_reset:
        idx = lower.find("$bku completed")
        reset_match = _BKU_RESET_AMOUNT_RE.search(description[idx:])
        if reset_match:
            bku = int(reset_match.group(1).replace(",", ""))
    elif plus_amounts:
        bku = plus_amounts[0]

    if plain_amounts:
        total = plain_amounts[-1]
    elif bku is not None:
        total = bku
    else:
        total = None

    return bku, total, bku_reset


def _format_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not buttons:
        return []
    return [format_button(btn) for btn in buttons]


def _claim_button_available(buttons: list[dict[str, Any]]) -> bool:
    return any(
        is_claim_button(btn) and not bool(btn.get("disabled", False))
        for btn in buttons
    )


def parse_roll(
    snapshot: MudaeMessageSnapshot,
    *,
    part: int = 1,
    parts: int = 1,
) -> ParseResult:
    warnings: list[str] = []
    fields = _empty_roll_fields()

    if not snapshot.embeds:
        warnings.append("Roll response has no embed")
        return ParseResult(
            kind=MessageKind.ROLL,
            summary="$roll · no embed",
            fields=fields,
            warnings=warnings,
        )

    embed = snapshot.embeds[0]
    if not is_character_embed(embed):
        warnings.append("Embed does not look like a character roll")

    description = embed.get("description") or ""
    footer = embed.get("footer") or ""
    character_name = embed.get("author") or None
    owner = get_character_owner(footer)
    claimed = owner is not None

    if _is_profile_embed(description):
        fields["is_profile"] = True

    fields["character_name"] = character_name
    fields["series"] = _parse_series(description)
    fields["starwish"] = _is_starwish(description)
    new_soulmate = _is_new_soulmate(description)
    fields["new_soulmate"] = True if new_soulmate else None
    bku, total_kakera, bku_reset = _parse_roll_kakera(description)
    fields["bku"] = bku
    fields["bku_reset"] = bku_reset if bku_reset else None
    fields["total_kakera"] = total_kakera
    fields["spheres"] = _parse_spheres(description, footer)
    fields["perk_8"] = True if _has_perk_8(footer) else None
    perk_6, spawned_by = _parse_perk_6_spawn(description)
    fields["perk_6"] = True if perk_6 else None
    fields["spawned_by"] = spawned_by
    rolls_left = _parse_rolls_left_warning(footer)
    fields["rolls_left"] = rolls_left

    wished_by = _parse_wished_by(snapshot.content)
    fields["wished_by"] = wished_by if wished_by else None

    keys = parse_keys(description)
    fields["keys"] = keys if keys else None

    omega_keys = parse_omega_keys(description)
    fields["omega_keys"] = omega_keys if omega_keys else None

    fields["claimed"] = claimed
    fields["owner"] = owner
    fields["claim_rank"] = _parse_rank(description, "Claims")
    fields["like_rank"] = _parse_rank(description, "Likes")

    buttons = _format_buttons(snapshot.buttons)
    fields["buttons"] = buttons if buttons else None
    fields["has_claim_button"] = has_claim_option(snapshot)
    fields["has_sphere_button"] = any(is_sphere_button(btn) for btn in snapshot.buttons)
    fields["can_claim"] = (not claimed) and _claim_button_available(snapshot.buttons)

    name = character_name or "Unknown"
    summary = f"$roll · {name}"
    if claimed and owner:
        summary += f" · claimed by {owner}"
    elif fields["can_claim"]:
        summary += " · unclaimed"
    if fields["total_kakera"] is not None:
        summary += f" · {fields['total_kakera']} kakera"
    if fields.get("spheres") is not None:
        summary += f" · {fields['spheres']} sp"
    if fields.get("perk_8"):
        summary += " · perk 8"
    if fields.get("perk_6"):
        summary += " · perk 6 spawn"
        if spawned_by:
            summary += f" by {spawned_by}"
        fields["is_perk_6_spawn"] = True
    if rolls_left is not None:
        summary += f" · {rolls_left} rolls left"
    if fields["series"]:
        summary += f" · {fields['series']}"
    if fields.get("starwish"):
        summary += " · starwish"
    if wished_by:
        summary += f" · wished by {len(wished_by)}"
    if new_soulmate:
        summary += " · new soulmate"
        if not snapshot.edited:
            record_new_soulmate(snapshot, fields)
    if fields.get("bku_reset"):
        summary += " · bku reset"
    elif fields.get("bku") is not None:
        summary += f" · bku +{fields['bku']}"
    if fields.get("omega_keys"):
        total_omega = sum(entry["gain"] for entry in fields["omega_keys"])
        summary += f" · omega +{total_omega}"
    if parts > 1:
        summary = f"$roll ({part}/{parts}) · {name}"

    return ParseResult(
        kind=MessageKind.ROLL,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def parse_roll_ownership(snapshot: MudaeMessageSnapshot) -> ParseResult:
    """Second roll message: footer updated with owner (often an edit)."""
    embed = snapshot.embeds[0] if snapshot.embeds else {}
    footer = embed.get("footer") or ""
    character_name = embed.get("author") or None
    owner = get_character_owner(footer)

    warnings: list[str] = []
    if footer and not is_ownership_footer(footer):
        warnings.append("Expected ownership footer on roll follow-up")
    if not owner:
        warnings.append("Could not parse owner from footer")

    fields: dict[str, Any] = {key: None for key in OWNERSHIP_FIELD_KEYS}
    fields["character_name"] = character_name
    fields["claimed"] = owner is not None
    fields["owner"] = owner
    if snapshot.edited:
        fields["via_embed_edit"] = True

    summary = f"Roll claimed · {character_name or '?'} → {owner or '?'}"
    if snapshot.edited:
        summary += " (embed edit)"
    return ParseResult(
        kind=MessageKind.ROLL_OWNERSHIP,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
