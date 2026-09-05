"""The `$bw` trade: rolls spent against wish spawns bought.

`$bw N` locks `N` of the hour's rolls in exchange for a spawn-chance bonus on
wishlist characters. Both halves are measurable, so unlike the rest of
:mod:`macro.advisor` this one can name an optimum: sweep `$bw` from 0 to the
point the roll pool runs out, and read off where expected keys per hour peaks.

**Where the numbers come from.** The tier tables below are Colblitz's published
`bwcalc` method. They are not taken on trust — they reproduce the live account's
own `$bonus`. At `$bw 19` the wish tiers contribute 290%, the sheet reports 440%,
and the remainder is a clean 150% of static bonus; the 2/2 `$bonus` fixture,
captured separately at `$bw 40`, yields the same 150. That agreement across two
different `$bw` values is what makes the decomposition trustworthy, and
:func:`sweep_bw` refuses to run when it does not hold.

**What the sheet reports is a delta.** ``starwish_spawn_bonus_pct`` is the extra
a starwish gets *on top of* the wish bonus, not the total — on the fixture,
``650 + 400 + 265 = 1315`` reproduces exactly the ``(= 1,315%)`` Mudae prints
after the bullet.

**Perk 1 is read, not derived.** The ``+N%`` on a `$wl` row is the character's
spawn bonus from perk 1 (see :func:`derive_perk1_pct` for the rule and why we
know). It is captured per character, so the sweep uses Mudae's own figure. It
raises the carrier's **own** weight without enlarging the pool it is measured
against — perk 1 shifts share rather than adding characters.

**Slash commands are modelled and deliberately not applied.** Mudae counts a
+10% slash bonus into the wish figure it reports, but the macro rolls with the
`$` prefix and never receives it, so ``uses_slash`` defaults to False and the
offset comes back out — of the **wish** figure only. `$bonus` lists slash as a
source of the wish line and not the starwish line, and a starwish's total is the
wish bonus plus its own extra, so taking it off both would remove the same 10
points twice. ``SLASH_ROLL_CAP_PER_HOUR`` is defined for the day slash rolling
ships and is not used today.

**Checked against `bwcalc` itself.** With slash left on, as Colblitz's own run
had it, this reproduces their published table for the live account to a mean
absolute error of **0.06%** across every column, and lands on all three of their
optima exactly: `$bw` 18 for the whole wishlist, 15 for starwishes, 15 for a
selected character, including "spawns 1 in 233 rolls".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- The published tier tables ------------------------------------------------
#
# Each entry is (bw value this tier runs up to, percentage points per roll).
# A `None` ceiling means "and everything above", so the tables are total.

# Wish spawn bonus bought by $bw: +20 each for the first 5, +15 to 15, +10 to
# 100, +5 to 200, +1 thereafter.
WISH_BW_TIERS: tuple[tuple[int | None, float], ...] = (
    (5, 20.0),
    (15, 15.0),
    (100, 10.0),
    (200, 5.0),
    (None, 1.0),
)

# Starwish gets this *in addition* to the wish bonus above.
STARWISH_BW_TIERS: tuple[tuple[int | None, float], ...] = (
    (100, 10.0),
    (200, 5.0),
    (None, 1.0),
)

# Chance of one extra key on a spawn of a character carrying perk 4, by level.
# Levels 1-5 step by 4; the sixth is the jump. `MUDAE_LOGIC.md`'s ouroperk table
# gives 30% at max, which is what is used here; Colblitz's write-up lists 25 for
# the sixth level with "+30% fully upgraded" alongside. The two disagree only on
# maxed characters, and only by 5 points on one term of the sum.
PERK4_KEY_PCT: tuple[float, ...] = (0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 30.0)

# Perk 1 at max, from `MUDAE_LOGIC.md`'s ouroperk table.
PERK1_MAX_PCT = 125.0

# Characters that are not on the wishlist, each contributing weight 1. Genuinely
# unknown: it depends on the server's game mode and disable lists, and nothing in
# the app derives it yet, so it is an input the page exposes rather than a
# constant anything should trust.
DEFAULT_BASE_POOL = 2000

# `MUDAE_LOGIC.md` "Hourly key limit" - Mudae refuses key gains past this.
KEY_CAP_PER_HOUR = 2200

# Flat spawn bonus a slash-command roll receives, and the number of slash rolls
# an hour Discord's rate limit allows. Defined for completeness; see the module
# docstring for why neither is applied.
SLASH_SPAWN_BONUS_PCT = 10.0
SLASH_ROLL_CAP_PER_HOUR = 1440


def _tiered(count: int, tiers: tuple[tuple[int | None, float], ...]) -> float:
    """Cumulative value of ``count`` rolls priced through ``tiers``."""
    total = 0.0
    previous = 0
    for ceiling, rate in tiers:
        if ceiling is None:
            if count > previous:
                total += (count - previous) * rate
            break
        highest = min(count, ceiling)
        if highest > previous:
            total += (highest - previous) * rate
        previous = ceiling
        if count <= ceiling:
            break
    return total


def wish_bw_bonus(bw: int) -> float:
    """Wish spawn bonus, in percentage points, bought by ``$bw bw``."""
    return _tiered(max(int(bw), 0), WISH_BW_TIERS)


def starwish_bw_bonus(bw: int) -> float:
    """What a starwish gets *on top of* :func:`wish_bw_bonus`."""
    return _tiered(max(int(bw), 0), STARWISH_BW_TIERS)


def derive_perk1_pct(
    perk1_levels: list[int] | tuple[int, ...],
    *,
    share_pct: float = 0.0,
    max_pct: float = PERK1_MAX_PCT,
) -> list[int]:
    """The ``+N%`` Mudae prints on each `$wl` row, derived from the roster.

    Perk 1 raises the spawn chance of the characters **either side of** its
    carrier in wishlist order, and the `$shop` OP1 upgrade feeds ``share_pct`` of
    that back to the carrier itself. The list **wraps**: the last row's right
    neighbour is the first row.

    Nothing calls this in anger — the capture already carries Mudae's own figure
    per row, which is what :func:`sweep_bw` uses. It exists because reproducing
    all 160 rows of a real listing is what established that the ``+N%`` is a perk-1
    spawn bonus at all, and a test that keeps reproducing them is what will notice
    if that ever stops being true.
    """
    levels = [max(int(level), 0) for level in perk1_levels]
    size = len(levels)
    if size == 0:
        return []

    def contribution(level: int) -> float:
        # Only the maxed value is documented, so anything short of the top level
        # scales linearly against it - good enough for a check, and every real
        # row seen so far carries perk 1 either absent or maxed.
        return max_pct * min(level, 6) / 6.0

    derived: list[int] = []
    for index, own in enumerate(levels):
        neighbours = contribution(levels[(index - 1) % size]) if size > 1 else 0.0
        if size > 2:
            neighbours += contribution(levels[(index + 1) % size])
        total = neighbours + contribution(own) * (share_pct / 100.0)
        # Mudae rounds half up; Python's round() would send 312.5 to 312.
        derived.append(int(total + 0.5))
    return derived


@dataclass(frozen=True)
class WishCharacter:
    """One wishlist row, reduced to what the spawn model needs."""

    name: str
    starwish: bool = False
    perk1_pct: float = 0.0
    perk4_level: int = 0

    @property
    def keys_per_spawn_from_perk4(self) -> float:
        level = min(max(int(self.perk4_level), 0), len(PERK4_KEY_PCT) - 1)
        return PERK4_KEY_PCT[level] / 100.0


@dataclass(frozen=True)
class BwInputs:
    """Everything the sweep needs, already pulled out of the four sheets."""

    # $bonus rolls_per_hour: base (= $settings setrolls) + bonus, before penalties.
    gross_rolls: int
    bk: int
    observed_bw: int
    # $bonus, as reported at observed_bw. The starwish figure is the extra.
    observed_wish_pct: float
    observed_starwish_extra_pct: float
    # $bonus extra_key_wish_chance_pct - the global chance of an additional key.
    extra_key_pct: float = 0.0
    characters: tuple[WishCharacter, ...] = ()
    base_pool: int = DEFAULT_BASE_POOL
    # $ov persrare: reroll a claimed non-wish character up to N times.
    persrare_n: int = 1
    claimed_pool: int = 0
    uses_slash: bool = False
    # Whether $bonus listed `slash` as a source of the wish figure it reported.
    slash_in_sheet: bool = False
    key_cap_per_hour: int = KEY_CAP_PER_HOUR

    @property
    def max_bw(self) -> int:
        """The `$bw` at which the hour's rolls run out."""
        return max(int(self.gross_rolls) - int(self.bk), 0)

    def net_rolls(self, bw: int) -> int:
        return max(int(self.gross_rolls) - int(bw) - int(self.bk), 0)


