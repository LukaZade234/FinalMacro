"""Runtime macro state exposed to the GUI."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from macro.reaction_power import display_reaction_power


class MacroPhase(str, Enum):
    IDLE = "Idle"
    CHECKING_TU = "Checking $tu"
    ROLLING = "Rolling"
    POST_ROLL = "Post-roll"
    STOPPING = "Stopping"


@dataclass
class RuleTraceEntry:
    """One line of rule-evaluation diagnostics for the Run tab."""

    block: str  # "character" / "kakera" / "sphere"
    roll_index: int
    character: str
    decision: str  # "claim" / "click" / "skip"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "block": self.block,
            "roll_index": self.roll_index,
            "character": self.character,
            "decision": self.decision,
            "reason": self.reason,
        }


@dataclass
class AccountState:
    rolls_left: int | None = None
    rolls_us_bonus: int | None = None  # stacked rolls added via $us, usable now
    claim_available: bool | None = None
    claim_cooldown_minutes: int | None = None
    power_percent: float | None = None
    power_max_percent: float = 155.0
    power_tracked_at: float = 0.0  # ``time.monotonic()`` when ``power_percent`` was anchored
    dk_stock: int | None = None
    dk_next_minutes: int | None = None
    rolls_reset_minutes: int | None = None
    next_claim_reset_minutes: int | None = None
    claim_expire_sec: int | None = None
    phase: MacroPhase = MacroPhase.IDLE
    own_usernames: list[str] = field(default_factory=list)
    own_user_ids: list[int] = field(default_factory=list)
    activity_log: list["ActivityLogEntry"] = field(default_factory=list)
    kakera_clicks_today: int = 0
    kakera_clicks_day: str = ""  # YYYY-MM-DD (UTC); resets daily
    perk8_priority_mode: str = "inactive"
    perk8_click_max: int | None = None
    rule_trace: list[RuleTraceEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rolls_left": self.rolls_left,
            "rolls_us_bonus": self.rolls_us_bonus,
            "claim_available": self.claim_available,
            "claim_cooldown_minutes": self.claim_cooldown_minutes,
            "power_percent": display_reaction_power(self.power_percent)
            if self.power_percent is not None
            else None,
            "power_max_percent": self.power_max_percent,
            "dk_stock": self.dk_stock,
            "dk_next_minutes": self.dk_next_minutes,
            "rolls_reset_minutes": self.rolls_reset_minutes,
            "next_claim_reset_minutes": self.next_claim_reset_minutes,
            "claim_expire_sec": self.claim_expire_sec,
            "phase": self.phase.value,
            "own_usernames": list(self.own_usernames),
            "own_user_ids": list(self.own_user_ids),
            "activity_log": [entry.to_dict() for entry in self.activity_log[-200:]],
            "kakera_clicks_today": self.kakera_clicks_today,
            "perk8_priority_mode": self.perk8_priority_mode,
            "perk8_click_max": self.perk8_click_max,
            "rule_trace": [entry.to_dict() for entry in self.rule_trace[-12:]],
        }

    def _today_key(self) -> str:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def rollover_kakera_budget_if_needed(self) -> None:
        today = self._today_key()
        if self.kakera_clicks_day != today:
            self.kakera_clicks_day = today
            self.kakera_clicks_today = 0

    def remaining_kakera_budget(self, daily_limit: int) -> int:
        self.rollover_kakera_budget_if_needed()
        return max(0, int(daily_limit) - int(self.kakera_clicks_today))

    def record_kakera_clicks(self, count: int) -> None:
        if count <= 0:
            return
        self.rollover_kakera_budget_if_needed()
        self.kakera_clicks_today += int(count)

    def append_rule_trace(self, entry: RuleTraceEntry, *, max_lines: int = 20) -> None:
        self.rule_trace.append(entry)
        if len(self.rule_trace) > max_lines:
            self.rule_trace = self.rule_trace[-max_lines:]

    def claim_label(self) -> str:
        if self.claim_available is True:
            return "can claim"
        if self.claim_available is False:
            cd = self.claim_cooldown_minutes
            return f"cooldown {cd}m" if cd is not None else "on cooldown"
        return "unknown"
