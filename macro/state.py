"""Runtime macro state exposed to the GUI."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    claim_available: bool | None = None
    claim_cooldown_minutes: int | None = None
    power_percent: int | None = None
    rolls_reset_minutes: int | None = None
    next_claim_reset_minutes: int | None = None
    claim_expire_sec: int | None = None
    phase: MacroPhase = MacroPhase.IDLE
    own_usernames: list[str] = field(default_factory=list)
    own_user_ids: list[int] = field(default_factory=list)
    activity_log: list[str] = field(default_factory=list)
    kakera_clicks_today: int = 0
    kakera_clicks_day: str = ""  # YYYY-MM-DD (UTC); resets daily
    rule_trace: list[RuleTraceEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rolls_left": self.rolls_left,
            "claim_available": self.claim_available,
            "claim_cooldown_minutes": self.claim_cooldown_minutes,
            "power_percent": self.power_percent,
            "rolls_reset_minutes": self.rolls_reset_minutes,
            "next_claim_reset_minutes": self.next_claim_reset_minutes,
            "claim_expire_sec": self.claim_expire_sec,
            "phase": self.phase.value,
            "own_usernames": list(self.own_usernames),
            "own_user_ids": list(self.own_user_ids),
            "activity_log": list(self.activity_log[-20:]),
            "kakera_clicks_today": self.kakera_clicks_today,
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
