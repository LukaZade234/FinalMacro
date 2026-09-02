#!/usr/bin/env python3
"""Score the perk-9 adaptive threshold against static allow-lists.

Usage: ``.venv/bin/python scripts/perk9_bakeoff.py``
Colblitz's own example account: ``--double 34 --flat 18 --shop9 100 --cap 20``.
``--tuned-for 120`` also scores one static filter picked for a 120-spawn day
against every other volume, which is what a user actually lives with.

Three modes exist for the "clicks expired unspent" work:

``--hazard-sweep --cap 20``
    The acceptance gate. Simulates whole days at a range of *true* perk-9
    arrival rates and reports clicks left unspent at the reset for today's
    policy, a hardcoded rate, and one measured per account. The learned column
    must reach ~0 unspent at every rate; if it only works near this account's
    own 0.37 then the estimator is still leaning on the prior.

``--with-us-burst``
    Regression for the ``$us`` exclusion: a simulated day with a drain in the
    middle must learn the same rate as the identical day without it.

``--from-logs --cap 20``
    Replays the real spawn arrival streams out of ``data/session_logs``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro.perk9_daily import hazard_interval
from macro.perk9_threshold import (
    best_static_strategy,
    build_ev_table,
    build_value_table,
    click_threshold,
    forecast_spawns,
    normalize_frequency,
)

# The colours a live preset ships with. Bottom-heavy by design: blue and teal
# are five spawns in six and are both missing, which is why applying this before
# the EV bar threw away almost everything the bar would have cleared.
LIVE_TYPES_ALLOWED = ("spY", "spR", "spO", "spW", "spL", "spP", "spD", "spM", "spG")
# This account's own fitted rate over 205 logged roll-hours — a fixture and a
# worked example, never a shipped default. See ``--hazard-sweep``.
OBSERVED_HAZARD = 0.367
DEFAULT_POOL = 154
# Mudae stops spawning buttons once the budget is spent, so a day whose logged
# stream ends early was truncated by exhaustion rather than by the reset.
COMPLETE_DAY_AFTER_HOUR = 23


def static_value(opportunities, clicks_max, ev, freq, allowed):
    from math import comb

    p_click = sum(freq[e] for e in allowed)
    if p_click <= 0:
        return 0.0
    mean = sum(freq[e] * ev[e] for e in allowed) / p_click
    used = 0.0
    cdf = 0.0
    for j in range(clicks_max):
        cdf += comb(opportunities, j) * p_click**j * (1 - p_click) ** (opportunities - j)
        used += 1.0 - cdf
    return mean * used


def walk_day(spawns, cap, ev, freq, block):
    """Forward pass under the DP policy: SP and clicks spent per block."""
    table = build_value_table(spawns, cap, ev, freq)
    dist = [0.0] * (cap + 1)
    dist[cap] = 1.0
    cumulative = 0.0
    rows = []
    for step in range(1, spawns + 1):
        left = spawns - step + 1
        nxt = [0.0] * (cap + 1)
        for clicks, mass in enumerate(dist):
            if mass <= 0:
                continue
            bar = click_threshold(table, left, clicks)
            for emoji, weight in freq.items():
                if clicks > 0 and ev[emoji] >= bar:
                    cumulative += mass * weight * ev[emoji]
                    nxt[clicks - 1] += mass * weight
                else:
                    nxt[clicks] += mass * weight
        dist = nxt
        if step % block == 0 or step == spawns:
            spent = cap - sum(c * m for c, m in enumerate(dist))
            rows.append((step, cumulative, spent))
    return table, rows


# ---------------------------------------------------------------------------
# Whole-day simulation: does the budget actually get spent?


def _draw_colour(rng, freq):
    roll = rng.random()
    total = 0.0
    for emoji, weight in freq.items():
        total += weight
        if roll <= total:
            return emoji
    return next(iter(freq))


def simulate_day(
    *,
    rng,
    table,
    ev,
    freq,
    pool,
    hazard,
    rolls,
    cap,
    estimator,
    types_allowed=None,
    spend_down_rolls=0,
):
    """Roll a whole day and return ``(SP earned, clicks unspent, spawns offered)``.

    ``estimator`` is the policy's own guess at spawns still to come, given the
    real state it can see — that is the piece the change is about. Once the
    budget is spent Mudae stops spawning buttons, so the pool keeps emptying but
    nothing more is offered, which is why an over-strict bar cannot be made up
    for later in the day.
    """
    rolled = 0
    clicks = cap
    earned = 0.0
    offered = 0
    for step in range(rolls):
        rolls_left = rolls - step
        if rng.random() >= hazard * (pool - rolled) / pool:
            continue
        rolled += 1
        if clicks <= 0:
            continue
        offered += 1
        emoji = _draw_colour(rng, freq)
        if types_allowed is not None and emoji not in types_allowed:
            continue
        if rolls_left <= spend_down_rolls:
            bar = 0.0
        else:
            bar = click_threshold(table, estimator(rolled, rolls_left), clicks)
        if ev[emoji] >= bar:
            earned += ev[emoji]
            clicks -= 1
    return earned, clicks, offered


def _policies(pool, spend_down_rolls, learned_hazard_value):
    """The policies the sweep compares, as the live code would run them."""

    def ceiling(rolled, _rolls_left):
        return max(0, pool - rolled)

    def forecast(rate):
        def estimate(rolled, rolls_left):
            return forecast_spawns(
                pool=pool, rolled=rolled, rolls_left=rolls_left, hazard=rate
            )

        return estimate

    return [
        # What ships today: the static list runs first and the estimate is the
        # pool remainder, which plateaus and never lets the bar reach zero.
        ("today", ceiling, LIVE_TYPES_ALLOWED, 0),
        # The trap: one account's fitted rate handed to everybody.
        ("fixed", forecast(OBSERVED_HAZARD), None, spend_down_rolls),
        ("learned", forecast(learned_hazard_value), None, spend_down_rolls),
        # Reference, not a candidate: clicking every sphere leaves the fewest
        # clicks unspent that the day physically allows, at the worst SP. It is
        # the floor the "unspent" column is judged against, because a day that
        # only offers 10 spheres cannot spend 20 clicks however lax the bar is.
        # A spend-down covering every roll is just "the bar is always zero".
        ("click-all", ceiling, None, 1 << 30),
    ]


def run_hazard_sweep(args, ev, freq) -> None:
    rates = [float(x) for x in args.hazard_rates.split(",") if x.strip()]
    volumes = [int(x) for x in args.roll_volumes.split(",") if x.strip()]
    pool = args.pool
    table = build_value_table(pool, args.cap, ev, freq)

    print(
        f"\nhazard sweep — pool={pool}  cap={args.cap}  "
        f"days={args.days}  spend-down={args.spend_down_pct:.1f}% of the day"
    )
    print(
        "  'unspent' is clicks that expire at the reset; 'click-all' is the"
        " floor the day allows.\n"
    )
    header = f"    {'true h0':>8} {'rolls/day':>10} {'spawns':>7}"
    for name in ("today", "fixed", "learned", "click-all"):
        header += f" {name + ' SP':>11} {'unspent':>8}"
    print(header)

    worst_excess = 0.0
    worst_sp_loss = 0.0
    worst_blind_gap = 0.0
    for rate in rates:
        for rolls in volumes:
            spend_down_rolls = max(1, int(rolls * args.spend_down_pct / 100.0))
            cells = {}
            spawns_seen = 0.0
            for name, estimator, allowed, sd in _policies(
                pool, spend_down_rolls, rate
            ):
                rng = random.Random(args.seed)
                totals = [0.0, 0.0, 0.0]
                for _ in range(args.days):
                    sp, unspent, offered = simulate_day(
                        rng=rng,
                        table=table,
                        ev=ev,
                        freq=freq,
                        pool=pool,
                        hazard=rate,
                        rolls=rolls,
                        cap=args.cap,
                        estimator=estimator,
                        types_allowed=allowed,
                        spend_down_rolls=sd,
                    )
                    totals[0] += sp
                    totals[1] += unspent
                    totals[2] += offered
                cells[name] = [value / args.days for value in totals]
                spawns_seen = max(spawns_seen, cells[name][2])

            worst_excess = max(
                worst_excess, cells["learned"][1] - cells["click-all"][1]
            )
            worst_sp_loss = max(worst_sp_loss, cells["today"][0] - cells["learned"][0])
            best_blind = cells["click-all"][0]
            if best_blind > 0:
                worst_blind_gap = min(
                    worst_blind_gap, cells["learned"][0] / best_blind - 1.0
                )
            row = f"    {rate:>8.2f} {rolls:>10} {spawns_seen:>7.0f}"
            for name in ("today", "fixed", "learned", "click-all"):
                row += f" {cells[name][0]:>11.0f} {cells[name][1]:>8.1f}"
            print(row)

    # Unspent clicks are the symptom; SP is what the user actually loses. A
    # click held back because the bar was still above zero is only wasted if the
    # day ends without spending it *and* the pickiness bought nothing.
    print(
        f"\n  SP vs today's policy, worst cell:      {-worst_sp_loss:+.0f}"
        + ("  — PASS" if worst_sp_loss <= 0 else "  — FAIL")
    )
    print(
        f"  SP vs clicking every sphere, worst:    {worst_blind_gap:+.1%}"
        + ("  — PASS" if worst_blind_gap >= -args.max_sp_loss else "  — FAIL")
    )
    print(
        f"  'learned' unspent above the floor:     {worst_excess:.2f} clicks"
        + ("  — PASS" if worst_excess <= args.max_unspent else "  — FAIL")
    )
    print(
        "  A learned column that only reaches the floor near 0.37 would mean the"
        "\n  estimator is still leaning on this account's own fitted rate."
    )


def run_us_burst_check(args) -> None:
    """A ``$us`` drain must not move the learned rate."""
    pool, rate = args.pool, args.us_burst_hazard
    stretch = args.us_burst_stretch

    def rolled_after(rolls, start):
        return start + round((pool - start) * (1.0 - pow(2.718281828, -rate * rolls / pool)))

    def measure(stretches):
        depletion = 0.0
        rolls = 0
        for start, end, count in stretches:
            step, counted = hazard_interval(
                pool=pool, rolled_from=start, rolled_to=end, rolls=count
            )
            depletion += step
            rolls += counted
        return depletion / rolls

    quiet_mid = rolled_after(stretch, 0)
    quiet_end = rolled_after(stretch, quiet_mid)
    quiet = measure([(0, quiet_mid, stretch), (quiet_mid, quiet_end, stretch)])

    after_burst = quiet_mid + args.us_burst_size
    burst_end = rolled_after(stretch, after_burst)
    with_burst = measure([(0, quiet_mid, stretch), (after_burst, burst_end, stretch)])

    # What counting the drain's characters against ordinary rolls alone gives.
    naive_step, naive_rolls = hazard_interval(
        pool=pool, rolled_from=0, rolled_to=burst_end, rolls=stretch * 2
    )
    naive = naive_step / naive_rolls

    print(f"\n$us burst check — pool={pool}  true h0={rate}")
    print(f"  quiet day                     h0 = {quiet:.4f}")
    print(
        f"  same day + {args.us_burst_size}-character drain  h0 = {with_burst:.4f}"
        + ("  — PASS" if abs(with_burst - quiet) < 0.005 else "  — FAIL")
    )
    print(
        f"  if the drain's spawns were charged to ordinary rolls: h0 = {naive:.4f}"
        f"  ({naive / rate:.1f}× the truth)"
    )


# ---------------------------------------------------------------------------
# Replaying the real arrival streams

_SPAWN_RE = re.compile(
    r"sphere (?:click ×\d+|skip) .*?: "
    r"(?:no sphere button matched filter|perk9 budget|\d+ sphere)"
)


def load_log_days(log_dir: Path) -> dict[str, list[dt.datetime]]:
    """Spawn arrival timestamps per UTC day, from the sphere debug lines.

    ``no sphere buttons`` means the roll had none, so only the filter/budget
    skips and the clicks count as a perk-9 spawn actually appearing.
    """
    days: dict[str, list[dt.datetime]] = {}
    for path in sorted(log_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for line in payload.get("lines", []):
            if not isinstance(line, dict):
                continue
            text = str(line.get("text") or "")
            if not _SPAWN_RE.search(text):
                continue
            try:
                when = dt.datetime.fromisoformat(str(line.get("ts")))
            except ValueError:
                continue
            when = when.astimezone(dt.timezone.utc)
            days.setdefault(when.date().isoformat(), []).append(when)
    for stamps in days.values():
        stamps.sort()
    return days


def replay_logged_day(stamps, *, table, ev, freq, cap, pool, rolls_per_hour, rng, mode):
    """Replay one day's real arrivals and return ``(SP, clicks unspent)``."""
    earned = 0.0
    clicks = cap
    rolled = 0
    for when in stamps:
        rolled += 1
        if clicks <= 0:
            continue
        emoji = _draw_colour(rng, freq)
        hours_left = 24.0 - (when.hour + when.minute / 60.0)
        if mode == "today":
            if emoji not in LIVE_TYPES_ALLOWED:
                continue
            spawns_left = max(0, pool - rolled)
            bar = click_threshold(table, spawns_left, clicks)
        else:
            if hours_left * 60.0 <= 60.0:
                bar = 0.0
            else:
                spawns_left = forecast_spawns(
                    pool=pool,
                    rolled=rolled,
                    rolls_left=int(rolls_per_hour * hours_left),
                    hazard=OBSERVED_HAZARD,
                )
                bar = click_threshold(table, spawns_left, clicks)
        if ev[emoji] >= bar:
            earned += ev[emoji]
            clicks -= 1
    return earned, clicks


