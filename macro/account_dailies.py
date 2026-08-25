"""Account-global ``$p`` / ``$daily`` cooldown math.

Both commands are per Discord account, not per server: sending on any channel
consumes the cooldown everywhere. ``$p`` resets on even UTC hours (00:00, 02:00,
…). ``$daily`` is a 20-hour cooldown from the successful claim.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from mudae.clock import as_utc, parse_iso_datetime, utc_now

DAILY_COOLDOWN = dt.timedelta(hours=20)
P_PERIOD_HOURS = 2
COMMAND_P = "p"
COMMAND_DAILY = "daily"


def next_p_reset_at(now: dt.datetime | None = None) -> dt.datetime:
    """First even UTC hour strictly after ``now`` (the next ``$p`` slot)."""
    now = as_utc(now or utc_now())
    candidate = now.replace(minute=0, second=0, microsecond=0)
    if now.hour % 2 == 0:
        candidate += dt.timedelta(hours=P_PERIOD_HOURS)
    else:
        candidate += dt.timedelta(hours=1)
    return candidate


def daily_ready_after_success(now: dt.datetime | None = None) -> dt.datetime:
    return as_utc(now or utc_now()) + DAILY_COOLDOWN


def ready_after_minutes(minutes: int, *, now: dt.datetime | None = None) -> dt.datetime:
    return as_utc(now or utc_now()) + dt.timedelta(minutes=max(0, int(minutes)))


def _parse_ready(raw: str | None) -> dt.datetime | None:
    return parse_iso_datetime(raw or "")


def iso_ready(stamp: dt.datetime) -> str:
    return as_utc(stamp).isoformat()


def is_ready(raw: str | None, *, now: dt.datetime | None = None) -> bool:
    """True when the stored deadline is missing or already passed."""
    ready_at = _parse_ready(raw)
    if ready_at is None:
        return True
    return as_utc(now or utc_now()) >= ready_at


def seconds_until_ready(raw: str | None, *, now: dt.datetime | None = None) -> float:
    ready_at = _parse_ready(raw)
    now = as_utc(now or utc_now())
    if ready_at is None:
        return 0.0
    return max(0.0, (ready_at - now).total_seconds())


@dataclass(frozen=True)
class AccountDailyPlan:
    """One account that should send ``$p`` and/or ``$daily`` now."""

    account_id: str
    account_name: str
    token: str
    channel_profile_id: str
    commands: tuple[str, ...]


def due_commands(account: Any, *, now: dt.datetime | None = None) -> tuple[str, ...]:
    """Commands that are due for this account (empty when no channel is set)."""
    channel_id = str(getattr(account, "daily_channel_id", "") or "").strip()
    if not channel_id:
        return ()
    now = as_utc(now or utc_now())
    cmds: list[str] = []
    if is_ready(getattr(account, "p_next_ready_at", ""), now=now):
        cmds.append(COMMAND_P)
    if is_ready(getattr(account, "daily_next_ready_at", ""), now=now):
        cmds.append(COMMAND_DAILY)
    return tuple(cmds)


def plans_due(
    accounts: list[Any],
    *,
    now: dt.datetime | None = None,
    prefer_account_id: str = "",
) -> list[AccountDailyPlan]:
    """Due ``$p``/``$daily`` work, current run account first, then list order."""
    now = as_utc(now or utc_now())
    preferred: list[AccountDailyPlan] = []
    rest: list[AccountDailyPlan] = []
    for account in accounts:
        cmds = due_commands(account, now=now)
        if not cmds:
            continue
        plan = AccountDailyPlan(
            account_id=str(account.id),
            account_name=str(getattr(account, "name", "") or account.id),
            token=str(getattr(account, "token", "") or ""),
            channel_profile_id=str(account.daily_channel_id).strip(),
            commands=cmds,
        )
        if prefer_account_id and plan.account_id == prefer_account_id:
            preferred.append(plan)
        else:
            rest.append(plan)
    return preferred + rest


def seconds_until_due(
    accounts: list[Any],
    *,
    now: dt.datetime | None = None,
) -> float | None:
    """Seconds until the next configured ``$p``/``$daily``, or ``None``.

    ``0.0`` means something is already due. ``None`` means no account has a
    designated channel, so the wait loop should not wake for this.
    """
    now = as_utc(now or utc_now())
    soonest: float | None = None
    any_channel = False
    for account in accounts:
        if not str(getattr(account, "daily_channel_id", "") or "").strip():
            continue
        any_channel = True
        for raw in (
            getattr(account, "p_next_ready_at", ""),
            getattr(account, "daily_next_ready_at", ""),
        ):
            remaining = seconds_until_ready(raw, now=now)
            if soonest is None or remaining < soonest:
                soonest = remaining
    if not any_channel:
        return None
    return soonest if soonest is not None else 0.0
