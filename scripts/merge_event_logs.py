#!/usr/bin/env python3
"""Merge diverged copies of ``data/events.jsonl`` from two machines.

Both devices append to the same log, so after a sync outage neither copy is a
prefix of the other — each holds rows the other never saw. Syncthing resolves
that by picking a winner and sidelining the loser as a ``.sync-conflict`` file,
which leaves rows out of the active log. This takes the union instead.

Rows are deduped on their exact content, so the shared history collapses and
only genuinely new rows survive. Reports and exits without writing unless
``--out`` or ``--in-place`` is given.

    .venv/bin/python scripts/merge_event_logs.py data/events.jsonl /mnt/server/events.jsonl
    .venv/bin/python scripts/merge_event_logs.py A.jsonl B.jsonl --in-place
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def read_rows(path: Path) -> tuple[list[dict], int]:
    """Parsed rows plus the count of lines that could not be parsed."""
    rows: list[dict] = []
    bad = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(row, dict):
                rows.append(row)
            else:
                bad += 1
    return rows, bad


def row_key(row: dict) -> str:
    """Exact-content identity — two rows differing anywhere are both kept.

    Safer than keying on message_id: one message can produce several events
    (a roll's keys), and ``recorded_at`` carries microseconds, so genuine
    duplicates really are byte-identical.
    """
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def sort_key(row: dict) -> str:
    return str(row.get("recorded_at") or "")


def describe(label: str, rows: list[dict]) -> None:
    by_date: Counter[str] = Counter(str(r.get("date_key") or "?") for r in rows)
    stamps = [s for s in (sort_key(r) for r in rows) if s]
    span = f"{min(stamps)[:19]} → {max(stamps)[:19]}" if stamps else "no timestamps"
    print(f"  {label}: {len(rows):,} rows over {len(by_date)} days   {span}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="two or more events.jsonl copies")
    parser.add_argument("--out", type=Path, help="write the merged log here")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="overwrite the FIRST input, backing it up to <name>.bak-<stamp> first",
    )
    args = parser.parse_args()

    if args.out and args.in_place:
        parser.error("pass --out or --in-place, not both")
    if len(args.inputs) < 2:
        parser.error("need at least two files to merge")
    for path in args.inputs:
        if not path.is_file():
            parser.error(f"not a file: {path}")

    merged: dict[str, dict] = {}
    contributed: dict[Path, int] = {}
    per_file_dates: dict[Path, set[str]] = defaultdict(set)

    print("inputs")
    for path in args.inputs:
        rows, bad = read_rows(path)
        before = len(merged)
        for row in rows:
            merged.setdefault(row_key(row), row)
            per_file_dates[path].add(str(row.get("date_key") or "?"))
        contributed[path] = len(merged) - before
        note = f"   ({bad} unparseable lines skipped)" if bad else ""
        describe(str(path), rows)
        print(f"      new rows contributed: {contributed[path]:,}{note}")

    rows = sorted(merged.values(), key=sort_key)
    print("\nmerged")
    describe("union", rows)

    only: dict[Path, set[str]] = {}
    for path in args.inputs:
        others: set[str] = set()
        for other in args.inputs:
            if other != path:
                others |= per_file_dates[other]
        only[path] = per_file_dates[path] - others
    for path, dates in only.items():
        if dates:
            print(f"  days only in {path.name}: {', '.join(sorted(dates))}")

    by_date: Counter[str] = Counter(str(r.get("date_key") or "?") for r in rows)
    kinds = sorted({str(r.get("kind") or "?") for r in rows})
    print("\n  per-day totals (last 12 days)")
    header = "    " + "date".ljust(12) + "".join(k.rjust(10) for k in kinds) + "total".rjust(8)
    print(header)
    for date in sorted(by_date)[-12:]:
        day = [r for r in rows if str(r.get("date_key") or "?") == date]
        counts = Counter(str(r.get("kind") or "?") for r in day)
        line = "    " + date.ljust(12)
        line += "".join(str(counts.get(k, 0)).rjust(10) for k in kinds)
        print(line + str(len(day)).rjust(8))

    target = args.out
    if args.in_place:
        target = args.inputs[0]
    if target is None:
        print("\nDry run — nothing written. Re-run with --out PATH or --in-place.")
        return 0

    if args.in_place:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = target.with_suffix(target.suffix + f".bak-{stamp}")
        shutil.copy2(target, backup)
        print(f"\nbacked up {target} → {backup}")

    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(target)
    print(f"wrote {len(rows):,} rows → {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