def run_from_logs(args, ev, freq) -> None:
    log_dir = Path(args.log_dir)
    if not log_dir.is_dir():
        print(f"\nno session logs at {log_dir}")
        return
    days = load_log_days(log_dir)
    table = build_value_table(args.pool, args.cap, ev, freq)

    complete = {
        day: stamps
        for day, stamps in days.items()
        if stamps and stamps[-1].hour >= COMPLETE_DAY_AFTER_HOUR
    }
    print(f"\nreplaying real arrivals from {log_dir} — pool={args.pool} cap={args.cap}")
    print(
        f"  {len(days)} logged days, {len(complete)} of them ran to the reset."
        " The rest stop early because the budget ran out and Mudae stopped"
        " spawning buttons, so their streams are truncated, not quiet."
    )
    print("  Colours are drawn from the frequency table: the character info line")
    print("  only carries a :spX: token for characters that belong to someone, so")
    print("  only about a fifth of logged spawns have a recorded colour. The")
    print("  arrival process is what changed here; the colour mix did not.\n")
    print(
        f"    {'day':>12} {'spawns':>7} {'last':>6}"
        f" {'today SP':>9} {'unspent':>8} {'new SP':>9} {'unspent':>8}"
    )
    totals = [0.0, 0.0]
    for day in sorted(complete if not args.all_days else days):
        stamps = days[day]
        row = [day, len(stamps), stamps[-1].strftime("%H:%M")]
        for index, mode in enumerate(("today", "new")):
            sp, unspent = replay_logged_day(
                stamps,
                table=table,
                ev=ev,
                freq=freq,
                cap=args.cap,
                pool=args.pool,
                rolls_per_hour=args.rolls_per_hour,
                rng=random.Random(args.seed),
                mode=mode,
            )
            row += [sp, unspent]
            totals[index] += unspent
        print(
            f"    {row[0]:>12} {row[1]:>7} {row[2]:>6}"
            f" {row[3]:>9.0f} {row[4]:>8} {row[5]:>9.0f} {row[6]:>8}"
        )
    print(f"\n  clicks expired unspent — today: {totals[0]:.0f}   new: {totals[1]:.0f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", default="30,60,120,250")
    parser.add_argument("--cap", type=int, default=10)
    parser.add_argument("--block", type=int, default=10)
    parser.add_argument("--double", type=float, default=0.0, help="$bonus double %%")
    parser.add_argument("--flat", type=float, default=0.0, help="$bonus flat spheres")
    parser.add_argument("--shop9", type=float, default=0.0, help="OP9 value %%")
    parser.add_argument("--tuned-for", type=int, default=0)
    parser.add_argument(
        "--hazard-sweep",
        action="store_true",
        help="the acceptance gate: whole days across a range of true arrival rates",
    )
    parser.add_argument("--hazard-rates", default="0.02,0.05,0.10,0.20,0.37")
    parser.add_argument("--roll-volumes", default="500,1500,3000")
    parser.add_argument("--pool", type=int, default=DEFAULT_POOL)
    parser.add_argument("--days", type=int, default=200, help="simulated days per cell")
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument(
        "--spend-down-pct",
        type=float,
        default=100.0 / 24.0,
        help="share of the day's rolls inside the last-hour spend-down",
    )
    parser.add_argument(
        "--max-unspent",
        type=float,
        default=2.0,
        help="clicks the learned policy may leave above the physical floor and pass",
    )
    parser.add_argument(
        "--max-sp-loss",
        type=float,
        default=0.03,
        help="how far below clicking every sphere the learned policy may fall",
    )
    parser.add_argument("--with-us-burst", action="store_true")
    parser.add_argument("--us-burst-hazard", type=float, default=0.05)
    parser.add_argument("--us-burst-stretch", type=int, default=500)
    parser.add_argument("--us-burst-size", type=int, default=57)
    parser.add_argument("--from-logs", action="store_true")
    parser.add_argument("--log-dir", default=str(ROOT / "data" / "session_logs"))
    parser.add_argument("--rolls-per-hour", type=int, default=62)
    parser.add_argument(
        "--all-days",
        action="store_true",
        help="include days truncated by the budget running out",
    )
    args = parser.parse_args()

    counts = [int(n) for n in args.counts.split(",") if n.strip()]
    ev = build_ev_table(
        double_chance_pct=args.double,
        additional_spheres=args.flat,
        shop9_bonus_pct=args.shop9,
    )
    freq = normalize_frequency(None)
    order = sorted(ev, key=lambda e: ev[e])

    if args.hazard_sweep or args.with_us_burst or args.from_logs:
        if args.hazard_sweep:
            run_hazard_sweep(args, ev, freq)
        if args.with_us_burst:
            run_us_burst_check(args)
        if args.from_logs:
            run_from_logs(args, ev, freq)
        return

    print(
        f"double={args.double}%  flat=+{args.flat}  shop9={args.shop9}%  cap={args.cap}"
    )
    print("EV: " + "  ".join(f"{e}={ev[e]:.0f}" for e in order))
    print(f"mean EV per spawn = {sum(freq[e] * ev[e] for e in freq):.1f}\n")

    print(f"{'N':>5} {'adaptive':>10} {'best static':>12} {'click-all':>10} {'gain':>8}")
    tables = {}
    for n in counts:
        table, rows = walk_day(n, args.cap, ev, freq, args.block)
        tables[n] = (table, rows)
        picks, static = best_static_strategy(n, args.cap, ev, freq)
        every = sum(freq[e] * ev[e] for e in freq) * min(n, args.cap)
        total = table[n][args.cap]
        gain = f"{total / static - 1:+.1%}" if static else "n/a"
        print(f"{n:>5} {total:>10.0f} {static:>12.0f} {every:>10.0f} {gain:>8}")

    for n in counts:
        table, rows = tables[n]
        print(f"\n  N={n}: SP per {args.block} spawns")
        previous = 0.0
        for step, cumulative, spent in rows:
            print(
                f"    after {step:>4}: cum={cumulative:>8.0f}"
                f"  (+{cumulative - previous:>6.0f})"
                f"  clicks used {spent:>5.2f}/{args.cap}"
            )
            previous = cumulative

    biggest = max(counts)
    table = tables[biggest][0]
    print(f"\n  threshold ladder (N={biggest}, full budget)")
    for left in sorted({biggest, biggest // 2, biggest // 4, args.cap * 2, args.cap}):
        if not 1 <= left <= biggest:
            continue
        bar = click_threshold(table, left, args.cap)
        passing = [e for e in order if ev[e] >= bar]
        print(f"    {left:>5} left: EV>={bar:>7.1f} -> {'+'.join(passing) or 'NOTHING'}")

    if args.tuned_for:
        picks, _ = best_static_strategy(args.tuned_for, args.cap, ev, freq)
        print(f"\n  one static filter tuned for N={args.tuned_for}: {'+'.join(picks)}")
        print(f"    {'N':>5} {'adaptive':>10} {'that filter':>12} {'gain':>9}")
        for n in counts:
            total = tables[n][0][n][args.cap]
            fixed = static_value(n, args.cap, ev, freq, picks)
            gain = f"{total / fixed - 1:+.1%}" if fixed else "n/a"
            print(f"    {n:>5} {total:>10.0f} {fixed:>12.0f} {gain:>9}")


if __name__ == "__main__":
    main()
