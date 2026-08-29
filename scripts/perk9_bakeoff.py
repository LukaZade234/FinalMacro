#!/usr/bin/env python3
"""Score the perk-9 adaptive threshold against static allow-lists.

Usage: ``.venv/bin/python scripts/perk9_bakeoff.py``
Colblitz's own example account: ``--double 34 --flat 18 --shop9 100 --cap 20``.
``--tuned-for 120`` also scores one static filter picked for a 120-spawn day
against every other volume, which is what a user actually lives with.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro.perk9_threshold import (
    best_static_strategy,
    build_ev_table,
    build_value_table,
    click_threshold,
    normalize_frequency,
)


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", default="30,60,120,250")
    parser.add_argument("--cap", type=int, default=10)
    parser.add_argument("--block", type=int, default=10)
    parser.add_argument("--double", type=float, default=0.0, help="$bonus double %%")
    parser.add_argument("--flat", type=float, default=0.0, help="$bonus flat spheres")
    parser.add_argument("--shop9", type=float, default=0.0, help="OP9 value %%")
    parser.add_argument("--tuned-for", type=int, default=0)
    args = parser.parse_args()

    counts = [int(n) for n in args.counts.split(",") if n.strip()]
    ev = build_ev_table(
        double_chance_pct=args.double,
        additional_spheres=args.flat,
        shop9_bonus_pct=args.shop9,
    )
    freq = normalize_frequency(None)
    order = sorted(ev, key=lambda e: ev[e])

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
