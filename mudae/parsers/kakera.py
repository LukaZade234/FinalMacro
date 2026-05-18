"""Parse Mudae kakera claim lines and embed kakera values."""

from __future__ import annotations

import re
from typing import Any

from mudae.constants import KAKERA_INFO
from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult


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


def parse_kakera_claim(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {"raw_content": content}

    type_match = re.search(r":(kakera[A-Z]*):", content, re.IGNORECASE)
    if type_match:
        fields["kakera_type"] = type_match.group(1)
    else:
        for k_type, info in KAKERA_INFO.items():
            if info["emoji"] in content:
                fields["kakera_type"] = k_type
                break

    clean = strip_markdown(content)
    amount_match = re.search(r"\+([\d,]+)\s*\(\$k\)", clean, re.IGNORECASE)
    if not amount_match:
        return ParseResult(
            kind=MessageKind.KAKERA_CLAIM,
            summary="Kakera claim (unparsed)",
            fields=fields,
            warnings=["Could not parse +N ($k) amount"],
        )

    fields["amount"] = int(amount_match.group(1).replace(",", ""))
    spheres = _parse_spheres_from_claim(content)
    if spheres is not None:
        fields["spheres"] = spheres

    pre_match = clean[: amount_match.start()].strip()

    if "breaks down into" in pre_match:
        pre_match = pre_match.split("breaks down into")[-1].strip()

    pre_match = re.sub(r"^<a?:[\w~]+:\d+>", "", pre_match).strip()
    pre_match = re.sub(r"^:[\w~]+:", "", pre_match).strip()
    pre_match = re.sub(r"^=>", "", pre_match).strip()
    for info in KAKERA_INFO.values():
        if pre_match.startswith(info["emoji"]):
            pre_match = pre_match[len(info["emoji"]) :].strip()

    fields["claimed_by"] = pre_match.strip() or None
    if not fields["claimed_by"]:
        warnings.append("Could not extract username from kakera line")

    ktype = fields.get("kakera_type", "kakera")
    summary = f"Kakera claim · +{fields['amount']} · {fields.get('claimed_by') or '?'}"
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
        r"<:(kakera[A-Z]?|kakeraP|kakeraT|kakeraG|kakeraL|kakeraW|kakeraR|kakeraO|kakeraY):\d+>"
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
