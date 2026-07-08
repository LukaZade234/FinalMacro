"""Macro configuration persisted with GUI settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# Kakera button identifiers in value order (purple is free → chaos most valuable).
KAKERA_TYPES: tuple[str, ...] = (
    "kakeraP",  # purple — free reaction
    "kakera",   # blue — default cheap
    "kakeraT",  # teal
    "kakeraG",  # green
    "kakeraY",  # yellow
    "kakeraO",  # orange
    "kakeraR",  # red
    "kakeraW",  # rainbow
    "kakeraL",  # light
    "kakeraD",  # dark
    "kakeraC",  # chaos
)

# Sphere identifiers in value order (no chaos sphere).
SPHERE_COLORS: tuple[str, ...] = (
    "spM",  # megasphere — free roll bonus
    "spP",  # purple — free in $oh
    "spB",  # blue
    "spT",  # teal
    "spG",  # green
    "spY",  # yellow
    "spD",  # dark
    "spL",  # light
    "spO",  # orange
    "spR",  # red (also matches bare ``:sp:`` roll buttons)
    "spW",  # rainbow
)


def _coerce_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n


def _coerce_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


@dataclass
class CharacterClaimRules:
    """When to claim a character on a roll.

    Chaos-key / sphere-count requirements are intentionally absent here — those
    are properties of kakera and sphere reactions, not character claims.
    """

    enabled: bool = True
    claim_on_wish_ping: bool = True
    only_final_hour: bool = True
    min_kakera: int | None = None
    max_claim_rank: int | None = None  # instant claim when claim rank ≤ this value

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CharacterClaimRules:
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", True)),
            claim_on_wish_ping=bool(data.get("claim_on_wish_ping", True)),
            only_final_hour=bool(data.get("only_final_hour", True)),
            min_kakera=_coerce_int_or_none(data.get("min_kakera")),
            max_claim_rank=_coerce_int_or_none(data.get("max_claim_rank")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LowPowerOverride:
    """When power drops below ``below_percent``, restrict kakera click filter."""

    below_percent: int = 30
    types_allowed: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LowPowerOverride:
        if not data:
            return cls()
        return cls(
            below_percent=int(data.get("below_percent", 30)),
            types_allowed=_coerce_str_list(data.get("types_allowed")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KakeraReactionRules:
    """When to click kakera buttons on rolled characters."""

    enabled: bool = False
    types_allowed: list[str] = field(default_factory=list)
    require_chaos_key: bool = False
    require_perk_8: bool = False
    min_spheres: int | None = None
    low_power: LowPowerOverride | None = None
    perk_8_budget_mode: bool = False
    # Kakera types clicked even while saving perk-8 budget (purple is free by default).
    perk_8_budget_bypass_types: list[str] = field(default_factory=lambda: ["kakeraP"])
    # Color filter for perk-8 characters while budget mode is on (empty = any).
    perk_8_types_allowed: list[str] = field(default_factory=list)
    auto_use_dk: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> KakeraReactionRules:
        if not data:
            return cls()
        lp_raw = data.get("low_power")
        low_power: LowPowerOverride | None = None
        if isinstance(lp_raw, dict):
            low_power = LowPowerOverride.from_dict(lp_raw)
        return cls(
            enabled=bool(data.get("enabled", False)),
            types_allowed=_coerce_str_list(data.get("types_allowed")),
            require_chaos_key=bool(data.get("require_chaos_key", False)),
            require_perk_8=bool(data.get("require_perk_8", False)),
            min_spheres=_coerce_int_or_none(data.get("min_spheres")),
            low_power=low_power,
            perk_8_budget_mode=bool(data.get("perk_8_budget_mode", False)),
            perk_8_budget_bypass_types=_coerce_str_list(
                data.get("perk_8_budget_bypass_types", ["kakeraP"])
            ),
            perk_8_types_allowed=_coerce_str_list(data.get("perk_8_types_allowed")),
            auto_use_dk=bool(data.get("auto_use_dk", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "types_allowed": list(self.types_allowed),
            "require_chaos_key": self.require_chaos_key,
            "require_perk_8": self.require_perk_8,
            "min_spheres": self.min_spheres,
            "low_power": self.low_power.to_dict() if self.low_power else None,
            "perk_8_budget_mode": self.perk_8_budget_mode,
            "perk_8_budget_bypass_types": list(self.perk_8_budget_bypass_types),
            "perk_8_types_allowed": list(self.perk_8_types_allowed),
            "auto_use_dk": self.auto_use_dk,
        }


@dataclass
class UsRollKakeraRules:
    """Kakera clicking policy for rolls added via ``$us`` (not normal hourly rolls)."""

    # When False, ``$us`` rolls use the same kakera rules as normal hourly rolls.
    override: bool = False
    # When override is True, skip all kakera on ``$us`` rolls.
    skip_kakera: bool = False
    types_allowed: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> UsRollKakeraRules:
        if not data:
            return cls()
        if "override" in data or "skip_kakera" in data:
            return cls(
                override=bool(data.get("override", False)),
                skip_kakera=bool(data.get("skip_kakera", False)),
                types_allowed=_coerce_str_list(data.get("types_allowed")),
            )
        # Legacy ``mode`` field migration.
        mode = str(data.get("mode", "normal")).strip().lower()
        if mode == "none":
            return cls(override=True, skip_kakera=True)
        if mode == "selected":
            return cls(
                override=True,
                types_allowed=_coerce_str_list(data.get("types_allowed")),
            )
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "override": self.override,
            "skip_kakera": self.skip_kakera,
            "types_allowed": list(self.types_allowed),
        }


@dataclass
class SphereReactionRules:
    """When to click sphere buttons (perk 9).

    Chaos keys only affect kakera reaction power — not sphere clicks.
    """

    enabled: bool = False
    types_allowed: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SphereReactionRules:
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            types_allowed=_coerce_str_list(data.get("types_allowed")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MacroConfig:
    roll_command: str = "wa"
    prefix: str = "$"
    roll_delay_sec: float = 0.6
    claim_reset_margin_minutes: int = 20
    claim_expire_sec: int = 45
    # $us mass-roll mode: rolls Mudae adds per "$us N" (capped at 20 by Mudae),
    # and how close to the hourly rolls reset (minutes) we refuse to add more
    # $us rolls since a reset would clear them. us_add_delay_sec is how long to
    # wait after sending "$us N" before re-checking $tu, so Mudae has time to
    # register the command (sending follow-ups too fast makes it ignore them).
    us_batch_size: int = 20
    us_reset_margin_minutes: int = 2
    # Seconds to wait after a bare "$us" stack read before sending "$us N".
    us_read_before_add_delay_sec: float = 2.0
    # Seconds to wait after "$us N" before re-checking $tu.
    us_add_delay_sec: float = 5.0
    # Seconds to wait after a roll timeout before resuming $us mode.
    us_roll_timeout_retry_sec: float = 5.0
    us_roll_kakera: UsRollKakeraRules = field(default_factory=UsRollKakeraRules)
    character_claim: CharacterClaimRules = field(default_factory=CharacterClaimRules)
    kakera_reaction: KakeraReactionRules = field(default_factory=KakeraReactionRules)
    sphere_reaction: SphereReactionRules = field(default_factory=SphereReactionRules)

    def normalized_roll_command(self) -> str:
        return self.roll_command.strip().lstrip("$").lower() or "wa"

    def us_batch(self) -> int:
        return max(1, min(20, int(self.us_batch_size)))

    def us_add_delay(self) -> float:
        return max(2.0, float(self.us_add_delay_sec))

    def us_read_before_add_delay(self) -> float:
        return max(2.0, float(self.us_read_before_add_delay_sec))

    def us_roll_timeout_retry_delay(self) -> float:
        return max(2.0, float(self.us_roll_timeout_retry_sec))

    def kakera_rules_for_roll(self, *, us_roll: bool) -> KakeraReactionRules:
        """Effective kakera rules for a roll (normal hourly vs ``$us``-added)."""
        base = self.kakera_reaction
        if not us_roll:
            return base
        policy = self.us_roll_kakera
        if not policy.override:
            return base
        if policy.skip_kakera:
            return KakeraReactionRules(enabled=False)
        return KakeraReactionRules(
            enabled=base.enabled,
            types_allowed=list(policy.types_allowed),
            require_chaos_key=base.require_chaos_key,
            require_perk_8=base.require_perk_8,
            min_spheres=base.min_spheres,
            low_power=base.low_power,
            perk_8_budget_mode=base.perk_8_budget_mode,
            perk_8_budget_bypass_types=list(base.perk_8_budget_bypass_types),
            perk_8_types_allowed=list(base.perk_8_types_allowed),
            auto_use_dk=base.auto_use_dk,
        )

    def roll_delay(self) -> float:
        return max(self.roll_delay_sec, 0.6)

    # --- legacy shims (read-only access for older callers) ---
    @property
    def auto_claim_wish(self) -> bool:
        return self.character_claim.claim_on_wish_ping

    @property
    def claim_best_at_claim_reset(self) -> bool:
        return self.character_claim.enabled

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MacroConfig:
        if not data:
            return cls()

        character_raw = data.get("character_claim")
        kakera_raw = data.get("kakera_reaction")
        sphere_raw = data.get("sphere_reaction")
        us_kakera_raw = data.get("us_roll_kakera")

        character_claim = CharacterClaimRules.from_dict(
            character_raw if isinstance(character_raw, dict) else None
        )
        kakera_reaction = KakeraReactionRules.from_dict(
            kakera_raw if isinstance(kakera_raw, dict) else None
        )
        sphere_reaction = SphereReactionRules.from_dict(
            sphere_raw if isinstance(sphere_raw, dict) else None
        )
        us_roll_kakera = UsRollKakeraRules.from_dict(
            us_kakera_raw if isinstance(us_kakera_raw, dict) else None
        )

        # Legacy migration: flat booleans → CharacterClaimRules.
        if not isinstance(character_raw, dict):
            legacy_auto_claim = data.get("auto_claim")
            wish = data.get("auto_claim_wish")
            best_at_reset = data.get("claim_best_at_claim_reset")
            if best_at_reset is None and legacy_auto_claim is not None:
                best_at_reset = legacy_auto_claim
            if wish is not None:
                character_claim.claim_on_wish_ping = bool(wish)
            if best_at_reset is not None:
                character_claim.enabled = bool(best_at_reset)
            character_claim.only_final_hour = True

        return cls(
            roll_command=str(data.get("roll_command", "wa")),
            prefix=str(data.get("prefix", "$")),
            roll_delay_sec=float(data.get("roll_delay_sec", 0.6)),
            claim_reset_margin_minutes=int(data.get("claim_reset_margin_minutes", 20)),
            claim_expire_sec=int(data.get("claim_expire_sec", 45)),
            us_batch_size=int(data.get("us_batch_size", 20)),
            us_reset_margin_minutes=int(data.get("us_reset_margin_minutes", 2)),
            us_read_before_add_delay_sec=float(data.get("us_read_before_add_delay_sec", 2.0)),
            us_add_delay_sec=float(data.get("us_add_delay_sec", 5.0)),
            us_roll_timeout_retry_sec=float(data.get("us_roll_timeout_retry_sec", 5.0)),
            us_roll_kakera=us_roll_kakera,
            character_claim=character_claim,
            kakera_reaction=kakera_reaction,
            sphere_reaction=sphere_reaction,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "roll_command": self.roll_command,
            "prefix": self.prefix,
            "roll_delay_sec": self.roll_delay_sec,
            "claim_reset_margin_minutes": self.claim_reset_margin_minutes,
            "claim_expire_sec": self.claim_expire_sec,
            "us_batch_size": self.us_batch_size,
            "us_reset_margin_minutes": self.us_reset_margin_minutes,
            "us_read_before_add_delay_sec": self.us_read_before_add_delay_sec,
            "us_add_delay_sec": self.us_add_delay_sec,
            "us_roll_timeout_retry_sec": self.us_roll_timeout_retry_sec,
            "us_roll_kakera": self.us_roll_kakera.to_dict(),
            "character_claim": self.character_claim.to_dict(),
            "kakera_reaction": self.kakera_reaction.to_dict(),
            "sphere_reaction": self.sphere_reaction.to_dict(),
        }