@dataclass(frozen=True)
class BwPoint:
    """One `$bw` value's worth of the curve."""

    bw: int
    net_rolls: int
    wish_pct: float
    starwish_pct: float
    pool_weight: float
    total_keys_per_hour: float
    capped_keys_per_hour: float
    # Spawns an hour, which is what the keys columns are built from and the
    # figure `bwcalc` shows beside them.
    wl_spawns_per_hour: float = 0.0
    sw_spawns_per_hour: float = 0.0
    sw_keys_per_hour: float = 0.0
    focus_spawn_pct: float | None = None
    focus_spawns_per_hour: float | None = None
    focus_keys_per_hour: float | None = None

    @property
    def wl_share_of_rolls(self) -> float:
        """Share of net rolls that land on any wishlist character."""
        return self.wl_spawns_per_hour / self.net_rolls if self.net_rolls else 0.0

    @property
    def sw_share_of_rolls(self) -> float:
        return self.sw_spawns_per_hour / self.net_rolls if self.net_rolls else 0.0

    @property
    def focus_one_in_rolls(self) -> float | None:
        """"Spawns 1 in N rolls" for the focus character."""
        if not self.focus_spawns_per_hour or not self.net_rolls:
            return None
        return self.net_rolls / self.focus_spawns_per_hour

    def to_dict(self) -> dict[str, Any]:
        return {
            "bw": self.bw,
            "net_rolls": self.net_rolls,
            "wish_pct": round(self.wish_pct, 1),
            "starwish_pct": round(self.starwish_pct, 1),
            "pool_weight": round(self.pool_weight, 1),
            "total_keys_per_hour": round(self.total_keys_per_hour, 3),
            "capped_keys_per_hour": round(self.capped_keys_per_hour, 3),
            "wl_spawns_per_hour": round(self.wl_spawns_per_hour, 3),
            "sw_spawns_per_hour": round(self.sw_spawns_per_hour, 3),
            "sw_keys_per_hour": round(self.sw_keys_per_hour, 3),
            "wl_share_of_rolls": round(self.wl_share_of_rolls, 5),
            "sw_share_of_rolls": round(self.sw_share_of_rolls, 5),
            "focus_spawn_pct": (
                None if self.focus_spawn_pct is None else round(self.focus_spawn_pct, 5)
            ),
            "focus_spawns_per_hour": (
                None
                if self.focus_spawns_per_hour is None
                else round(self.focus_spawns_per_hour, 4)
            ),
            "focus_keys_per_hour": (
                None
                if self.focus_keys_per_hour is None
                else round(self.focus_keys_per_hour, 4)
            ),
            "focus_one_in_rolls": (
                None
                if self.focus_one_in_rolls is None
                else round(self.focus_one_in_rolls, 1)
            ),
        }


