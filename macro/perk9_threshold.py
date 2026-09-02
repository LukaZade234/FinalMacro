"""Perk-9 adaptive click/skip threshold.

Perk 9 spawns sphere buttons on characters rolled today and each click spends
one slot of a daily budget (``10 + OP9``). The colour mix is bottom-heavy, so a
static allow-list either burns the budget on blue or lets slots expire unused.
This module scores one click with Colblitz's published EV formula, then solves
``V(opportunities_left, clicks_left)`` backwards so the bar falls as the day
runs out: click a colour when its EV beats the value of saving the slot for a
later spawn. ``macro/rule_eval.py`` only reads the resulting context; the table
is built by ``macro/sphere_reactor.py`` once per roll batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb, exp
from typing import Any

from mudae.constants import canonical_sphere_emoji

# Colblitz p9calc, 138,925 observed sphere rolls (supplied 2026-08-29).
# Dark and light are measured averages of what they resolve into, which is why
# they are absent from ``mudae.constants.SPHERE_BASE_SP``. Dark outranks orange
# here; ``SPHERE_VALUE_RANK`` disagrees because it orders $oh clicks, not EV.
COLBLITZ_SPHERE_BASE_SP: dict[str, float] = {
    "spB": 10.0,
    "spT": 20.0,
    "spG": 35.0,
    "spY": 55.0,
    "spL": 75.9,
    "spO": 90.0,
    "spD": 104.5,
    "spR": 150.0,
    "spW": 500.0,
}

# Conditional on a sphere button appearing, so these sum to 1.0 and one unit of
# ``opportunities`` is one perk-9 spawn (not one roll).
COLBLITZ_SPHERE_FREQUENCY: dict[str, float] = {
    "spB": 0.5958,
    "spT": 0.2410,
    "spG": 0.0788,
    "spL": 0.0298,
    "spY": 0.0267,
    "spD": 0.0145,
    "spO": 0.0099,
    "spR": 0.0031,
    "spW": 0.0004,
}

# The threshold barely moves past this many remaining spawns, so cap the table
# instead of letting a bad estimate build a huge one.
MAX_TABLE_OPPORTUNITIES = 1000
# Below this many logged clicks our own frequencies are noise next to the
# 138,925-roll defaults.
MIN_FREQUENCY_SAMPLES = 500
# Click history kept on the Run panel before it would wrap.
PERK9_HISTORY_SHOWN = 24
# Unspent clicks expire at the UTC reset, so inside this last stretch of the day
# every remaining sphere is worth more than the slot it costs. This is the one
# guarantee that holds no matter how wrong the spawn forecast is.
PERK9_SPENDDOWN_MINUTES = 60


def _ev_key(emoji: str | None) -> str:
    """Canonical lookup key; bare ``sp`` is red, like ``sphere_base_sp``."""
    key = canonical_sphere_emoji(emoji)
    return "spR" if key == "sp" else key


def sphere_ev(
    base_sp: float,
    *,
    double_chance_pct: float = 0.0,
    additional_spheres: float = 0.0,
    shop9_bonus_pct: float = 0.0,
) -> float:
    """``(base × (1 + double) + flat) × (1 + shop9)`` — Colblitz's EV formula."""
    double = float(double_chance_pct) / 100.0
    shop9 = float(shop9_bonus_pct) / 100.0
    return (float(base_sp) * (1.0 + double) + float(additional_spheres)) * (1.0 + shop9)


def _overlay(defaults: dict[str, float], overrides: dict[str, float] | None) -> dict[str, float]:
    """Layer re-measured colours over the defaults, keyed canonically.

    The preset stores only colours the user actually edited, and the Presets
    panel shows the defaults for the rest, so a partial map must *not* shrink
    the model down to the handful of edited colours.
    """
    merged = {_ev_key(emoji): float(value) for emoji, value in defaults.items()}
    for emoji, value in (overrides or {}).items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            merged[_ev_key(emoji)] = number
    return merged


