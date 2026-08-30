#!/usr/bin/env python3
"""A/B the $ot policies against each other.

Four named configurations, which is what `--policies` takes by default:

``cap``        the whole pre-Extra-Chance solver — the 4th blue always ends the
               board, and every certain ship is harvested on sight.
``rule-only``  the same policy under the real end condition. This is the *bug
               fix* on its own: it never walks away from a live board.
``defer``      Extra Chance play without the hunt — hold the certain ships back
               while nothing can end the board, but probe by plain EV.
``hunt``       what ships: `defer` plus the blue bonus, and that bonus applies
               only at 6-7 colours (`OT_BLUE_BONUS_COLORS`).

Because the bonus wins at 6-7 colours and measured *negative* at 8-9, an
aggregate mean averages a real effect against a real regression. Pass
``--by-colors``, or fix ``--colors``, for anything you intend to act on.

``--known``       replays the real boards baked into `macro/ot_replay.py`.
                  Ground truth, but still a small sample.

``--from-log P``  replays every fully-revealed $ot board in a minigame log
                  (docs/minigames_to_use.jsonl, data/minigame_log.json) and
                  reports what a human actually scored on them.

``--trials N``    generates boards for volume, under BOTH priors — `uniform`
                  (every legal placement equally likely, which is exactly what
                  the solver assumes) and `sequential` (ships dropped one at a
                  time, closer to how a bot would build a board). If the
                  ranking flips between them, it is a property of the prior and
                  not of the policy; say so rather than picking a winner.

Usage:
  .venv/bin/python scripts/ot_bakeoff.py --known --by-colors
  .venv/bin/python scripts/ot_bakeoff.py --from-log docs/minigames_to_use.jsonl
  .venv/bin/python scripts/ot_bakeoff.py --trials 120 --by-colors
  .venv/bin/python scripts/ot_bakeoff.py --sweep-blue-bonus 120 --colors 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro.ot_replay import (  # noqa: E402
    GENERATORS,
    KNOWN_BOARDS,
    paired_delta,
    replay_known_boards,
    replay_logged_boards,
    score_ot_trials,
    split_by_colors,
)
from macro.ot_solver import OT_BLUE_BONUS_SP, PROBE_POLICIES  # noqa: E402

# The configurations worth comparing, as (label, kwargs). `cap` is the whole
# pre-Extra-Chance solver — rules and policy — so it is the honest "before".
NAMED_RUNS: dict[str, dict] = {
    "cap": dict(policy="risk", extra_chance=False),
    "rule-only": dict(policy="risk"),
    "defer": dict(policy="hunt", blue_bonus=0.0),
    "hunt": dict(policy="hunt"),
}


def _print_row(result: dict, label: str | None = None) -> None:
    """One policy's line.

    ``ceiling`` is the SP of every ship cell — what a perfect game takes for
    free. It is a yardstick, not a cap: blue pays 10 SP as well, and under Extra
    Chance a board can be cleared outright, so a good game lands over 100%.

    ``paid`` adds `ot_replay.OT_CLICK_BONUS_SP` per click. Base SP is not what Mudae
    actually pays — there is a large per-click term — and since Extra Chance
    buys extra *clicks*, base SP understates it. See `macro.ot_replay`.
    """
    print(
        f"  {label or result['policy']:11} avg_sp={result['avg_sp']:8.1f}"
        f"  ceiling={result['avg_ceiling']:8.1f}"
        f"  share={result['share_of_ceiling'] * 100:6.1f}%"
        f"  clicks={result['avg_clicks']:5.2f}"
        f"  blues={result['avg_blues']:.2f}"
        f"  perfect={result['perfect']:3d}"
        f"  paid={result['avg_paid_sp']:8.1f}"
    )


def _print_by_colors(results: dict[str, dict], baseline: str) -> None:
    """Break every run down per colour count.

    The blue bonus wins at 6-7 colours and measured *negative* at 8-9, which is
    why it is only switched on for the first two. An aggregate mean averages
    those together and reports neither, so anything comparing policies has to
    come through here.
    """
    base = results.get(baseline)
    if base is None:
        return
    base_split = split_by_colors(base)
    print(f"\n  per colour count (delta vs {baseline}):")
    for colours in sorted(base_split):
        n = base_split[colours]["boards"]
        print(f"    N={colours} ({n} boards)  {baseline}={base_split[colours]['avg_sp']:8.1f}")
        for label, result in results.items():
            if label == baseline:
                continue
            rows = split_by_colors(result).get(colours)
            if not rows:
                continue
            delta = paired_delta(rows["per_board"], base_split[colours]["per_board"])
            mark = "*" if delta["significant"] else " "
            print(
                f"      {label:11} {rows['avg_sp']:8.1f}"
                f"  {delta['mean']:+8.1f} SP  t={delta['t']:+5.2f}{mark}"
            )


def _print_deltas(results: dict[str, dict], baseline: str) -> None:
    base = results.get(baseline)
    if base is None:
        return
    print(f"\n  paired vs {baseline}:")
    for policy, result in results.items():
        if policy == baseline:
            continue
        delta = paired_delta(result["per_board"], base["per_board"])
        verdict = "SIGNIFICANT" if delta["significant"] else "not significant"
        need = (
            f", ~{delta['boards_needed']} boards needed"
            if not delta["significant"] and delta["boards_needed"]
            else ""
        )
        print(
            f"    {policy:11} {delta['mean']:+8.1f} SP  t={delta['t']:+5.2f}"
            f"  changed {delta['changed']}/{delta['n']}  ({verdict}{need})"
        )


def _runs(policies: list[str]) -> dict[str, dict]:
    """Named configurations first, then any bare policy names asked for."""
    return {
        name: (NAMED_RUNS[name] if name in NAMED_RUNS else dict(policy=name))
        for name in policies
    }


def run_known(policies: list[str], baseline: str, by_colors: bool) -> None:
    print(f"REAL boards baked into macro/ot_replay.py: {len(KNOWN_BOARDS)}")
    print("Ground truth — Mudae generated these layouts — but still a tiny sample.")
    results = {
        label: replay_known_boards(**kwargs) for label, kwargs in _runs(policies).items()
    }
    scored = next(iter(results.values()))
    print(f"They really paid {scored['logged_avg_sp']:.1f} SP a board (hand / old solver).\n")
    for label, result in results.items():
        _print_row(result, label)
    names = scored["names"]
    print("\n  per board:")
    print(f"    {'':11}" + "".join(f"{name:>10}" for name in names))
    for label, result in results.items():
        print(
            f"    {label:11}" + "".join(f"{value:10.0f}" for value in result["per_board"])
        )
    _print_deltas(results, baseline)
    if by_colors:
        _print_by_colors(results, baseline)


def run_from_log(path: str, policies: list[str], baseline: str, by_colors: bool) -> None:
    results = {
        label: replay_logged_boards(path, **kwargs)
        for label, kwargs in _runs(policies).items()
    }
    first = next(iter(results.values()))
    if not first["boards"]:
        print(f"no fully-revealed $ot boards found in {path}")
        return
    print(f"REAL logged boards: {first['boards']}  (source: {path})")
    print(f"They really scored {first['logged_avg_sp']:.1f} SP a board.\n")
    for label, result in results.items():
        _print_row(result, label)
    _print_deltas(results, baseline)
    if by_colors:
        _print_by_colors(results, baseline)


def run_trials(
    trials: int,
    policies: list[str],
    baseline: str,
    generators: list[str],
    colors: int | None,
    by_colors: bool,
) -> None:
    label = "all colour counts" if colors is None else f"{colors}-colour boards"
    print(f"SYNTHETIC: {trials} {label} per generator.")
    print("A model of Mudae's generator, not Mudae. Confirm anything important")
    print("against real boards.\n")
    for generator in generators:
        print(f"generator = {generator}")
        results = {
            name: score_ot_trials(
                trials=trials,
                n_colors=colors,
                generator=generator,
                seed=7,
                **kwargs,
            )
            for name, kwargs in _runs(policies).items()
        }
        for name, result in results.items():
            _print_row(result, name)
        _print_deltas(results, baseline)
        if by_colors and colors is None:
            _print_by_colors(results, baseline)
        print()


def run_blue_bonus_sweep(trials: int, generators: list[str], colors: int | None) -> None:
    """Sweep the hunt's blue bonus, the knob that decides how hard to chase blues.

    Bonus 0 is `defer` — the Extra Chance phase without the hunt — and a large
    enough bonus is pure "click the likeliest blue". This is the sweep that says
    the bonus belongs at 6-7 colours and nowhere else, so run it with `--colors`
    fixed; averaged across colour counts it hides the sign change.
    """
    bonuses = [0.0, 60.0, 150.0, 300.0, 600.0, 1000.0, 3000.0]
    print(f"BLUE BONUS SWEEP: {trials} boards per bonus per generator.")
    print(f"bonus=0 is `defer`; the shipped value is {OT_BLUE_BONUS_SP:.0f}.\n")
    for generator in generators:
        print(f"generator = {generator}")
        base = score_ot_trials(
            trials=trials,
            n_colors=colors,
            generator=generator,
            policy="risk",
            extra_chance=False,
            seed=7,
        )
        print(f"  cap (old rules)      avg_sp={base['avg_sp']:8.1f}")
        for bonus in bonuses:
            result = score_ot_trials(
                trials=trials,
                n_colors=colors,
                generator=generator,
                policy="hunt",
                blue_bonus=bonus,
                seed=7,
            )
            delta = paired_delta(result["per_board"], base["per_board"])
            print(
                f"  bonus={bonus:7.1f}      avg_sp={result['avg_sp']:8.1f}"
                f"  clicks={result['avg_clicks']:5.2f}"
                f"  {delta['mean']:+8.1f} SP  t={delta['t']:+5.2f}"
                f"  {'SIGNIFICANT' if delta['significant'] else 'ns'}"
            )
        print()


def run_risk_sweep(trials: int, generators: list[str], colors: int | None) -> None:
    """Sweep the one knob that spans the whole probe family.

    `risk` scores ``ev(c) - lambda * P(blue at c)``, so lambda = 0 IS `greedy`
    and a large enough lambda IS `safe`. Sweeping it turns four hand-named
    rules into one curve, which is the only way to tell a real effect from a
    lucky name.
    """
    lambdas = [0.0, 30.0, 60.0, 90.0, 150.0, 250.0, 500.0, 1000.0]
    print(f"RISK SWEEP: {trials} boards per lambda per generator.")
    print("lambda=0 is `greedy`; large lambda is `safe`.\n")
    for generator in generators:
        print(f"generator = {generator}")
        base: list[float] | None = None
        for penalty in lambdas:
            result = score_ot_trials(
                trials=trials,
                n_colors=colors,
                generator=generator,
                policy="risk",
                risk_penalty=penalty,
                seed=7,
            )
            if base is None:
                base = result["per_board"]
                note = "(baseline = greedy)"
            else:
                delta = paired_delta(result["per_board"], base)
                note = (
                    f"{delta['mean']:+7.1f} SP  t={delta['t']:+5.2f}"
                    f"  {'SIGNIFICANT' if delta['significant'] else 'ns'}"
                )
            print(
                f"  lambda={penalty:7.1f}  avg_sp={result['avg_sp']:8.1f}"
                f"  share={result['share_of_ceiling'] * 100:5.1f}%   {note}"
            )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-log", dest="from_log", help="replay a minigame log")
    parser.add_argument("--known", action="store_true", help="replay the baked-in boards")
    parser.add_argument("--trials", type=int, default=0, help="synthetic boards per generator")
    parser.add_argument(
        "--policies",
        default="cap,rule-only,defer,hunt",
        help=(
            f"comma-separated, from {','.join(NAMED_RUNS)}"
            f" or a bare policy in {','.join(PROBE_POLICIES)}"
        ),
    )
    parser.add_argument("--baseline", default="cap")
    parser.add_argument("--generator", default="both", help="uniform, sequential or both")
    parser.add_argument("--colors", type=int, default=None, help="fix the colour count")
    parser.add_argument(
        "--by-colors",
        action="store_true",
        help="break results down per colour count (the bonus flips sign at 8)",
    )
    parser.add_argument(
        "--sweep-risk",
        type=int,
        default=0,
        metavar="TRIALS",
        help="sweep the risk penalty, which spans greedy through safe",
    )
    parser.add_argument(
        "--sweep-blue-bonus",
        type=int,
        default=0,
        metavar="TRIALS",
        help="sweep the hunt's blue bonus; pair it with --colors",
    )
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    known = set(NAMED_RUNS) | set(PROBE_POLICIES)
    unknown = [p for p in policies if p not in known]
    if unknown:
        parser.error(f"unknown policies: {', '.join(unknown)}")
    if args.baseline not in policies:
        parser.error(f"baseline {args.baseline!r} is not among --policies")
    generators = list(GENERATORS) if args.generator == "both" else [args.generator]

    if args.sweep_risk:
        run_risk_sweep(args.sweep_risk, generators, args.colors)
        return
    if args.sweep_blue_bonus:
        run_blue_bonus_sweep(args.sweep_blue_bonus, generators, args.colors)
        return
    if args.from_log:
        run_from_log(args.from_log, policies, args.baseline, args.by_colors)
        print()
    if args.known or not (args.from_log or args.trials):
        run_known(policies, args.baseline, args.by_colors)
        print()
    if args.trials:
        run_trials(
            args.trials,
            policies,
            args.baseline,
            generators,
            args.colors,
            args.by_colors,
        )


if __name__ == "__main__":
    main()
