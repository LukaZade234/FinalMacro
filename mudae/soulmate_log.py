"""Persist new soulmate events for per-server statistics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mudae.types import MudaeMessageSnapshot

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "soulmate_log.json"
_events: list[dict[str, Any]] = []


def _load_disk_log() -> None:
    global _events
    if not _LOG_PATH.is_file():
        return
    try:
        raw = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if isinstance(raw, list):
        _events = [entry for entry in raw if isinstance(entry, dict)]


def _save_disk_log() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOG_PATH.write_text(json.dumps(_events, indent=2), encoding="utf-8")


def record_new_soulmate(
    snapshot: MudaeMessageSnapshot,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Append a soulmate event and return the stored entry."""
    entry = {
        "guild_id": snapshot.guild_id,
        "guild_name": snapshot.guild_name,
        "channel_id": snapshot.channel_id,
        "channel_name": snapshot.channel_name,
        "character_name": fields.get("character_name"),
        "series": fields.get("series"),
        "owner": fields.get("owner"),
        "time": snapshot.created_at,
        "message_id": snapshot.message_id,
    }
    _events.append(entry)
    _save_disk_log()
    return entry


def get_soulmate_events() -> list[dict[str, Any]]:
    return [dict(entry) for entry in _events]


def soulmates_by_guild() -> dict[str, list[dict[str, Any]]]:
    """Group logged soulmates by guild name (or id string)."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in _events:
        key = entry.get("guild_name") or str(entry.get("guild_id") or "unknown")
        grouped.setdefault(key, []).append(dict(entry))
    return grouped


_load_disk_log()
