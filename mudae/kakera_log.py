"""Persist kakera earnings from button clicks and BKU with account context."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from mudae.account_context import resolve_log_account
from mudae.clock import utc_date_key
from mudae import event_log
from macro.state import MacroPhase
from mudae.types import MessageKind, MudaeMessageSnapshot

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "kakera_log.json"
_events: list[dict[str, Any]] = []
_recording_account_id: str = ""
_recording_account_name: str = ""

EARN_METHOD_LABELS: dict[str, str] = {
    "kakera_click": "Kakera click",
    "daily_kakera": "Daily kakera ($dk)",
    "bku_reset": "BKU reset",
    "bku_roll": "BKU roll gain",
}


def earn_method_label(method: str | None) -> str:
    key = str(method or "").strip()
    if not key:
        return "Unknown"
    return EARN_METHOD_LABELS.get(key, key.replace("_", " ").title())


def _bind_events() -> None:
    global _events
    _events = event_log.events("kakera")


def _load_disk_log() -> None:
    event_log.ensure_loaded()
    _bind_events()


def _save_disk_log() -> None:
    event_log.mark_dirty()


def flush_disk_log() -> None:
    """Force pending events to disk (called on disconnect/exit)."""
    event_log.flush()


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


def normalize_earn_method(entry: dict[str, Any]) -> str:
    method = str(entry.get("earn_method") or entry.get("source") or "").strip()
    if method in {"kakera_breakdown", "sphere_click"}:
        return "kakera_click"
    if method in EARN_METHOD_LABELS:
        return method
    return method or "unknown"


def earn_method_from_parse(kind: MessageKind, fields: dict[str, Any]) -> str | None:
    if kind == MessageKind.KAKERA_CLAIM:
        return "kakera_click"
    if kind == MessageKind.DK_CLAIM:
        return str(fields.get("earn_method") or "daily_kakera")
    if kind == MessageKind.TU and fields.get("dk_used"):
        return "daily_kakera"
    if kind == MessageKind.ROLL:
        if fields.get("bku_reset"):
            return "bku_reset"
        if fields.get("bku") is not None:
            return "bku_roll"
    return None


def should_record_earning(
    kind: MessageKind,
    fields: dict[str, Any],
    own_usernames: list[str],
) -> bool:
    if kind == MessageKind.ROLL:
        return False
    if kind in {MessageKind.DK_CLAIM, MessageKind.TU} and fields.get("dk_used"):
        amount = fields.get("amount")
        if amount is None:
            return False
        try:
            return int(amount) > 0
        except (TypeError, ValueError):
            return False
    if kind != MessageKind.KAKERA_CLAIM:
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


def should_record_roll_bku(
    fields: dict[str, Any],
    own_usernames: list[str],
    phase: MacroPhase,
) -> bool:
    bku = fields.get("bku")
    if bku is None:
        return False
    try:
        if int(bku) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    if phase in {MacroPhase.ROLLING, MacroPhase.POST_ROLL}:
        return True
    owner = str(fields.get("owner") or "").strip()
    if owner:
        if username_matches_own(owner, own_usernames):
            return True
        rec = str(_recording_account_name or "").strip()
        return bool(rec and owner.strip().lower() == rec.strip().lower())
    return False


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


def record_kakera_earning(
    snapshot: MudaeMessageSnapshot,
    fields: dict[str, Any],
    *,
    earn_method: str,
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Append one kakera earning event and return the stored entry."""
    stamp = now or dt.datetime.now(dt.timezone.utc)
    acc_id = str(account_id if account_id is not None else _recording_account_id).strip()
    acc_name = str(
        account_name if account_name is not None else _recording_account_name or "Main"
    ).strip() or "Main"
    amount = int(fields["amount"])
    method = str(earn_method or fields.get("earn_method") or "unknown").strip()
    entry = {
        "guild_id": snapshot.guild_id,
        "guild_name": snapshot.guild_name,
        "channel_id": snapshot.channel_id,
        "channel_name": snapshot.channel_name,
        "account_id": acc_id,
        "account_name": acc_name,
        "amount": amount,
        "earn_method": method,
        "source": method,
        "kakera_type": fields.get("kakera_type") or fields.get("sphere_type"),
        "character_name": fields.get("character_name"),
        "starwish": bool(fields.get("starwish")),
        "claimed_by": fields.get("claimed_by"),
        "recorded_at": stamp.isoformat(),
        "date_key": utc_date_key(stamp),
        "time": snapshot.created_at,
        "message_id": snapshot.message_id,
    }
    event_log.append("kakera", entry)
    return entry


def record_roll_bku_earning(
    snapshot: MudaeMessageSnapshot,
    fields: dict[str, Any],
    *,
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Log BKU payout from a roll embed (reset or incremental pool gain)."""
    msg_id = snapshot.message_id
    method = "bku_reset" if fields.get("bku_reset") else "bku_roll"
    # Dedupe only against recent entries (re-parses arrive close together);
    # scanning the full history gets slower as the log grows.
    for existing in _events[-200:]:
        if existing.get("message_id") == msg_id and existing.get("earn_method") == method:
            return existing
    payload = dict(fields)
    payload["amount"] = int(fields["bku"])
    payload["earn_method"] = method
    return record_kakera_earning(
        snapshot,
        payload,
        earn_method=method,
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
    method = normalize_earn_method(out)
    out["earn_method"] = method
    out["earn_method_label"] = earn_method_label(method)
    return out


def build_stats(
    entries: list[dict[str, Any]],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Aggregate totals and chart series from enriched log entries."""
    stamp = now or dt.datetime.now(dt.timezone.utc)
    today = stamp.date()
    week_start = today - dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    totals = {"all_time": 0, "today": 0, "week": 0, "month": 0, "year": 0}
    daily: dict[str, int] = {}
    monthly: dict[str, int] = {}
    by_method: dict[str, int] = {}

    for entry in entries:
        amount = int(entry.get("amount") or 0)
        if amount <= 0:
            continue
        when = _parse_entry_datetime(entry)
        day = when.date()
        date_key = day.strftime("%Y-%m-%d")
        month_key = day.strftime("%Y-%m")
        method = normalize_earn_method(entry)

        totals["all_time"] += amount
        daily[date_key] = daily.get(date_key, 0) + amount
        monthly[month_key] = monthly.get(month_key, 0) + amount
        by_method[method] = by_method.get(method, 0) + amount

        if day == today:
            totals["today"] += amount
        if day >= week_start:
            totals["week"] += amount
        if day >= month_start:
            totals["month"] += amount
        if day >= year_start:
            totals["year"] += amount

    daily_series = [
        {"date": key, "amount": daily[key]}
        for key in sorted(daily.keys())
    ]
    monthly_series = []
    for key in sorted(monthly.keys()):
        year, month = key.split("-", 1)
        label = dt.date(int(year), int(month), 1).strftime("%b %Y")
        monthly_series.append({"month": key, "label": label, "amount": monthly[key]})

    by_method_series = [
        {
            "id": method,
            "label": earn_method_label(method),
            "amount": amount,
        }
        for method, amount in sorted(by_method.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "totals": totals,
        "daily_series": daily_series,
        "monthly_series": monthly_series,
        "by_method": by_method_series,
    }


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
        "kakera",
        accounts_store,
        account=account,
        server=server,
        method=method,
        type_id=type_id,
        offset=offset,
        limit=limit or PAGE_SIZE,
    )


def get_kakera_events() -> list[dict[str, Any]]:
    return [dict(entry) for entry in _events]


def reset_for_tests(path: Path | None = None) -> None:
    event_log.reset_for_tests(path)
    _bind_events()


_load_disk_log()