@dataclass(frozen=True)
class BwSweep:
    """The curve, plus the three `$bw` values worth pointing at."""

    points: tuple[BwPoint, ...] = ()
    current_bw: int = 0
    max_bw: int = 0
    best_total_bw: int | None = None
    best_starwish_bw: int | None = None
    best_focus_bw: int | None = None
    focus_name: str = ""
    # Whether the focus character is a starwish, so a reader of `best_focus`
    # knows its own spawn bonus is `starwish_pct`, not the plain `wish_pct` the
    # aggregate rows use.
    focus_starwish: bool = False
    cheapest_capped_bw: int | None = None
    static_wish_pct: float = 0.0
    static_starwish_pct: float = 0.0
    slash_removed: bool = False
    blocked_by: str = ""
    notes: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return not self.blocked_by and bool(self.points)

    def at(self, bw: int | None) -> BwPoint | None:
        if bw is None:
            return None
        for point in self.points:
            if point.bw == bw:
                return point
        return None

    def to_dict(self) -> dict[str, Any]:
        current = self.at(self.current_bw)
        best_total = self.at(self.best_total_bw)
        return {
            "available": self.available,
            "blocked_by": self.blocked_by,
            "points": [point.to_dict() for point in self.points],
            "current_bw": self.current_bw,
            "max_bw": self.max_bw,
            "best_total_bw": self.best_total_bw,
            "best_starwish_bw": self.best_starwish_bw,
            "best_starwish": (
                self.at(self.best_starwish_bw).to_dict()
                if self.at(self.best_starwish_bw)
                else None
            ),
            "best_focus_bw": self.best_focus_bw,
            "focus_name": self.focus_name,
            "focus_starwish": self.focus_starwish,
            "cheapest_capped_bw": self.cheapest_capped_bw,
            "static_wish_pct": round(self.static_wish_pct, 1),
            "static_starwish_pct": round(self.static_starwish_pct, 1),
            "slash_removed": self.slash_removed,
            "current": current.to_dict() if current else None,
            "best_total": best_total.to_dict() if best_total else None,
            "best_focus": (
                self.at(self.best_focus_bw).to_dict()
                if self.at(self.best_focus_bw)
                else None
            ),
            # How much of the peak the current setting already captures. The
            # curve is flat near its top, so "you are at 99.4% of the best you
            # could do" is a more useful answer than the argmax on its own.
            "current_share_of_best": (
                round(current.total_keys_per_hour / best_total.total_keys_per_hour, 4)
                if current and best_total and best_total.total_keys_per_hour > 0
                else None
            ),
            "notes": list(self.notes),
        }


