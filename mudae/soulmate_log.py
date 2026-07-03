"""Persist new soulmate events with account and server context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mudae.account_context import (
    DEFAULT_ACCOUNT_NAME,
    defaults_from_store,
    main_account_defaults,
    resolve_log_account,
)
from mudae.types import MudaeMessageSnapshot

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "soulmate_log.json"
_events: list[dict[str, Any]] = []
_recording_account_id: str = ""
_recording_account_name: str = ""
_DEFAULT_ACCOUNT_NAME = DEFAULT_ACCOUNT_NAME


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


def set_recording_account(account_id: str, account_name: str) -> None:
    """Bind subsequent soulmate records to the running account."""
    global _recording_account_id, _recording_account_name
    _recording_account_id = str(account_id or "").strip()
    _recording_account_name = str(account_name or _DEFAULT_ACCOUNT_NAME).strip() or _DEFAULT_ACCOUNT_NAME


def clear_recording_account() -> None:
    set_recording_account("", _DEFAULT_ACCOUNT_NAME)


def enrich_entry(
    entry: dict[str, Any],
    *,
    account_by_id: dict[str, Any],
    main_account_id: str,
    main_account_name: str,
) -> dict[str, Any]:
    """Fill missing account fields; legacy rows assume the active/default account."""
    out = dict(entry)
    acc_id, acc_name, inferred = resolve_log_account(
        entry,
        account_by_id=account_by_id,
        default_account_id=main_account_id,
        default_account_name=main_account_name,
    )
    out["account_id"] = acc_id
    out["account_name"] = acc_name
    out["account_inferred"] = inferred
    if acc_id and acc_id in account_by_id:
        out["account_type"] = str(getattr(account_by_id[acc_id], "type", "Main") or "Main")
    else:
        out["account_type"] = str(entry.get("account_type") or "Main")
    return out


def record_new_soulmate(
    snapshot: MudaeMessageSnapshot,
    fields: dict[str, Any],
    *,
    account_id: str | None = None,
    account_name: str | None = None,
) -> dict[str, Any]:
    """Append a soulmate event and return the stored entry."""
    acc_id = str(account_id if account_id is not None else _recording_account_id).strip()
    acc_name = str(
        account_name if account_name is not None else _recording_account_name or _DEFAULT_ACCOUNT_NAME
    ).strip() or _DEFAULT_ACCOUNT_NAME
    entry = {
        "guild_id": snapshot.guild_id,
        "guild_name": snapshot.guild_name,
        "channel_id": snapshot.channel_id,
        "channel_name": snapshot.channel_name,
        "account_id": acc_id,
        "account_name": acc_name,
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


def events_for_client(accounts_store: Any) -> list[dict[str, Any]]:
    """Return soulmate rows enriched for the GUI (newest first)."""
    main_id, main_name, account_by_id = defaults_from_store(accounts_store)
    enriched = [
        enrich_entry(
            entry,
            account_by_id=account_by_id,
            main_account_id=main_id,
            main_account_name=main_name,
        )
        for entry in _events
    ]
    enriched.reverse()
    return enriched


def soulmates_by_guild() -> dict[str, list[dict[str, Any]]]:
    """Group logged soulmates by guild name (or id string)."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in _events:
        key = entry.get("guild_name") or str(entry.get("guild_id") or "unknown")
        grouped.setdefault(key, []).append(dict(entry))
    return grouped


_load_disk_log()