def sphere_base_values(overrides: dict[str, float] | None = None) -> dict[str, float]:
    """Base SP per colour, with any settings override layered on."""
    return _overlay(COLBLITZ_SPHERE_BASE_SP, overrides)


def build_ev_table(
    base_values: dict[str, float] | None = None,
    *,
    double_chance_pct: float = 0.0,
    additional_spheres: float = 0.0,
    shop9_bonus_pct: float = 0.0,
) -> dict[str, float]:
    """Per-colour EV from base SP plus the account's ``$bonus`` / ``$shop``."""
    return {
        emoji: sphere_ev(
            base,
            double_chance_pct=double_chance_pct,
            additional_spheres=additional_spheres,
            shop9_bonus_pct=shop9_bonus_pct,
        )
        for emoji, base in _overlay(COLBLITZ_SPHERE_BASE_SP, base_values).items()
    }


def normalize_frequency(freq: dict[str, float] | None) -> dict[str, float]:
    """Scale colour weights to sum to 1 so the DP stays a real expectation.

    User-entered percentages rarely total exactly 100; they are still the
    relative mix of a button that *did* spawn. A colour set to 0 drops out.
    """
    cleaned = {
        emoji: weight
        for emoji, weight in _overlay(COLBLITZ_SPHERE_FREQUENCY, freq).items()
        if weight > 0
    }
    total = sum(cleaned.values())
    if total <= 0:
        return dict(COLBLITZ_SPHERE_FREQUENCY)
    return {emoji: weight / total for emoji, weight in cleaned.items()}


def build_value_table(
    opportunities_left: int,
    clicks_left: int,
    ev_by_emoji: dict[str, float],
    freq_by_emoji: dict[str, float],
) -> list[list[float]]:
    """``V[r][c]`` — expected SP from ``r`` spawns with ``c`` clicks in hand."""
    rows = max(0, min(int(opportunities_left), MAX_TABLE_OPPORTUNITIES))
    cols = max(0, int(clicks_left))
    table = [[0.0] * (cols + 1) for _ in range(rows + 1)]
    if rows == 0 or cols == 0:
        return table
    weights = [
        (freq, ev_by_emoji.get(emoji, 0.0)) for emoji, freq in freq_by_emoji.items()
    ]
    for r in range(1, rows + 1):
        prev = table[r - 1]
        row = table[r]
        for c in range(1, cols + 1):
            skip = prev[c]
            spend = prev[c - 1]
            row[c] = sum(freq * max(ev + spend, skip) for freq, ev in weights)
    return table


def click_threshold(table: list[list[float]], r: int, c: int) -> float:
    """Minimum EV worth a click at ``r`` spawns / ``c`` clicks left."""
    if c <= 0 or r <= 0:
        return float("inf")
    row = table[min(r, len(table) - 1) - 1]
    if c >= len(row):
        c = len(row) - 1
    if c <= 0:
        return float("inf")
    return row[c] - row[c - 1]


def best_static_strategy(
    opportunities: int,
    clicks_max: int,
    ev_by_emoji: dict[str, float],
    freq_by_emoji: dict[str, float],
) -> tuple[list[str], float]:
    """Best fixed allow-list and its expected SP (Colblitz's binomial method).

    Benchmark only — the live decision path uses the DP. Requires knowing the
    day's spawn count up front, which is exactly what the DP does not.
    """
    order = sorted(freq_by_emoji, key=lambda emoji: ev_by_emoji.get(emoji, 0.0))
    best: tuple[list[str], float] = ([], 0.0)
    for cut in range(len(order) + 1):
        clicked = order[cut:]
        p_click = sum(freq_by_emoji[emoji] for emoji in clicked)
        if p_click <= 0:
            continue
        # Mean SP *per click*, so the product with expected clicks has SP units.
        mean = sum(freq_by_emoji[e] * ev_by_emoji.get(e, 0.0) for e in clicked) / p_click
        used = 0.0
        cdf = 0.0
        spawns = int(opportunities)
        # P(X > j) is 0 once j reaches the spawn count, and 0**negative raises.
        for j in range(min(int(clicks_max), spawns)):
            cdf += comb(spawns, j) * p_click**j * (1.0 - p_click) ** (spawns - j)
            used += 1.0 - cdf
        total = mean * used
        if total > best[1]:
            best = (list(clicked), total)
    return best


