"""Persist connection fields between sessions."""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "settings.json"


def load_settings() -> dict[str, str]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        with SETTINGS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return {k: str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(values: dict[str, str]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(values, f, indent=2)
