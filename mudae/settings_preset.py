"""Mudae server settings preset model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MudaeSettingsPreset:
    id: str
    name: str
    description: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_from_channel_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MudaeSettingsPreset:
        tags = data.get("tags") or []
        raw_fields = data.get("fields") or {}
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or "Preset"),
            description=str(data.get("description") or ""),
            fields=dict(raw_fields) if isinstance(raw_fields, dict) else {},
            tags=[str(t) for t in tags if t],
            created_from_channel_id=(
                str(data["created_from_channel_id"])
                if data.get("created_from_channel_id")
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
