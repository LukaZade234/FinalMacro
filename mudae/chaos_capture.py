"""Raw capture of Mudae messages after a chaos kakera click.

Chaos can grant bonus spheres, extra ``$oh`` / ``$oc`` / ``$oq``, +5/10/15
rolls, ``$kl 1`` / ``$kl 10``, a 50% react-power refund, a self-only character
with 1–4 free kakera buttons, or a wish spawn. Those cases are not parsed yet.

Until they are documented, every Mudae message after a confirmed ``kakeraC``
click is stored until the next *commanded* roll (the reply to a ``$wa`` / ``$wg``
we sent). Unsolicited character / wish embeds from chaos stay in the window.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mudae.clock import utc_date_key, utc_now
from mudae.commands import is_roll_command
from mudae.log_store import DebouncedJsonLog
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "chaos_log.json"
_events: list[dict[str, Any]] = []
_open: dict[str, Any] | None = None
_recording_account_id: str = ""
_recording_account_name: str = ""

_MAX_MESSAGES = 80

_writer = DebouncedJsonLog(lambda: _LOG_PATH, lambda: _events)


def log_path() -> Path:
    return _LOG_PATH


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
    _writer.mark_dirty()


def flush_disk_log() -> None:
    _writer.flush()


def set_recording_account(account_id: str, account_name: str) -> None:
    global _recording_account_id, _recording_account_name
    _recording_account_id = str(account_id or "").strip()
    _recording_account_name = str(account_name or "Main").strip() or "Main"


def clear_recording_account() -> None:
    set_recording_account("", "Main")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _is_next_commanded_roll(
    snapshot: MudaeMessageSnapshot,
    parsed: ParseResult,
    clicked_message_id: int,
) -> bool:
    """True for the next roll reply we sent — not a chaos spawn/wish embed."""
    if snapshot.message_id == clicked_message_id:
        return False
    if snapshot.edited:
        return False
    if parsed.fields.get("perk_6") or parsed.fields.get("is_perk_6_spawn"):
        return False
    parser = str(parsed.fields.get("parser_command") or "").strip().lower()
    command = str(parsed.fields.get("command") or "").strip().lower()
    tagged_roll = parser == "roll" or (command and is_roll_command(command))
    if parsed.kind == MessageKind.ROLL_LIMIT:
        return tagged_roll or not command
    if not tagged_roll:
        return False
    return parsed.fields.get("character_name") is not None


def _message_record(
    snapshot: MudaeMessageSnapshot,
    parsed: ParseResult,
    *,
    recorded_at: str,
) -> dict[str, Any]:
    return {
        "recorded_at": recorded_at,
        "message_id": snapshot.message_id,
        "channel_id": snapshot.channel_id,
        "channel_name": snapshot.channel_name,
        "guild_id": snapshot.guild_id,
        "guild_name": snapshot.guild_name,
        "author_id": snapshot.author_id,
        "author_name": snapshot.author_name,
        "content": snapshot.content,
        "embeds": _json_safe(snapshot.embeds),
        "buttons": _json_safe(snapshot.buttons),
        "created_at": snapshot.created_at,
        "edited": snapshot.edited,
        "kind": parsed.kind.value,
        "summary": parsed.summary,
        "fields": _json_safe(parsed.fields),
        "warnings": list(parsed.warnings),
    }


def _fill_context(window: dict[str, Any], snapshot: MudaeMessageSnapshot) -> None:
    if window.get("guild_id") is None and snapshot.guild_id is not None:
        window["guild_id"] = snapshot.guild_id
        window["guild_name"] = snapshot.guild_name or ""
    if not window.get("channel_name"):
        window["channel_id"] = snapshot.channel_id
        window["channel_name"] = snapshot.channel_name


def begin_window(
    *,
    clicked_message_id: int,
    character_name: str,
    account_id: str | None = None,
    account_name: str | None = None,
) -> None:
    """Start capturing after a chaos kakera click. Flushes a still-open window."""
    global _open
    if _open is not None:
        close_open_window("next_chaos")
    stamp = utc_now()
    acc_id = str(account_id if account_id is not None else _recording_account_id).strip()
    acc_name = str(
        account_name if account_name is not None else _recording_account_name or "Main"
    ).strip() or "Main"
    _open = {
        "kind": "unparsed",
        "clicked_message_id": int(clicked_message_id),
        "character_name": str(character_name or ""),
        "account_id": acc_id,
        "account_name": acc_name,
        "guild_id": None,
        "guild_name": "",
        "channel_id": None,
        "channel_name": "",
        "clicked_at": stamp.isoformat(timespec="seconds"),
        "date_key": utc_date_key(stamp),
        "messages": [],
    }


def close_open_window(reason: str) -> dict[str, Any] | None:
    """Persist the open window if it captured any messages. Return it or None."""
    global _open
    window = _open
    _open = None
    if window is None:
        return None
    messages = list(window.get("messages") or [])
    if not messages:
        return None
    stamp = utc_now()
    window["messages"] = messages
    window["closed_at"] = stamp.isoformat(timespec="seconds")
    window["closed_reason"] = str(reason or "unknown")
    window["message_count"] = len(messages)
    _events.append(window)
    _save_disk_log()
    flush_disk_log()
    return window


def note_parsed(
    snapshot: MudaeMessageSnapshot,
    parsed: ParseResult,
) -> dict[str, Any] | None:
    """Append a Mudae message to the open window.

    Returns the closed window when this message ends the capture (next commanded
    roll is not stored). Returns None while the window stays open or if idle.
    """
    window = _open
    if window is None or not snapshot.is_mudae:
        return None
    clicked_id = int(window.get("clicked_message_id") or 0)
    if _is_next_commanded_roll(snapshot, parsed, clicked_id):
        return close_open_window("next_roll")
    _fill_context(window, snapshot)
    stamp = utc_now().isoformat(timespec="seconds")
    window["messages"].append(_message_record(snapshot, parsed, recorded_at=stamp))
    if len(window["messages"]) >= _MAX_MESSAGES:
        return close_open_window("cap")
    return None


def open_window() -> dict[str, Any] | None:
    """Currently capturing window, or None. Tests / debug only."""
    if _open is None:
        return None
    return dict(_open)


_load_disk_log()
