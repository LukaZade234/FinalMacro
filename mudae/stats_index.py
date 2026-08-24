"""In-memory daily cube for Statistics cards, charts, and paged event tables.

Source of truth remains EventLog. This index is rebuilt on load/replace and
incremented on append so QML never has to parse or walk the full log.
"""

from __future__ import annotations

import datetime as dt
import threading
from typing import Any

from mudae.account_context import defaults_from_store, resolve_log_account
from mudae.clock import parse_iso_datetime, utc_date_key

PAGE_SIZE = 80
KINDS = ("kakera", "sphere", "key", "soulmate")
KEY_TYPES = ("bronze", "silver", "gold", "chaos", "omega")

_lock = threading.Lock()
# kind -> {(date_key, account_id, guild, method, type_id): [amount, count]}
_cells: dict[str, dict[tuple[str, str, str, str, str], list[int]]] = {
    kind: {} for kind in KINDS
}
_account_names: dict[str, dict[str, str]] = {kind: {} for kind in KINDS}


def reset() -> None:
    with _lock:
        _clear_unlocked()


def rebuild() -> None:
    from mudae import event_log

    snapshots = {kind: list(event_log.events(kind)) for kind in KINDS}
    with _lock:
        _clear_unlocked()
        for kind, rows in snapshots.items():
            for entry in rows:
                _add_unlocked(kind, entry)


def rebuild_kind(kind: str) -> None:
    from mudae import event_log

    if kind not in _cells:
        raise ValueError(f"unknown event kind {kind!r}")
    rows = list(event_log.events(kind))
    with _lock:
        _cells[kind] = {}
        _account_names[kind] = {}
        for entry in rows:
            _add_unlocked(kind, entry)


def add(kind: str, entry: dict[str, Any]) -> None:
    if kind not in _cells:
        return
    with _lock:
        _add_unlocked(kind, entry)


