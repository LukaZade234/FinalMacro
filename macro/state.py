"""Runtime macro state exposed to the GUI."""

from __future__ import annotations

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
        }

    def claim_label(self) -> str:
        if self.claim_available is True:
            return "can claim"
        if self.claim_available is False:
            cd = self.claim_cooldown_minutes
            return f"cooldown {cd}m" if cd is not None else "on cooldown"
        return "unknown"
