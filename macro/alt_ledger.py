"""What the alts did for the main, per alt per Mudae day, kept on disk.

``data/alts_ledger.json``::

    {
      "days": {"2026-11-05": {"<account id>": {"claims": 2, "kakera_earned": 3100,
                                               "characters_given": 2, "kakera_passed": 0,
                                               "spheres_passed": 0}}},
      "transfers": [{"at": iso, "day": …, "account_id": …, "alt": …, "transfer": …,
                     "what": …, "ok": …, "confirmed": …, "reason": …, "why": …}],
      "pending": {"<account id>": ["Flareon"]},
      "last_pass": {"<account id>": {"kakera": "2026-11-05", "spheres": "2026-11-05"}}
    }

* ``pending`` — characters an alt claimed for the main and has not given yet.
  Saved so a restart between the claim and the batch-end ``$give`` does not
  leave them on the alt unnoticed.
* ``last_pass`` — the Mudae day each start-of-day step was last done:
  ``minigames`` (the alt's own daily minigames) and ``kakera`` / ``spheres``
  (the "once a day" pass). An alt does each once a day and is not asked
  again until the next one: unlike the main, it gains no extra uses later.

Days are Mudae days (UTC). Only the last :data:`KEEP_DAYS` days and
:data:`KEEP_TRANSFERS` transfers are kept. ``data/`` is synced between
machines; the alts run on one machine at a time, so a single file is enough.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any, Callable

from macro.perk8_daily import mudae_daily_date

KEEP_DAYS = 35
KEEP_TRANSFERS = 300
COUNTERS = (
    "claims",
    "kakera_earned",
    "characters_given",
    "kakera_passed",
    "spheres_passed",
    "minigames_played",
    "spheres_earned",
    "fd_cycles",
)
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "alts_ledger.json"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class AltLedger:
    def __init__(
        self,
        path: Path | None = DEFAULT_PATH,
        *,
        clock: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self.days: dict[str, dict[str, dict[str, int]]] = {}
        self.transfers: list[dict[str, Any]] = []
        self.pending: dict[str, list[str]] = {}
        self.last_pass: dict[str, dict[str, str]] = {}
        self.load()

    # ---- disk ---------------------------------------------------------------

    def load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        days = data.get("days")
        self.days = {
            str(day): {
                str(acc): {k: int(v) for k, v in (row or {}).items() if k in COUNTERS}
                for acc, row in (accs or {}).items()
            }
            for day, accs in (days.items() if isinstance(days, dict) else [])
        }
        self.transfers = [t for t in data.get("transfers") or [] if isinstance(t, dict)]
        pending = data.get("pending")
        self.pending = {
            str(acc): [str(n) for n in names if str(n).strip()]
            for acc, names in (pending.items() if isinstance(pending, dict) else [])
            if isinstance(names, list)
        }
        last = data.get("last_pass")
        self.last_pass = {
            str(acc): {str(k): str(v) for k, v in (row or {}).items()}
            for acc, row in (last.items() if isinstance(last, dict) else [])
        }

    def save(self) -> None:
        if self._path is None:
            return
        with self._lock:
            keep = sorted(self.days)[-KEEP_DAYS:]
            self.days = {d: self.days[d] for d in keep}
            del self.transfers[:-KEEP_TRANSFERS]
            payload = {
                "days": self.days,
                "transfers": self.transfers,
                "pending": {a: n for a, n in self.pending.items() if n},
                "last_pass": self.last_pass,
            }
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                tmp.replace(self._path)
            except OSError:
                pass

    # ---- recording ----------------------------------------------------------

    def today(self) -> str:
        return mudae_daily_date(self._clock()).isoformat()

    def add(self, account_id: str, counter: str, amount: int = 1) -> None:
        if counter not in COUNTERS or not amount:
            return
        row = self.days.setdefault(self.today(), {}).setdefault(str(account_id), {})
        row[counter] = int(row.get(counter, 0)) + int(amount)
        self.save()

    def record_transfer(self, account_id: str, alt_name: str, result: Any, *, why: str = "") -> dict[str, Any]:
        """One exchange with Mudae; a confirmed one also counts in the day."""
        now = self._clock()
        entry = {
            "at": now.isoformat(timespec="seconds"),
            "time": now.strftime("%H:%M:%S"),
            "day": self.today(),
            "account_id": str(account_id),
            "alt": alt_name,
            "transfer": result.transfer,
            "what": result.character or (f"{result.amount:,}" if result.amount else ""),
            "ok": bool(result.ok),
            "confirmed": bool(result.confirmed),
            "reason": result.reason,
            "why": why,
        }
        self.transfers.append(entry)
        if result.ok:
            counter = {
                "character": "characters_given",
                "kakera": "kakera_passed",
                "spheres": "spheres_passed",
            }.get(str(result.transfer))
            amount = 1 if result.transfer == "character" else int(result.amount or 0)
            if counter:
                row = self.days.setdefault(self.today(), {}).setdefault(str(account_id), {})
                row[counter] = int(row.get(counter, 0)) + amount
        self.save()
        return entry

    def set_pending(self, account_id: str, names: list[str]) -> None:
        self.pending[str(account_id)] = list(names)
        self.save()

    def done_today(self, account_id: str, step: str) -> bool:
        return self.last_pass.get(str(account_id), {}).get(step) == self.today()

    def mark_done(self, account_id: str, step: str) -> None:
        self.last_pass.setdefault(str(account_id), {})[step] = self.today()
        self.save()

    # The pass modes read better with these names.
    passed_today = done_today
    mark_passed = mark_done

    # ---- reading ------------------------------------------------------------

    def day(self, day: str | None = None) -> dict[str, dict[str, int]]:
        return {acc: dict(row) for acc, row in self.days.get(day or self.today(), {}).items()}

    def last_days(self, n: int = 7) -> dict[str, dict[str, int]]:
        """Totals per account over the last ``n`` Mudae days, today included."""
        end = mudae_daily_date(self._clock())
        wanted = {(end - dt.timedelta(days=i)).isoformat() for i in range(n)}
        out: dict[str, dict[str, int]] = {}
        for day, accs in self.days.items():
            if day not in wanted:
                continue
            for acc, row in accs.items():
                total = out.setdefault(acc, {})
                for k, v in row.items():
                    total[k] = total.get(k, 0) + int(v)
        return out
