"""Persist app configuration locally in ``data/settings.json`` (gitignored).

This file is never committed; each machine keeps its own copy. Loaded on startup
and written by ``save_app_settings()`` from ``gui/bridge.py``. While the app is
running, ``AppBridge`` watches this file and reloads stores when it changes on
disk (external editor, sync tool, second instance, etc.).

Typical top-level keys:

- ``accounts`` — Discord tokens and account metadata
- ``presets`` / ``active_preset_id`` — macro roll/claim presets
- ``mudae_settings_presets`` / ``default_mudae_settings_preset_id`` — Mudae
  server ``$settings`` templates (Servers → Settings presets tab)
- ``servers`` / ``active_server_id`` / ``active_channel_id`` — server profiles;
  each channel may store fetched ``settings`` and ``bonus`` snapshots
- ``targets`` — per (account, channel) run bindings
"""

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
