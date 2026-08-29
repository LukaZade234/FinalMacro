#!/usr/bin/env python3
"""A/B the $oc lookahead policy against the old fixed-priority (legacy) one.

Two modes:

``--from-log PATH``  replays the REAL boards recorded in a minigame log
                     (docs/minigames_to_use.jsonl, data/minigame_log.json).
                     This is ground truth — prefer it. Reports paired
                     per-board deltas with a t-statistic, so an
                     inconclusive result reads as inconclusive.

default              replays synthetic boards for volume. The generator is
                     calibrated against those real boards but is still a
                     model, not Mudae's actual generator. Confirm anything
                     important with --from-log.

Usage: ``.venv/bin/python scripts/oc_bakeoff.py --from-log docs/minigames_to_use.jsonl``
       ``.venv/bin/python scripts/oc_bakeoff.py --trials 2000 --budget 5,7``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro.oc_replay import paired_delta, replay_logged_boards, score_oc_trials


def run_from_log(path: str) -> None:
    legacy = replay_logged_boards(path, policy="legacy")
    current = replay_logged_boards(path, policy="lookahead")
    if not legacy["boards"]:
        print(f"no fully-revealed $oc boards found in {path}")
        return

    print(f"REAL logged boards: {legacy['boards']}  (source: {path})")
    print("Ground truth — Mudae generated these layouts.\n")
    print(
        f"  {'legacy (pre-lookahead)':26} avg_sp={legacy['avg_sp']:7.2f}"
        f"  win={legacy['win_rate'] * 100:5.1f}%"
    )
    print(
        f"  {'current (lookahead)':26} avg_sp={current['avg_sp']:7.2f}"
        f"  win={current['win_rate'] * 100:5.1f}%"
    )

    stat = paired_delta(current["per_board"], legacy["per_board"])
    print()
    print(f"  paired delta : {stat['mean']:+.2f} SP per board")
    print(f"  95% CI       : [{stat['ci_low']:+.2f}, {stat['ci_high']:+.2f}]")
    print(f"  t            : {stat['t']:+.2f}")
    print(f"  boards changed: {stat['changed']} / {stat['n']}")
    print()
    if stat["significant"]:
        print("  VERDICT: significant at 95%.")
    else:
        need = stat["boards_needed"]
        print("  VERDICT: NOT significant — this sample cannot tell these apart.")
        if need:
            print(f"           ~{need:,} boards would be needed to confirm an effect this size")
            print(f"           (have {stat['n']}). Do not ship on this evidence.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-log",
        dest="from_log",
        type=str,
        default=None,
        help="Replay real boards from a minigame log (.json or .jsonl) instead of synthetic ones",
    )
    parser.add_argument("--trials", type=int, default=2000, help="Synthetic boards per policy")
    parser.add_argument(
        "--budget",
        type=str,
        default="5,7",
        help="Comma-separated click budgets to test",
    )
    parser.add_argument("--seed", type=int, default=0, help="RNG seed (shared across policies)")
    args = parser.parse_args()

    if args.from_log:
        run_from_log(args.from_log)
        return

    budgets = [int(b) for b in args.budget.split(",") if b.strip()]
    print(f"trials={args.trials} seed={args.seed}")
    print(
        "NOTE: boards are a self-consistent synthetic model for A/B comparison "
        "only, not validated against Mudae's real $oc generator.\n"
    )

    for budget in budgets:
        print(f"--- budget={budget} ---")
        results = {
            policy: score_oc_trials(
                trials=args.trials, budget=budget, seed=args.seed, policy=policy,
            )
            for policy in ("legacy", "lookahead")
        }
        legacy_sp = results["legacy"]["avg_sp"]
        lookahead_sp = results["lookahead"]["avg_sp"]
        uplift = ((lookahead_sp / legacy_sp) - 1.0) * 100 if legacy_sp else 0.0
        for policy, result in results.items():
            print(
                f"{policy:10}  avg_sp={result['avg_sp']:7.1f}"
                f"  avg_clicks={result['avg_clicks']:.2f}"
            )
        print(f"lookahead uplift: {uplift:+.1f}%\n")


if __name__ == "__main__":
    main()
