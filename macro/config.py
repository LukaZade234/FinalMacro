"""Macro configuration persisted with GUI settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MacroConfig:
    roll_command: str = "wa"
    prefix: str = "$"
    roll_delay_sec: float = 0.6
    rolls_left_stop: int = 2
    auto_claim_wish: bool = True
    claim_best_at_claim_reset: bool = True
    claim_reset_margin_minutes: int = 20
    claim_expire_sec: int = 45

    def normalized_roll_command(self) -> str:
        return self.roll_command.strip().lstrip("$").lower() or "wa"

    def roll_delay(self) -> float:
        return max(self.roll_delay_sec, 0.6)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MacroConfig:
        if not data:
            return cls()
        legacy_auto_claim = data.get("auto_claim")
        claim_best = data.get("claim_best_at_claim_reset")
        if claim_best is None and legacy_auto_claim is not None:
            claim_best = legacy_auto_claim
        return cls(
            roll_command=str(data.get("roll_command", "wa")),
            prefix=str(data.get("prefix", "$")),
            roll_delay_sec=float(data.get("roll_delay_sec", 0.6)),
            rolls_left_stop=int(data.get("rolls_left_stop", 2)),
            auto_claim_wish=bool(data.get("auto_claim_wish", True)),
            claim_best_at_claim_reset=bool(claim_best if claim_best is not None else True),
            claim_reset_margin_minutes=int(data.get("claim_reset_margin_minutes", 20)),
            claim_expire_sec=int(data.get("claim_expire_sec", 45)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
