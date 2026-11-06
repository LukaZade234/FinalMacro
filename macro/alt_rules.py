"""How one alt supports the main: the Claims, Kakera and Spheres parts.

A tier is a quick-pick that fills all three parts at once. Changing any part
afterwards makes the alt ``custom``; picking a tier again resets the parts.
:func:`tier_of` works the tier out from the parts, so a stored ``tier`` that
no longer matches them cannot mislead anyone.

Turn order is not stored here: it is the order of the alts on the Alts page
(``AltsStore.order``), the same for every account.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

TIER_SUPPORT = "support"
TIER_SHARED = "shared"
TIER_INDEPENDENT = "independent"
TIER_CUSTOM = "custom"
TIERS = (TIER_SUPPORT, TIER_SHARED, TIER_INDEPENDENT)

# Claims · whose rolls the alt claims from.
SOURCE_MAIN = "main"  # the main's rolls only — never rolls itself
SOURCE_BOTH = "both"  # the main's first, then its own batch after the main's
SOURCE_OWN = "own"  # its own; helps on the main's rolls only when idle
SOURCES = (SOURCE_MAIN, SOURCE_BOTH, SOURCE_OWN)

POLICY_PRESET = "preset"  # its own rolls follow a preset's claim rules
POLICY_FIRST = "first"  # first unclaimed character, no requirements
POLICIES = (POLICY_PRESET, POLICY_FIRST)

AFTER_GIVE = "give"
AFTER_KEEP = "keep"

# When kakera / spheres are passed to the main.
PASS_NEVER = "never"
PASS_SESSION = "session"
PASS_DAILY = "daily"
PASS_ABOVE = "above"
PASS_MODES = (PASS_NEVER, PASS_SESSION, PASS_DAILY, PASS_ABOVE)

KL_OFF = "off"
KL_DAILY = "daily"
KL_HOURLY = "hourly"

BUTTONS_OFF = "off"
BUTTONS_PERK9 = "perk9"
BUTTONS_TWENTY = "twenty"  # roll until the day's 20 sphere clicks are spent

DEFAULT_MAIN_ROLL_KAKERA = ["kakeraO", "kakeraR", "kakeraW", "kakeraL", "kakeraC"]
ALL_MINIGAMES = ["oh", "oc", "oq", "ot"]


def _pick(value: Any, allowed: tuple[str, ...], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(x) for x in value if str(x).strip()]


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@dataclass
class AltClaims:
    source: str = SOURCE_MAIN
    own_policy: str = POLICY_PRESET
    # Preset id for the alt's own rolls ("" = the main's preset).
    own_preset_id: str = ""
    own_after: str = AFTER_KEEP
    force_divorce: bool = True
    spend_rt: bool = True
    snipe_guard: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AltClaims:
        d = data or {}
        base = cls()
        return cls(
            source=_pick(d.get("source"), SOURCES, base.source),
            own_policy=_pick(d.get("own_policy"), POLICIES, base.own_policy),
            own_preset_id=str(d.get("own_preset_id") or ""),
            own_after=_pick(d.get("own_after"), (AFTER_GIVE, AFTER_KEEP), base.own_after),
            force_divorce=bool(d.get("force_divorce", base.force_divorce)),
            spend_rt=bool(d.get("spend_rt", base.spend_rt)),
            snipe_guard=bool(d.get("snipe_guard", base.snipe_guard)),
        )


@dataclass
class AltKakera:
    on_main_rolls: bool = True
    main_roll_types: list[str] = field(default_factory=lambda: list(DEFAULT_MAIN_ROLL_KAKERA))
    on_own_rolls: bool = False
    use_dk: bool = True
    auto_kl: str = KL_DAILY
    pass_mode: str = PASS_SESSION
    keep: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AltKakera:
        d = data or {}
        base = cls()
        types = d.get("main_roll_types")
        return cls(
            on_main_rolls=bool(d.get("on_main_rolls", base.on_main_rolls)),
            main_roll_types=_str_list(types) if types is not None else list(base.main_roll_types),
            on_own_rolls=bool(d.get("on_own_rolls", base.on_own_rolls)),
            use_dk=bool(d.get("use_dk", base.use_dk)),
            auto_kl=_pick(d.get("auto_kl"), (KL_OFF, KL_DAILY, KL_HOURLY), base.auto_kl),
            pass_mode=_pick(d.get("pass_mode"), PASS_MODES, base.pass_mode),
            keep=_int(d.get("keep"), base.keep),
        )


@dataclass
class AltSpheres:
    minigames: bool = True
    games: list[str] = field(default_factory=lambda: list(ALL_MINIGAMES))
    buttons: str = BUTTONS_OFF
    pass_mode: str = PASS_DAILY
    keep: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AltSpheres:
        d = data or {}
        base = cls()
        games = d.get("games")
        return cls(
            minigames=bool(d.get("minigames", base.minigames)),
            games=[g for g in _str_list(games) if g in ALL_MINIGAMES] if games is not None else list(base.games),
            buttons=_pick(d.get("buttons"), (BUTTONS_OFF, BUTTONS_PERK9, BUTTONS_TWENTY), base.buttons),
            pass_mode=_pick(d.get("pass_mode"), PASS_MODES, base.pass_mode),
            keep=_int(d.get("keep"), base.keep),
        )


@dataclass
class AltRules:
    enabled: bool = True
    claims: AltClaims = field(default_factory=AltClaims)
    kakera: AltKakera = field(default_factory=AltKakera)
    spheres: AltSpheres = field(default_factory=AltSpheres)

    @property
    def rolls(self) -> bool:
        """Whether the alt rolls at all (after the main's batch)."""
        return self.claims.source != SOURCE_MAIN

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AltRules:
        d = data or {}
        return cls(
            enabled=bool(d.get("enabled", True)),
            claims=AltClaims.from_dict(d.get("claims")),
            kakera=AltKakera.from_dict(d.get("kakera")),
            spheres=AltSpheres.from_dict(d.get("spheres")),
        )

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["tier"] = tier_of(self)
        return out

    def parts(self) -> dict[str, Any]:
        """The three parts only — what a tier decides."""
        data = asdict(self)
        data.pop("enabled", None)
        return data


_TIER_RULES: dict[str, AltRules] = {
    TIER_SUPPORT: AltRules(
        claims=AltClaims(source=SOURCE_MAIN, own_after=AFTER_GIVE, force_divorce=True, spend_rt=True),
        kakera=AltKakera(on_main_rolls=True, on_own_rolls=False, auto_kl=KL_DAILY, pass_mode=PASS_SESSION),
        spheres=AltSpheres(minigames=True, buttons=BUTTONS_OFF, pass_mode=PASS_DAILY),
    ),
    TIER_SHARED: AltRules(
        claims=AltClaims(source=SOURCE_BOTH, own_after=AFTER_KEEP, force_divorce=True, spend_rt=False),
        kakera=AltKakera(on_main_rolls=True, on_own_rolls=True, auto_kl=KL_DAILY, pass_mode=PASS_SESSION),
        spheres=AltSpheres(minigames=True, buttons=BUTTONS_TWENTY, pass_mode=PASS_DAILY),
    ),
    TIER_INDEPENDENT: AltRules(
        claims=AltClaims(source=SOURCE_OWN, own_after=AFTER_KEEP, force_divorce=False, spend_rt=False),
        kakera=AltKakera(
            on_main_rolls=False,
            main_roll_types=["kakeraR", "kakeraW", "kakeraC"],
            on_own_rolls=True,
            auto_kl=KL_HOURLY,
            pass_mode=PASS_ABOVE,
        ),
        spheres=AltSpheres(minigames=True, buttons=BUTTONS_PERK9, pass_mode=PASS_NEVER),
    ),
}


def rules_for_tier(tier: str, *, enabled: bool = True) -> AltRules:
    if tier not in _TIER_RULES:
        raise KeyError(tier)
    rules = copy.deepcopy(_TIER_RULES[tier])
    rules.enabled = enabled
    return rules


def tier_of(rules: AltRules) -> str:
    """The tier whose parts these are exactly, else ``custom``.

    Only the behaviour a tier sets is compared, so an alt's own preset
    choice, reserve amounts, kakera colours or *when* it passes to the main
    (timing, not behaviour) don't knock it out of its tier. Picking a tier
    still sets its pass timing.
    """
    parts = _tier_view(rules)
    for tier in TIERS:
        if _tier_view(_TIER_RULES[tier]) == parts:
            return tier
    return TIER_CUSTOM


def _tier_view(rules: AltRules) -> dict[str, Any]:
    data = rules.parts()
    data["claims"].pop("own_preset_id", None)
    data["kakera"].pop("keep", None)
    data["kakera"].pop("main_roll_types", None)
    data["kakera"].pop("pass_mode", None)
    data["spheres"].pop("pass_mode", None)
    data["spheres"].pop("keep", None)
    return data
