"""Per-channel Mudae values remembered for later commands (e.g. $bonus uses $settings)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "channel_cache.json"
_settings_by_channel: dict[int, dict[str, Any]] = {}


def _load_disk_cache() -> None:
    global _settings_by_channel
    if not _CACHE_PATH.is_file():
        return
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        try:
            channel_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            _settings_by_channel[channel_id] = value


def _save_disk_cache() -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {str(channel_id): fields for channel_id, fields in _settings_by_channel.items()}
    _CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def remember_settings(channel_id: int, fields: dict[str, Any]) -> None:
    """Store parsed $settings fields for this channel (memory + disk)."""
    _settings_by_channel[channel_id] = dict(fields)
    _save_disk_cache()


def get_channel_settings(channel_id: int) -> dict[str, Any] | None:
    fields = _settings_by_channel.get(channel_id)
    return dict(fields) if fields else None


def get_setrolls(channel_id: int) -> int | None:
    fields = get_channel_settings(channel_id)
    if not fields:
        return None
    value = fields.get("setrolls")
    if value is None:
        return None
    return int(value)


_load_disk_cache()
