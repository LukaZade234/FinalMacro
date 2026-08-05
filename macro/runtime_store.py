"""Persist ``$tu`` runtime fields per account on a channel profile.

When ``character_claim.persist_tu_state`` is enabled, rolls/timers/power are saved
after each ``$tu`` and on disconnect so the next session can skip an initial
``$tu`` and extrapolate countdowns (including passive reaction-power regen).
Hourly roll and claim resets are inferred from saved deadlines plus ``$settings``
(``setrolls``, ``setclaim``, ``setinterval``, ``shifthour``).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from macro.perk8_daily import parse_iso
from macro.reaction_power import apply_passive_regen
from macro.reset_schedule import (
    HOURLY_ROLL_PERIOD_MINUTES,
    MudaeResetSchedule,
    advance_periodic_deadline,
    count_hourly_resets_between,
    minutes_until_deadline,
    next_hourly_reset_at,
)
from macro.state import AccountState

MACRO_RUNTIME_KEY = "macro_runtime"
# Discard snapshots older than this (timers would be too stale to trust).
MAX_RECORD_AGE_HOURS = 168


@dataclass
class MacroRuntimeRecord:
    saved_at: str = ""
    rolls_left: int | None = None
    rolls_us_bonus: int | None = None
    us_stacked: float | None = None
    claim_available: bool | None = None
    claim_cooldown_minutes: int | None = None
    next_claim_reset_minutes: int | None = None
    claim_expire_sec: int | None = None
    power_percent: float | None = None
    power_max_percent: float = 155.0
    power_updated_at: str = ""
    dk_stock: int | None = None
    dk_next_minutes: int | None = None
    rolls_reset_at: str = ""
    claim_reset_at: str = ""
    rt_available: bool | None = None
    rt_next_minutes: int | None = None
    rt_reset_at: str = ""
    dk_reset_at: str = ""
    setrolls: int | None = None
    setclaim: int | None = None
    setinterval: int | None = None
    shifthour: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MacroRuntimeRecord:
        if not data:
            return cls()
        return cls(
            saved_at=str(data.get("saved_at") or ""),
            rolls_left=_coerce_int(data.get("rolls_left")),
            rolls_us_bonus=_coerce_int(data.get("rolls_us_bonus")),
            us_stacked=_coerce_float(data.get("us_stacked")),
            claim_available=_coerce_bool(data.get("claim_available")),
            claim_cooldown_minutes=_coerce_int(data.get("claim_cooldown_minutes")),
            next_claim_reset_minutes=_coerce_int(data.get("next_claim_reset_minutes")),
            claim_expire_sec=_coerce_int(data.get("claim_expire_sec")),
            power_percent=_coerce_float(data.get("power_percent")),
            power_max_percent=float(data.get("power_max_percent") or 155.0),
            power_updated_at=str(data.get("power_updated_at") or ""),
            dk_stock=_coerce_int(data.get("dk_stock")),
            dk_next_minutes=_coerce_int(data.get("dk_next_minutes")),
            rolls_reset_at=str(data.get("rolls_reset_at") or ""),
            claim_reset_at=str(data.get("claim_reset_at") or ""),
            rt_available=_coerce_bool(data.get("rt_available")),
            rt_next_minutes=_coerce_int(data.get("rt_next_minutes")),
            rt_reset_at=str(data.get("rt_reset_at") or ""),
            dk_reset_at=str(data.get("dk_reset_at") or ""),
            setrolls=_coerce_int(data.get("setrolls")),
            setclaim=_coerce_int(data.get("setclaim")),
            setinterval=_coerce_int(data.get("setinterval")),
            shifthour=_coerce_int(data.get("shifthour")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "saved_at": self.saved_at,
            "rolls_left": self.rolls_left,
            "rolls_us_bonus": self.rolls_us_bonus,
            "us_stacked": self.us_stacked,
            "claim_available": self.claim_available,
            "claim_cooldown_minutes": self.claim_cooldown_minutes,
            "next_claim_reset_minutes": self.next_claim_reset_minutes,
            "claim_expire_sec": self.claim_expire_sec,
            "power_percent": self.power_percent,
            "power_max_percent": self.power_max_percent,
            "power_updated_at": self.power_updated_at,
            "dk_stock": self.dk_stock,
            "dk_next_minutes": self.dk_next_minutes,
            "rolls_reset_at": self.rolls_reset_at,
            "claim_reset_at": self.claim_reset_at,
            "rt_available": self.rt_available,
            "rt_next_minutes": self.rt_next_minutes,
            "rt_reset_at": self.rt_reset_at,
            "dk_reset_at": self.dk_reset_at,
            "setrolls": self.setrolls,
            "setclaim": self.setclaim,
            "setinterval": self.setinterval,
            "shifthour": self.shifthour,
        }

    def schedule_fields(self) -> dict[str, Any]:
        return {
            "setrolls": self.setrolls,
            "setclaim": self.setclaim,
            "setinterval": self.setinterval,
            "shifthour": self.shifthour,
        }


@dataclass(frozen=True)
class RuntimeRestoreResult:
    applied: bool
    needs_tu: bool
    message: str = ""


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).isoformat()


def _deadline_iso(now: dt.datetime, minutes: int | None) -> str:
    if minutes is None or minutes <= 0:
        return ""
    return _iso(now + dt.timedelta(minutes=int(minutes)))


def _minutes_until(deadline_iso: str, now: dt.datetime) -> tuple[int | None, bool]:
    """Return (minutes remaining, deadline_passed)."""
    if not deadline_iso:
        return None, False
    deadline = parse_iso(deadline_iso)
    if deadline is None:
        return None, False
    delta = (deadline - now).total_seconds()
    if delta <= 0:
        return 0, True
    return max(1, int(delta // 60)), False


def _record_age_hours(record: MacroRuntimeRecord, now: dt.datetime) -> float | None:
    saved = parse_iso(record.saved_at)
    if saved is None:
        return None
    return (now - saved).total_seconds() / 3600.0


def _resolve_schedule(
    record: MacroRuntimeRecord,
    settings: dict[str, Any] | None,
) -> MudaeResetSchedule:
    return MudaeResetSchedule.from_sources(settings, record.schedule_fields())


def _roll_resets_crossed(
    record: MacroRuntimeRecord,
    schedule: MudaeResetSchedule,
    now: dt.datetime,
) -> tuple[int, int | None]:
    """Return (periods_crossed, minutes_until_next_reset)."""
    if record.rolls_reset_at:
        advance = advance_periodic_deadline(
            record.rolls_reset_at,
            HOURLY_ROLL_PERIOD_MINUTES,
            now,
        )
        return advance.periods_crossed, advance.minutes_remaining

    saved = parse_iso(record.saved_at)
    if saved is None:
        return 0, None
    crossed = count_hourly_resets_between(saved, now, schedule)
    if crossed:
        return crossed, minutes_until_deadline(next_hourly_reset_at(now, schedule), now)
    return 0, minutes_until_deadline(next_hourly_reset_at(now, schedule), now)


def _claim_resets_crossed(
    record: MacroRuntimeRecord,
    schedule: MudaeResetSchedule,
    now: dt.datetime,
) -> tuple[int, int | None]:
    period = schedule.claim_period_minutes()
    if record.claim_reset_at:
        advance = advance_periodic_deadline(record.claim_reset_at, period, now)
        return advance.periods_crossed, advance.minutes_remaining

    saved = parse_iso(record.saved_at)
    if saved is None or record.next_claim_reset_minutes is None:
        return 0, record.next_claim_reset_minutes

    first_deadline = saved + dt.timedelta(minutes=int(record.next_claim_reset_minutes))
    advance = advance_periodic_deadline(_iso(first_deadline), period, now)
    return advance.periods_crossed, advance.minutes_remaining


def load_runtime_record(daily_resets: dict[str, Any] | None) -> MacroRuntimeRecord:
    if not daily_resets:
        return MacroRuntimeRecord()
    raw = daily_resets.get(MACRO_RUNTIME_KEY)
    if isinstance(raw, dict):
        return MacroRuntimeRecord.from_dict(raw)
    return MacroRuntimeRecord()


def save_runtime_record(
    daily_resets: dict[str, Any],
    record: MacroRuntimeRecord,
) -> dict[str, Any]:
    updated = dict(daily_resets or {})
    updated[MACRO_RUNTIME_KEY] = record.to_dict()
    return updated


def snapshot_from_state(
    state: AccountState,
    *,
    now: dt.datetime | None = None,
    settings: dict[str, Any] | None = None,
) -> MacroRuntimeRecord:
    """Build a persisted snapshot from live runtime state."""
    now = now or _utc_now()
    schedule = MudaeResetSchedule.from_sources(settings)
    return MacroRuntimeRecord(
        saved_at=_iso(now),
        rolls_left=state.rolls_left,
        rolls_us_bonus=state.rolls_us_bonus,
        us_stacked=state.us_stacked,
        claim_available=state.claim_available,
        claim_cooldown_minutes=state.claim_cooldown_minutes,
        next_claim_reset_minutes=state.next_claim_reset_minutes,
        claim_expire_sec=state.claim_expire_sec,
        power_percent=state.power_percent,
        power_max_percent=float(state.power_max_percent or 155.0),
        power_updated_at=_iso(now),
        dk_stock=state.dk_stock,
        dk_next_minutes=state.dk_next_minutes,
        rolls_reset_at=_deadline_iso(now, state.rolls_reset_minutes),
        claim_reset_at=_deadline_iso(now, state.next_claim_reset_minutes),
        rt_available=state.rt_available,
        rt_next_minutes=state.rt_next_minutes,
        rt_reset_at=_deadline_iso(now, state.rt_next_minutes),
        dk_reset_at=_deadline_iso(now, state.dk_next_minutes),
        setrolls=schedule.setrolls,
        setclaim=schedule.setclaim,
        setinterval=schedule.setinterval,
        shifthour=schedule.shifthour,
    )


def apply_power_with_regen(
    state: AccountState,
    record: MacroRuntimeRecord,
    *,
    now: dt.datetime | None = None,
) -> None:
    now = now or _utc_now()
    if record.power_percent is None:
        return
    max_power = float(record.power_max_percent or state.power_max_percent or 155.0)
    state.power_max_percent = max_power
    anchor = parse_iso(record.power_updated_at) or parse_iso(record.saved_at)
    if anchor is not None:
        elapsed = (now - anchor).total_seconds()
        state.power_percent = apply_passive_regen(
            float(record.power_percent),
            elapsed,
            max_power=max_power,
        )
    else:
        state.power_percent = float(record.power_percent)
    import time

    state.power_tracked_at = time.monotonic()


def apply_to_state(
    state: AccountState,
    record: MacroRuntimeRecord,
    *,
    now: dt.datetime | None = None,
    settings: dict[str, Any] | None = None,
) -> RuntimeRestoreResult:
    """Restore runtime fields from a persisted snapshot."""
    now = now or _utc_now()
    if not record.saved_at:
        return RuntimeRestoreResult(False, True, "no saved runtime")

    age = _record_age_hours(record, now)
    if age is not None and age > MAX_RECORD_AGE_HOURS:
        return RuntimeRestoreResult(False, True, "saved runtime too old")

    schedule = _resolve_schedule(record, settings)
    roll_crossed, roll_remaining = _roll_resets_crossed(record, schedule, now)
    claim_crossed, claim_remaining = _claim_resets_crossed(record, schedule, now)

    if roll_crossed > 0:
        if schedule.setrolls is not None:
            state.rolls_left = schedule.setrolls
        elif record.rolls_left is not None:
            return RuntimeRestoreResult(
                False,
                True,
                "roll reset passed but setrolls unknown",
            )
        else:
            return RuntimeRestoreResult(False, True, "rolls unknown after reset")
        state.rolls_us_bonus = 0
        state.rolls_reset_minutes = roll_remaining
    else:
        if record.rolls_left is None:
            return RuntimeRestoreResult(False, True, "rolls unknown in saved runtime")
        state.rolls_left = record.rolls_left
        state.rolls_us_bonus = record.rolls_us_bonus
        state.rolls_reset_minutes = roll_remaining

    if state.rolls_reset_minutes is None:
        state.rolls_reset_minutes = minutes_until_deadline(
            next_hourly_reset_at(now, schedule),
            now,
        )

    saved_at = parse_iso(record.saved_at)
    elapsed_min = int((now - saved_at).total_seconds() // 60) if saved_at else 0

    if claim_crossed > 0:
        state.claim_available = True
        state.claim_cooldown_minutes = 0
        state.next_claim_reset_minutes = claim_remaining
    elif record.claim_available:
        state.claim_available = True
        state.claim_cooldown_minutes = 0
        state.next_claim_reset_minutes = (
            claim_remaining
            if claim_remaining is not None
            else record.next_claim_reset_minutes
        )
    elif record.claim_cooldown_minutes is not None:
        new_cd = max(0, int(record.claim_cooldown_minutes) - elapsed_min)
        state.claim_cooldown_minutes = new_cd if new_cd > 0 else None
        state.claim_available = new_cd == 0
        state.next_claim_reset_minutes = (
            claim_remaining
            if claim_remaining is not None
            else record.next_claim_reset_minutes
        )
    else:
        state.claim_available = record.claim_available
        state.claim_cooldown_minutes = record.claim_cooldown_minutes
        state.next_claim_reset_minutes = (
            claim_remaining
            if claim_remaining is not None
            else record.next_claim_reset_minutes
        )

    rt_minutes, rt_passed = _minutes_until(record.rt_reset_at, now)
    if rt_passed:
        state.rt_available = True
        state.rt_next_minutes = None
    else:
        state.rt_available = record.rt_available
        state.rt_next_minutes = (
            rt_minutes if rt_minutes is not None else record.rt_next_minutes
        )

    dk_minutes, _ = _minutes_until(record.dk_reset_at, now)
    state.dk_stock = record.dk_stock
    state.dk_next_minutes = (
        dk_minutes if dk_minutes is not None else record.dk_next_minutes
    )

    state.claim_expire_sec = record.claim_expire_sec
    state.us_stacked = record.us_stacked

    apply_power_with_regen(state, record, now=now)

    notes: list[str] = []
    if roll_crossed:
        notes.append(f"{roll_crossed} roll reset(s)")
    if claim_crossed:
        notes.append(f"{claim_crossed} claim reset(s)")
    message = "restored saved $tu state"
    if notes:
        message += f" ({', '.join(notes)} applied)"

    return RuntimeRestoreResult(True, False, message)


def can_skip_initial_tu(result: RuntimeRestoreResult) -> bool:
    return result.applied and not result.needs_tu
