"""Persist key gains from rolls and perk-6 spawns."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from mudae.account_context import resolve_log_account
from mudae.clock import utc_date_key
from mudae import event_log
from macro.state import MacroPhase
from mudae.types import MessageKind, MudaeMessageSnapshot

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "key_log.json"
_events: list[dict[str, Any]] = []
_recording_account_id: str = ""
_recording_account_name: str = ""

_ROLL_LIKE_KINDS = frozenset(
    {
        MessageKind.ROLL,
        MessageKind.CHARACTER_EMBED,
        MessageKind.KAKERA_BUTTONS,
        MessageKind.CLAIM_BUTTONS,
    }
)

KEY_TYPES = ("bronze", "silver", "gold", "chaos", "omega")

KEY_TYPE_LABELS: dict[str, str] = {
    "bronze": "Bronze",
    "silver": "Silver",
    "gold": "Gold",
    "chaos": "Chaos",
    "omega": "Omega",
}

SOURCE_LABELS: dict[str, str] = {
    "roll": "Roll",
    "perk6_spawn": "Perk 6 spawn",
    "chaos": "Chaos kakera",
}


def key_type_label(key_type: str | None) -> str:
    key = str(key_type or "").strip().lower()
    return KEY_TYPE_LABELS.get(key, key.replace("_", " ").title() or "Unknown")


def source_label(source: str | None) -> str:
    key = str(source or "").strip()
    if not key:
        return "Unknown"
    return SOURCE_LABELS.get(key, key.replace("_", " ").title())


def normalize_source(entry: dict[str, Any]) -> str:
    return str(entry.get("source") or "unknown").strip() or "unknown"


def normalize_key_type(entry: dict[str, Any]) -> str:
    return str(entry.get("key_type") or "unknown").strip().lower() or "unknown"


def _bind_events() -> None:
    global _events
    _events = event_log.events("key")


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


def _character_name_is_profile_author(
    character_name: str,
    own_usernames: list[str],
    account_name: str,
) -> bool:
    name = character_name.strip().lower()
    if not name:
        return False
    rec = (account_name or "").strip().lower()
    if rec and name == rec:
        return True
    return any(name == u.strip().lower() for u in own_usernames if u)


def is_roll_like_kind(kind: MessageKind) -> bool:
    return kind in _ROLL_LIKE_KINDS


def should_record_roll_keys(
    kind: MessageKind,
    fields: dict[str, Any],
    own_usernames: list[str],
    phase: MacroPhase,
    *,
    macro_running: bool = False,
) -> bool:
    del macro_running  # kept for callers; recording is phase-gated, not run-gated
    if not is_roll_like_kind(kind):
        return False
    if fields.get("is_profile"):
        return False
    if not fields.get("character_name"):
        return False
    if not fields.get("keys") and not fields.get("omega_keys"):
        return False
    character = str(fields.get("character_name") or "")
    if _character_name_is_profile_author(
        character, own_usernames, _recording_account_name
    ):
        return False
    if phase in {MacroPhase.ROLLING, MacroPhase.POST_ROLL}:
        return True
    owner = str(fields.get("owner") or "").strip()
    if owner and username_matches_own(owner, own_usernames):
        return True
    rec = str(_recording_account_name or "").strip()
    return bool(rec and owner and owner.strip().lower() == rec.strip().lower())


def roll_source_from_fields(fields: dict[str, Any]) -> str:
    if fields.get("is_perk_6_spawn"):
        return "perk6_spawn"
    return "roll"


def count_tier_keys_by_type(keys: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Each key line on the roll embed is one key gained on that roll."""
    out: dict[str, list[int]] = {}
    for entry in keys or []:
        key_type = str(entry.get("type") or "").strip().lower()
        if key_type not in KEY_TYPE_LABELS or key_type == "omega":
            continue
        try:
            level = int(entry.get("level"))
        except (TypeError, ValueError):
            continue
        out.setdefault(key_type, []).append(level)
    return out


def total_omega_gain(omega_keys: list[dict[str, Any]]) -> int:
    total = 0
    for entry in omega_keys or []:
        try:
            gain = int(entry.get("gain"))
        except (TypeError, ValueError, AttributeError):
            continue
        if gain > 0:
            total += gain
    return total


def _logged_types_for_message(message_id: int | None) -> set[str]:
    if not message_id:
        return set()
    return {
        normalize_key_type(entry)
        for entry in _events
        if entry.get("message_id") == message_id
    }


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


