#!/usr/bin/env python3
"""Score the $oh policy against real logged boards, or synthetic ones.

``--from-log PATH``  replays the REAL boards recorded in a minigame log
                     (docs/minigames_to_use.jsonl, data/minigame_log.json).
                     Ground truth — prefer it. Reports paired per-board
                     deltas with a t-statistic, so an inconclusive result
                     reads as inconclusive.

``--reveals``        sweeps the number of initially revealed tiles (an
                     upgradeable perk) on synthetic boards.

Unveil targets are random, so every $oh replay is stochastic: each board is
averaged over several seeds. Synthetic boards are calibrated against the
logged ones but are still a model — confirm anything important --from-log.

Usage: ``.venv/bin/python scripts/oh_bakeoff.py --from-log docs/minigames_to_use.jsonl``
       ``.venv/bin/python scripts/oh_bakeoff.py --reveals 1,3,5,7,10``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro import oh_replay
from macro.oc_replay import paired_delta
from macro.oh_replay import (
    OC_GRANT_TRUE_SP,
    replay_logged_boards,
    score_oh_trials,
)


def _seeds(count: int) -> tuple[int, ...]:
    return tuple(range(count))


def run_from_log(path: str, seeds: int) -> None:
    legacy = replay_logged_boards(path, policy="legacy", seeds=_seeds(seeds))
    current = replay_logged_boards(path, policy="current", seeds=_seeds(seeds))
    if not legacy["boards"]:
        print(f"no recoverable $oh boards found in {path}")
        return

    print(f"REAL logged boards: {legacy['boards']}  seeds/board: {legacy['seeds']}")
    print(f"Source: {path}\n")
    print(f"  {'live logged play':28} avg_sp={legacy['logged_avg_sp']:7.2f}")
    print(f"  {'legacy (rank order)':28} avg_sp={legacy['avg_sp']:7.2f}")
    print(f"  {'current (SP order)':28} avg_sp={current['avg_sp']:7.2f}")
    print(
        f"  $oc grants/game={current['oc_grants_per_game']:.3f}"
        f"  free purples/game={current['free_clicks_per_game']:.2f}"
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
        print("  VERDICT: NOT significant — this sample cannot tell these apart.")
        if stat["boards_needed"]:
            print(
                f"           ~{stat['boards_needed']:,} boards would be needed"
                f" (have {stat['n']}). Do not ship on this evidence."
            )


def run_reveals(spec: str, trials: int) -> None:
    levels = [int(x) for x in spec.split(",") if x.strip()]
    print(f"synthetic boards per level: {trials}")
    print("The initially-revealed count is an upgradeable perk (logged: 1-10).\n")
    for oc_value, label in ((0.0, "$oc grant = 0 SP"), (OC_GRANT_TRUE_SP, "$oc grant = 314 SP")):
        oh_replay.OC_GRANT_VALUE = oc_value
        print(f"  --- {label} ---")
        print(f"  {'reveals':>8} {'avg SP':>9} {'$oc/game':>9}")
        for level in levels:
            result = score_oh_trials(trials=trials, initial_revealed=level)
            print(
                f"  {level:8} {result['avg_sp']:9.1f} {result['oc_grants_per_game']:9.3f}"
            )
        print()
    oh_replay.OC_GRANT_VALUE = 0.0
    print("  $oc spawns are invisible even once unveiled, so they cannot be")
    print("  targeted. Pricing them at 314 SP pushes a policy search toward")
    print("  'never claim a revealed sphere', which is why the shipped default")
    print("  is 0. Both columns are shown so no result rests on that choice.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-log",
        dest="from_log",
        type=str,
        default=None,
        help="Replay real boards from a minigame log (.json or .jsonl)",
    )
    parser.add_argument(
        "--reveals",
        type=str,
        default=None,
        help="Comma-separated initial-reveal counts to sweep on synthetic boards",
    )
    parser.add_argument("--trials", type=int, default=4000, help="Synthetic boards per level")
    parser.add_argument("--seeds", type=int, default=8, help="Seeds averaged per logged board")
    args = parser.parse_args()

    if args.from_log:
        run_from_log(args.from_log, args.seeds)
        return
    run_reveals(args.reveals or "1,3,5,7,10", args.trials)


if __name__ == "__main__":
    main()
