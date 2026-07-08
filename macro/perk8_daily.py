"""Per-account daily reset tracking (persisted on channel profiles)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

PERK8_MIN_ROLL_POOL = 10
PERK8_DAILY_KEY = "perk8"
PERK8_DEFAULT_REFILL_MINUTES = 24 * 60
PERK8_DAILY_CLICK_BUDGET = 40


class Perk8PriorityMode(str, Enum):
    """How ``perk_8_budget_mode`` should behave for the current session."""

    INACTIVE = "inactive"  # budget mode off, or not checked
    ACTIVE = "active"  # prioritize perk-8 kakera until daily clicks used
    DONE = "done"  # 40/40 — equal clicking for rest of daily cycle
    INSUFFICIENT_POOL = "insufficient_pool"  # roll pool < 10 — equal clicking


@dataclass
class Perk8DailyRecord:
    """Persisted perk-8 daily state for one account on one channel."""

    clicks_exhausted: bool = False
    refill_at: str = ""  # ISO-8601 UTC when daily clicks are expected back
    last_refill_minutes: int | None = None
    last_clicked: int | None = None
    last_click_max: int | None = None
    last_roll_pool: int | None = None
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Perk8DailyRecord:
        if not data:
            return cls()
        return cls(
            clicks_exhausted=bool(data.get("clicks_exhausted", False)),
            refill_at=str(data.get("refill_at") or ""),
            last_refill_minutes=_coerce_int(data.get("last_refill_minutes")),
            last_clicked=_coerce_int(data.get("last_clicked")),
            last_click_max=_coerce_int(data.get("last_click_max")),
            last_roll_pool=_coerce_int(data.get("last_roll_pool")),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clicks_exhausted": self.clicks_exhausted,
            "refill_at": self.refill_at,
            "last_refill_minutes": self.last_refill_minutes,
            "last_clicked": self.last_clicked,
            "last_click_max": self.last_click_max,
            "last_roll_pool": self.last_roll_pool,
            "updated_at": self.updated_at,
        }


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(dt_value: dt.datetime) -> str:
    return dt_value.astimezone(dt.timezone.utc).isoformat()


def _parse_iso(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def load_perk8_record(daily_resets: dict[str, Any] | None) -> Perk8DailyRecord:
    if not daily_resets:
        return Perk8DailyRecord()
    raw = daily_resets.get(PERK8_DAILY_KEY)
    if isinstance(raw, dict):
        return Perk8DailyRecord.from_dict(raw)
    return Perk8DailyRecord()


def save_perk8_record(
    daily_resets: dict[str, Any],
    record: Perk8DailyRecord,
) -> dict[str, Any]:
    updated = dict(daily_resets or {})
    updated[PERK8_DAILY_KEY] = record.to_dict()
    return updated


def _set_refill_deadline(
    record: Perk8DailyRecord,
    now: dt.datetime,
    *,
    refill_minutes: int | None = None,
) -> None:
    """Persist when perk-8 clicks are expected back."""
    minutes = refill_minutes if refill_minutes is not None else record.last_refill_minutes
    if minutes is not None and minutes > 0:
        deadline = now + dt.timedelta(minutes=minutes)
        midnight = _next_utc_midnight(now)
        if deadline > midnight:
            deadline = midnight
        record.last_refill_minutes = int((deadline - now).total_seconds() // 60) or 1
        record.refill_at = _iso(deadline)
        return
    midnight = _next_utc_midnight(now)
    record.last_refill_minutes = int((midnight - now).total_seconds() // 60) or 1
    record.refill_at = _iso(midnight)


def _next_utc_midnight(now: dt.datetime) -> dt.datetime:
    """Next UTC midnight — Mudae daily perk-8 reset when shifthour is 0."""
    day = now.astimezone(dt.timezone.utc).date()
    return dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0), tzinfo=dt.timezone.utc)


def refresh_exhausted_if_refill_passed(
    record: Perk8DailyRecord,
    *,
    now: dt.datetime | None = None,
) -> Perk8DailyRecord:
    """Clear a stale exhausted flag once the daily refill has passed."""
    if not record.clicks_exhausted:
        return record
    now = now or _utc_now()
    updated = _parse_iso(record.updated_at)
    if updated is not None and updated.astimezone(dt.timezone.utc).date() < now.date():
        record.clicks_exhausted = False
        return record
    refill_at = _parse_iso(record.refill_at)
    if refill_at is not None and now >= refill_at:
        record.clicks_exhausted = False
    return record


def sync_refill_deadline(
    record: Perk8DailyRecord,
    refill_minutes: int,
    *,
    now: dt.datetime | None = None,
) -> Perk8DailyRecord:
    """Persist the next refill ETA from ``$tu`` / ``$ohu8`` text."""
    if refill_minutes <= 0:
        return record
    now = now or _utc_now()
    record.last_refill_minutes = int(refill_minutes)
    record.refill_at = _iso(now + dt.timedelta(minutes=int(refill_minutes)))
    return record


def _clicks_below_cap(record: Perk8DailyRecord) -> bool:
    return (
        record.last_clicked is not None
        and record.last_click_max is not None
        and int(record.last_clicked) < int(record.last_click_max)
    )


def should_skip_ohu8_until_refill(
    record: Perk8DailyRecord,
    *,
    now: dt.datetime | None = None,
) -> bool:
    """True when daily perk-8 clicks are spent and the refill ETA has not passed."""
    now = now or _utc_now()
    record = refresh_exhausted_if_refill_passed(record, now=now)
    if not record.clicks_exhausted:
        return False
    if _clicks_below_cap(record):
        return False
    refill_at = _parse_iso(record.refill_at)
    if refill_at is None:
        return True
    return now < refill_at


def should_query_ohu8_on_refill(
    record: Perk8DailyRecord,
    *,
    now: dt.datetime | None = None,
) -> bool:
    """True when a mid-session ``$ohu8`` re-query is warranted (refill passed, etc.)."""
    now = now or _utc_now()
    if record.clicks_exhausted and _clicks_below_cap(record):
        return True
    refill_at = _parse_iso(record.refill_at)
    if refill_at is not None and now >= refill_at:
        if record.clicks_exhausted:
            return True
        clicked = record.last_clicked
        cap = record.last_click_max
        if clicked is not None and cap is not None and int(clicked) >= int(cap):
            return True
    return False


def apply_cached_perk8(record: Perk8DailyRecord) -> Perk8PriorityMode:
    """Derive session mode from persisted state without querying Mudae."""
    if record.clicks_exhausted:
        if _clicks_below_cap(record):
            return Perk8PriorityMode.ACTIVE
        return Perk8PriorityMode.DONE
    if (
        record.last_roll_pool is not None
        and record.last_roll_pool < PERK8_MIN_ROLL_POOL
    ):
        return Perk8PriorityMode.INSUFFICIENT_POOL
    return Perk8PriorityMode.ACTIVE


def mode_from_ohu8_fields(fields: dict[str, Any]) -> Perk8PriorityMode:
    clicked = fields.get("perk8_clicked_today")
    click_max = fields.get("perk8_click_max")
    roll_pool = fields.get("perk8_roll_pool")

    if clicked is not None and click_max is not None and int(clicked) >= int(click_max):
        return Perk8PriorityMode.DONE

    if roll_pool is not None and int(roll_pool) < PERK8_MIN_ROLL_POOL:
        return Perk8PriorityMode.INSUFFICIENT_POOL

    return Perk8PriorityMode.ACTIVE


def update_record_from_ohu8(
    record: Perk8DailyRecord,
    fields: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> tuple[Perk8DailyRecord, Perk8PriorityMode]:
    """Merge a fresh ``$ohu8`` parse into persisted state."""
    now = now or _utc_now()
    mode = mode_from_ohu8_fields(fields)

    clicked = _coerce_int(fields.get("perk8_clicked_today"))
    click_max = _coerce_int(fields.get("perk8_click_max"))
    roll_pool = _coerce_int(fields.get("perk8_roll_pool"))
    refill_minutes = _coerce_int(fields.get("perk8_refill_minutes"))

    record.last_clicked = clicked
    record.last_click_max = click_max
    record.last_roll_pool = roll_pool
    record.updated_at = _iso(now)
    if refill_minutes is not None:
        record.last_refill_minutes = refill_minutes
        sync_refill_deadline(record, refill_minutes, now=now)

    if mode is Perk8PriorityMode.DONE:
        record.clicks_exhausted = True
        if refill_minutes is None:
            _set_refill_deadline(record, now)
    else:
        record.clicks_exhausted = False

    return record, mode


def mark_perk8_exhausted(
    record: Perk8DailyRecord,
    *,
    now: dt.datetime | None = None,
    clicked_today: int | None = None,
) -> Perk8DailyRecord:
    """Mark clicks done mid-session using the last known refill ETA."""
    now = now or _utc_now()
    record.clicks_exhausted = True
    record.updated_at = _iso(now)
    _set_refill_deadline(record, now)
    if clicked_today is not None:
        record.last_clicked = int(clicked_today)
    elif record.last_click_max is not None:
        record.last_clicked = record.last_click_max
    return record


def perk8_budget_applies(mode: Perk8PriorityMode) -> bool:
    return mode is Perk8PriorityMode.ACTIVE


def perk8_requirements_relaxed(mode: Perk8PriorityMode) -> bool:
    """When True, ``require_perk_8`` and budget priority are not enforced."""
    return mode in (Perk8PriorityMode.DONE, Perk8PriorityMode.INSUFFICIENT_POOL)
