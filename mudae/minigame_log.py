"""Persist one row per minigame session: board, clicks, win, base SP.

Chat ``+N`` includes bonuses. ``base_value`` is the sum of clicked cells at
``SPHERE_BASE_SP`` so solver stats stay comparable across servers.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from macro.minigame_board import spawn_cell_emojis
from mudae.account_context import defaults_from_store, resolve_log_account
from mudae.clock import utc_date_key
from mudae.constants import sphere_base_sp
from mudae.log_store import DebouncedJsonLog, FileSignature, file_signature

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "minigame_log.json"
_events: list[dict[str, Any]] = []
_recording_account_id: str = ""
_recording_account_name: str = ""
_disk_sig: FileSignature | None = None

_writer = DebouncedJsonLog(
    lambda: _LOG_PATH,
    lambda: _events,
    on_written=lambda: _capture_disk_sig(),
)


def _capture_disk_sig() -> None:
    global _disk_sig
    _disk_sig = file_signature(_LOG_PATH)


def log_path() -> Path:
    """Absolute path of the minigame stats file (``data/minigame_log.json``)."""
    return _LOG_PATH

GAME_LABELS: dict[str, str] = {
    "oh": "$oh",
    "oc": "$oc",
    "oq": "$oq",
    "ot": "$ot",
}

_SPAWN_LABELS = {
    "spP": "Purple",
    "spB": "Blue",
    "spT": "Teal",
    "spG": "Green",
    "spY": "Yellow",
    "spO": "Orange",
    "spR": "Red",
    "spW": "Rainbow",
    "spL": "Light",
    "spD": "Dark",
    "spU": "Hidden ($oc)",
}

_SPAWN_ORDER = (
    "spP",
    "spB",
    "spT",
    "spG",
    "spY",
    "spO",
    "spR",
    "spW",
    "spL",
    "spD",
    "spU",
)

# Only $oc / $oq have a red/rainbow win. $oh and $ot must not move win rate.
WIN_GAMES = frozenset({"oc", "oq"})


def game_label(game: str | None) -> str:
    key = str(game or "").strip().lower()
    if not key:
        return "Unknown"
    return GAME_LABELS.get(key, f"${key}")


def _load_disk_log() -> bool:
    global _events
    if not _LOG_PATH.is_file():
        return False
    try:
        raw = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(raw, list):
        return False
    _events = [entry for entry in raw if isinstance(entry, dict)]
    return True


def refresh_from_disk() -> bool:
    """Re-read the minigame JSON if Syncthing (or another process) changed it."""
    global _disk_sig
    if _writer.is_dirty():
        return False
    sig = file_signature(_LOG_PATH)
    if sig is None or sig == _disk_sig:
        return False
    if not _load_disk_log():
        return False
    _disk_sig = sig
    return True


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


def _parse_entry_datetime(entry: dict[str, Any]) -> dt.datetime:
    raw = entry.get("recorded_at") or entry.get("time") or ""
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if "T" in text:
            try:
                parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                return parsed
            except ValueError:
                pass
        if len(text) == 8 and text.count(":") == 2:
            today = dt.datetime.now(dt.timezone.utc).date()
            try:
                time_part = dt.datetime.strptime(text, "%H:%M:%S").time()
                return dt.datetime.combine(today, time_part, tzinfo=dt.timezone.utc)
            except ValueError:
                pass
    return dt.datetime.now(dt.timezone.utc)


def record_minigame_session(
    session: dict[str, Any],
    *,
    channel_id: int,
    channel_name: str | None = None,
    guild_id: int | None = None,
    guild_name: str | None = None,
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any] | None:
    """Append one finished minigame. Skip sessions that never showed a grid."""
    reason = str(session.get("reason") or "")
    if reason in {"no grid", "exhausted"}:
        return None
    clicks = list(session.get("clicks") or [])
    board = list(session.get("board") or [])
    if not clicks and not any(cell not in {"", "spU"} for cell in board):
        return None

    stamp = now or dt.datetime.now(dt.timezone.utc)
    acc_id = str(account_id if account_id is not None else _recording_account_id).strip()
    acc_name = str(
        account_name if account_name is not None else _recording_account_name or "Main"
    ).strip() or "Main"
    game = str(session.get("game") or "").strip().lower()
    entry = {
        "game": game,
        "game_label": game_label(game),
        "guild_id": guild_id,
        "guild_name": guild_name or "",
        "channel_id": int(channel_id),
        "channel_name": str(channel_name or ""),
        "account_id": acc_id,
        "account_name": acc_name,
        "won": bool(session.get("won")),
        "base_value": int(session.get("base_value") or 0),
        "clicks": clicks,
        "board": board,
        "clicks_paid": int(session.get("clicks_paid") or 0),
        "clicks_budget": int(session.get("clicks_budget") or 0),
        "oc_bonus": int(session.get("oc_bonus") or 0),
        "oc_spawn": int(session.get("oc_spawn") or 0),
        "oq_bonus": int(session.get("oq_bonus") or 0),
        "ot_bonus": int(session.get("ot_bonus") or 0),
        "spheres_bonus": int(session.get("spheres_bonus") or 0),
        "reason": reason,
        "recorded_at": stamp.isoformat(),
        "date_key": utc_date_key(stamp),
        "time": stamp.strftime("%H:%M:%S"),
    }
    _events.append(entry)
    _save_disk_log()
    flush_disk_log()
    return entry


def enrich_entry(
    entry: dict[str, Any],
    *,
    account_by_id: dict[str, Any],
    main_account_id: str,
    main_account_name: str,
) -> dict[str, Any]:
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
    out["game_label"] = game_label(out.get("game"))
    return out


def _spawn_label(emoji: str) -> str:
    return _SPAWN_LABELS.get(emoji, emoji)


def _counts_to_series(counts: dict[str, int], total: int) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    leftover = dict(counts)
    for emoji in _SPAWN_ORDER:
        count = leftover.pop(emoji, 0)
        if count <= 0:
            continue
        series.append(
            {
                "emoji": emoji,
                "label": _spawn_label(emoji),
                "count": count,
                "rate": (count / total) if total else 0.0,
                "base_sp": sphere_base_sp(emoji),
            }
        )
    for emoji, count in sorted(leftover.items()):
        series.append(
            {
                "emoji": emoji,
                "label": _spawn_label(emoji),
                "count": count,
                "rate": (count / total) if total else 0.0,
                "base_sp": sphere_base_sp(emoji),
            }
        )
    return series


def build_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    games = len(entries)
    scored = 0
    wins = 0
    base_value = sum(int(entry.get("base_value") or 0) for entry in entries)
    oc_grants = 0
    oq_grants = 0
    ot_grants = 0
    by_game: dict[str, dict[str, Any]] = {}
    spawn_counts: dict[str, int] = {}
    click_counts: dict[str, int] = {}
    revealed = 0
    clicks_n = 0

    for entry in entries:
        game = str(entry.get("game") or "").strip().lower() or "unknown"
        bucket = by_game.setdefault(
            game,
            {
                "id": game,
                "label": game_label(game),
                "games": 0,
                "wins": 0,
                "base_value": 0,
                "oc_bonus": 0,
                "oq_bonus": 0,
                "ot_bonus": 0,
                "has_win": game in WIN_GAMES,
            },
        )
        bucket["games"] += 1
        if game in WIN_GAMES:
            scored += 1
            if entry.get("won"):
                wins += 1
                bucket["wins"] += 1
        bucket["base_value"] += int(entry.get("base_value") or 0)
        grants = int(entry.get("oc_bonus") or 0)
        if not grants:
            grants = sum(int(click.get("oc_bonus") or 0) for click in entry.get("clicks") or [])
        bucket["oc_bonus"] += grants
        oc_grants += grants
        oq_grant = int(entry.get("oq_bonus") or 0)
        ot_grant = int(entry.get("ot_bonus") or 0)
        bucket["oq_bonus"] += oq_grant
        bucket["ot_bonus"] += ot_grant
        oq_grants += oq_grant
        ot_grants += ot_grant
        for emoji in spawn_cell_emojis(
            list(entry.get("board") or []),
            game=game,
            clicks=list(entry.get("clicks") or []),
        ):
            spawn_counts[emoji] = spawn_counts.get(emoji, 0) + 1
            revealed += 1
        for click in entry.get("clicks") or []:
            emoji = str(click.get("emoji") or "").strip()
            if not emoji:
                continue
            if emoji == "sp":
                emoji = "spR"
            click_counts[emoji] = click_counts.get(emoji, 0) + 1
            clicks_n += 1

    by_game_series = []
    for game, bucket in sorted(by_game.items()):
        count = int(bucket["games"])
        bucket["win_rate"] = (
            (bucket["wins"] / count) if count and bucket["has_win"] else 0.0
        )
        bucket["avg_base_value"] = (bucket["base_value"] / count) if count else 0.0
        by_game_series.append(bucket)

    return {
        "totals": {
            "games": games,
            "wins": wins,
            "scored_games": scored,
            "win_rate": (wins / scored) if scored else 0.0,
            "base_value": base_value,
            "avg_base_value": (base_value / games) if games else 0.0,
            "revealed_cells": revealed,
            "oc_grants": oc_grants,
            "oq_grants": oq_grants,
            "ot_grants": ot_grants,
        },
        "by_game": by_game_series,
        "spawn": _counts_to_series(spawn_counts, revealed),
        "clicked": _counts_to_series(click_counts, clicks_n),
    }


def client_payload(accounts_store: Any) -> dict[str, Any]:
    refresh_from_disk()
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
    stats = build_stats(enriched)
    return {
        "entries": enriched,
        "totals": stats["totals"],
        "by_game": stats["by_game"],
        "spawn": stats["spawn"],
        "clicked": stats["clicked"],
    }


def get_minigame_events() -> list[dict[str, Any]]:
    refresh_from_disk()
    return [dict(entry) for entry in _events]


_load_disk_log()
_capture_disk_sig()
