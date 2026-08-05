"""Extrapolate Mudae roll/claim timers from ``$settings`` + saved ``$tu`` deadlines."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from macro.perk8_daily import parse_iso

HOURLY_ROLL_PERIOD_MINUTES = 60


@dataclass(frozen=True)
class MudaeResetSchedule:
    setrolls: int | None = None
    setclaim: int | None = None
    setinterval: int = 0
    shifthour: int = 0

    @classmethod
    def from_sources(
        cls,
        settings: dict[str, Any] | None = None,
        record_fields: dict[str, Any] | None = None,
    ) -> MudaeResetSchedule:
        settings = settings or {}
        record_fields = record_fields or {}

        def pick(key: str, default: int | None = None) -> int | None:
            for source in (settings, record_fields):
                val = source.get(key)
                if val is None or val == "":
                    continue
                try:
                    return int(val)
                except (TypeError, ValueError):
                    continue
            return default

        interval = pick("setinterval", 0)
        shift = pick("shifthour", 0)
        return cls(
            setrolls=pick("setrolls"),
            setclaim=pick("setclaim"),
            setinterval=interval if interval is not None else 0,
            shifthour=shift if shift is not None else 0,
        )

    @property
    def hourly_reset_minute(self) -> int:
        return (self.setinterval + self.shifthour) % 60

    def claim_period_minutes(self) -> int:
        if self.setclaim is not None and self.setclaim > 0:
            return self.setclaim
        return HOURLY_ROLL_PERIOD_MINUTES


@dataclass(frozen=True)
class PeriodicAdvance:
    minutes_remaining: int | None
    periods_crossed: int
    next_deadline: dt.datetime | None


def next_hourly_reset_at(now: dt.datetime, schedule: MudaeResetSchedule) -> dt.datetime:
    """Next hourly rolls reset at ``setinterval`` + ``shifthour`` past the hour."""
    now = now.astimezone(dt.timezone.utc)
    minute = schedule.hourly_reset_minute
    candidate = now.replace(minute=minute, second=0, microsecond=0)
    if now >= candidate:
        candidate += dt.timedelta(hours=1)
    return candidate


def count_hourly_resets_between(
    start: dt.datetime,
    end: dt.datetime,
    schedule: MudaeResetSchedule,
) -> int:
    """Hourly roll resets strictly after ``start`` and at or before ``end``."""
    if end <= start:
        return 0
    count = 0
    cursor = start
    while True:
        nxt = next_hourly_reset_at(cursor, schedule)
        if nxt <= end:
            count += 1
            cursor = nxt
            continue
        break
    return count


def advance_periodic_deadline(
    deadline_iso: str,
    period_minutes: int,
    now: dt.datetime,
) -> PeriodicAdvance:
    """Advance a repeating deadline through ``now``."""
    deadline = parse_iso(deadline_iso)
    if deadline is None or period_minutes <= 0:
        return PeriodicAdvance(None, 0, None)

    crossed = 0
    while deadline <= now:
        crossed += 1
        deadline += dt.timedelta(minutes=period_minutes)

    if deadline > now:
        remaining = max(1, int((deadline - now).total_seconds() // 60))
    else:
        remaining = None
    return PeriodicAdvance(remaining, crossed, deadline)


def minutes_until_deadline(deadline: dt.datetime, now: dt.datetime) -> int:
    return max(1, int((deadline - now).total_seconds() // 60))
