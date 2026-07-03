"""Parse Mudae kakera claim lines and embed kakera values."""

from __future__ import annotations

import re
from typing import Any

from mudae.constants import KAKERA_INFO
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

# kakera[A-Z]? already matches every single-letter variant (kakeraC, kakeraD,
# kakeraP, kakeraT, kakeraG, kakeraL, kakeraW, kakeraR, kakeraO, kakeraY) plus
# the bare ``kakera`` (blue / default).
_KAKERA_EMOJI_RE = re.compile(
    r"<:(kakera[A-Z]?):\d+>",
    re.IGNORECASE,
)
# ``**user +5,934** ($k)`` or ``=> **user +5,934** ($k)`` or ``User +546 ($k)``
_CLAIM_TAIL_PATTERNS = (
    re.compile(
        r"(?:=>\s*)?\*\*([^*]+?)\s*\+([\d,]+)\*\*\s*\(\$k\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:=>\s*)?([^\s+]+)\s*\+([\d,]+)\s*\(\$k\)",
        re.IGNORECASE,
    ),
)


def _parse_spheres_from_claim(content: str) -> int | None:
    """Spheres gained on this click, e.g. ``($k) **+46** <:sp:...>``."""
    clean = strip_markdown(content)
    lower = clean.lower()
    idx = lower.find("($k)")
    chunk = clean[idx + 4 :] if idx >= 0 else clean
    match = re.search(
        r"\+([\d,]+)\s*<:sp:",
        chunk,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _parse_source_kakera_type(content: str) -> str | None:
    """Clicked kakera — for white/light, the type before ``breaks down into``."""
    lower = content.lower()
    if "breaks down into" in lower:
        head = re.split(r"breaks down into", content, maxsplit=1, flags=re.IGNORECASE)[0]
        match = _KAKERA_EMOJI_RE.search(head)
        if match:
            return match.group(1)
    match = _KAKERA_EMOJI_RE.search(content)
    if match:
        return match.group(1)
    for k_type, info in KAKERA_INFO.items():
        if info["emoji"] in content:
            return k_type
    return None


def _parse_claim_tail(content: str) -> tuple[str | None, int | None]:
    """Username and total from the ``user +N ($k)`` tail (after ``=>`` on breakdowns)."""
    for text in (content, strip_markdown(content)):
        for pattern in _CLAIM_TAIL_PATTERNS:
            match = pattern.search(text)
            if match:
                user = match.group(1).strip()
                amount = int(match.group(2).replace(",", ""))
                return user, amount
    return None, None


def parse_kakera_claim(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {}

    fields["earn_method"] = "kakera_click"

    kakera_type = _parse_source_kakera_type(content)
    if kakera_type:
        fields["kakera_type"] = kakera_type

    claimed_by, amount = _parse_claim_tail(content)
    if amount is not None:
        fields["amount"] = amount
    if claimed_by:
        fields["claimed_by"] = claimed_by

    spheres = _parse_spheres_from_claim(content)
    if spheres is not None:
        fields["spheres"] = spheres

    if amount is None:
        return ParseResult(
            kind=MessageKind.KAKERA_CLAIM,
            summary="Kakera claim (unparsed)",
            fields=fields,
            warnings=["Could not parse +N ($k) amount"],
        )
    if not claimed_by:
        warnings.append("Could not extract username from kakera line")

    summary = f"Kakera claim · {kakera_type or 'kakera'} · +{amount} · {claimed_by or '?'}"
    if spheres is not None:
        summary += f" · +{spheres} sp"
    return ParseResult(
        kind=MessageKind.KAKERA_CLAIM,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def parse_kakera_value(description: str) -> int:
    if not description:
        return 0
    match = re.search(
        r"\*{0,2}(\d{1,3}(?:,\d{3})*|\d+)\*{0,2}\s*(?:<:kakera:|:kakera:|kakera)",
        description,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def parse_individual_kakera(description: str) -> dict[str, int]:
    if not description:
        return {}
    kakera_map: dict[str, int] = {}
    pattern = (
        r"\*{0,2}(\d{1,3}(?:,\d{3})*|\d+)\*{0,2}\s*"
        r"<:(kakera[A-Z]?):\d+>"
    )
    for match in re.finditer(pattern, description, re.IGNORECASE):
        try:
            kakera_map[match.group(2)] = int(match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            continue
    return kakera_map


def parse_keys(description: str) -> list[dict[str, Any]]:
    if not description:
        return []
    keys: list[dict[str, Any]] = []
    pattern = r"<:(bronze|silver|gold|chaos)key:\d+>\s*\(\*{0,2}(\d+)\*{0,2}\)"
    for match in re.finditer(pattern, description, re.IGNORECASE):
        keys.append({"type": match.group(1).lower(), "level": int(match.group(2))})
    return keys


def parse_omega_keys(description: str) -> list[dict[str, Any]]:
    """Omega keys gained on this roll, e.g. ``<:omegakey:...> **+1**``."""
    if not description:
        return []
    keys: list[dict[str, Any]] = []
    pattern = r"<:omegakey:\d+>\s*\*{0,2}\+?([\d,]+)\*{0,2}"
    for match in re.finditer(pattern, description, re.IGNORECASE):
        keys.append({"gain": int(match.group(1).replace(",", ""))})
    return keys