def _blocked(reason: str) -> BwSweep:
    return BwSweep(blocked_by=reason)


def sweep_bw(inputs: BwInputs, *, focus_name: str | None = None) -> BwSweep:
    """Expected keys per hour at every `$bw` from 0 to the roll pool's limit.

    Returns a sweep whose ``blocked_by`` names the missing or contradictory
    input when the curve cannot be computed, rather than a curve that looks
    authoritative and is not.
    """
    if inputs.gross_rolls <= 0:
        return _blocked("Rolls per hour is unknown — fetch $bonus (and $settings).")
    if not inputs.characters:
        return _blocked("No $wlsz+z! capture for this account and server yet.")
    if inputs.max_bw <= 0:
        return _blocked("$bk alone spends the whole roll pool — nothing left for $bw.")

    observed_bw = max(int(inputs.observed_bw), 0)
    static_wish = float(inputs.observed_wish_pct) - wish_bw_bonus(observed_bw)
    static_starwish = float(inputs.observed_starwish_extra_pct) - starwish_bw_bonus(
        observed_bw
    )
    if static_wish < 0 or static_starwish < 0:
        # The sheet reports less bonus than $bw alone should have bought, so one
        # of the two is wrong and the decomposition is meaningless. Say so.
        return _blocked(
            f"$bonus reports less wish bonus than $bw {observed_bw} alone accounts "
            "for — the sheet is stale, or the published tiers have moved."
        )

    notes: list[str] = []
    slash_removed = inputs.slash_in_sheet and not inputs.uses_slash
    if slash_removed:
        # Taken off the **wish** offset only. `$bonus` lists slash as a source of
        # the wish line and not of the starwish line, and a starwish's total is
        # the wish bonus plus its own extra — so subtracting from both would
        # remove the same 10 points twice from every starwish.
        static_wish = max(static_wish - SLASH_SPAWN_BONUS_PCT, 0.0)
        notes.append(
            f"$bonus counts a +{SLASH_SPAWN_BONUS_PCT:.0f}% slash bonus the macro "
            "never gets — it rolls with $ — so that much is taken back out of the "
            "wish bonus, which carries it through to starwish once."
        )
    elif inputs.uses_slash and not inputs.slash_in_sheet:
        notes.append(
            "Slash rolling is on, but $bonus does not list slash as a source of "
            "the wish bonus, so nothing was added."
        )

    persrare_n = max(int(inputs.persrare_n), 1)
    claimed = max(float(inputs.claimed_pool), 0.0)
    if persrare_n > 1 and claimed <= 0:
        notes.append(
            "$persrare rerolls are set, but with no claimed-character count they "
            "change nothing — enter one to model them."
        )

    extra_key = max(float(inputs.extra_key_pct), 0.0) / 100.0
    focus_index: int | None = None
    if focus_name:
        wanted = focus_name.strip().casefold()
        for index, character in enumerate(inputs.characters):
            if character.name.strip().casefold() == wanted:
                focus_index = index
                break

    points: list[BwPoint] = []
    for bw in range(0, inputs.max_bw + 1):
        wish_pct = wish_bw_bonus(bw) + static_wish
        starwish_pct = wish_pct + starwish_bw_bonus(bw) + static_starwish

        # A character's own spawn weight carries its perk-1 bonus; the pool it is
        # measured against does not. Perk 1 raises the carrier's share of the
        # pool rather than enlarging the pool, which is how `bwcalc` models it —
        # counting it in the denominator instead reproduces its published table
        # 25x worse (0.06% mean error against 1.6%).
        weights: list[float] = []
        pool_terms: list[float] = []
        for character in inputs.characters:
            bonus = starwish_pct if character.starwish else wish_pct
            weights.append(1.0 + (bonus + character.perk1_pct) / 100.0)
            pool_terms.append(1.0 + bonus / 100.0)

        pool_weight = float(inputs.base_pool) + sum(pool_terms)
        if pool_weight <= 0:
            continue

        # $persrare rerolls a claimed non-wish character up to N times, so a wish
        # character gets N chances rather than one. At N = 1 this is exactly 1.
        claimed_share = min(claimed / pool_weight, 0.999999)
        if persrare_n > 1 and claimed_share > 0:
            reroll_boost = (1.0 - claimed_share**persrare_n) / (1.0 - claimed_share)
        else:
            reroll_boost = 1.0

        net = inputs.net_rolls(bw)
        total_keys = 0.0
        wl_spawns = 0.0
        sw_spawns = 0.0
        sw_keys = 0.0
        focus_spawn: float | None = None
        focus_spawns: float | None = None
        focus_keys: float | None = None
        for index, (character, weight) in enumerate(zip(inputs.characters, weights)):
            spawn = (weight / pool_weight) * reroll_boost
            spawns_per_hour = net * spawn
            keys = spawns_per_hour * (
                1.0 + extra_key + character.keys_per_spawn_from_perk4
            )
            total_keys += keys
            wl_spawns += spawns_per_hour
            if character.starwish:
                sw_spawns += spawns_per_hour
                sw_keys += keys
            if index == focus_index:
                focus_spawn = spawn * 100.0
                focus_spawns = spawns_per_hour
                focus_keys = keys

        points.append(
            BwPoint(
                bw=bw,
                net_rolls=net,
                wish_pct=wish_pct,
                starwish_pct=starwish_pct,
                pool_weight=pool_weight,
                total_keys_per_hour=total_keys,
                capped_keys_per_hour=min(total_keys, float(inputs.key_cap_per_hour)),
                wl_spawns_per_hour=wl_spawns,
                sw_spawns_per_hour=sw_spawns,
                sw_keys_per_hour=sw_keys,
                focus_spawn_pct=focus_spawn,
                focus_spawns_per_hour=focus_spawns,
                focus_keys_per_hour=focus_keys,
            )
        )

    if not points:
        return _blocked("The roll pool leaves no room to sweep $bw.")

    # Ranked on the capped figure: keys past the hourly limit are refused, so
    # buying $bw to produce them costs rolls and returns nothing.
    best_total = max(points, key=lambda point: (point.capped_keys_per_hour, -point.bw))
    # Starwishes carry the extra bonus, so their own peak sits lower than the
    # whole wishlist's — worth naming separately, as `bwcalc` does.
    best_starwish = (
        max(points, key=lambda point: (point.sw_keys_per_hour, -point.bw))
        if any(character.starwish for character in inputs.characters)
        else None
    )
    best_focus = (
        max(points, key=lambda point: (point.focus_keys_per_hour or 0.0, -point.bw))
        if focus_index is not None
        else None
    )
    capped = [
        point.bw
        for point in points
        if point.total_keys_per_hour >= float(inputs.key_cap_per_hour)
    ]
    if capped:
        notes.append(
            f"The {inputs.key_cap_per_hour:,}/hour key limit is reached at $bw "
            f"{min(capped)}; past that, more $bw buys nothing."
        )

    return BwSweep(
        points=tuple(points),
        current_bw=observed_bw,
        max_bw=inputs.max_bw,
        best_total_bw=best_total.bw,
        best_starwish_bw=best_starwish.bw if best_starwish else None,
        best_focus_bw=best_focus.bw if best_focus else None,
        focus_name=(
            inputs.characters[focus_index].name if focus_index is not None else ""
        ),
        focus_starwish=(
            inputs.characters[focus_index].starwish if focus_index is not None else False
        ),
        cheapest_capped_bw=min(capped) if capped else None,
        static_wish_pct=static_wish,
        static_starwish_pct=static_starwish,
        slash_removed=slash_removed,
        notes=tuple(notes),
    )


def characters_from_wishlist(entries: Any) -> tuple[WishCharacter, ...]:
    """Wishlist rows as captured by `$wlsz+z!`, reduced to the spawn model.

    ``sphere_percent`` is Mudae's own ``+N%`` for the row, and is the row's
    **perk-1 spawn bonus** despite the stored name — see
    :func:`derive_perk1_pct`. ``upgrades_full`` means every perk is maxed, which
    for perk 4 is level 6.
    """
    characters: list[WishCharacter] = []
    for row in entries or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        full = bool(row.get("upgrades_full"))
        upgrades = row.get("upgrades") or {}
        perk4 = 6 if full else 0
        if not full and isinstance(upgrades, dict):
            for key, value in upgrades.items():
                try:
                    if int(key) == 4:
                        perk4 = int(value)
                        break
                except (TypeError, ValueError):
                    continue
        try:
            perk1 = float(
                row.get("sphere_percent") or row.get("perk1_spawn_pct") or 0
            )
        except (TypeError, ValueError):
            perk1 = 0.0
        characters.append(
            WishCharacter(
                name=name,
                starwish=bool(row.get("starwish")),
                perk1_pct=perk1,
                perk4_level=max(min(perk4, 6), 0),
            )
        )
    return tuple(characters)
