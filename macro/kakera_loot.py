"""Spend kakera on ``$kl`` loots in fixed batches until a batch is unaffordable.

Started from the Run page. ``$ku`` gives the opening balance; after that the
balance is kept locally — each batch costs ``loot_value × batch`` and refunds
whatever its ``:morekakera:`` line says — so the run stops exactly when the next
whole batch can no longer be paid for. A smaller last batch is never sent.

Mudae's rate limit is one ``$kl`` per 5 s from ``$kl 100`` and per 20 s from
``$kl 1000``, measured here from the previous send.

Two things interrupt the loop:

* **The confirm prompt.** Mudae sometimes asks "Do you want to spend X? (y/n)".
  It is answered ``y`` only when X is the batch cost; anything else means the
  preset's loot value is wrong, so it is answered ``n`` and the run stops.
* **A failed attempt** — a red cross on the command, or no result at all. The
  balance is re-read with ``$ku`` (a missed result may still have spent), and
  the batch is retried once after the cooldown. A second failure in a row
  stops the run.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from macro.config import KakeraLootRules
from mudae.macro_activity import enter_macro_activity, exit_macro_activity
from mudae.types import ParseResult

_KU_TIMEOUT_SEC = 12.0
_KU_ATTEMPTS = 3
_REPLY_TIMEOUT_SEC = 15.0
# Added to Mudae's cooldown so a send never lands a hair early.
_COOLDOWN_MARGIN_SEC = 1.0
# Below ``$kl 100`` there is no cooldown; still leave Mudae a beat.
_MIN_GAP_SEC = 2.0
# Between two *different* commands (``$ku`` then ``$kl``). Mudae struggles
# with commands sent too close together; see "Spacing commands" in
# MUDAE_LOGIC.md.
_COMMAND_GAP_SEC = 1.0
_MAX_CONSECUTIVE_FAILURES = 2


def kl_cooldown_sec(batch: int) -> float:
    """Mudae's own per-use limit for ``$kl <batch>``."""
    if batch >= 1000:
        return 20.0
    if batch >= 100:
        return 5.0
    return 0.0


def kl_gap_sec(batch: int) -> float:
    cooldown = kl_cooldown_sec(batch)
    return cooldown + _COOLDOWN_MARGIN_SEC if cooldown else _MIN_GAP_SEC


def _kl_outcome(parsed: ParseResult) -> str | None:
    return parsed.fields.get("kl_outcome")


