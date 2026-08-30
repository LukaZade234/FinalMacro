#!/usr/bin/env python3
"""A/B the $ot probe policies against each other.

Ship cells are free and only blue costs a click, so the *only* decision worth
scoring is which cell to probe when nothing is a certain ship. This script
measures that choice three ways:

``--known``       replays the 7 real boards baked into `macro/ot_replay.py`.
                  Ground truth, but far too few to settle anything.

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
  .venv/bin/python scripts/ot_bakeoff.py --known
  .venv/bin/python scripts/ot_bakeoff.py --from-log docs/minigames_to_use.jsonl
  .venv/bin/python scripts/ot_bakeoff.py --trials 200 --policies greedy,mixed,safe
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
)
from macro.ot_solver import DEFAULT_PROBE_POLICY, PROBE_POLICIES  # noqa: E402


def _print_row(result: dict) -> None:
    """One policy's line.

    ``ceiling`` is the SP of every ship cell — what a perfect game takes for
    free. It is a yardstick, not a cap: blue pays 10 SP as well, so a game that
    had to spend its four blues can land just over 100%.
    """
    print(
        f"  {result['policy']:11} avg_sp={result['avg_sp']:8.1f}"
        f"  ceiling={result['avg_ceiling']:8.1f}"
        f"  share={result['share_of_ceiling'] * 100:5.1f}%"
        f"  blues={result['avg_blues']:.2f}"
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


def run_known(policies: list[str], baseline: str) -> None:
    print(f"REAL boards baked into macro/ot_replay.py: {len(KNOWN_BOARDS)}")
    print("Ground truth — Mudae generated these layouts — but 7 is a tiny sample.\n")
    results = {policy: replay_known_boards(policy=policy) for policy in policies}
    for result in results.values():
        _print_row(result)
    names = results[policies[0]]["names"]
    print("\n  per board:")
    print(f"    {'':11}" + "".join(f"{name:>10}" for name in names))
    for policy, result in results.items():
        print(
            f"    {policy:11}" + "".join(f"{value:10.0f}" for value in result["per_board"])
        )
    _print_deltas(results, baseline)


def run_from_log(path: str, policies: list[str], baseline: str) -> None:
    results = {policy: replay_logged_boards(path, policy=policy) for policy in policies}
    first = results[policies[0]]
    if not first["boards"]:
        print(f"no fully-revealed $ot boards found in {path}")
        return
    print(f"REAL logged boards: {first['boards']}  (source: {path})")
    print(f"Played by hand at {first['logged_avg_sp']:.1f} SP average.\n")
    for result in results.values():
        _print_row(result)
    _print_deltas(results, baseline)


def run_trials(
    trials: int, policies: list[str], baseline: str, generators: list[str], colors: int | None
) -> None:
    label = "all colour counts" if colors is None else f"{colors}-colour boards"
    print(f"SYNTHETIC: {trials} {label} per generator.")
    print("A model of Mudae's generator, not Mudae. Confirm anything important")
    print("against real boards.\n")
    for generator in generators:
        print(f"generator = {generator}")
        results = {
            policy: score_ot_trials(
                trials=trials,
                n_colors=colors,
                generator=generator,
                policy=policy,
                seed=7,
            )
            for policy in policies
        }
        for result in results.values():
            _print_row(result)
        _print_deltas(results, baseline)
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
        default=",".join(PROBE_POLICIES[:4]),
        help=f"comma-separated, from {','.join(PROBE_POLICIES)}",
    )
    parser.add_argument("--baseline", default=DEFAULT_PROBE_POLICY)
    parser.add_argument("--generator", default="both", help="uniform, sequential or both")
    parser.add_argument("--colors", type=int, default=None, help="fix the colour count")
    parser.add_argument(
        "--sweep-risk",
        type=int,
        default=0,
        metavar="TRIALS",
        help="sweep the risk penalty, which spans greedy through safe",
    )
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    unknown = [p for p in policies if p not in PROBE_POLICIES]
    if unknown:
        parser.error(f"unknown policies: {', '.join(unknown)}")
    generators = list(GENERATORS) if args.generator == "both" else [args.generator]

    if args.sweep_risk:
        run_risk_sweep(args.sweep_risk, generators, args.colors)
        return
    if args.from_log:
        run_from_log(args.from_log, policies, args.baseline)
        print()
    if args.known or not (args.from_log or args.trials):
        run_known(policies, args.baseline)
        print()
    if args.trials:
        run_trials(args.trials, policies, args.baseline, generators, args.colors)


if __name__ == "__main__":
    main()
