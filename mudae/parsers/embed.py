"""Parse Mudae character embeds and ownership footers."""

from __future__ import annotations

import re
from typing import Any

from mudae.buttons import is_claim_button
from mudae.parsers.kakera import parse_individual_kakera, parse_keys, parse_kakera_value
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_OWNER_BOLD_RE = re.compile(
    r"(?:belongs to|pertence a)\s+\*\*(.+?)\*\*",
    re.IGNORECASE,
)
_OWNER_PLAIN_RE = re.compile(
    r"(?:belongs to|pertence a)\s+(.+)$",
    re.IGNORECASE,
)


def is_ownership_footer(footer: str) -> bool:
    lower = footer.lower()
    return "belongs to" in lower or "pertence a" in lower


def is_ownership_update_footer(footer: str) -> bool:
    """True when the footer is *only* the ownership line (claim-confirmation edit).

    Roll embeds of already-owned characters prefix the footer with key/sphere
    counts, e.g. ``(🔑27) · Belongs to X`` — those edits are still rolls, not
    ownership updates.
    """
    lower = footer.strip().lower()
    return lower.startswith("belongs to") or lower.startswith("pertence a")


def get_character_owner(footer: str) -> str | None:
    if not footer:
        return None
    match = _OWNER_BOLD_RE.search(footer)
    if match:
        return match.group(1).strip()
    match = _OWNER_PLAIN_RE.search(footer)
    if match:
        return match.group(1).strip()
    return None


def is_character_embed(embed: dict[str, Any]) -> bool:
    """Heuristic: Mudae roll embeds have author name + description body."""
    if not embed:
        return False
    author = embed.get("author") or ""
    description = embed.get("description") or ""
    if not author or not description:
        return False
    # Exclude obvious non-roll embeds (e.g. help menus with titles only)
    title = (embed.get("title") or "").lower()
    if title and "help" in title:
        return False
    return True


def has_claim_option(snapshot: MudaeMessageSnapshot) -> bool:
    return any(is_claim_button(btn) for btn in snapshot.buttons)


def count_chaos_keys(description: str) -> int:
    return sum(1 for key in parse_keys(description) if key["type"] == "chaos")


def parse_character_embed(snapshot: MudaeMessageSnapshot) -> ParseResult:
    from mudae.parsers.roll import parse_roll

    result = parse_roll(snapshot)
    return ParseResult(
        kind=MessageKind.CHARACTER_EMBED,
        summary=result.summary.replace("$roll", "Character", 1),
        fields=result.fields,
        warnings=result.warnings,
    )


def parse_ownership_update(snapshot: MudaeMessageSnapshot) -> ParseResult:
    embed = snapshot.embeds[0] if snapshot.embeds else {}
    footer = embed.get("footer") or ""
    owner = get_character_owner(footer)
    fields = {
        "character_name": embed.get("author"),
        "footer": footer,
        "claimed": owner is not None,
        "owner": owner,
    }
    summary = f"Ownership · {fields['character_name'] or '?'} → {owner or '?'}"
    return ParseResult(
        kind=MessageKind.OWNERSHIP_UPDATE,
        summary=summary,
        fields=fields,
        warnings=[] if owner else ["Could not parse owner from footer"],
    )
