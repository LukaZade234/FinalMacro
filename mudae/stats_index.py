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
from mudae.constants import canonical_sphere_emoji

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
    from mudae import event_log

    event_log.ensure_loaded()
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


REPORT_TREND_DAYS = 14
REPORT_BASELINE_DAYS = 7


def daily_report(
    accounts_store: Any,
    *,
    date_key: str = "",
    account: str = "all",
    server: str = "all",
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """One UTC day rolled up across every kind, against its recent baseline.

    The Statistics sub-views slice the cube by kind; this slices the same cells
    by *day* instead, which is the shape you want when asking "how did
    yesterday go" rather than "how is kakera trending".

    ``delta_pct`` compares the day against the mean of the ``REPORT_BASELINE_DAYS``
    days before it — not against all history, so a long-running account is judged
    on its current pace. Days with no baseline report ``None`` rather than 0%,
    because "no comparison" is not "no change".
    """
    from mudae import event_log

    event_log.ensure_loaded()
    main_id, main_name, account_by_id = defaults_from_store(accounts_store)
    account = _norm_filter(account)
    server = _norm_filter(server)
    now = now or dt.datetime.now(dt.timezone.utc)

    with _lock:
        days = _report_days_unlocked(
            account=account,
            server=server,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
        target = str(date_key or "").strip()[:10]
        if not target:
            target = days[-1] if days else utc_date_key(now)

        target_day = _parse_day(target)
        baseline_days: list[str] = []
        trend_days: list[str] = []
        if target_day is not None:
            for offset in range(1, REPORT_BASELINE_DAYS + 1):
                baseline_days.append((target_day - dt.timedelta(days=offset)).isoformat())
            for offset in range(REPORT_TREND_DAYS - 1, -1, -1):
                trend_days.append((target_day - dt.timedelta(days=offset)).isoformat())

        kinds: dict[str, Any] = {}
        for kind in KINDS:
            kinds[kind] = _report_kind_unlocked(
                kind,
                target=target,
                baseline_days=baseline_days,
                account=account,
                server=server,
                main_id=main_id,
                main_name=main_name,
                account_by_id=account_by_id,
            )

        trend = []
        for day in trend_days:
            row: dict[str, Any] = {"date": day}
            for kind in KINDS:
                row[kind] = _report_day_total_unlocked(
                    kind,
                    day=day,
                    account=account,
                    server=server,
                    main_id=main_id,
                    main_name=main_name,
                    account_by_id=account_by_id,
                )
            trend.append(row)

        for kind in KINDS:
            kinds[kind]["all_time"] = _report_all_time(
                kind,
                target=target,
                account=account,
                server=server,
                main_id=main_id,
                main_name=main_name,
                account_by_id=account_by_id,
            )

        matrix_args = dict(
            day=target,
            account=account,
            server=server,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
        # Kakera types only exist on clicks, so the colour split is taken over
        # clicks alone — $bku payouts and $dk carry no colour at all.
        breakdowns = {
            "kakera": _report_matrix("kakera", only_method="kakera_click", **matrix_args),
            "sphere": _report_matrix("sphere", **matrix_args),
            "key": _report_matrix("key", **matrix_args),
        }

        options = _filter_options_unlocked(
            "kakera",
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )

    # Outside the lock: these read the raw event lists rather than the cube,
    # because the cube keeps neither the hour an event landed nor its order.
    row_args = dict(
        account=account,
        server=server,
        main_id=main_id,
        main_name=main_name,
        account_by_id=account_by_id,
    )
    rows = {kind: _day_rows(kind, target, **row_args) for kind in KINDS}

    # Perk 8 and perk 9 are *per account, per server* allowances: every pairing
    # gets its own forty kakera clicks and its own sphere spawns, and each
    # expires on its own at the UTC reset. Laying two of them on one tape reads
    # as a single account spending a budget nobody has, so the tapes are drawn
    # only for a report narrowed to one account on one server.
    scoped = account != "all" and server != "all"

    from mudae import minigame_stats

    return {
        "date": target,
        "available_days": days,
        "kinds": kinds,
        "trend": trend,
        "breakdowns": breakdowns,
        "hourly": {
            "kakera_by_method": _hourly(rows["kakera"], "kakera", split_method=True),
            "sphere": _hourly(rows["sphere"], "sphere", split_method=False),
            "key": _hourly(rows["key"], "key", split_method=False),
        },
        "tapes": {
            "perk8": _perk8_tape(rows["kakera"], scoped=scoped),
            "perk9": _perk9_tape(rows["sphere"], scoped=scoped),
        },
        "scope": {"account": account, "server": server, "scoped": scoped},
        "soulmates": _soulmate_rows(rows["soulmate"]),
        "minigames": minigame_stats.daily_yield(target, account=account, server=server),
        "filter_options": {
            "accounts": options.get("accounts", []),
            "servers": options.get("servers", []),
        },
    }


def _report_days_unlocked(
    *,
    account: str,
    server: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> list[str]:
    seen: set[str] = set()
    for kind in KINDS:
        for key in _cells[kind]:
            if not key[0]:
                continue
            if not _cell_matches(
                kind,
                key,
                account=account,
                server=server,
                method="all",
                type_id="all",
                main_id=main_id,
                main_name=main_name,
                account_by_id=account_by_id,
            ):
                continue
            seen.add(key[0])
    return sorted(seen)


def _report_day_total_unlocked(
    kind: str,
    *,
    day: str,
    account: str,
    server: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> int:
    total = 0
    for key, cell in _cells[kind].items():
        if key[0] != day:
            continue
        if not _cell_matches(
            kind,
            key,
            account=account,
            server=server,
            method="all",
            type_id="all",
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        ):
            continue
        total += cell[0] if kind != "soulmate" else cell[1]
    return total


def _report_kind_unlocked(
    kind: str,
    *,
    target: str,
    baseline_days: list[str],
    account: str,
    server: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> dict[str, Any]:
    by_method: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = 0
    count = 0
    baseline_lookup = set(baseline_days)
    baseline_total = 0
    baseline_seen: set[str] = set()

    for key, cell in _cells[kind].items():
        day = key[0]
        on_target = day == target
        on_baseline = day in baseline_lookup
        if not on_target and not on_baseline:
            continue
        if not _cell_matches(
            kind,
            key,
            account=account,
            server=server,
            method="all",
            type_id="all",
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        ):
            continue
        # Soulmates have no amount — the row itself is the event.
        amount = cell[0] if kind != "soulmate" else cell[1]
        if on_target:
            total += amount
            count += cell[1]
            if key[3]:
                by_method[key[3]] = by_method.get(key[3], 0) + amount
            if key[4]:
                by_type[key[4]] = by_type.get(key[4], 0) + amount
        else:
            baseline_total += amount
            baseline_seen.add(day)

    average = baseline_total / len(baseline_seen) if baseline_seen else None
    delta_pct: float | None = None
    if average:
        delta_pct = round((total - average) / average * 100.0, 1)

    return {
        "total": total,
        "count": count,
        "average": round(average, 1) if average is not None else None,
        "delta_pct": delta_pct,
        "baseline_days": len(baseline_seen),
        "by_method": _labeled_series(kind, "method", by_method),
        "by_type": _labeled_series(kind, "type", by_type),
    }


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
        sphere_type = str(entry.get("sphere_type") or "").strip()
        if sphere_type:
            sphere_type = canonical_sphere_emoji(sphere_type)
        return method or "unknown", sphere_type
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
    if kind == "kakera" and field == "type":
        from mudae.constants import KAKERA_INFO

        info = KAKERA_INFO.get(item_id)
        if info:
            return str(info.get("label") or item_id)
    if kind == "sphere" and field == "type":
        from mudae.constants import sphere_label

        if item_id:
            return sphere_label(item_id)
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


# --- daily report detail ------------------------------------------------------
#
# The cube is aggregated per (day, account, guild, method, type), which covers
# every total and share the report needs. Two things it deliberately does not
# keep are the time an event happened and the order events arrived in, so the
# hourly panels and the click tapes read the day's raw events instead. One day
# is a cheap scan over an already-loaded list.

# Mudae grants 40 kakera clicks a day on perk-8 characters
# (docs/MUDAE_LOGIC.md, "Perk 8"). Purple is free power on every roll and cannot
# spawn on a perk-8 character, so a purple click never consumes a slot.
PERK8_DAILY_CLICKS = 40
PERK8_FREE_COLOURS = frozenset({"kakeraP"})


def _entry_hour(entry: dict[str, Any]) -> int | None:
    raw = str(entry.get("time") or "")
    if len(raw) >= 2 and raw[:2].isdigit():
        hour = int(raw[:2])
        return hour if 0 <= hour < 24 else None
    stamp = parse_iso_datetime(str(entry.get("recorded_at") or ""))
    return stamp.astimezone(dt.timezone.utc).hour if stamp is not None else None


def _entry_sort_key(entry: dict[str, Any]) -> str:
    """Order within a day: the clock time, falling back to the full stamp."""
    return str(entry.get("time") or entry.get("recorded_at") or "")


def _raw_matches(
    entry: dict[str, Any],
    *,
    account: str,
    server: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> bool:
    """Account/server filtering for a raw event, matching ``_cell_matches``."""
    if account != "all":
        resolved, _name, _inferred = _resolve_account(
            str(entry.get("account_id") or ""),
            str(entry.get("account_name") or ""),
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
        if resolved != account:
            return False
    if server != "all" and _guild_key(entry) != server:
        return False
    return True


def _day_rows(
    kind: str,
    day: str,
    *,
    account: str,
    server: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> list[dict[str, Any]]:
    from mudae import event_log

    rows = [
        entry
        for entry in event_log.events(kind)
        if _date_key(entry) == day
        and _raw_matches(
            entry,
            account=account,
            server=server,
            main_id=main_id,
            main_name=main_name,
            account_by_id=account_by_id,
        )
    ]
    rows.sort(key=_entry_sort_key)
    return rows


def _report_all_time(
    kind: str,
    *,
    target: str,
    account: str,
    server: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
) -> dict[str, Any]:
    """The day against the mean of every day that saw activity.

    The mean is over *active* days, not calendar days: a gap where the macro was
    not running is not a zero-earning day, and averaging it in would quietly
    flatter every day that follows.
    """
    per_day: dict[str, int] = {}
    for key, cell in _cells[kind].items():
        day = key[0]
        if not day:
            continue
        if not _cell_matches(
            kind, key, account=account, server=server, method="all", type_id="all",
            main_id=main_id, main_name=main_name, account_by_id=account_by_id,
        ):
            continue
        amount = cell[0] if kind != "soulmate" else cell[1]
        per_day[day] = per_day.get(day, 0) + amount

    total = per_day.get(target, 0)
    others = {day: value for day, value in per_day.items() if day != target}
    average = (sum(others.values()) / len(others)) if others else None
    delta = None
    if average:
        delta = round((total - average) / average * 100.0, 1)
    return {
        "average": round(average, 1) if average is not None else None,
        "delta_pct": delta,
        "active_days": len(per_day),
    }


def _report_matrix(
    kind: str,
    *,
    day: str,
    account: str,
    server: str,
    main_id: str,
    main_name: str,
    account_by_id: dict[str, Any],
    only_method: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Amount **and** event count per method and per type for one day.

    ``only_method`` narrows the type breakdown, which is what makes the kakera
    colour split honest: ``$bku`` payouts and ``$dk`` carry no kakera type at
    all, so a colour share has to be taken over clicks alone rather than over
    the day's whole take.
    """
    methods: dict[str, list[int]] = {}
    types: dict[str, list[int]] = {}
    for key, cell in _cells[kind].items():
        if key[0] != day:
            continue
        if not _cell_matches(
            kind, key, account=account, server=server, method="all", type_id="all",
            main_id=main_id, main_name=main_name, account_by_id=account_by_id,
        ):
            continue
        amount = cell[0] if kind != "soulmate" else cell[1]
        if key[3]:
            row = methods.setdefault(key[3], [0, 0])
            row[0] += amount
            row[1] += cell[1]
        if key[4] and (not only_method or key[3] == only_method):
            row = types.setdefault(key[4], [0, 0])
            row[0] += amount
            row[1] += cell[1]

    def _rows(field: str, source: dict[str, list[int]]) -> list[dict[str, Any]]:
        return [
            {
                "id": item_id,
                "label": _label_for(kind, field, item_id),
                "amount": pair[0],
                "count": pair[1],
            }
            for item_id, pair in sorted(
                source.items(), key=lambda pair: pair[1][0], reverse=True
            )
        ]

    return {"by_method": _rows("method", methods), "by_type": _rows("type", types)}


def _hourly(rows: list[dict[str, Any]], kind: str, *, split_method: bool) -> Any:
    if not split_method:
        out = [0] * 24
        for entry in rows:
            hour = _entry_hour(entry)
            if hour is None:
                continue
            out[hour] += _amount(kind, entry)
        return out

    buckets: dict[str, list[int]] = {}
    for entry in rows:
        hour = _entry_hour(entry)
        if hour is None:
            continue
        method, _type_id = _method_and_type(kind, entry)
        buckets.setdefault(method, [0] * 24)[hour] += _amount(kind, entry)
    return [
        {"id": method, "label": _label_for(kind, "method", method), "values": values}
        for method, values in sorted(
            buckets.items(), key=lambda pair: sum(pair[1]), reverse=True
        )
    ]


# Said in the payload rather than in the view, so every shell that draws a tape
# gives the same reason for an empty one.
TAPE_SCOPE_NOTE = (
    "Perk 8 and perk 9 have their own daily allowance on every account and "
    "server, so they cannot be added up. Pick one account and one server above "
    "to see the day's clicks."
)


def _unscoped_tape() -> dict[str, Any]:
    """An empty tape that says why it is empty, not a tape of zero clicks."""
    return {
        "slots": [],
        "cap": None,
        "scoped": False,
        "exact": False,
        "note": TAPE_SCOPE_NOTE,
    }


def _perk8_tape(rows: list[dict[str, Any]], *, scoped: bool = True) -> dict[str, Any]:
    """The colours that plausibly spent the day's 40 perk-8 clicks.

    The log does not mark *which* click consumed a perk-8 slot, so this is an
    approximation and the payload says so. Purple is excluded because it cannot
    spawn on a perk-8 character and so never takes one; what is left is taken in
    time order up to the daily budget.

    ``scoped`` is false when the report covers more than one account or server,
    where there is no single budget to lay these clicks against.
    """
    if not scoped:
        return _unscoped_tape()
    clicks = [
        entry for entry in rows
        if _method_and_type("kakera", entry)[0] == "kakera_click"
        and str(entry.get("kakera_type") or "") not in PERK8_FREE_COLOURS
        and str(entry.get("kakera_type") or "")
    ]
    slots = [
        {
            "id": str(entry.get("kakera_type") or ""),
            "label": _label_for("kakera", "type", str(entry.get("kakera_type") or "")),
            "amount": _amount("kakera", entry),
            "time": str(entry.get("time") or ""),
        }
        for entry in clicks[:PERK8_DAILY_CLICKS]
    ]
    return {
        "slots": slots,
        "cap": PERK8_DAILY_CLICKS,
        "candidates": len(clicks),
        "exact": False,
        "scoped": True,
        "note": (
            "Purple is excluded because it cannot spawn on a perk-8 character. "
            "The log does not record which click consumed a slot, so these are "
            "the day's first non-purple reactions."
        ),
    }


def _perk9_tape(rows: list[dict[str, Any]], *, scoped: bool = True) -> dict[str, Any]:
    """Every sphere button clicked that day, in the order they were clicked.

    Empty when the report is not narrowed to one account on one server: the
    spawns of two accounts interleaved would not be either account's day.
    """
    if not scoped:
        return _unscoped_tape()
    from mudae.constants import SPHERE_TRANSFORM_EMOJIS

    slots = []
    for entry in rows:
        if str(entry.get("source") or "") != "sphere_click":
            continue
        sphere = canonical_sphere_emoji(str(entry.get("sphere_type") or ""))
        resolved = [
            canonical_sphere_emoji(str(item))
            for item in (entry.get("sphere_resolved") or [])
            if item
        ]
        slots.append({
            "id": sphere,
            "label": _label_for("sphere", "type", sphere),
            "amount": _amount("sphere", entry),
            "time": str(entry.get("time") or ""),
            # A transform is spent as one colour and pays out as others. The tape
            # shows the sphere that was clicked; what it became is named on hover,
            # so the tile stays a record of what was pressed.
            "transform": sphere in SPHERE_TRANSFORM_EMOJIS,
            "resolved": resolved,
        })
    return {"slots": slots, "cap": None, "exact": True, "scoped": True}


def _soulmate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "character": str(entry.get("character_name") or "").strip(),
            "series": str(entry.get("series") or "").strip(),
            "time": str(entry.get("time") or "")[:5],
            "server": _guild_key(entry),
            "starwish": bool(entry.get("starwish")),
        }
        for entry in rows
    ]
