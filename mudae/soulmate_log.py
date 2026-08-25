"""Persist new soulmate events with account and server context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mudae.account_context import (
    UNKNOWN_ACCOUNT_NAME,
    defaults_from_store,
    resolve_log_account,
)
from mudae import event_log
from mudae.types import MudaeMessageSnapshot

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "soulmate_log.json"
_events: list[dict[str, Any]] = []
_recording_account_id: str = ""
_recording_account_name: str = ""


def _bind_events() -> None:
    global _events
    _events = event_log.events("soulmate")


def _load_disk_log() -> None:
    event_log.ensure_loaded()
    _bind_events()
    if _backfill_account_name_from_owner():
        event_log.mark_dirty(rewrite=True)
        event_log.flush()
        from mudae import stats_index

        stats_index.rebuild_kind("soulmate")


def _save_disk_log() -> None:
    event_log.mark_dirty(rewrite=True)
    event_log.flush()


def set_recording_account(account_id: str, account_name: str) -> None:
    """Bind subsequent soulmate records to the running account."""
    global _recording_account_id, _recording_account_name
    _recording_account_id = str(account_id or "").strip()
    _recording_account_name = str(account_name or "").strip()


def clear_recording_account() -> None:
    set_recording_account("", "")


def _placeholder_account_name(name: str) -> bool:
    return str(name or "").strip().lower() in {"", "default"}


def _backfill_account_name_from_owner() -> bool:
    """Copy ``owner`` onto rows that never stored which app account rolled them.

    Early soulmates were logged without ``account_id`` / ``account_name`` while
    the GUI profile was still called Default. The Mudae owner is the roller.
    """
    changed = False
    for entry in _events:
        stored = str(entry.get("account_name") or "").strip()
        if not _placeholder_account_name(stored):
            continue
        owner = str(entry.get("owner") or "").strip()
        if not owner:
            continue
        entry["account_name"] = owner
        changed = True
    return changed


def persist_legacy_account_ids(accounts_store: Any) -> int:
    """Match owner / account_name to a stored profile and write ``account_id``."""
    _main_id, _main_name, account_by_id = defaults_from_store(accounts_store)
    by_name = {
        str(getattr(acc, "name", "") or "").strip().lower(): acc
        for acc in account_by_id.values()
        if str(getattr(acc, "name", "") or "").strip()
    }
    updated = 0
    for entry in _events:
        stored_id = str(entry.get("account_id") or "").strip()
        stored_name = str(entry.get("account_name") or "").strip()
        owner = str(entry.get("owner") or "").strip()
        name = stored_name if not _placeholder_account_name(stored_name) else owner
        if not name:
            continue
        acc = by_name.get(name.lower())
        if acc is None:
            continue
        want_id = str(acc.id)
        want_name = str(acc.name)
        if stored_id == want_id and stored_name == want_name:
            continue
        entry["account_id"] = want_id
        entry["account_name"] = want_name
        updated += 1
    if updated:
        _save_disk_log()
        from mudae import stats_index

        stats_index.rebuild_kind("soulmate")
    return updated


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


def _normalize_character_name(name: str | None) -> str:
    if not name:
        return ""
    return str(name).strip().lower()


def _soulmate_identity(guild_id: int | None, character_name: str | None) -> tuple[str, str]:
    return (str(guild_id or ""), _normalize_character_name(character_name))


def _find_logged_soulmate(
    guild_id: int | None,
    character_name: str | None,
) -> dict[str, Any] | None:
    """Return an existing row for this character on this server, if any."""
    target = _soulmate_identity(guild_id, character_name)
    if not target[1]:
        return None
    for entry in reversed(_events):
        if _soulmate_identity(entry.get("guild_id"), entry.get("character_name")) == target:
            return dict(entry)
    return None


def record_new_soulmate(
    snapshot: MudaeMessageSnapshot,
    fields: dict[str, Any],
    *,
    account_id: str | None = None,
    account_name: str | None = None,
) -> dict[str, Any]:
    """Append a soulmate event and return the stored entry."""
    if snapshot.message_id:
        for entry in _events:
            if entry.get("message_id") == snapshot.message_id:
                return dict(entry)

    existing = _find_logged_soulmate(snapshot.guild_id, fields.get("character_name"))
    if existing is not None:
        return existing

    acc_id = str(account_id if account_id is not None else _recording_account_id).strip()
    acc_name = str(
        account_name
        if account_name is not None
        else _recording_account_name
        or fields.get("owner")
        or UNKNOWN_ACCOUNT_NAME
    ).strip() or UNKNOWN_ACCOUNT_NAME
    entry = {
        "guild_id": snapshot.guild_id,
        "guild_name": snapshot.guild_name,
        "channel_id": snapshot.channel_id,
        "channel_name": snapshot.channel_name,
        "account_id": acc_id,
        "account_name": acc_name,
        "character_name": fields.get("character_name"),
        "starwish": bool(fields.get("starwish")),
        "series": fields.get("series"),
        "owner": fields.get("owner"),
        "time": snapshot.created_at,
        "message_id": snapshot.message_id,
    }
    event_log.append("soulmate", entry)
    event_log.flush()
    return entry


def dedupe_stored_events() -> int:
    """Remove duplicate rows; keep the first entry per message and per server+character."""
    seen_messages: set[int] = set()
    seen_identities: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    removed = 0
    for entry in _events:
        message_id = entry.get("message_id")
        if message_id is not None:
            try:
                mid = int(message_id)
            except (TypeError, ValueError):
                mid = None
            if mid is not None and mid in seen_messages:
                removed += 1
                continue
        identity = _soulmate_identity(entry.get("guild_id"), entry.get("character_name"))
        if identity[1] and identity in seen_identities:
            removed += 1
            continue
        if message_id is not None:
            try:
                seen_messages.add(int(message_id))
            except (TypeError, ValueError):
                pass
        if identity[1]:
            seen_identities.add(identity)
        kept.append(entry)
    event_log.replace("soulmate", kept)
    _bind_events()
    if removed:
        _save_disk_log()
    return removed


def get_soulmate_events() -> list[dict[str, Any]]:
    return [dict(entry) for entry in _events]


def client_payload(
    accounts_store: Any,
    *,
    account: str = "all",
    server: str = "all",
    method: str = "all",
    type_id: str = "all",
    offset: int = 0,
    limit: int = 80,
) -> dict[str, Any]:
    from mudae.stats_index import PAGE_SIZE, payload

    return payload(
        "soulmate",
        accounts_store,
        account=account,
        server=server,
        method=method,
        type_id=type_id,
        offset=offset,
        limit=limit or PAGE_SIZE,
    )


def events_for_client(accounts_store: Any) -> list[dict[str, Any]]:
    """Return soulmate rows enriched for the GUI (newest first)."""
    persist_legacy_account_ids(accounts_store)
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


def reset_for_tests(path: Path | None = None) -> None:
    event_log.reset_for_tests(path)
    _bind_events()


_load_disk_log()
