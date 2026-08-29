"""Perk-8 reaction-power and ``$dk`` reservation.

Paid reacts are costed as chaos keys. Today's remaining perk-8 clicks expire at
UTC midnight and always beat tomorrow. After 40/40, normal chaos kakera stay on
unless a spend would make the next day's 40-click burst fail; ``$dk`` on those
reacts is allowed only when a replacement is back by midnight (or the burst
still completes).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, replace
from typing import Any

from macro.perk8_daily import PERK8_DAILY_CLICK_BUDGET, next_daily_reset, parse_iso
from macro.reaction_power import (
    BASE_REACTION_COST,
    DEFAULT_MAX_REACTION_POWER,
    REGEN_INTERVAL_SEC,
    REGEN_PERCENT_PER_3MIN,
    apply_passive_regen,
    refresh_reaction_power,
)
from mudae.clock import utc_now

DEFAULT_DK_COOLDOWN_MINUTES = 20 * 60
DEFAULT_POWER_WINDOW_HOURS = 4.0
MIN_POWER_WINDOW_HOURS = 1.0
MAX_POWER_WINDOW_HOURS = 12.0

_HOURS_RE = re.compile(r"(\d+)\s*h", re.IGNORECASE)
_MINUTES_RE = re.compile(r"(\d+)\s*m", re.IGNORECASE)
_REGEN_PER_SEC = REGEN_PERCENT_PER_3MIN / REGEN_INTERVAL_SEC


def clamp_power_window_hours(value: Any) -> float:
    try:
        hours = float(value)
    except (TypeError, ValueError):
        hours = DEFAULT_POWER_WINDOW_HOURS
    if hours < MIN_POWER_WINDOW_HOURS:
        return MIN_POWER_WINDOW_HOURS
    if hours > MAX_POWER_WINDOW_HOURS:
        return MAX_POWER_WINDOW_HOURS
    return hours


def chaos_click_cost(*, perk8: bool, base_cost: float = BASE_REACTION_COST) -> float:
    """Power % for one paid kakera react, assuming a chaos key."""
    cost = float(base_cost) / 2.0
    if perk8:
        cost /= 2.0
    return cost


def dk_cooldown_minutes_from_bonus(raw: Any) -> int:
    """``$bonus.dk_cooldown`` (``10h``, ``20h``) → minutes. Default 20h."""
    if isinstance(raw, (int, float)) and float(raw) > 0:
        # Numeric values from tests / sheets are hours when <= 48, else minutes.
        value = float(raw)
        if value <= 48:
            return int(round(value * 60))
        return int(round(value))
    text = str(raw or "").strip()
    if not text:
        return DEFAULT_DK_COOLDOWN_MINUTES
    hours = 0
    minutes = 0
    hm = _HOURS_RE.search(text)
    if hm:
        hours = int(hm.group(1))
    mm = _MINUTES_RE.search(text)
    if mm:
        minutes = int(mm.group(1))
    total = hours * 60 + minutes
    return total if total > 0 else DEFAULT_DK_COOLDOWN_MINUTES


def kakera_base_cost_from_bonus(raw: Any) -> float:
    if raw is None or raw == "":
        return BASE_REACTION_COST
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return BASE_REACTION_COST
    return value if value > 0 else BASE_REACTION_COST


def seconds_until_midnight(now: dt.datetime) -> float:
    reset = next_daily_reset(now)
    return max(0.0, (reset - now).total_seconds())


@dataclass
class PowerSnapshot:
    power: float
    max_power: float
    dk_stock: int
    dk_next_sec: float | None
    dk_cooldown_sec: float
    perk8_cost: float
    normal_cost: float


def snapshot_from_state(
    state: Any,
    *,
    now: dt.datetime | None = None,
) -> PowerSnapshot:
    refresh_reaction_power(state)
    stamp = now or utc_now()
    power = getattr(state, "power_percent", None)
    max_power = float(
        getattr(state, "power_max_percent", None) or DEFAULT_MAX_REACTION_POWER
    )
    stock = getattr(state, "dk_stock", None)
    base = float(getattr(state, "kakera_base_cost", None) or BASE_REACTION_COST)
    cooldown_min = getattr(state, "dk_cooldown_minutes", None)
    if cooldown_min is None or int(cooldown_min) <= 0:
        cooldown_sec = float(DEFAULT_DK_COOLDOWN_MINUTES * 60)
    else:
        cooldown_sec = float(int(cooldown_min) * 60)
    return PowerSnapshot(
        power=0.0 if power is None else max(0.0, float(power)),
        max_power=max_power,
        dk_stock=0 if stock is None else max(0, int(stock)),
        dk_next_sec=_dk_next_sec(state, stamp),
        dk_cooldown_sec=cooldown_sec,
        perk8_cost=chaos_click_cost(perk8=True, base_cost=base),
        normal_cost=chaos_click_cost(perk8=False, base_cost=base),
    )


def _dk_next_sec(state: Any, now: dt.datetime) -> float | None:
    deadline = parse_iso(str(getattr(state, "dk_reset_at", "") or ""))
    if deadline is not None:
        return max(0.0, (deadline - now).total_seconds())
    minutes = getattr(state, "dk_next_minutes", None)
    if minutes is None:
        return None
    try:
        return max(0.0, float(minutes) * 60.0)
    except (TypeError, ValueError):
        return None


def _apply_spend(snap: PowerSnapshot, cost: float) -> PowerSnapshot:
    return replace(snap, power=max(0.0, float(snap.power) - float(cost)))


def _apply_dk_use(snap: PowerSnapshot, *, t: float = 0.0) -> PowerSnapshot:
    stock = max(0, int(snap.dk_stock) - 1)
    dk_next = snap.dk_next_sec
    if stock == 0 and (dk_next is None or dk_next < t):
        dk_next = t + float(snap.dk_cooldown_sec)
    return replace(snap, power=float(snap.max_power), dk_stock=stock, dk_next_sec=dk_next)


def burst_completes(
    snap: PowerSnapshot,
    *,
    clicks: int,
    cost: float,
    horizon_sec: float,
) -> bool:
    """True when ``clicks`` at ``cost``% can be paid within ``horizon_sec``."""
    if clicks <= 0:
        return True
    if cost <= 0:
        return True
    if cost > float(snap.max_power) + 1e-9:
        return False
    power = float(snap.power)
    stock = int(snap.dk_stock)
    dk_next = snap.dk_next_sec
    cooldown = float(snap.dk_cooldown_sec)
    max_power = float(snap.max_power)
    t = 0.0
    done = 0
    horizon = max(0.0, float(horizon_sec))
    for _ in range(clicks * 4 + 40):
        if done >= clicks:
            return True
        if t > horizon + 1e-6:
            return False
        if power + 1e-9 >= cost:
            power -= cost
            done += 1
            continue
        if stock > 0:
            stock -= 1
            power = max_power
            if stock == 0 and (dk_next is None or dk_next < t):
                dk_next = t + cooldown
            continue
        wait_regen = (cost - power) / _REGEN_PER_SEC if _REGEN_PER_SEC > 0 else float("inf")
        if power + 1e-9 >= max_power:
            wait_regen = float("inf")
        wait_dk = (dk_next - t) if dk_next is not None else float("inf")
        wait = min(wait_regen, wait_dk)
        if wait < 0:
            wait = 0.0
        if wait == float("inf") or t + wait > horizon + 1e-6:
            return False
        power = apply_passive_regen(power, wait, max_power=max_power)
        t += wait
        if dk_next is not None and t + 1e-6 >= dk_next:
            stock += 1
            dk_next = t + cooldown
    return done >= clicks


def _idle_until(snap: PowerSnapshot, until_sec: float) -> PowerSnapshot:
    """Regen and collect ``$dk`` recharges with no clicks, up to ``until_sec``."""
    if until_sec <= 0:
        return snap
    power = float(snap.power)
    stock = int(snap.dk_stock)
    dk_next = snap.dk_next_sec
    cooldown = float(snap.dk_cooldown_sec)
    max_power = float(snap.max_power)
    t = 0.0
    while dk_next is not None and dk_next <= until_sec + 1e-9:
        wait = max(0.0, dk_next - t)
        power = apply_passive_regen(power, wait, max_power=max_power)
        t = dk_next
        stock += 1
        dk_next = t + cooldown
    power = apply_passive_regen(power, until_sec - t, max_power=max_power)
    next_sec = None if dk_next is None else max(0.0, dk_next - until_sec)
    return replace(snap, power=power, dk_stock=stock, dk_next_sec=next_sec)


def next_day_burst_completes(
    snap: PowerSnapshot,
    *,
    clicks: int,
    window_sec: float,
    until_midnight_sec: float,
) -> bool:
    rested = _idle_until(snap, until_midnight_sec)
    return burst_completes(
        rested,
        clicks=clicks,
        cost=snap.perk8_cost,
        horizon_sec=window_sec,
    )


def today_horizon_sec(window_sec: float, until_midnight_sec: float) -> float:
    return max(0.0, min(float(window_sec), float(until_midnight_sec)))


def should_spend_paid_non_perk8(
    snap: PowerSnapshot,
    *,
    cost: float,
    remaining: int,
    window_sec: float,
    until_midnight_sec: float,
    click_cap: int = PERK8_DAILY_CLICK_BUDGET,
) -> bool:
    """True when a paid non-perk-8 react does not break the perk-8 floor."""
    if cost <= 0:
        return True
    after = _apply_spend(snap, cost)
    if remaining > 0:
        horizon = today_horizon_sec(window_sec, until_midnight_sec)
        ok_now = burst_completes(
            snap, clicks=remaining, cost=snap.perk8_cost, horizon_sec=horizon
        )
        ok_after = burst_completes(
            after, clicks=remaining, cost=snap.perk8_cost, horizon_sec=horizon
        )
        if ok_now and not ok_after:
            return False
        return True
    cap = max(1, int(click_cap))
    ok_now = next_day_burst_completes(
        snap,
        clicks=cap,
        window_sec=window_sec,
        until_midnight_sec=until_midnight_sec,
    )
    ok_after = next_day_burst_completes(
        after,
        clicks=cap,
        window_sec=window_sec,
        until_midnight_sec=until_midnight_sec,
    )
    if ok_now and not ok_after:
        return False
    return True


def dk_allowed_for_click(
    snap: PowerSnapshot,
    *,
    perk8: bool,
    remaining: int,
    window_sec: float,
    until_midnight_sec: float,
    click_cap: int = PERK8_DAILY_CLICK_BUDGET,
    power_save: bool = True,
    budget_mode: bool = True,
) -> bool:
    """Whether ``$dk`` may refill for this react under the reserve rules."""
    if not power_save or not budget_mode:
        return True
    if remaining > 0:
        return bool(perk8)
    after = _apply_dk_use(snap, t=0.0)
    if after.dk_stock > 0:
        return True
    if (
        after.dk_next_sec is not None
        and after.dk_next_sec <= float(until_midnight_sec) + 1e-6
    ):
        return True
    return next_day_burst_completes(
        after,
        clicks=max(1, int(click_cap)),
        window_sec=window_sec,
        until_midnight_sec=until_midnight_sec,
    )


def power_save_enabled(rules: Any) -> bool:
    if not bool(getattr(rules, "perk_8_budget_mode", False)):
        return False
    if not bool(getattr(rules, "perk_8_priority", True)):
        return False
    return bool(getattr(rules, "perk_8_power_save", False))


def window_sec_from_rules(rules: Any) -> float:
    hours = clamp_power_window_hours(
        getattr(rules, "perk_8_power_window_hours", DEFAULT_POWER_WINDOW_HOURS)
    )
    return hours * 3600.0


def remaining_perk8_clicks(state: Any) -> int:
    mode = str(getattr(state, "perk8_priority_mode", "") or "")
    if mode == "done":
        return 0
    cap = getattr(state, "perk8_click_max", None)
    try:
        daily = max(1, int(cap)) if cap is not None else PERK8_DAILY_CLICK_BUDGET
    except (TypeError, ValueError):
        daily = PERK8_DAILY_CLICK_BUDGET
    return int(state.remaining_kakera_budget(daily))


def spendable_power_percent(
    snap: PowerSnapshot,
    *,
    remaining: int,
    window_sec: float,
    until_midnight_sec: float,
    click_cap: int = PERK8_DAILY_CLICK_BUDGET,
) -> float:
    """Largest paid spend (power %) that still leaves the perk-8 floor intact."""
    hi = max(0.0, float(snap.power))
    if hi <= 0:
        return 0.0
    if should_spend_paid_non_perk8(
        snap,
        cost=hi,
        remaining=remaining,
        window_sec=window_sec,
        until_midnight_sec=until_midnight_sec,
        click_cap=click_cap,
    ):
        return hi
    lo = 0.0
    for _ in range(20):
        mid = (lo + hi) / 2.0
        if should_spend_paid_non_perk8(
            snap,
            cost=mid,
            remaining=remaining,
            window_sec=window_sec,
            until_midnight_sec=until_midnight_sec,
            click_cap=click_cap,
        ):
            lo = mid
        else:
            hi = mid
    return lo


def power_save_status(
    state: Any,
    rules: Any,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any] | None:
    """Live smart-saver snapshot for the Run page. ``None`` when the toggle is off."""
    if not power_save_enabled(rules):
        return None
    stamp = now or utc_now()
    remaining = remaining_perk8_clicks(state)
    cap = getattr(state, "perk8_click_max", None)
    try:
        click_cap = max(1, int(cap)) if cap is not None else PERK8_DAILY_CLICK_BUDGET
    except (TypeError, ValueError):
        click_cap = PERK8_DAILY_CLICK_BUDGET
    window_sec = window_sec_from_rules(rules)
    until_midnight = seconds_until_midnight(stamp)
    snap = snapshot_from_state(state, now=stamp)
    mode = str(getattr(state, "perk8_priority_mode", "") or "")
    priority = mode == "active" and remaining > 0
    blocked = not should_spend_paid_non_perk8(
        snap,
        cost=snap.normal_cost,
        remaining=remaining,
        window_sec=window_sec,
        until_midnight_sec=until_midnight,
        click_cap=click_cap,
    )
    power_known = getattr(state, "power_percent", None) is not None
    spendable = (
        spendable_power_percent(
            snap,
            remaining=remaining,
            window_sec=window_sec,
            until_midnight_sec=until_midnight,
            click_cap=click_cap,
        )
        if power_known
        else None
    )
    return {
        "enabled": True,
        "perk8_priority": priority,
        "normal_clicks": not priority,
        "power_blocked": blocked,
        "kakera_free": (not priority) and not blocked,
        "spendable_percent": None if spendable is None else round(float(spendable), 1),
        "power_percent": None if not power_known else round(float(snap.power), 1),
        "remaining": remaining,
        "window_hours": clamp_power_window_hours(
            getattr(rules, "perk_8_power_window_hours", DEFAULT_POWER_WINDOW_HOURS)
        ),
    }


def dk_allowed_for_state(
    state: Any,
    rules: Any,
    *,
    perk8: bool,
    now: dt.datetime | None = None,
) -> bool:
    """``$dk`` gate using live state. ``auto_use_dk`` is checked by the caller."""
    if not power_save_enabled(rules):
        return True
    stamp = now or utc_now()
    remaining = remaining_perk8_clicks(state)
    cap = getattr(state, "perk8_click_max", None)
    try:
        click_cap = max(1, int(cap)) if cap is not None else PERK8_DAILY_CLICK_BUDGET
    except (TypeError, ValueError):
        click_cap = PERK8_DAILY_CLICK_BUDGET
    return dk_allowed_for_click(
        snapshot_from_state(state, now=stamp),
        perk8=perk8,
        remaining=remaining,
        window_sec=window_sec_from_rules(rules),
        until_midnight_sec=seconds_until_midnight(stamp),
        click_cap=click_cap,
        power_save=True,
        budget_mode=True,
    )
