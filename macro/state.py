"""Runtime macro state exposed to the GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from macro.perk9_daily import PERK9_CLICK_MAX_DEFAULT
from mudae.clock import utc_date_key

# Enough click history for the Run panel; the cap is 20 on a maxed account.
PERK9_CLICK_HISTORY_MAX = 40


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
    chaos_rolls_left: int = 0  # +N this hour not yet folded by $tu; ordinary rolls
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
    # ``$ohu9``'s ``(Perk 9) Rolled today: 44/154``. ``pool - rolled`` caps how
    # many more perk-9 sphere spawns today, which paces the adaptive threshold.
    perk9_rolled_today: int | None = None
    perk9_roll_pool: int | None = None
    # Tracked between ``$ohu9`` syncs so the macro does not re-query every session.
    perk9_spawns_today: int = 0
    # Rolls made today that are representative of this account's normal pace, so
    # the perk-9 arrival rate can be inverted from them. ``$us`` rolls are
    # excluded: they still spawn buttons, but a burst of them tears through the
    # pool far faster than ordinary rolling and would inflate the learned rate.
    perk9_regular_rolls_today: int = 0
    # Perk-9 spawns per roll, averaged over the account's recent days
    # (``macro.perk9_daily.learned_hazard``). ``None`` until enough regular
    # rolls have been seen, which keeps the estimate on the pool ceiling alone.
    perk9_hazard: float | None = None
    # Spawn count at the last ``$ohu9`` sync, so spawns seen since then can be
    # subtracted from Mudae's ``pool - rolled`` between queries.
    perk9_spawns_at_sync: int = 0
    perk9_click_emojis: list[str] = field(default_factory=list)
    # Mudae's hourly key cap ("You reached the limit of 2,200 keys per hour!"),
    # as the number it named; ``None`` while keys are still being granted. Only
    # reachable with $us, so the $us drain policy is what acts on it.
    key_limit_hit: int | None = None
    perk9_unknown_clicks: int = 0
    kakera_base_cost: float = 30.0
    dk_cooldown_minutes: int = 20 * 60
    # Perk-9 EV inputs from the run channel's $bonus / $shop, written by
    # ``macro.sheet_caps.apply_sheet_caps`` like the other sheet-derived caps.
    sphere_double_chance_pct: float = 0.0
    additional_spheres: float = 0.0
    perk9_sphere_value_pct: float = 0.0
    rolls_per_hour_net: int | None = None
    # Discord channel id of the current Run target, as a string. The perk-9
    # click budget is spent per channel, so the reads that rebuild the Run
    # panel from the sphere earning log have to know which one to count.
    run_channel_id: str = ""

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
            "perk9_rolled_today": self.perk9_rolled_today,
            "perk9_roll_pool": self.perk9_roll_pool,
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
        if not self.perk9_clicks_day:
            # No stamp yet means "not tracked this session", not "stale from
            # another day" — clearing here would discard counts just restored
            # from $ohu9 or the persisted record.
            self.perk9_clicks_day = today
            return
        if self.perk9_clicks_day != today:
            self.perk9_clicks_day = today
            self.perk9_clicks_today = 0
            self.perk9_spawns_today = 0
            self.perk9_spawns_at_sync = 0
            self.perk9_regular_rolls_today = 0
            # The perk-9 pool refills with the day. Leaving yesterday's count
            # here says "only 6 of 154 characters are still rollable", which
            # makes the adaptive threshold think the day is nearly over and drop
            # its bar to zero on the first roll after the reset. ``None`` stays
            # ``None``: that means "never measured", not "none rolled".
            if self.perk9_rolled_today is not None:
                self.perk9_rolled_today = 0
            self.perk9_click_emojis = []
            self.perk9_unknown_clicks = 0

    def clear_perk9_channel_tracking(self) -> None:
        """Forget every perk-9 counter that belongs to one channel.

        Mudae meters the sphere-button budget per channel, so on a switch these
        all go back to zero and are refilled from the new channel's own record.
        ``perk9_hazard`` is deliberately left alone: it is the account's roll
        pace, learned across days, and describes the account rather than where
        it happened to be rolling.
        """
        self.perk9_clicks_today = 0
        self.perk9_clicks_day = ""
        self.perk9_spawns_today = 0
        self.perk9_spawns_at_sync = 0
        self.perk9_regular_rolls_today = 0
        self.perk9_rolled_today = None
        self.perk9_roll_pool = None
        self.perk9_click_emojis = []
        self.perk9_unknown_clicks = 0

    def record_perk9_click(self, count: int = 1) -> None:
        if count <= 0:
            return
        self.rollover_perk9_if_needed()
        self.perk9_clicks_today += int(count)

    def record_perk9_spawn(self, count: int = 1) -> None:
        """One perk-9 sphere button appeared on a roll (clicked or not)."""
        if count <= 0:
            return
        self.rollover_perk9_if_needed()
        self.perk9_spawns_today += int(count)

    def record_perk9_regular_roll(self, count: int = 1) -> None:
        """One ordinary (non-``$us``) roll, the denominator of the learned rate."""
        if count <= 0:
            return
        self.rollover_perk9_if_needed()
        self.perk9_regular_rolls_today += int(count)

    def note_key_limit(self, limit: int | None) -> bool:
        """Record Mudae's hourly key cap. True the first time it is seen."""
        if limit is None:
            return False
        first = self.key_limit_hit is None
        self.key_limit_hit = int(limit)
        return first

    def clear_key_limit(self) -> None:
        """The hourly window has rolled over; keys are being granted again."""
        self.key_limit_hit = None

    def record_perk9_click_emoji(self, emoji: str | None) -> None:
        """Remember which colour was clicked, oldest first, for the Run panel."""
        if not emoji:
            return
        self.rollover_perk9_if_needed()
        self.perk9_click_emojis.append(str(emoji))
        del self.perk9_click_emojis[:-PERK9_CLICK_HISTORY_MAX]

    def sync_perk9_unknown_clicks(self) -> None:
        """Clicks Mudae counted that this session never saw show as face-down.

        Connecting mid-day, or a click whose confirmation was missed, leaves the
        colour unknowable — the panel renders those as ``spU`` rather than
        pretending the history is complete.
        """
        gap = int(self.perk9_clicks_today) - len(self.perk9_click_emojis)
        self.perk9_unknown_clicks = max(0, gap)

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
