"""Parse Mudae ``$limroul`` — the player's own character-pool limits.

``$ov``'s last bullet is ``· Character pool limits: see $limroul``, and this is
what it points at. The sheet is mostly help text; two lines carry data::

    $limroul 7000 7000 5000 5000
    ...
    Current $limroul: 2,000 $wa, 2,000 $ha, 2,000 $wg, 2,000 $hg
    Less popular characters you can roll:
    $topwa #2,000 (Global: #3,405) · $topha #2,000 (Global: #5,111)
    $topwg #2,000 (Global: #8,083) · $tophg #2,000 (Global: #11,077)

The ``Current`` line is the one the app needed: **how many different characters
each roulette can roll**, which is the `$bw` sweep's pool size — the input that
decides which `$bw` wins and that the page had been asking a person to guess.
The four roulettes can differ, because a lower limit than the server's ceiling
is itself an unlock ("Only Player Premium and kakeraloots/kakeratowers let you
use lower values"), so the sweep has to be told which roulette it is modelling
rather than assuming they agree.

The ceiling in the example command is the *server's* cap, the same figure
``$settings`` reports as ``servlimroul`` — kept so the two can be checked
against each other.

The ``$top…`` lines are the rank of the least popular character each roulette
still reaches, locally and globally. The gap between the two is the server's own
disable list: local #2,000 sitting at global #3,405 means 1,405 more popular
characters are disabled here.

Never sent automatically, like ``$ov``: it goes out only when a person asks.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.types import MessageKind, ParseResult

# The four roulettes, in the order Mudae always prints them.
ROULETTES: tuple[str, ...] = ("wa", "ha", "wg", "hg")

ROULETTE_LABELS: dict[str, str] = {
    "wa": "$wa — anime waifus",
    "ha": "$ha — anime husbandos",
    "wg": "$wg — game waifus",
    "hg": "$hg — game husbandos",
}

_CURRENT_RE = re.compile(r"current\s+\$limroul\s*:\s*(.+)", re.IGNORECASE)
_LIMIT_PAIR_RE = re.compile(r"([\d,]+)\s*\$(wa|ha|wg|hg)\b", re.IGNORECASE)
_SYNTAX_LIMITS_RE = re.compile(
    r"^\s*\$limroul\s+(\d[\d,]*)\s+(\d[\d,]*)\s+(\d[\d,]*)\s+(\d[\d,]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_TOP_RE = re.compile(
    r"\$top(wa|ha|wg|hg)\s*#\s*([\d,]+)\s*\(\s*global\s*:\s*#\s*([\d,]+)\s*\)",
    re.IGNORECASE,
)


def _int(text: str) -> int:
    return int(str(text).replace(",", "").strip())


def is_limroul_response(content: str) -> bool:
    """Mudae's ``$limroul`` reply.

    Anchored on the two lines that carry data rather than on the word alone:
    ``$limroul`` is named by ``$settings`` (as ``$servlimroul``) and by ``$ov``,
    and neither of those is this sheet.
    """
    if not content:
        return False
    lower = content.lower()
    if "current $limroul" in lower:
        return True
    return "syntax: $limroul" in lower and "$antidisable" in lower


def limits_agree(limits: dict[str, Any] | None) -> int | None:
    """The one pool size, when all four roulettes have the same limit.

    ``None`` when they differ — then which roulette is being modelled is a real
    question and something has to answer it, rather than a detail to average
    away.
    """
    values = [(limits or {}).get(key) for key in ROULETTES]
    if any(value is None for value in values):
        return None
    first = int(values[0])
    return first if all(int(value) == first for value in values) else None


def _parse_limits(line: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for amount, roulette in _LIMIT_PAIR_RE.findall(line):
        out[roulette.lower()] = _int(amount)
    return out


def parse_limroul(content: str) -> ParseResult:
    warnings: list[str] = []
    fields: dict[str, Any] = {
        "limits": None,
        "server_max": None,
        "tops": None,
        "limits_agree": None,
    }

    text = content or ""

    current = _CURRENT_RE.search(text)
    if current:
        limits = _parse_limits(current.group(1))
        missing = [key for key in ROULETTES if key not in limits]
        if missing:
            warnings.append(
                "Current $limroul is missing " + ", ".join(f"${key}" for key in missing)
            )
        if limits:
            fields["limits"] = limits
            fields["limits_agree"] = limits_agree(limits)
    else:
        warnings.append("No 'Current $limroul' line — pool sizes not read")

    # The example command is the server's ceiling, not the player's setting, so
    # it is read only from the bare four-number line and never from the prose.
    ceiling = _SYNTAX_LIMITS_RE.search(text)
    if ceiling:
        fields["server_max"] = {
            key: _int(ceiling.group(index + 1)) for index, key in enumerate(ROULETTES)
        }

    tops: dict[str, dict[str, int]] = {}
    for roulette, rank, global_rank in _TOP_RE.findall(text):
        tops[roulette.lower()] = {"rank": _int(rank), "global_rank": _int(global_rank)}
    if tops:
        fields["tops"] = tops

    return ParseResult(
        kind=MessageKind.LIMROUL,
        summary=_build_summary(fields),
        fields=fields,
        warnings=warnings,
    )


def _build_summary(fields: dict[str, Any]) -> str:
    limits = fields.get("limits") or {}
    if not limits:
        return "$limroul · no pool limits read"
    same = fields.get("limits_agree")
    if same is not None:
        return f"$limroul · {same:,} in every roulette"
    parts = [
        f"{limits[key]:,} ${key}" for key in ROULETTES if limits.get(key) is not None
    ]
    return "$limroul · " + ", ".join(parts)
