"""Runtime macro state exposed to the GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from macro.perk9_daily import PERK9_CLICK_MAX_DEFAULT
from mudae.clock import utc_date_key


class MacroPhase(str, Enum):
    IDLE = "Idle"
    CHECKING_TU = "Checking $tu"
    ROLLING = "Rolling"
    POST_ROLL = "Post-roll"
    STOPPING = "Stopping"


@dataclass
class AccountState:
    rolls_left: int | None = None
    rolls_us_bonus: int | None = None  # stacked rolls added via $us, usable now
    us_stacked: float | None = None  # full stacked pool from bare $us
    claim_available: bool | None = None
    claim_cooldown_minutes: int | None = None
    power_percent: float | None = None
    power_max_percent: float = 155.0
    power_tracked_at: float = 0.0  # ``time.monotonic()`` when ``power_percent`` was anchored
    power_updated_at: str = ""  # UTC ISO; GUI regenerates from this
    dk_stock: int | None = None
    dk_next_minutes: int | None = None
    dk_reset_at: str = ""
    rolls_reset_minutes: int | None = None
    rolls_reset_at: str = ""
    next_claim_reset_minutes: int | None = None
    claim_reset_at: str = ""
    claim_cooldown_at: str = ""
    claim_expire_sec: int | None = None
    rt_available: bool | None = None
    rt_next_minutes: int | None = None
    rt_reset_at: str = ""
    phase: MacroPhase = MacroPhase.IDLE
    own_usernames: list[str] = field(default_factory=list)
    own_user_ids: list[int] = field(default_factory=list)
    activity_log: list["ActivityLogEntry"] = field(default_factory=list)
    kakera_clicks_today: int = 0
    kakera_clicks_day: str = ""  # YYYY-MM-DD (UTC); resets daily
    perk8_priority_mode: str = "inactive"
    perk8_click_max: int | None = None
    perk9_clicks_today: int = 0
    perk9_clicks_day: str = ""  # YYYY-MM-DD (UTC); resets daily
    perk9_click_max: int = PERK9_CLICK_MAX_DEFAULT
    kakera_base_cost: float = 30.0
    dk_cooldown_minutes: int = 20 * 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "rolls_left": self.rolls_left,
            "rolls_us_bonus": self.rolls_us_bonus,
            "us_stacked": self.us_stacked,
            "claim_available": self.claim_available,
            "claim_cooldown_minutes": self.claim_cooldown_minutes,
            "power_percent": float(self.power_percent)
            if self.power_percent is not None
            else None,
            "power_max_percent": self.power_max_percent,
            "power_updated_at": self.power_updated_at,
            "dk_stock": self.dk_stock,
            "dk_next_minutes": self.dk_next_minutes,
            "dk_reset_at": self.dk_reset_at,
            "rolls_reset_minutes": self.rolls_reset_minutes,
            "rolls_reset_at": self.rolls_reset_at,
            "next_claim_reset_minutes": self.next_claim_reset_minutes,
            "claim_reset_at": self.claim_reset_at,
            "claim_cooldown_at": self.claim_cooldown_at,
            "claim_expire_sec": self.claim_expire_sec,
            "rt_available": self.rt_available,
            "rt_next_minutes": self.rt_next_minutes,
            "rt_reset_at": self.rt_reset_at,
            "phase": self.phase.value,
            "own_usernames": list(self.own_usernames),
            "own_user_ids": list(self.own_user_ids),
            "activity_log": [entry.to_dict() for entry in self.activity_log[-400:]],
            "kakera_clicks_today": self.kakera_clicks_today,
            "perk8_priority_mode": self.perk8_priority_mode,
            "perk8_click_max": self.perk8_click_max,
            "perk9_clicks_today": self.perk9_clicks_today,
            "perk9_click_max": self.perk9_click_max,
        }

    def _today_key(self) -> str:
        return utc_date_key()

    def rollover_kakera_budget_if_needed(self) -> None:
        today = self._today_key()
        if self.kakera_clicks_day != today:
            self.kakera_clicks_day = today
            self.kakera_clicks_today = 0

    def remaining_kakera_budget(self, daily_limit: int) -> int:
        self.rollover_kakera_budget_if_needed()
        return max(0, int(daily_limit) - int(self.kakera_clicks_today))

    def clamp_kakera_clicks_to_perk8_cap(self) -> None:
        """Keep the perk-8 tracker at the daily cap after equal clicking resumes."""
        cap = self.perk8_click_max
        if cap is None:
            return
        try:
            limit = int(cap)
        except (TypeError, ValueError):
            return
        if limit > 0:
            self.kakera_clicks_today = min(int(self.kakera_clicks_today), limit)

    def record_kakera_clicks(self, count: int) -> None:
        if count <= 0:
            return
        self.rollover_kakera_budget_if_needed()
        self.kakera_clicks_today += int(count)
        self.clamp_kakera_clicks_to_perk8_cap()

    def rollover_perk9_if_needed(self) -> None:
        today = self._today_key()
        if self.perk9_clicks_day != today:
            self.perk9_clicks_day = today
            self.perk9_clicks_today = 0

    def record_perk9_click(self, count: int = 1) -> None:
        if count <= 0:
            return
        self.rollover_perk9_if_needed()
        self.perk9_clicks_today += int(count)

    def set_rolls_reset(self, minutes: int | None, *, now: Any = None) -> None:
        from macro.live_clock import apply_countdown

        apply_countdown(self, "rolls_reset_minutes", "rolls_reset_at", minutes, now=now)

    def set_claim_reset(self, minutes: int | None, *, now: Any = None) -> None:
        from macro.live_clock import apply_countdown

        apply_countdown(
            self, "next_claim_reset_minutes", "claim_reset_at", minutes, now=now
        )

    def set_claim_cooldown(self, minutes: int | None, *, now: Any = None) -> None:
        from macro.live_clock import apply_countdown

        apply_countdown(
            self, "claim_cooldown_minutes", "claim_cooldown_at", minutes, now=now
        )

    def set_rt_reset(self, minutes: int | None, *, now: Any = None) -> None:
        from macro.live_clock import apply_countdown

        apply_countdown(self, "rt_next_minutes", "rt_reset_at", minutes, now=now)

    def set_dk_reset(self, minutes: int | None, *, now: Any = None) -> None:
        from macro.live_clock import apply_countdown

        apply_countdown(self, "dk_next_minutes", "dk_reset_at", minutes, now=now)

    def claim_label(self) -> str:
        if self.claim_available is True:
            return "can claim"
        if self.claim_available is False:
            cd = self.claim_cooldown_minutes
            return f"cooldown {cd}m" if cd is not None else "on cooldown"
        return "unknown"
