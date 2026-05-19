"""Parse Mudae claim confirmations (marriage, customized text, kakera bonuses)."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

_KAKERA_BONUS_RE = re.compile(
    r"\*\*\+([\d,]+)\*\*(?:<:kakera:|:kakera:)([^<\n]*)",
    re.IGNORECASE,
)
_SKIP_LINE_RE = re.compile(
    r"(?:<:kakera:|:kakera:|<:sp:|default kakera value)",
    re.IGNORECASE,
)


def parse_claim_kakera(content: str) -> tuple[int | None, list[dict[str, Any]]]:
    """Sum all claim kakera lines (e.g. Emerald + Bronze wish bonuses)."""
    bonuses: list[dict[str, Any]] = []
    for match in _KAKERA_BONUS_RE.finditer(content):
        amount = int(match.group(1).replace(",", ""))
        label = (match.group(2) or "").strip()
        if label.startswith("("):
            label = label[1:]
        if label.endswith(")"):
            label = label[:-1]
        bonuses.append({"amount": amount, "label": label.strip() or None})

    if bonuses:
        return sum(entry["amount"] for entry in bonuses), bonuses

    clean = strip_markdown(content)
    fallback: list[dict[str, Any]] = []
    for match in re.finditer(
        r"\+([\d,]+)\s*(?:<:kakera:|:kakera:)([^<\n]*)",
        clean,
        re.IGNORECASE,
    ):
        amount = int(match.group(1).replace(",", ""))
        label = (match.group(2) or "").strip().strip("()")
        fallback.append({"amount": amount, "label": label or None})
    if fallback:
        return sum(entry["amount"] for entry in fallback), fallback
    return None, []


def _parse_claim_spheres(content: str) -> int | None:
    match = re.search(
        r"\+\s*\*{0,2}([\d,]+)\*{0,2}\s*<:sp:",
        content,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def is_marriage_claim(content: str) -> bool:
    lower = (content or "").lower()
    return "are now married" in lower or "casaram" in lower


def extract_claim_names(content: str) -> list[str]:
    """Bold names in claim prose (excludes kakera/sphere bonus lines)."""
    if not content:
        return []
    names: list[str] = []
    for line in content.splitlines():
        if not line.strip() or _SKIP_LINE_RE.search(line):
            continue
        for match in re.finditer(r"\*\*([^*]+)\*\*", line):
            text = match.group(1).strip()
            if not text or text.startswith("+"):
                continue
            if re.fullmatch(r"[\d,.]+", text):
                continue
            names.append(text)
    return names


def is_custom_claim(content: str) -> bool:
    """Custom claim text: any wording, as long as username and character are present."""
    if not content or is_marriage_claim(content):
        return False
    return len(extract_claim_names(content)) >= 2


def _parse_claim_participants(content: str) -> tuple[str | None, str | None]:
    marriage = re.search(
        r"(?:💖\s*)?(.*?)\s+and\s+(.*?)\s+are now married",
        content,
        re.IGNORECASE,
    )
    if marriage:
        return (
            strip_markdown(marriage.group(1)).strip(),
            strip_markdown(marriage.group(2)).strip(),
        )

    names = extract_claim_names(content)
    if len(names) >= 2:
        return names[0], names[1]
    return None, None


def parse_claim(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {}

    winner, character = _parse_claim_participants(content)
    if winner:
        fields["winner"] = winner
    if character:
        fields["character"] = character
    if not winner or not character:
        warnings.append("Could not parse claim participants")

    kakera, bonuses = parse_claim_kakera(content)
    if kakera is not None:
        fields["kakera"] = kakera
    if bonuses:
        fields["kakera_bonuses"] = bonuses

    spheres = _parse_claim_spheres(content)
    if spheres is not None:
        fields["spheres"] = spheres

    winner_label = fields.get("winner", "?")
    character_label = fields.get("character", "?")
    if is_marriage_claim(content):
        summary = f"Marriage · {winner_label} + {character_label}"
        kind = MessageKind.MARRIAGE
    else:
        summary = f"Claim · {winner_label} → {character_label}"
        kind = MessageKind.CLAIM

    if kakera is not None:
        summary += f" · +{kakera} kakera"
    if spheres is not None:
        summary += f" · +{spheres} sp"
    return ParseResult(
        kind=kind,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