def estimate_sphere_colour_frequency(
    events: list[dict[str, Any]] | None = None,
    *,
    min_samples: int = MIN_FREQUENCY_SAMPLES,
) -> dict[str, float] | None:
    """Our own logged colour mix, or ``None`` when the sample is too small.

    Advisory: the Presets panel shows this next to the user's numbers. It never
    overrides them.
    """
    from mudae.sphere_log import get_sphere_events, normalize_source

    rows = get_sphere_events() if events is None else events
    counts: dict[str, int] = {}
    total = 0
    for entry in rows:
        if normalize_source(entry) != "sphere_click":
            continue
        emoji = _ev_key(entry.get("sphere_type"))
        if not emoji or emoji not in COLBLITZ_SPHERE_BASE_SP:
            continue
        counts[emoji] = counts.get(emoji, 0) + 1
        total += 1
    if total < int(min_samples):
        return None
    return {emoji: count / total for emoji, count in counts.items()}


def hours_until_reset(now: Any = None) -> float:
    """Hours left before the perk-9 budget expires at 00:00 UTC."""
    from macro.perk8_daily import next_daily_reset
    from mudae.clock import utc_now

    moment = now or utc_now()
    return max(0.0, (next_daily_reset(moment) - moment).total_seconds() / 3600.0)


def is_spend_down_window(now: Any = None) -> bool:
    """True inside the last hour of the day, when saving a click is pure loss."""
    return hours_until_reset(now) * 60.0 <= PERK9_SPENDDOWN_MINUTES


def forecast_spawns(*, pool: int, rolled: int, rolls_left: int, hazard: float) -> int:
    """Perk-9 spawns still to come from ``rolls_left`` more rolls.

    Rolls sample the pool without replacement, so the arrival rate decays as the
    pool empties. Integrating that over the rolls still available today:

        (pool − rolled) × (1 − exp(−hazard × rolls_left / pool))

    which is the *forecast* the value table needs, as opposed to ``pool −
    rolled`` — a ceiling on distinct characters that the tail of the day never
    comes close to reaching.
    """
    try:
        pool_n = int(pool)
        rolled_n = int(rolled)
        rolls_n = max(0, int(rolls_left))
        rate = float(hazard)
    except (TypeError, ValueError):
        return 0
    remaining = max(0, pool_n - rolled_n)
    if pool_n <= 0 or remaining <= 0 or rolls_n <= 0 or rate <= 0:
        return 0
    return int(round(remaining * (1.0 - exp(-rate * rolls_n / pool_n))))


def estimate_opportunities_left(
    state: Any,
    *,
    manual_override: int = 0,
    rolls_per_hour: int | None = None,
    now: Any = None,
) -> int | None:
    """How many more perk-9 sphere spawns to expect today.

    Mudae's own ``(Perk 9) Rolled today: 44/154`` from ``$ohu9`` gives a hard
    ceiling — the pool cannot spawn a character twice — but the tail of a pool
    is effectively unrollable, so that number plateaus and the value table never
    learns the day is ending. When the account's own arrival rate has been
    measured (``state.perk9_hazard``, learned in ``macro.perk9_daily``), prefer
    the forecast of spawns the remaining rolls will actually produce. ``None``
    means we cannot tell, so the caller keeps the static filter.
    """
    from macro.perk9_daily import rolled_today_estimate

    if manual_override and int(manual_override) > 0:
        return int(manual_override)

    pool = getattr(state, "perk9_roll_pool", None)
    # ``rolled`` is only as fresh as the last $ohu9, so the estimate brings it
    # forward by the spawns seen since — otherwise it sits still all session.
    rolled_now = rolled_today_estimate(state)
    from_pool: int | None = None
    if pool is not None and rolled_now is not None:
        from_pool = max(0, int(pool) - rolled_now)

    hazard = getattr(state, "perk9_hazard", None)
    from_rolls: int | None = None
    if rolls_per_hour and int(rolls_per_hour) > 0 and hazard and float(hazard) > 0:
        rolls_left_today = int(
            round(int(rolls_per_hour) * hours_until_reset(now))
        )
        rolls_now = getattr(state, "rolls_left", None)
        if rolls_now is not None:
            rolls_left_today += max(0, int(rolls_now))
        if pool is not None and rolled_now is not None:
            from_rolls = forecast_spawns(
                pool=int(pool),
                rolled=rolled_now,
                rolls_left=rolls_left_today,
                hazard=float(hazard),
            )
        else:
            # No pool to deplete against; the undecayed rate is the best we have.
            from_rolls = int(round(rolls_left_today * float(hazard)))

    candidates = [n for n in (from_pool, from_rolls) if n is not None]
    if not candidates:
        return None
    return max(0, min(candidates))


