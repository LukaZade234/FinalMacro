"""Store named Mudae server settings presets (distinct from macro presets).

Persisted inside ``data/settings.json`` under ``mudae_settings_presets`` — see
``gui/settings.py`` (gitignored, local only).
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.settings_normalize import normalize_settings_fields
from mudae.settings_preset import MudaeSettingsPreset


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:48] or "mudae_preset"


class MudaeSettingsPresetStore:
    def __init__(self) -> None:
        self.presets: dict[str, MudaeSettingsPreset] = {}
        self.default_preset_id: str = ""

    def load_from_settings(self, data: dict[str, Any]) -> None:
        raw = data.get("mudae_settings_presets") or {}
        self.presets = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(value, dict):
                    preset = MudaeSettingsPreset.from_dict({"id": str(key), **value})
                    self.presets[preset.id] = preset
        self.default_preset_id = str(data.get("default_mudae_settings_preset_id") or "")
        self._ensure_default()

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            "mudae_settings_presets": {
                key: {
                    "name": preset.name,
                    "description": preset.description,
                    "fields": preset.fields,
                    "tags": preset.tags,
                    "created_from_channel_id": preset.created_from_channel_id,
                }
                for key, preset in self.presets.items()
            },
            "default_mudae_settings_preset_id": self.default_preset_id,
        }

    def to_client_dict(self) -> dict[str, Any]:
        return {
            "presets": [
                {
                    "id": preset.id,
                    "name": preset.name,
                    "description": preset.description,
                    "fields": preset.fields,
                    "tags": preset.tags,
                    "created_from_channel_id": preset.created_from_channel_id,
                }
                for preset in self.presets.values()
            ],
            "default_preset_id": self.default_preset_id,
        }

    def _ensure_default(self) -> None:
        if self.presets and self.default_preset_id not in self.presets:
            self.default_preset_id = next(iter(self.presets))
        if not self.presets:
            self.default_preset_id = ""

    def find(self, preset_id: str) -> MudaeSettingsPreset | None:
        return self.presets.get(preset_id)

    def add_preset(
        self,
        name: str,
        *,
        fields: dict[str, Any] | None = None,
        copy_from: str | None = None,
        created_from_channel_id: str | None = None,
    ) -> str:
        preset_id = _slugify(name)
        suffix = 1
        candidate = preset_id
        while candidate in self.presets:
            candidate = f"{preset_id}_{suffix}"
            suffix += 1
        source_fields: dict[str, Any] = {}
        if copy_from and copy_from in self.presets:
            source_fields = dict(self.presets[copy_from].fields)
        if fields is not None:
            source_fields = normalize_settings_fields(dict(fields))
        self.presets[candidate] = MudaeSettingsPreset(
            id=candidate,
            name=name.strip() or candidate,
            fields=source_fields,
            created_from_channel_id=created_from_channel_id,
        )
        if not self.default_preset_id:
            self.default_preset_id = candidate
        return candidate

    def remove_preset(self, preset_id: str) -> bool:
        if preset_id not in self.presets:
            return False
        if len(self.presets) <= 1:
            return False
        del self.presets[preset_id]
        if self.default_preset_id == preset_id:
            self.default_preset_id = next(iter(self.presets))
        return True

    def update_preset_fields(self, preset_id: str, fields: dict[str, Any]) -> bool:
        preset = self.find(preset_id)
        if preset is None:
            return False
        preset.fields = normalize_settings_fields(dict(fields))
        return True

    def rename_preset(self, preset_id: str, new_name: str) -> str | None:
        preset = self.find(preset_id)
        if preset is None:
            return None
        preset.name = new_name.strip() or preset.name
        return preset_id

    def set_default(self, preset_id: str) -> None:
        if preset_id in self.presets:
            self.default_preset_id = preset_id