def payload(
    kind: str,
    accounts_store: Any,
    *,
    account: str = "all",
    server: str = "all",
    method: str = "all",
    type_id: str = "all",
    offset: int = 0,
    limit: int = PAGE_SIZE,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Filtered summary plus one page of enriched events (newest first)."""
    if kind not in _cells:
        raise ValueError(f"unknown event kind {kind!r}")
    main_id, main_name, account_by_id = defaults_from_store(accounts_store)
    account = _norm_filter(account)
    server = _norm_filter(server)
    method = _norm_filter(method)
    type_id = _norm_filter(type_id)
    offset = max(0, int(offset))
    limit = PAGE_SIZE if int(limit) <= 0 else int(limit)

    if kind == "soulmate":
        from mudae.soulmate_log import persist_legacy_account_ids

        persist_legacy_account_ids(accounts_store)

    stamp = now or dt.datetime.now(dt.timezone.utc)
    today = stamp.date()
    week_start = today - dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    with _lock:
        summary = _summarize_unlocked(
            kind,
            account=account,
            server=server,
            method=method,
            type_id=type_id,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
            today=today,
            week_start=week_start,
            month_start=month_start,
            year_start=year_start,
        )
        filter_options = _filter_options_unlocked(
            kind,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
        soulmate_charts = (
            _soulmate_charts_unlocked(
                main_id=main_id,
                main_name=main_name,
                account_by_id=account_by_id,
            )
            if kind == "soulmate"
            else None
        )

    recent, event_count = _recent_page(
        kind,
        accounts_store,
        account=account,
        server=server,
        method=method,
        type_id=type_id,
        offset=offset,
        limit=limit,
        main_id=main_id,
        main_name=main_name,
        account_by_id=account_by_id,
    )
    out: dict[str, Any] = {
        **summary,
        "recent": recent,
        "event_count": event_count,
        "has_more": offset + len(recent) < event_count,
        "filter_options": filter_options,
    }
    if soulmate_charts is not None:
        out.update(soulmate_charts)
    return out


def _clear_unlocked() -> None:
    for kind in KINDS:
        _cells[kind] = {}
        _account_names[kind] = {}


def _add_unlocked(kind: str, entry: dict[str, Any]) -> None:
    amount = _amount(kind, entry)
    if kind != "soulmate" and amount <= 0:
        return
    key = _dims(kind, entry)
    cell = _cells[kind].get(key)
    if cell is None:
        cell = [0, 0]
        _cells[kind][key] = cell
    cell[0] += amount
    cell[1] += 1
    acc_id = key[1]
    name = str(entry.get("account_name") or "").strip()
    if acc_id and name:
        _account_names[kind][acc_id] = name


def _amount(kind: str, entry: dict[str, Any]) -> int:
    if kind == "soulmate":
        return 1
    try:
        return int(entry.get("amount") or 0)
    except (TypeError, ValueError):
        return 0


def _dims(kind: str, entry: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _date_key(entry),
        str(entry.get("account_id") or "").strip(),
        _guild_key(entry),
        *_method_and_type(kind, entry),
    )


def _date_key(entry: dict[str, Any]) -> str:
    key = str(entry.get("date_key") or "").strip()
    if len(key) >= 10:
        return key[:10]
    parsed = parse_iso_datetime(str(entry.get("recorded_at") or ""))
    if parsed is not None:
        return utc_date_key(parsed)
    return ""


def _guild_key(entry: dict[str, Any]) -> str:
    name = str(entry.get("guild_name") or "").strip()
    if name:
        return name
    return str(entry.get("guild_id") or "unknown")


def _method_and_type(kind: str, entry: dict[str, Any]) -> tuple[str, str]:
    if kind == "kakera":
        method = str(entry.get("earn_method") or entry.get("source") or "").strip()
        if method in {"kakera_breakdown", "sphere_click"}:
            method = "kakera_click"
        return method or "unknown", str(entry.get("kakera_type") or "").strip()
    if kind == "sphere":
        method = str(entry.get("source") or entry.get("earn_method") or "").strip()
        return method or "unknown", str(entry.get("sphere_type") or "").strip()
    if kind == "key":
        method = str(entry.get("source") or "").strip() or "unknown"
        type_id = str(entry.get("key_type") or "unknown").strip().lower() or "unknown"
        return method, type_id
    return "", ""


def _norm_filter(value: str) -> str:
    text = str(value or "").strip()
    if not text or text == "all":
        return "all"
    return text


def _resolve_account(
    account_id: str,
    account_name: str,
    *,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> tuple[str, str, bool]:
    return resolve_log_account(
        {"account_id": account_id, "account_name": account_name},
        account_by_id=account_by_id,
        default_account_id=main_id,
        default_account_name=main_name,
    )


def _cell_account(
    kind: str,
    account_id: str,
    *,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> tuple[str, str, bool]:
    stored_name = _account_names[kind].get(account_id, "")
    return _resolve_account(
        account_id,
        stored_name,
        main_id=main_id,
        main_name=main_name,
        account_by_id=account_by_id,
    )


def _cell_matches(
    kind: str,
    key: tuple[str, str, str, str, str],
    *,
    account: str,
    server: str,
    method: str,
    type_id: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> bool:
    _date, acc_id, guild, meth, typ = key
    if account != "all":
        resolved, _, _ = _cell_account(
            kind,
            acc_id,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
        if resolved != account:
            return False
    if server != "all" and guild != server:
        return False
    if method != "all" and meth != method:
        return False
    if type_id != "all" and typ != type_id:
        return False
    return True


def _empty_periods() -> dict[str, int]:
    return {"all_time": 0, "today": 0, "week": 0, "month": 0, "year": 0}


def _add_periods(
    totals: dict[str, int],
    amount: int,
    day: dt.date | None,
    today: dt.date,
    week_start: dt.date,
    month_start: dt.date,
    year_start: dt.date,
) -> None:
    totals["all_time"] += amount
    if day is None:
        return
    if day == today:
        totals["today"] += amount
    if day >= week_start:
        totals["week"] += amount
    if day >= month_start:
        totals["month"] += amount
    if day >= year_start:
        totals["year"] += amount


def _parse_day(date_key: str) -> dt.date | None:
    if len(date_key) < 10:
        return None
    try:
        return dt.date.fromisoformat(date_key[:10])
    except ValueError:
        return None


def _month_label(month_key: str) -> str:
    try:
        year, month = month_key.split("-", 1)
        return dt.date(int(year), int(month), 1).strftime("%b %Y")
    except (TypeError, ValueError):
        return month_key


def _summarize_unlocked(
    kind: str,
    *,
    account: str,
    server: str,
    method: str,
    type_id: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
    today: dt.date,
    week_start: dt.date,
    month_start: dt.date,
    year_start: dt.date,
) -> dict[str, Any]:
    totals = _empty_periods()
    totals_by_type = {kt: _empty_periods() for kt in KEY_TYPES}
    daily_amount: dict[str, int] = {}
    daily_keys: dict[str, dict[str, int]] = {}
    monthly_amount: dict[str, int] = {}
    monthly_keys: dict[str, dict[str, int]] = {}
    omega_daily: dict[str, int] = {}
    by_method: dict[str, int] = {}
    by_type: dict[str, int] = {}

    for key, (amount, _count) in _cells[kind].items():
        if not _cell_matches(
            kind,
            key,
            account=account,
            server=server,
            method=method,
            type_id=type_id,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        ):
            continue
        date_key, _acc, _guild, meth, typ = key
        day = _parse_day(date_key)
        _add_periods(totals, amount, day, today, week_start, month_start, year_start)
        if date_key:
            daily_amount[date_key] = daily_amount.get(date_key, 0) + amount
            monthly_key = date_key[:7]
            monthly_amount[monthly_key] = monthly_amount.get(monthly_key, 0) + amount
        if meth:
            by_method[meth] = by_method.get(meth, 0) + amount
        if typ:
            by_type[typ] = by_type.get(typ, 0) + amount
        if kind == "key" and typ in totals_by_type:
            _add_periods(
                totals_by_type[typ],
                amount,
                day,
                today,
                week_start,
                month_start,
                year_start,
            )
            if date_key:
                daily_keys.setdefault(date_key, {kt: 0 for kt in KEY_TYPES})
                daily_keys[date_key][typ] = daily_keys[date_key].get(typ, 0) + amount
                monthly_key = date_key[:7]
                monthly_keys.setdefault(monthly_key, {kt: 0 for kt in KEY_TYPES})
                monthly_keys[monthly_key][typ] = monthly_keys[monthly_key].get(typ, 0) + amount
            if typ == "omega" and date_key:
                omega_daily[date_key] = omega_daily.get(date_key, 0) + amount

    if kind == "key":
        daily_series = []
        for date_key in sorted(daily_keys):
            row = {"date": date_key, **daily_keys[date_key]}
            row["total"] = sum(daily_keys[date_key].values())
            daily_series.append(row)
        monthly_series = []
        for month_key in sorted(monthly_keys):
            row = {
                "month": month_key,
                "label": _month_label(month_key),
                **monthly_keys[month_key],
            }
            row["total"] = sum(monthly_keys[month_key].values())
            monthly_series.append(row)
        return {
            "totals_by_type": totals_by_type,
            "daily_series": daily_series,
            "monthly_series": monthly_series,
            "omega_daily_series": [
                {"date": key, "amount": omega_daily[key]} for key in sorted(omega_daily)
            ],
            "by_source": _labeled_series(kind, "method", by_method),
            "by_key_type": _labeled_series(kind, "type", by_type),
        }

    daily_series = [
        {"date": key, "amount": daily_amount[key]} for key in sorted(daily_amount)
    ]
    monthly_series = [
        {
            "month": key,
            "label": _month_label(key),
            "amount": monthly_amount[key],
        }
        for key in sorted(monthly_amount)
    ]
    breakdown_key = "by_method" if kind == "kakera" else "by_source"
    breakdown_kind = "method"
    out = {
        "totals": totals,
        "daily_series": daily_series,
        "monthly_series": monthly_series,
        breakdown_key: _labeled_series(kind, breakdown_kind, by_method),
    }
    return out


def _labeled_series(
    kind: str,
    field: str,
    amounts: dict[str, int],
) -> list[dict[str, Any]]:
    rows = []
    for item_id, amount in sorted(amounts.items(), key=lambda pair: pair[1], reverse=True):
        rows.append(
            {
                "id": item_id,
                "label": _label_for(kind, field, item_id),
                "amount": amount,
            }
        )
    return rows


def _label_for(kind: str, field: str, item_id: str) -> str:
    if kind == "kakera" and field == "method":
        from mudae.kakera_log import earn_method_label

        return earn_method_label(item_id)
    if kind == "sphere" and field == "method":
        from mudae.sphere_log import source_label

        return source_label(item_id)
    if kind == "key" and field == "method":
        from mudae.key_log import source_label

        return source_label(item_id)
    if kind == "key" and field == "type":
        from mudae.key_log import key_type_label

        return key_type_label(item_id)
    if not item_id:
        return "Unknown"
    return item_id.replace("_", " ").title()


def _filter_options_unlocked(
    kind: str,
    *,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> dict[str, list[dict[str, str]]]:
    accounts: dict[str, str] = {}
    servers: dict[str, str] = {}
    methods: dict[str, str] = {}
    types: dict[str, str] = {}
    for key in _cells[kind]:
        _date, acc_id, guild, meth, typ = key
        resolved, name, inferred = _cell_account(
            kind,
            acc_id,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
        if resolved:
            label = name
            if inferred:
                label = f"{name} (inferred)"
            accounts.setdefault(resolved, label)
        if guild:
            servers.setdefault(guild, guild)
        if meth:
            methods.setdefault(meth, _label_for(kind, "method", meth))
        if typ:
            field = "type" if kind == "key" else "type"
            types.setdefault(typ, _label_for(kind, field, typ) if kind == "key" else typ)
    return {
        "accounts": [{"id": key, "label": accounts[key]} for key in sorted(accounts, key=lambda i: accounts[i].lower())],
        "servers": [{"id": key, "label": servers[key]} for key in sorted(servers, key=str.lower)],
        "methods": [{"id": key, "label": methods[key]} for key in sorted(methods, key=lambda i: methods[i].lower())],
        "types": [{"id": key, "label": types[key]} for key in sorted(types, key=lambda i: types[i].lower())],
    }


def _soulmate_charts_unlocked(
    *,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> dict[str, Any]:
    by_account: dict[str, list[Any]] = {}
    by_server: dict[str, int] = {}
    by_server_accounts: dict[str, dict[str, list[Any]]] = {}
    for key, (_amount, count) in _cells["soulmate"].items():
        _date, acc_id, guild, _meth, _typ = key
        resolved, name, _inferred = _cell_account(
            "soulmate",
            acc_id,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
        acc_key = resolved or "unknown"
        acc_label = name or "Unknown"
        bucket = by_account.get(acc_key)
        if bucket is None:
            by_account[acc_key] = [acc_label, 0]
            bucket = by_account[acc_key]
        bucket[1] += count
        if guild:
            by_server[guild] = by_server.get(guild, 0) + count
            nested = by_server_accounts.setdefault(guild, {})
            nested_bucket = nested.get(acc_key)
            if nested_bucket is None:
                nested[acc_key] = [acc_label, 0]
                nested_bucket = nested[acc_key]
            nested_bucket[1] += count

    def _items(mapping: dict[str, list[Any]]) -> list[dict[str, Any]]:
        rows = [
            {"id": key, "label": values[0], "count": values[1]}
            for key, values in mapping.items()
        ]
        rows.sort(key=lambda row: row["count"], reverse=True)
        return rows

    return {
        "by_account": _items(by_account),
        "by_server": [
            {"id": key, "label": key, "count": by_server[key]}
            for key in sorted(by_server, key=lambda i: by_server[i], reverse=True)
        ],
        "by_server_accounts": {
            server: _items(accounts) for server, accounts in by_server_accounts.items()
        },
    }


def _recent_page(
    kind: str,
    accounts_store: Any,
    *,
    account: str,
    server: str,
    method: str,
    type_id: str,
    offset: int,
    limit: int,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    from mudae import event_log

    del accounts_store
    enrich = _enricher(kind)
    seen = 0
    page: list[dict[str, Any]] = []
    for entry in reversed(event_log.events(kind)):
        if not _entry_matches(
            kind,
            entry,
            account=account,
            server=server,
            method=method,
            type_id=type_id,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        ):
            continue
        if seen >= offset:
            page.append(
                enrich(
                    entry,
                    account_by_id=account_by_id,
                    main_account_id=main_id,
                    main_account_name=main_name,
                )
            )
            if len(page) >= limit:
                break
        seen += 1
    count = _filtered_event_count(
        kind,
        account=account,
        server=server,
        method=method,
        type_id=type_id,
        main_id=main_id,
        main_name=main_name,
        account_by_id=account_by_id,
    )
    return page, count


def _filtered_event_count(
    kind: str,
    *,
    account: str,
    server: str,
    method: str,
    type_id: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> int:
    total = 0
    with _lock:
        for key, (_amount, count) in _cells[kind].items():
            if _cell_matches(
                kind,
                key,
                account=account,
                server=server,
                method=method,
                type_id=type_id,
                main_id=main_id,
                main_name=main_name,
                account_by_id=account_by_id,
            ):
                total += count
    return total


def _entry_matches(
    kind: str,
    entry: dict[str, Any],
    *,
    account: str,
    server: str,
    method: str,
    type_id: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> bool:
    if account != "all":
        resolved, _, _ = resolve_log_account(
            entry,
            account_by_id=account_by_id,
            default_account_id=main_id,
            default_account_name=main_name,
        )
        if resolved != account:
            return False
    if server != "all" and _guild_key(entry) != server:
        return False
    meth, typ = _method_and_type(kind, entry)
    if method != "all" and meth != method:
        return False
    if type_id != "all" and typ != type_id:
        return False
    return True


def _enricher(kind: str):
    if kind == "kakera":
        from mudae.kakera_log import enrich_entry

        return enrich_entry
    if kind == "sphere":
        from mudae.sphere_log import enrich_entry

        return enrich_entry
    if kind == "key":
        from mudae.key_log import enrich_entry

        return enrich_entry
    from mudae.soulmate_log import enrich_entry

    return enrich_entry
