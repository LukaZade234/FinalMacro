"""Perk 9 daily sphere-button click budget.

Persisted on the channel profile (``daily_resets.perk9``) so a restart can
restore the Run-tab counter. The reactor does not skip at the cap — Mudae
stops spawning those buttons on its own.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from macro.perk8_daily import mudae_daily_date, next_daily_reset, parse_iso
from mudae.constants import SPHERE_ROLL_FREE_EMOJIS
from mudae.sphere_log import get_sphere_events, normalize_source

# Default daily cap when ``$shop`` has not been fetched (10 base + 10 OP9).
PERK9_CLICK_MAX_DEFAULT = 20
PERK9_DAILY_KEY = "perk9"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(dt_value: dt.datetime) -> str:
    return dt_value.astimezone(dt.timezone.utc).isoformat()


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_perk9_click_from_parse(state: Any, fields: dict[str, Any]) -> bool:
    """Update the Run-tab perk 9 counter from a parsed roll-button confirmation.

    Mudae's ``(used/max)`` is the source of truth, so a missed or extra local
    increment is corrected on the next parsed click. Megasphere is ignored.
    Returns True when the persisted counter should be saved.
    """
    if not is_perk9_sphere_click(fields.get("sphere_type")):
        return False
    cap = _coerce_int(fields.get("daily_max"))
    used = _coerce_int(fields.get("daily_used"))
    rollover = getattr(state, "rollover_perk9_if_needed", None)
    if callable(rollover):
        rollover()
    if cap is not None:
        state.perk9_click_max = cap
    if used is not None:
        state.perk9_clicks_today = used
        return True
    record = getattr(state, "record_perk9_click", None)
    if callable(record):
        record()
        return True
    return False


def is_perk9_sphere_click(sphere_type: str | None) -> bool:
    """True when a sphere-button click should consume perk 9 (not megasphere)."""
    if not sphere_type:
        return True
    key = str(sphere_type).strip()
    return key not in SPHERE_ROLL_FREE_EMOJIS and key.lower() not in {
        emoji.lower() for emoji in SPHERE_ROLL_FREE_EMOJIS
    }


def count_perk9_clicks(events: list[dict[str, Any]], *, date_key: str) -> int:
    """Count today's perk-9 sphere-button clicks from the earning log."""
    total = 0
    for entry in events:
        if entry.get("date_key") != date_key:
            continue
        if normalize_source(entry) != "sphere_click":
            continue
        if not is_perk9_sphere_click(entry.get("sphere_type")):
            continue
        total += 1
    return total


def sync_perk9_clicks_from_log(state: Any) -> None:
    """Raise ``state.perk9_clicks_today`` to match logged clicks for today."""
    from mudae.clock import utc_date_key

    rollover = getattr(state, "rollover_perk9_if_needed", None)
    if callable(rollover):
        rollover()
    today = utc_date_key()
    counted = count_perk9_clicks(get_sphere_events(), date_key=today)
    current = int(getattr(state, "perk9_clicks_today", 0) or 0)
    if counted > current:
        state.perk9_clicks_today = counted
        state.perk9_clicks_day = today


@dataclass
class Perk9DailyRecord:
    """Persisted perk-9 / megasphere daily state for one account on one channel."""

    clicks_exhausted: bool = False
    last_clicked: int | None = None
    last_click_max: int | None = None
    megasphere_exhausted: bool = False
    stock: int | None = None
    refill_at: str = ""
    last_refill_minutes: int | None = None
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Perk9DailyRecord:
        if not data:
            return cls()
        return cls(
            clicks_exhausted=bool(data.get("clicks_exhausted", False)),
            last_clicked=_coerce_int(data.get("last_clicked")),
            last_click_max=_coerce_int(data.get("last_click_max")),
            megasphere_exhausted=bool(data.get("megasphere_exhausted", False)),
            stock=_coerce_int(data.get("stock")),
            refill_at=str(data.get("refill_at") or ""),
            last_refill_minutes=_coerce_int(data.get("last_refill_minutes")),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clicks_exhausted": self.clicks_exhausted,
            "last_clicked": self.last_clicked,
            "last_click_max": self.last_click_max,
            "megasphere_exhausted": self.megasphere_exhausted,
            "stock": self.stock,
            "refill_at": self.refill_at,
            "last_refill_minutes": self.last_refill_minutes,
            "updated_at": self.updated_at,
        }


def load_perk9_record(daily_resets: dict[str, Any] | None) -> Perk9DailyRecord:
    if not daily_resets:
        return Perk9DailyRecord()
    raw = daily_resets.get(PERK9_DAILY_KEY)
    if isinstance(raw, dict):
        return Perk9DailyRecord.from_dict(raw)
    return Perk9DailyRecord()


def save_perk9_record(
    daily_resets: dict[str, Any],
    record: Perk9DailyRecord,
) -> dict[str, Any]:
    updated = dict(daily_resets or {})
    updated[PERK9_DAILY_KEY] = record.to_dict()
    return updated


