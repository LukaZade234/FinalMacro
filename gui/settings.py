"""Persist app configuration (accounts, presets, targets, servers)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "settings.json"

_LEGACY_KEYS = frozenset({"token", "channel_id", "macro"})


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        with SETTINGS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(values: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    for key in _LEGACY_KEYS:
        values.pop(key, None)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(values, f, indent=2)


def save_app_settings(**fragments: dict[str, Any]) -> None:
    data = load_settings()
    for fragment in fragments.values():
        data.update(fragment)
    save_settings(data)
