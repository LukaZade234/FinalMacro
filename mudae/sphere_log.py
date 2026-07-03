"""Persist sphere earnings with account and source context."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from mudae.account_context import defaults_from_store, resolve_log_account
from mudae.types import MessageKind, MudaeMessageSnapshot

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "sphere_log.json"
_events: list[dict[str, Any]] = []
_recording_account_id: str = ""
_recording_account_name: str = ""

# ``minigame_<id>`` uses ids from ``MINIGAME_IDS`` (oh, oc, oq, …).
SOURCE_LABELS: dict[str, str] = {
    "sphere_click": "Sphere button click",
    "kakera_bonus": "Bonus from kakera click",
    "minigame_oh": "$oh minigame",
    "minigame_oc": "$oc minigame",
    "minigame_oq": "$oq minigame",
}

MINIGAME_IDS = frozenset({"oh", "oc", "oq"})


def source_label(source: str | None) -> str:
    key = str(source or "").strip()
    if not key:
        return "Unknown"
    if key in SOURCE_LABELS:
        return SOURCE_LABELS[key]
    if key.startswith("minigame_"):
        game = key.removeprefix("minigame_").upper()
        return f"${game} minigame"
    return key.replace("_", " ").title()


def minigame_source(game: str) -> str:
    game_id = str(game or "").strip().lower()
    return f"minigame_{game_id}"


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
    global _recording_account_id, _recording_account_name
    _recording_account_id = str(account_id or "").strip()
    _recording_account_name = str(account_name or "Main").strip() or "Main"


def clear_recording_account() -> None:
    set_recording_account("", "Main")


def username_matches_own(claimed_by: str | None, own_usernames: list[str]) -> bool:
    if not claimed_by or not own_usernames:
        return False
    norm = claimed_by.strip().lower()
    return any(name.strip().lower() == norm for name in own_usernames if name)


def normalize_source(entry: dict[str, Any]) -> str:
    return str(entry.get("source") or entry.get("earn_method") or "unknown").strip() or "unknown"


def should_record_sphere_click(
    kind: MessageKind,
    fields: dict[str, Any],
    own_usernames: list[str],
) -> bool:
    if kind != MessageKind.SPHERE_CLICK:
        return False
    amount = fields.get("amount")
    if amount is None:
        return False
    try:
        if int(amount) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    return username_matches_own(str(fields.get("claimed_by") or ""), own_usernames)


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


def record_sphere_earning(
    snapshot: MudaeMessageSnapshot,
    fields: dict[str, Any],
    *,
    source: str,
    amount: int | None = None,
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Append one sphere earning event and return the stored entry."""
    stamp = now or dt.datetime.now(dt.timezone.utc)
    acc_id = str(account_id if account_id is not None else _recording_account_id).strip()
    acc_name = str(
        account_name if account_name is not None else _recording_account_name or "Main"
    ).strip() or "Main"
    value = int(amount if amount is not None else fields["amount"])
    src = str(source).strip()
    entry = {
        "guild_id": snapshot.guild_id,
        "guild_name": snapshot.guild_name,
        "channel_id": snapshot.channel_id,
        "channel_name": snapshot.channel_name,
        "account_id": acc_id,
        "account_name": acc_name,
        "amount": value,
        "source": src,
        "sphere_type": fields.get("sphere_type") or fields.get("kakera_type"),
        "character_name": fields.get("character_name"),
        "claimed_by": fields.get("claimed_by"),
        "recorded_at": stamp.isoformat(),
        "date_key": stamp.strftime("%Y-%m-%d"),
        "time": snapshot.created_at,
        "message_id": snapshot.message_id,
    }
    _events.append(entry)
    _save_disk_log()
    return entry


def record_minigame_earning(
    *,
    game: str,
    amount: int,
    channel_id: int,
    channel_name: str | None = None,
    guild_id: int | None = None,
    guild_name: str | None = None,
    clicks: int | None = None,
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Log total spheres from a minigame session (``$oh``, ``$oc``, ``$oq``, …)."""
    game_id = str(game or "").strip().lower()
    snapshot = MudaeMessageSnapshot(
        message_id=0,
        channel_id=int(channel_id),
        channel_name=str(channel_name or ""),
        guild_id=guild_id,
        guild_name=guild_name,
        author_id=0,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[],
        buttons=[],
        created_at=dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S"),
    )
    fields: dict[str, Any] = {"amount": int(amount)}
    if clicks is not None:
        fields["minigame_clicks"] = int(clicks)
    return record_sphere_earning(
        snapshot,
        fields,
        source=minigame_source(game_id),
        amount=int(amount),
        account_id=account_id,
        account_name=account_name,
        now=now,
    )


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
    src = normalize_source(out)
    out["source"] = src
    out["source_label"] = source_label(src)
    return out


def build_stats(
    entries: list[dict[str, Any]],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    stamp = now or dt.datetime.now(dt.timezone.utc)
    today = stamp.date()
    week_start = today - dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    totals = {"all_time": 0, "today": 0, "week": 0, "month": 0, "year": 0}
    daily: dict[str, int] = {}
    monthly: dict[str, int] = {}
    by_source: dict[str, int] = {}

    for entry in entries:
        amount = int(entry.get("amount") or 0)
        if amount <= 0:
            continue
        when = _parse_entry_datetime(entry)
        day = when.date()
        date_key = day.strftime("%Y-%m-%d")
        month_key = day.strftime("%Y-%m")
        src = normalize_source(entry)

        totals["all_time"] += amount
        daily[date_key] = daily.get(date_key, 0) + amount
        monthly[month_key] = monthly.get(month_key, 0) + amount
        by_source[src] = by_source.get(src, 0) + amount

        if day == today:
            totals["today"] += amount
        if day >= week_start:
            totals["week"] += amount
        if day >= month_start:
            totals["month"] += amount
        if day >= year_start:
            totals["year"] += amount

    daily_series = [{"date": key, "amount": daily[key]} for key in sorted(daily.keys())]
    monthly_series = []
    for key in sorted(monthly.keys()):
        year, month = key.split("-", 1)
        label = dt.date(int(year), int(month), 1).strftime("%b %Y")
        monthly_series.append({"month": key, "label": label, "amount": monthly[key]})

    by_source_series = [
        {"id": src, "label": source_label(src), "amount": amount}
        for src, amount in sorted(by_source.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "totals": totals,
        "daily_series": daily_series,
        "monthly_series": monthly_series,
        "by_source": by_source_series,
    }


def client_payload(accounts_store: Any) -> dict[str, Any]:
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
        "daily_series": stats["daily_series"],
        "monthly_series": stats["monthly_series"],
        "by_source": stats["by_source"],
    }


def get_sphere_events() -> list[dict[str, Any]]:
    return [dict(entry) for entry in _events]


_load_disk_log()
