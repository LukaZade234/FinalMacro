"""Parse reaction power from ``$tu``, ``$ku``, and kakera-react denial lines."""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import parse_hours_minutes
from mudae.types import MessageKind, ParseResult

_KAKERA_REACT_DENIED_RE = re.compile(
    r"can't react to kakera for \*\*(?:(\d+)h\s*)?(\d+)\*\* min",
    re.IGNORECASE,
)
_POWER_PERCENT_RE = re.compile(r"power:\s*\*\*(\d+)%\*\*", re.IGNORECASE)
_POWER_CONSUMPTION_RE = re.compile(
    r"(?:each kakera reaction consumes|cada reação de kakera consume)\s*(\d+)%",
    re.IGNORECASE,
)
_DENIED_USER_RE = re.compile(r"\*\*([^*]+)\*\*")


def parse_reaction_power_fields(content: str) -> dict[str, Any]:
    """Extract power / kakera-react status shared by ``$tu`` and ``$ku``."""
    fields: dict[str, Any] = {}
    lower = (content or "").lower()

    power_match = _POWER_PERCENT_RE.search(lower)
    if power_match:
        fields["power_percent"] = int(power_match.group(1))

    consumption_match = _POWER_CONSUMPTION_RE.search(lower)
    if consumption_match:
        fields["power_consumption_percent"] = int(consumption_match.group(1))

    if "you __can__ react to kakera" in lower or (
        "você __pode__" in lower and "kakera" in lower
    ):
        fields["kakera_react_available"] = True
    else:
        kakera_wait = _KAKERA_REACT_DENIED_RE.search(lower)
        if kakera_wait:
            h, m = parse_hours_minutes(kakera_wait)
            fields["kakera_react_available"] = False
            fields["kakera_cooldown_minutes"] = h * 60 + m

    return fields


def is_ku_response(content: str) -> bool:
    if not content:
        return False
    lower = content.lower()
    if "($ku)" not in lower:
        return False
    return "power:" in lower or "can't react to kakera" in lower


def parse_ku(content: str) -> ParseResult:
    fields = parse_reaction_power_fields(content)
    summary_parts = ["$ku"]
    if (power := fields.get("power_percent")) is not None:
        summary_parts.append(f"power {power}%")
    if fields.get("kakera_react_available") is True:
        summary_parts.append("can react")
    elif fields.get("kakera_cooldown_minutes") is not None:
        summary_parts.append(f"react cd {fields['kakera_cooldown_minutes']}m")
    return ParseResult(
        kind=MessageKind.TU,
        summary=" · ".join(summary_parts),
        fields=fields,
    )


def is_kakera_react_denied(content: str) -> bool:
    if not content or "($k)" in content.lower():
        return False
    lower = content.lower()
    return "can't react to kakera" in lower and _KAKERA_REACT_DENIED_RE.search(lower) is not None


def parse_kakera_react_denied(content: str) -> ParseResult:
    fields: dict[str, Any] = {}
    lower = content.lower()
    match = _KAKERA_REACT_DENIED_RE.search(lower)
    if match:
        h, m = parse_hours_minutes(match)
        fields["kakera_cooldown_minutes"] = h * 60 + m
    user_match = _DENIED_USER_RE.match(content.strip())
    if user_match:
        fields["claimed_by"] = user_match.group(1).strip()
    cd = fields.get("kakera_cooldown_minutes")
    summary = f"Kakera react denied · wait {cd}m" if cd is not None else "Kakera react denied"
    return ParseResult(
        kind=MessageKind.KAKERA_REACT_DENIED,
        summary=summary,
        fields=fields,
    )
