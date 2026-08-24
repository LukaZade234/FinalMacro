#!/usr/bin/env python3
"""Replay every $oq world with MIXED and the old entropy heuristic.

Usage: ``.venv/bin/python scripts/oq_bakeoff.py``
Optional: ``--limit 500`` for a quicker sample.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro.oq_replay import score_oq_policy
from macro.oq_solver import HUNT_POLICY_ENTROPY, HUNT_POLICY_MIXED
import macro.oq_worlds as oq_worlds
from macro.oq_worlds import ensure_built


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Replay only the first N worlds")
    parser.add_argument(
        "--stride",
        type=int,
        default=0,
        help="Take every Nth world (avoids clustering in combination order)",
    )
    args = parser.parse_args()
    ensure_built()
    indices = list(range(len(oq_worlds.ALL_WORLDS)))
    if args.stride > 1:
        indices = indices[:: args.stride]
    if args.limit > 0:
        indices = indices[: args.limit]
    print(f"worlds={len(indices)}")
    for policy in (HUNT_POLICY_MIXED, HUNT_POLICY_ENTROPY):
        result = score_oq_policy(policy, world_indices=indices)
        print(
            f"{result['policy']:8}  wins={result['wins']:5}/{result['games']}"
            f"  red={result['win_rate'] * 100:5.1f}%"
            f"  avg_base_sp={result['avg_base_sp']:.1f}"
        )


if __name__ == "__main__":
    main()