@dataclass
class Perk9ThresholdContext:
    """Everything ``passes_sphere_reaction`` needs to judge one sphere button."""

    ev_by_emoji: dict[str, float]
    value_table: list[list[float]]
    opportunities_left: int
    clicks_left: int
    spend_down: bool = False

    def threshold(self) -> float:
        if self.spend_down:
            # Last hour of the day: a saved click is worth nothing at the reset,
            # so every colour beats holding on to it.
            return 0.0
        return click_threshold(
            self.value_table, self.opportunities_left, self.clicks_left
        )

    def ev_for(self, emoji: str | None) -> float | None:
        return self.ev_by_emoji.get(_ev_key(emoji))

    def should_click(self, emoji: str | None) -> bool:
        """Click when this colour's EV beats the value of saving the slot."""
        if self.clicks_left <= 0 or self.opportunities_left <= 0:
            return False
        ev = self.ev_for(emoji)
        if ev is None:
            # Unknown colour already cleared the user's allow-list; do not drop it.
            return True
        return ev >= self.threshold()


def adaptive_status(state: Any, rules: Any = None, *, now: Any = None) -> dict[str, Any]:
    """Live perk-9 panel payload: tracked counts, click history, and the EV bar.

    Mirrors ``macro.perk8_power.power_save_status`` — ``enabled`` false keeps the
    Run page from drawing anything.
    """
    if rules is None or not getattr(rules, "budget_aware", False):
        return {"enabled": False}

    used = int(getattr(state, "perk9_clicks_today", 0) or 0)
    cap = int(getattr(state, "perk9_click_max", 0) or 0)
    clicks_left = max(0, cap - used)
    spawns_seen = int(getattr(state, "perk9_spawns_today", 0) or 0)
    # Newest first. The earning log also covers clicks made before this session,
    # so prefer whichever source resolved more colours and only fall back to
    # face-down for clicks neither one can name.
    from macro.perk9_daily import recent_perk9_click_colours

    session_history = list(reversed(list(getattr(state, "perk9_click_emojis", []) or [])))
    try:
        logged_history = recent_perk9_click_colours(used)
    except Exception:
        logged_history = []
    history = (
        logged_history if len(logged_history) >= len(session_history) else session_history
    )[:used]
    unknown = max(0, used - len(history))
    history = history + ["spU"] * unknown

    spawns_left = estimate_opportunities_left(
        state,
        manual_override=int(getattr(rules, "expected_daily_opportunities", 0) or 0),
        rolls_per_hour=getattr(state, "rolls_per_hour_net", None),
        now=now,
    )
    spend_down = is_spend_down_window(now)
    pool = getattr(state, "perk9_roll_pool", None)
    rolled = getattr(state, "perk9_rolled_today", None)
    hazard = getattr(state, "perk9_hazard", None)
    status: dict[str, Any] = {
        "enabled": True,
        "clicks_used": used,
        "clicks_max": cap,
        "clicks_left": clicks_left,
        "spawns_seen": spawns_seen,
        "spawns_left": spawns_left,
        # The pool remainder the forecast sits under, so the panel can show why
        # "left today" is smaller than "rolled/pool" implies.
        "spawns_ceiling": (
            max(0, int(pool) - int(rolled))
            if pool is not None and rolled is not None
            else None
        ),
        "hazard": round(float(hazard), 4) if hazard else None,
        "spend_down": spend_down,
        # Today's expected run: what has appeared plus what is still coming.
        "spawns_total": (
            spawns_seen + spawns_left if spawns_left is not None else None
        ),
        "rolled_today": getattr(state, "perk9_rolled_today", None),
        "roll_pool": getattr(state, "perk9_roll_pool", None),
        "history": history[:PERK9_HISTORY_SHOWN],
        "unknown_clicks": unknown,
        "allowed": [],
        "threshold": None,
        "looser_at": None,
        "looser_adds": [],
        "stricter_at": None,
        "stricter_drops": [],
    }

    ctx = build_perk9_threshold_context(
        opportunities_left=spawns_left or 0,
        clicks_left=clicks_left,
        base_values=getattr(rules, "sphere_values", None) or None,
        frequency=getattr(rules, "sphere_frequency", None) or None,
        double_chance_pct=float(getattr(state, "sphere_double_chance_pct", 0.0) or 0.0),
        additional_spheres=float(getattr(state, "additional_spheres", 0.0) or 0.0),
        shop9_bonus_pct=float(getattr(state, "perk9_sphere_value_pct", 0.0) or 0.0),
        spend_down=spend_down,
    )
    if ctx is None:
        return status

    order = sorted(ctx.ev_by_emoji, key=lambda e: ctx.ev_by_emoji[e])

    def allowed_at(spawns: int, clicks: int) -> list[str]:
        bar = 0.0 if ctx.spend_down else click_threshold(ctx.value_table, spawns, clicks)
        return [e for e in order if ctx.ev_by_emoji[e] >= bar]

    now_allowed = allowed_at(ctx.opportunities_left, clicks_left)
    status["allowed"] = now_allowed
    status["threshold"] = round(ctx.threshold(), 1)

    # Fewer spawns left lowers the bar; spending clicks raises it. Report the
    # next move in each direction, and only when the set actually changes —
    # repeating the current row would tell the user nothing.
    for spawns in range(ctx.opportunities_left - 1, 0, -1):
        nxt = allowed_at(spawns, clicks_left)
        if nxt != now_allowed:
            status["looser_at"] = spawns
            status["looser_adds"] = [e for e in nxt if e not in now_allowed]
            break
    for clicks in range(clicks_left - 1, 0, -1):
        nxt = allowed_at(ctx.opportunities_left, clicks)
        if nxt != now_allowed:
            status["stricter_at"] = clicks
            status["stricter_drops"] = [e for e in now_allowed if e not in nxt]
            break
    return status


