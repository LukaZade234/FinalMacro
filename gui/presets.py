"""Named macro presets (MacroConfig payloads)."""

from __future__ import annotations

import re
from typing import Any

from macro.config import MacroConfig


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:48] or "preset"


class PresetStore:
    def __init__(self) -> None:
        self.presets: dict[str, MacroConfig] = {}
        self.default_preset_id: str = "default"
        self.active_preset_id: str = "default"

    def load_from_settings(self, data: dict[str, Any]) -> None:
        raw = data.get("presets") or {}
        self.presets = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(value, dict):
                    self.presets[str(key)] = MacroConfig.from_dict(value)

        legacy_macro = data.get("macro")
        if isinstance(legacy_macro, dict) and not self.presets:
            self.presets["default"] = MacroConfig.from_dict(legacy_macro)

        if not self.presets:
            self.presets["default"] = MacroConfig()

        self.default_preset_id = str(data.get("default_preset_id") or "default")
        if self.default_preset_id not in self.presets:
            self.default_preset_id = next(iter(self.presets))

        self.active_preset_id = str(data.get("active_preset_id") or self.default_preset_id)
        self._ensure_active_selection()

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            "presets": {key: cfg.to_dict() for key, cfg in self.presets.items()},
            "default_preset_id": self.default_preset_id,
            "active_preset_id": self.active_preset_id,
        }

    def to_client_dict(self) -> dict[str, Any]:
        return {
            "presets": [
                {"id": key, "name": key, "config": cfg.to_dict()}
                for key, cfg in self.presets.items()
            ],
            "default_preset_id": self.default_preset_id,
            "active_preset_id": self.active_preset_id,
        }

    def _ensure_active_selection(self) -> None:
        if self.active_preset_id not in self.presets:
            self.active_preset_id = self.default_preset_id
        if self.default_preset_id not in self.presets and self.presets:
            self.default_preset_id = next(iter(self.presets))

    def find_preset(self, preset_id: str) -> MacroConfig | None:
        return self.presets.get(preset_id)

    def active_preset(self) -> MacroConfig:
        preset = self.find_preset(self.active_preset_id)
        if preset is None:
            return MacroConfig()
        return preset

    def set_active(self, preset_id: str) -> None:
        if preset_id in self.presets:
            self.active_preset_id = preset_id

    def add_preset(self, name: str, *, copy_from: str | None = None) -> str:
        preset_id = _slugify(name)
        base = self.default_preset_id
        if copy_from and copy_from in self.presets:
            base = copy_from
        source = self.presets.get(base, MacroConfig())
        suffix = 1
        candidate = preset_id
        while candidate in self.presets:
            candidate = f"{preset_id}_{suffix}"
            suffix += 1
        self.presets[candidate] = MacroConfig.from_dict(source.to_dict())
        return candidate

    def remove_preset(self, preset_id: str) -> bool:
        if preset_id == self.default_preset_id or len(self.presets) <= 1:
            return False
        if preset_id not in self.presets:
            return False
        del self.presets[preset_id]
        if self.active_preset_id == preset_id:
            self.active_preset_id = self.default_preset_id
        return True

    def rename_preset(self, preset_id: str, new_name: str) -> str | None:
        if preset_id not in self.presets:
            return None
        new_id = _slugify(new_name)
        if new_id == preset_id:
            return preset_id
        suffix = 1
        candidate = new_id
        while candidate in self.presets and candidate != preset_id:
            candidate = f"{new_id}_{suffix}"
            suffix += 1
        self.presets[candidate] = self.presets.pop(preset_id)
        if self.default_preset_id == preset_id:
            self.default_preset_id = candidate
        if self.active_preset_id == preset_id:
            self.active_preset_id = candidate
        return candidate

    def update_preset(self, preset_id: str, config: MacroConfig) -> None:
        if preset_id in self.presets:
            self.presets[preset_id] = config
