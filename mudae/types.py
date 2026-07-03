"""Shared types for Mudae message capture and parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageKind(str, Enum):
    COMMAND = "command"
    COMMAND_RESPONSE = "command_response"
    SETTINGS = "settings"
    BONUS = "bonus"
    ROLL = "roll"
    ROLL_OWNERSHIP = "roll_ownership"
    TU = "tu"
    KAKERA_CLAIM = "kakera_claim"
    DK_CLAIM = "dk_claim"
    KAKERA_REACT_DENIED = "kakera_react_denied"
    SPHERE_CLICK = "sphere_click"
    MARRIAGE = "marriage"
    CLAIM = "claim"
    CLAIM_INTERVAL = "claim_interval"
    CHARACTER_EMBED = "character_embed"
    CLAIM_BUTTONS = "claim_buttons"
    KAKERA_BUTTONS = "kakera_buttons"
    OWNERSHIP_UPDATE = "ownership_update"
    CHANNEL = "channel"
    UNKNOWN = "unknown"


@dataclass
class MudaeMessageSnapshot:
    message_id: int
    channel_id: int
    channel_name: str
    guild_id: int | None
    guild_name: str | None
    author_id: int
    author_name: str
    is_mudae: bool
    content: str
    embeds: list[dict[str, Any]]
    buttons: list[dict[str, Any]]
    created_at: str
    edited: bool = False


@dataclass
class ParseResult:
    kind: MessageKind
    summary: str
    fields: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "summary": self.summary,
            "fields": self.fields,
            "warnings": self.warnings,
        }