class KakeraLootRunner:
    """One Run-page ``$kl`` session."""

    def __init__(
        self,
        actions: Any,
        monitor: Any,
        *,
        rules: KakeraLootRules,
        log: Callable[[str], None],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        reply_timeout_sec: float = _REPLY_TIMEOUT_SEC,
    ) -> None:
        self._actions = actions
        self._monitor = monitor
        self._rules = rules
        self._log = log
        self._sleep = sleep
        self._clock = clock
        self._reply_timeout = reply_timeout_sec
        self._last_sent: float | None = None
        self._stop = False

    def request_stop(self) -> None:
        """Finish after the batch in flight; never interrupts one mid-confirm."""
        self._stop = True

    async def run(self, *, prefix: str = "$") -> dict[str, Any]:
        enter_macro_activity(self._monitor)
        try:
            return await self._run(prefix=prefix)
        finally:
            exit_macro_activity(self._monitor)

    async def _run(self, *, prefix: str) -> dict[str, Any]:
        batch = self._rules.batch
        cost = self._rules.batch_cost()
        summary: dict[str, Any] = {
            "batches": 0,
            "spent": 0,
            "refunded": 0,
            "balance": None,
            "reason": "",
        }

        balance = await self._read_balance(prefix=prefix)
        if balance is None:
            summary["reason"] = "ku failed"
            return summary
        summary["balance"] = balance
        self._log(f"$ku: {balance:,} kakera · $kl {batch:,} costs {cost:,}")

        failures = 0
        while balance >= cost:
            if self._stop:
                summary["reason"] = "stopped"
                break
            await self._wait_gap(batch)
            if self._stop:
                summary["reason"] = "stopped"
                break
            outcome, gained = await self._spend_batch(prefix=prefix, batch=batch, cost=cost)
            if outcome == "done":
                failures = 0
                balance = balance - cost + gained
                summary["batches"] += 1
                summary["spent"] += cost
                summary["refunded"] += gained
                summary["balance"] = balance
                self._log(
                    f"$kl {batch:,} #{summary['batches']}: +{gained:,} kakera · "
                    f"balance {balance:,}"
                )
                continue
            if outcome == "wrong cost":
                summary["reason"] = "wrong cost"
                break
            failures += 1
            self._log(f"$kl {batch:,}: {outcome} ({failures}/{_MAX_CONSECUTIVE_FAILURES})")
            synced = await self._read_balance(prefix=prefix)
            if synced is None:
                summary["reason"] = "ku failed"
                break
            balance = synced
            summary["balance"] = balance
            self._log(f"$ku: {balance:,} kakera")
            if failures >= _MAX_CONSECUTIVE_FAILURES:
                summary["reason"] = "failed"
                break
        else:
            summary["reason"] = "insufficient"

        if summary["reason"] == "insufficient" and summary["batches"] == 0:
            self._log(f"$kl: not enough kakera for one batch ({balance:,} < {cost:,})")
        self._log(
            f"$kl done · {summary['batches']} × $kl {batch:,} · "
            f"spent {summary['spent']:,} · refunded {summary['refunded']:,} · "
            f"left {balance:,}"
        )
        return summary

    async def _wait_gap(self, batch: int) -> None:
        if self._last_sent is None:
            return
        remaining = self._last_sent + kl_gap_sec(batch) - self._clock()
        if remaining > 0:
            await self._sleep(remaining)

    async def _read_balance(self, *, prefix: str) -> int | None:
        for attempt in range(1, _KU_ATTEMPTS + 1):
            self._actions.drain_queue()
            await self._actions.send_command("ku", prefix=prefix)
            result = await self._actions.wait_for(
                lambda _s, p: p.fields.get("kakera_stock") is not None,
                timeout=_KU_TIMEOUT_SEC,
            )
            if result is not None:
                await self._sleep(_COMMAND_GAP_SEC)
                return int(result[1].fields["kakera_stock"])
            if attempt < _KU_ATTEMPTS:
                self._log(f"$ku: no stock line (attempt {attempt}/{_KU_ATTEMPTS}) — retrying")
        self._log("$ku: could not read the kakera stock — stopping")
        return None

    async def _spend_batch(self, *, prefix: str, batch: int, cost: int) -> tuple[str, int]:
        """``("done", refund)`` or ``(reason, 0)``."""
        self._actions.drain_queue()
        message_id = await self._actions.send_command(f"kl {batch}", prefix=prefix)
        self._last_sent = self._clock()
        reply = await self._await_reply(message_id)
        if reply == "denied":
            return "refused (❌)", 0
        if reply is None:
            return "no reply", 0

        if _kl_outcome(reply) == "prompt":
            asked = reply.fields.get("kl_spend")
            if asked is not None and int(asked) != cost:
                await self._actions.send_text("n")
                self._log(
                    f"$kl: Mudae asked to spend {int(asked):,}, expected {cost:,} — "
                    "answered n. Check the loot value in Presets."
                )
                return "wrong cost", 0
            await self._actions.send_text("y")
            self._log("$kl: Mudae asked to confirm — sent y")
            result = await self._actions.wait_for(
                lambda _s, p: _kl_outcome(p) == "result",
                timeout=self._reply_timeout,
            )
            if result is None:
                return "no reply after y", 0
            reply = result[1]

        return "done", int(reply.fields.get("kl_kakera_gained") or 0)

    async def _await_reply(self, message_id: int | None) -> ParseResult | str | None:
        """The prompt or result, ``"denied"`` on a red cross, ``None`` on timeout."""
        reply_task = asyncio.ensure_future(
            self._actions.wait_for(
                lambda _s, p: _kl_outcome(p) in {"prompt", "result"},
                timeout=self._reply_timeout,
            )
        )
        tasks: set[asyncio.Future[Any]] = {reply_task}
        cross_task: asyncio.Future[Any] | None = None
        if message_id is not None:
            cross_task = asyncio.ensure_future(
                self._actions.wait_for_mudae_cross(message_id, timeout=self._reply_timeout)
            )
            tasks.add(cross_task)
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if cross_task is not None and cross_task in done and cross_task.result():
                return "denied"
            found = await reply_task
            return found[1] if found else None
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
