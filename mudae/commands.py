"""Command aliases and response-based command detection."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mudae.types import MudaeMessageSnapshot

# All Mudae roll commands (short and long forms) -> canonical parser id "roll".
ROLL_COMMAND_ALIASES: dict[str, str] = {
    "waifu": "roll",
    "w": "roll",
    "wx": "roll",
    "waifua": "roll",
    "wa": "roll",
    "waifug": "roll",
    "wg": "roll",
    "waifub": "roll",
    "wb": "roll",
    "husbando": "roll",
    "h": "roll",
    "hx": "roll",
    "husbandoa": "roll",
    "ha": "roll",
    "husbandog": "roll",
    "hg": "roll",
    "husbandob": "roll",
    "hb": "roll",
    "marry": "roll",
    "m": "roll",
    "mx": "roll",
    "marrya": "roll",
    "ma": "roll",
    "marryg": "roll",
    "mg": "roll",
    "marryb": "roll",
    "mb": "roll",
}

# Alternate spellings -> canonical parser id.
COMMAND_ALIASES: dict[str, str] = {
    "setting": "settings",
    "sets": "settings",
    "bonuses": "bonus",
    **ROLL_COMMAND_ALIASES,
}

# (canonical parser id, detector)
ResponseDetector = Callable[[str], bool]

_TU_HAS_ROLLS_RE = re.compile(r"rolls?.*(?:left|restantes)", re.IGNORECASE)
_TU_HAS_CLAIM_RE = re.compile(
    r"(?:you __can__|can't claim|você __pode__|calma aí)",
    re.IGNORECASE,
)


def is_roll_command(command: str) -> bool:
    return normalize_command(command) == "roll"


def is_settings_response(content: str) -> bool:
    if not content:
        return False
    lower = content.lower()
    if "server settings" not in lower:
        return False
    return (
        "($prefix)" in lower
        or "prefix:" in lower
        or "($setclaim)" in lower
        or "claim reset:" in lower
    )


def is_bonus_response(content: str) -> bool:
    if not content:
        return False
    lower = content.lower()
    return (
        "($bk)" in lower
        or "additional bonus for kakera buttons" in lower
        or "<:morekakera:" in lower
    )


def is_shop_response(content: str) -> bool:
    from mudae.parsers.shop import is_shop_response as _is_shop

    return _is_shop(content)


def is_us_response(content: str) -> bool:
    if not content:
        return False
    return "rolls stacked" in content.lower()


def is_ohu_response(content: str) -> bool:
    from mudae.parsers.ohu import is_ohu_response as _is_ohu

    return _is_ohu(content)


def is_ohu8_response(content: str) -> bool:
    from mudae.parsers.ohu8 import is_ohu8_response as _is_ohu8

    return _is_ohu8(content)


def is_ku_response(content: str) -> bool:
    from mudae.parsers.reaction_power import is_ku_response as _is_ku

    return _is_ku(content)


def is_tu_response(content: str) -> bool:
    if not content:
        return False
    lower = content.lower()
    has_rolls = bool(_TU_HAS_ROLLS_RE.search(lower))
    has_claim = bool(_TU_HAS_CLAIM_RE.search(lower))
    return has_rolls and has_claim


def is_roll_response(snapshot: MudaeMessageSnapshot) -> bool:
    from mudae.parsers.embed import is_character_embed

    if not snapshot.embeds:
        return False
    return is_character_embed(snapshot.embeds[0])


RESPONSE_DETECTORS: list[tuple[str, ResponseDetector]] = [
    ("bonus", is_bonus_response),
    ("settings", is_settings_response),
    ("shop", is_shop_response),
    ("tu", is_tu_response),
    ("ku", is_ku_response),
    ("us", is_us_response),
    ("ohu", is_ohu_response),
    ("ohu8", is_ohu8_response),
]


def normalize_command(command: str) -> str:
    """Map user-typed command to canonical parser id when known."""
    key = command.lower()
    return COMMAND_ALIASES.get(key, key)


def detect_command_from_response(content: str) -> str | None:
    """Guess which $command produced this Mudae message (text heuristics)."""
    for command_id, detector in RESPONSE_DETECTORS:
        if detector(content):
            return command_id
    return None


def detect_command_from_snapshot(
    snapshot: MudaeMessageSnapshot,
    *,
    user_input: str | None = None,
) -> str | None:
    """Guess command from embed/component shape when a user $command was sent."""
    from mudae.message_text import snapshot_visible_text

    if user_input and is_roll_response(snapshot):
        return "roll"
    return detect_command_from_response(snapshot_visible_text(snapshot))


@dataclass(frozen=True)
class ResolvedCommand:
    """How to label and parse a Mudae command response."""

    display: str
    parser: str | None
    user_input: str | None
    detected: str | None
    part: int = 1
    parts: int = 1

    @property
    def response_label(self) -> str:
        from mudae.command_context import response_label as make_label

        return make_label(self.display, part=self.part, parts=self.parts)


def resolve_command(
    user_input: str | None,
    content: str,
    *,
    known_parsers: set[str],
    snapshot: MudaeMessageSnapshot | None = None,
) -> ResolvedCommand | None:
    """
    Combine what the user typed with what the response content suggests.

    - User alias ($wa) can map to parser id (roll).
    - Unknown user command + known response shape -> use detected parser.
    - No user command + known response -> treat as detected command.
    """
    detected = (
        detect_command_from_snapshot(snapshot, user_input=user_input)
        if snapshot is not None
        else detect_command_from_response(content)
    )
    user_canonical = normalize_command(user_input) if user_input else None

    parser: str | None = None
    if user_canonical and user_canonical in known_parsers:
        parser = user_canonical
    elif detected and detected in known_parsers:
        parser = detected
    elif user_canonical:
        parser = user_canonical
    elif detected:
        parser = detected

    if not user_input and not detected and not parser:
        return None

    display = user_input or detected or parser or "unknown"
    return ResolvedCommand(
        display=display,
        parser=parser,
        user_input=user_input,
        detected=detected,
    )