def build_perk9_threshold_context(
    *,
    opportunities_left: int,
    clicks_left: int,
    base_values: dict[str, float] | None = None,
    frequency: dict[str, float] | None = None,
    double_chance_pct: float = 0.0,
    additional_spheres: float = 0.0,
    shop9_bonus_pct: float = 0.0,
    spend_down: bool = False,
) -> Perk9ThresholdContext | None:
    """Build the per-batch context, or ``None`` to fall back to the static filter."""
    try:
        spawns = int(opportunities_left)
        clicks = int(clicks_left)
    except (TypeError, ValueError):
        return None
    if clicks <= 0 or spawns <= 0:
        return None
    ev_by_emoji = build_ev_table(
        base_values,
        double_chance_pct=double_chance_pct,
        additional_spheres=additional_spheres,
        shop9_bonus_pct=shop9_bonus_pct,
    )
    freq_by_emoji = normalize_frequency(frequency)
    capped = min(spawns, MAX_TABLE_OPPORTUNITIES)
    table = build_value_table(capped, clicks, ev_by_emoji, freq_by_emoji)
    return Perk9ThresholdContext(
        ev_by_emoji=ev_by_emoji,
        value_table=table,
        opportunities_left=capped,
        clicks_left=clicks,
        spend_down=bool(spend_down),
    )