def _append_event(
    snapshot: MudaeMessageSnapshot,
    *,
    character_name: str,
    key_type: str,
    amount: int,
    source: str,
    level_after: int | None = None,
    levels_after: list[int] | None = None,
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    stamp = now or dt.datetime.now(dt.timezone.utc)
    acc_id = str(account_id if account_id is not None else _recording_account_id).strip()
    acc_name = str(
        account_name if account_name is not None else _recording_account_name or "Main"
    ).strip() or "Main"
    src = str(source).strip()
    kt = str(key_type).strip().lower()
    entry = {
        "guild_id": snapshot.guild_id,
        "guild_name": snapshot.guild_name,
        "channel_id": snapshot.channel_id,
        "channel_name": snapshot.channel_name,
        "account_id": acc_id,
        "account_name": acc_name,
        "character_name": character_name,
        "key_type": kt,
        "amount": int(amount),
        "source": src,
        "level_after": level_after,
        "levels_after": levels_after,
        "recorded_at": stamp.isoformat(),
        "date_key": utc_date_key(stamp),
        "time": snapshot.created_at,
        "message_id": snapshot.message_id,
    }
    event_log.append("key", entry)
    return entry


def record_roll_key_events(
    snapshot: MudaeMessageSnapshot,
    fields: dict[str, Any],
    *,
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
    from_macro: bool = False,
) -> list[dict[str, Any]]:
    """Log keys shown on a roll embed: one line per key gained, omega from +N."""
    del from_macro
    character = str(fields.get("character_name") or "Unknown").strip() or "Unknown"
    source = roll_source_from_fields(fields)
    created: list[dict[str, Any]] = []
    already_logged = _logged_types_for_message(snapshot.message_id)

    for key_type, levels in count_tier_keys_by_type(list(fields.get("keys") or [])).items():
        amount = len(levels)
        if amount <= 0 or key_type in already_logged:
            continue
        created.append(
            _append_event(
                snapshot,
                character_name=character,
                key_type=key_type,
                amount=amount,
                source=source,
                level_after=max(levels),
                levels_after=list(levels),
                account_id=account_id,
                account_name=account_name,
                now=now,
            )
        )
        already_logged.add(key_type)

    omega_gain = total_omega_gain(list(fields.get("omega_keys") or []))
    if omega_gain > 0 and "omega" not in already_logged:
        created.append(
            _append_event(
                snapshot,
                character_name=character,
                key_type="omega",
                amount=omega_gain,
                source=source,
                level_after=None,
                account_id=account_id,
                account_name=account_name,
                now=now,
            )
        )

    return created


def record_chaos_omega(
    snapshot: MudaeMessageSnapshot,
    *,
    amount: int,
    character_name: str = "",
    account_id: str | None = None,
    account_name: str | None = None,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    """Log omega keys granted on a chaos-kakera claim (not a roll embed)."""
    gain = max(0, int(amount))
    if gain <= 0:
        return []
    already_logged = _logged_types_for_message(snapshot.message_id)
    if "omega" in already_logged:
        return []
    name = str(character_name or "").strip() or "Chaos kakera"
    return [
        _append_event(
            snapshot,
            character_name=name,
            key_type="omega",
            amount=gain,
            source="chaos",
            level_after=None,
            account_id=account_id,
            account_name=account_name,
            now=now,
        )
    ]


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
    kt = normalize_key_type(out)
    out["source"] = src
    out["source_label"] = source_label(src)
    out["key_type"] = kt
    out["key_type_label"] = key_type_label(kt)
    return out


def _empty_period_totals() -> dict[str, int]:
    return {"all_time": 0, "today": 0, "week": 0, "month": 0, "year": 0}


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

    totals_by_type = {key_type: _empty_period_totals() for key_type in KEY_TYPES}
    daily: dict[str, dict[str, int]] = {}
    monthly: dict[str, dict[str, int]] = {}
    omega_daily: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_key_type: dict[str, int] = {}

    for entry in entries:
        amount = int(entry.get("amount") or 0)
        if amount <= 0:
            continue
        key_type = normalize_key_type(entry)
        if key_type not in KEY_TYPES:
            continue
        when = _parse_entry_datetime(entry)
        day = when.date()
        date_key = day.strftime("%Y-%m-%d")
        month_key = day.strftime("%Y-%m")
        src = normalize_source(entry)

        daily.setdefault(date_key, {kt: 0 for kt in KEY_TYPES})
        daily[date_key][key_type] = daily[date_key].get(key_type, 0) + amount
        monthly.setdefault(month_key, {kt: 0 for kt in KEY_TYPES})
        monthly[month_key][key_type] = monthly[month_key].get(key_type, 0) + amount
        by_source[src] = by_source.get(src, 0) + amount
        by_key_type[key_type] = by_key_type.get(key_type, 0) + amount

        if key_type == "omega":
            omega_daily[date_key] = omega_daily.get(date_key, 0) + amount

        type_totals = totals_by_type[key_type]
        type_totals["all_time"] += amount
        if day == today:
            type_totals["today"] += amount
        if day >= week_start:
            type_totals["week"] += amount
        if day >= month_start:
            type_totals["month"] += amount
        if day >= year_start:
            type_totals["year"] += amount

    daily_series = []
    for date_key in sorted(daily.keys()):
        row = {"date": date_key, **daily[date_key]}
        row["total"] = sum(daily[date_key].values())
        daily_series.append(row)

    monthly_series = []
    for month_key in sorted(monthly.keys()):
        year, month = month_key.split("-", 1)
        label = dt.date(int(year), int(month), 1).strftime("%b %Y")
        row = {"month": month_key, "label": label, **monthly[month_key]}
        row["total"] = sum(monthly[month_key].values())
        monthly_series.append(row)

    omega_daily_series = [
        {"date": key, "amount": omega_daily[key]} for key in sorted(omega_daily.keys())
    ]

    by_source_series = [
        {"id": src, "label": source_label(src), "amount": amount}
        for src, amount in sorted(by_source.items(), key=lambda item: item[1], reverse=True)
    ]
    by_key_type_series = [
        {"id": kt, "label": key_type_label(kt), "amount": amount}
        for kt, amount in sorted(by_key_type.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "totals_by_type": totals_by_type,
        "daily_series": daily_series,
        "monthly_series": monthly_series,
        "omega_daily_series": omega_daily_series,
        "by_source": by_source_series,
        "by_key_type": by_key_type_series,
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
        "key",
        accounts_store,
        account=account,
        server=server,
        method=method,
        type_id=type_id,
        offset=offset,
        limit=limit or PAGE_SIZE,
    )


def get_key_events() -> list[dict[str, Any]]:
    event_log.ensure_loaded()
    return [dict(entry) for entry in _events]


def reset_for_tests(path: Path | None = None) -> None:
    """Clear in-memory state (tests only)."""
    global _recording_account_id, _recording_account_name
    event_log.reset_for_tests(path)
    _bind_events()
    _recording_account_id = ""
    _recording_account_name = ""


_load_disk_log()