def _set_refill_deadline(
    record: Perk9DailyRecord,
    now: dt.datetime,
    *,
    refill_minutes: int | None = None,
) -> None:
    minutes = refill_minutes if refill_minutes is not None else record.last_refill_minutes
    if minutes is not None and minutes > 0:
        deadline = now + dt.timedelta(minutes=minutes)
        reset_at = next_daily_reset(now)
        if deadline > reset_at:
            deadline = reset_at
        record.last_refill_minutes = int((deadline - now).total_seconds() // 60) or 1
        record.refill_at = _iso(deadline)
        return
    reset_at = next_daily_reset(now)
    record.last_refill_minutes = int((reset_at - now).total_seconds() // 60) or 1
    record.refill_at = _iso(reset_at)


def refresh_exhausted_if_refill_passed(
    record: Perk9DailyRecord,
    *,
    now: dt.datetime | None = None,
) -> Perk9DailyRecord:
    """Clear stale perk-9 / megasphere flags once the daily refill has passed."""
    now = now or _utc_now()
    updated = parse_iso(record.updated_at)
    refill_at = parse_iso(record.refill_at)
    new_day = bool(
        updated is not None and mudae_daily_date(updated) < mudae_daily_date(now)
    )
    refill_passed = bool(refill_at is not None and now >= refill_at)
    if not (new_day or refill_passed):
        return record
    record.clicks_exhausted = False
    record.megasphere_exhausted = False
    if new_day or refill_passed:
        record.last_clicked = 0 if record.last_click_max is not None else None
    return record


def _clicks_at_cap(record: Perk9DailyRecord) -> bool:
    return (
        record.last_clicked is not None
        and record.last_click_max is not None
        and int(record.last_clicked) >= int(record.last_click_max)
    )


def update_record_from_ohu(
    record: Perk9DailyRecord,
    fields: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> Perk9DailyRecord:
    """Merge ``buttons clicked`` / megasphere / stock from ``$ohu`` / ``$ohu8``."""
    now = now or _utc_now()
    clicked = _coerce_int(fields.get("perk9_clicked_today"))
    click_max = _coerce_int(fields.get("perk9_click_max"))
    stock = _coerce_int(fields.get("sphere_stock"))
    refill_minutes = _coerce_int(
        fields.get("perk8_refill_minutes") or fields.get("refill_minutes")
    )
    megasphere_left = fields.get("megasphere_left")

    if clicked is not None:
        record.last_clicked = clicked
    if click_max is not None:
        record.last_click_max = click_max
    if stock is not None:
        record.stock = stock
    if megasphere_left is False:
        record.megasphere_exhausted = True
    elif megasphere_left is True:
        record.megasphere_exhausted = False

    record.updated_at = _iso(now)
    if refill_minutes is not None:
        record.last_refill_minutes = refill_minutes
        _set_refill_deadline(record, now, refill_minutes=refill_minutes)

    if _clicks_at_cap(record):
        record.clicks_exhausted = True
        if refill_minutes is None:
            _set_refill_deadline(record, now)
    elif clicked is not None:
        record.clicks_exhausted = False
    return record


def persist_click_progress(
    record: Perk9DailyRecord,
    *,
    clicked_today: int,
    click_max: int | None = None,
    now: dt.datetime | None = None,
) -> Perk9DailyRecord:
    """Write the live click counter back; mark exhausted at the cap."""
    now = now or _utc_now()
    record.last_clicked = int(clicked_today)
    if click_max is not None:
        record.last_click_max = int(click_max)
    record.updated_at = _iso(now)
    if _clicks_at_cap(record):
        record.clicks_exhausted = True
        _set_refill_deadline(record, now)
    else:
        record.clicks_exhausted = False
    return record


def apply_record_to_state(
    state: Any,
    record: Perk9DailyRecord,
    *,
    now: dt.datetime | None = None,
) -> None:
    """Copy persisted perk-9 clicks onto runtime state for the GUI."""
    from mudae.clock import utc_date_key

    now = now or _utc_now()
    record = refresh_exhausted_if_refill_passed(record, now=now)
    if (
        record.last_clicked is None
        and record.last_click_max is None
        and not record.clicks_exhausted
    ):
        return

    updated = parse_iso(record.updated_at)
    refill_at = parse_iso(record.refill_at)
    new_day = bool(
        (updated is not None and mudae_daily_date(updated) < mudae_daily_date(now))
        or (refill_at is not None and now >= refill_at)
    )
    if record.last_click_max is not None:
        state.perk9_click_max = int(record.last_click_max)
    if new_day:
        state.perk9_clicks_today = 0
        state.perk9_clicks_day = utc_date_key(now)
        return

    clicked = record.last_clicked
    if clicked is None and record.clicks_exhausted and record.last_click_max is not None:
        clicked = record.last_click_max
    if clicked is not None:
        state.perk9_clicks_today = int(clicked)
        state.perk9_clicks_day = utc_date_key(now)
