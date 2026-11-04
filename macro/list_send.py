"""Send a list plan to Mudae: clear, confirm, add back, flip toggles.

The plan comes from `macro.list_commands.plan_list_commands`; this module only
sends it and reads Mudae's answers. Mudae's behaviour, as captured 2026-11-04:

* **Clear** (``$eall`` / ``$aeall`` / ``$wrall``) answers "Type confirm to
  confirm the clean of your $…". The macro types ``confirm``; Mudae then ticks
  the **clear command**. Nothing is added until that tick arrives — adding on
  top of an uncleared list would duplicate or reorder it.
* **Adds** ask nothing and are ticked, except a ``$sw`` past the starwish
  limit, which offers to trade wishlist slots for more starwish slots::

      You reached your limit of 29 $starwish!
      Would you like to sacrifice 1,122 wishlist slots to upgrade this limit by +33? (y/n/yes/no)

  The caller's ``starwish_trade`` decides (the bridge accepts when the
  wishlist still has room for every wish in the preset afterwards). A refusal
  answers ``n`` and stops — a missing starwish would shift every later insert.
* A red ❌ on any command stops the send.
* ``$eall`` does **not** reset the toggles; the caller passes only the toggles
  that must flip, worked out from a fresh ``$dld``. A toggle is **not ticked**:
  Mudae replies "… series are now DISABLED / ENABLED for YOUR rolls!", so the
  macro waits for that reply (quick) instead, and checks it went the way the
  preset wants.

An add whose tick never comes is recorded as unconfirmed rather than stopping
the send — the caller re-reads the list afterwards and compares it with the
preset, which is the real check.

**Pacing.** Every message waits at least :data:`COMMAND_GAP_SEC` after the
previous one *and* after Mudae's answer to it, so Mudae never has two of the
macro's messages land back to back. Each command's answer time is logged.
"""

from __future__ import annotations

import asyncio
import math
import time
import types
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from mudae.parsers.list_prompts import (
    is_list_clear_prompt,
    is_starwish_limit_prompt,
    parse_list_prompt,
    toggle_result,
)

# Between two messages the macro sends, and after each answer
# (MUDAE_LOGIC.md › Spacing commands).
COMMAND_GAP_SEC = 1.0
REPLY_TIMEOUT_SEC = 12.0
# A toggle's reply comes straight back; past this, carry on regardless.
TOGGLE_REPLY_TIMEOUT_SEC = 5.0
# A tick that the gateway does not deliver is found by re-fetching the
# message; this is how often, so a missed event costs seconds, not the
# whole reply timeout.
TICK_RECHECK_SEC = 2.0

# Decides Mudae's offer to trade wishlist slots for starwish slots:
# (prompt fields) -> (accept, explanation).
StarwishTrade = Callable[[dict[str, Any]], tuple[bool, str]]


@dataclass
class SendOutcome:
    ok: bool = False
    reason: str = ""
    sent: list[str] = field(default_factory=list)
    unconfirmed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trades: list[str] = field(default_factory=list)


@types.coroutine
def _yield_once():  # type: ignore[no-untyped-def]
    """Let other tasks run one step — what ``asyncio.sleep(0)`` does, without
    depending on ``asyncio.sleep`` itself (tests replace it)."""
    yield


def _text_of(snapshot: Any) -> str:
    from mudae.message_text import snapshot_visible_text

    return snapshot_visible_text(snapshot)


class ListSender:
    def __init__(
        self,
        actions: Any,
        *,
        log: Callable[[str], None] | None = None,
        progress: Callable[[str], None] | None = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        gap: float = COMMAND_GAP_SEC,
        reply_timeout: float = REPLY_TIMEOUT_SEC,
        clock: Callable[[], float] = time.monotonic,
        starwish_trade: StarwishTrade | None = None,
    ) -> None:
        self._actions = actions
        self._log = log or (lambda _t: None)
        self._progress = progress or (lambda _t: None)
        self._sleep = sleep
        self._gap = gap
        self._timeout = reply_timeout
        self._clock = clock
        self._last_sent: float | None = None
        self._starwish_trade = starwish_trade

    # --- pacing ---------------------------------------------------------------

    async def _space(self) -> None:
        """Wait out the rest of the gap since the previous message."""
        if self._last_sent is None:
            return
        wait = self._last_sent + self._gap - self._clock()
        if wait > 0:
            await self._sleep(wait)

    async def _send_command(self, command: str) -> int | None:
        await self._space()
        self._actions.drain_queue()
        message_id = await self._actions.send_command(command)
        self._last_sent = self._clock()
        return message_id

    async def _send_text(self, text: str) -> None:
        await self._space()
        await self._actions.send_text(text)
        self._last_sent = self._clock()

    def _took(self) -> str:
        if self._last_sent is None:
            return ""
        return f"{self._clock() - self._last_sent:.1f}s"

    async def _await_tick(self, message_id: int, first: "asyncio.Future[Any] | None" = None) -> bool:
        """Wait for Mudae's tick on ``message_id``, re-checking every few seconds.

        Each short wait ends with a re-fetch of the message when no event came,
        so a tick the gateway never delivers is still found within
        :data:`TICK_RECHECK_SEC` instead of after the whole reply timeout.
        ``first`` is a wait already started (registered before a send).
        """
        # A fixed number of short checks adding up to the reply timeout —
        # counted rather than clocked, so a wait that returns at once cannot spin.
        checks = max(1, math.ceil(self._timeout / TICK_RECHECK_SEC))
        if first is not None:
            checks -= 1
            if await first:
                return True
        for _ in range(checks):
            if await self._actions.wait_for_mudae_tick(message_id, timeout=TICK_RECHECK_SEC):
                return True
        return False

    # --- racing Mudae's possible answers -----------------------------------

    async def _race(self, waits: dict[str, Awaitable[Any]]) -> tuple[str | None, Any]:
        """The first wait to come back with something, as ``(label, value)``.

        A wait that times out returns a falsy value; only when every wait has
        done so is the answer ``(None, None)``.
        """
        tasks = {asyncio.ensure_future(w): label for label, w in waits.items()}
        try:
            pending = set(tasks)
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task.exception() is None and task.result():
                        return tasks[task], task.result()
            return None, None
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _prompt_wait(self, matches: Callable[[str], bool]) -> Awaitable[Any]:
        return self._actions.wait_for(
            lambda s, _p: bool(getattr(s, "is_mudae", True)) and matches(_text_of(s)),
            timeout=self._timeout,
        )

    # --- steps ---------------------------------------------------------------

    async def clear(self, command: str) -> str:
        """``""`` once the list is cleared, or why it was not."""
        message_id = await self._send_command(command)
        if message_id is None:
            return f"{command} could not be sent"
        label, _ = await self._race(
            {
                "prompt": self._prompt_wait(is_list_clear_prompt),
                "tick": self._await_tick(message_id),
                "cross": self._actions.wait_for_mudae_cross(message_id, timeout=self._timeout),
            }
        )
        if label == "cross":
            return f"Mudae refused {command} (❌)"
        if label == "tick":
            # Ticked without asking — nothing to confirm (an empty list, say).
            return ""
        if label is None:
            return f"Mudae did not answer {command}"
        self._log(f"{command}: Mudae asked to confirm ({self._took()}) — sending confirm")
        await self._sleep(self._gap)
        # Listen for the tick *before* typing confirm: Mudae ticks the clear
        # command almost at once, often while `confirm` is still being sent.
        tick = asyncio.ensure_future(
            self._actions.wait_for_mudae_tick(message_id, timeout=TICK_RECHECK_SEC)
        )
        await _yield_once()  # let the wait register before anything is sent
        try:
            await self._send_text("confirm")
            ticked = await self._await_tick(message_id, first=tick)
        finally:
            if not tick.done():
                tick.cancel()
        if ticked:
            self._log(f"{command}: cleared — ticked {self._took()} after confirm")
            await self._sleep(self._gap)
            return ""
        return f"{command} was not ticked after confirm — the list may not be cleared"

    async def add(self, command: str) -> tuple[str, str]:
        """``(status, detail)`` — status is ``ok`` / ``unconfirmed`` / ``stop``."""
        message_id = await self._send_command(command)
        if message_id is None:
            return "stop", f"could not send {command[:40]}…"
        label, found = await self._race(
            {
                "tick": self._await_tick(message_id),
                "cross": self._actions.wait_for_mudae_cross(message_id, timeout=self._timeout),
                "sw_limit": self._prompt_wait(is_starwish_limit_prompt),
            }
        )
        short = command if len(command) <= 40 else command[:40] + "…"
        if label == "tick":
            self._log(f"{short}: ticked after {self._took()}")
            await self._sleep(self._gap)
            return "ok", ""
        if label == "cross":
            return "stop", f"Mudae refused {short} (❌)"
        if label == "sw_limit":
            snapshot = found[0] if isinstance(found, tuple) else found
            fields = parse_list_prompt(_text_of(snapshot)).fields
            accept, why = (
                self._starwish_trade(fields) if self._starwish_trade else (False, "")
            )
            await self._sleep(self._gap)
            if not accept:
                await self._send_text("n")
                return "stop", why or (
                    "Mudae offered to trade wishlist slots for more $starwish slots — answered n."
                )
            tick = asyncio.ensure_future(
                self._actions.wait_for_mudae_tick(message_id, timeout=TICK_RECHECK_SEC)
            )
            await _yield_once()
            try:
                await self._send_text("y")
                ticked = await self._await_tick(message_id, first=tick)
            finally:
                if not tick.done():
                    tick.cancel()
            self._log(why)
            if ticked:
                await self._sleep(self._gap)
                return "traded", why
            return "unconfirmed", "no tick after y"
        self._log(f"{short}: no tick within {self._timeout:.0f}s")
        return "unconfirmed", "no tick"

    async def toggle(self, command: str, *, turn_on: bool | None) -> tuple[str, str]:
        """Flip one toggle. Never waits for a tick — toggles are not ticked.

        ``(status, detail)``: ``ok``, ``unconfirmed`` (no reply in time),
        ``wrong`` (Mudae says it went the other way), or ``stop`` (❌).
        """
        message_id = await self._send_command(command)
        if message_id is None:
            return "stop", f"could not send {command}"
        timeout = min(self._timeout, TOGGLE_REPLY_TIMEOUT_SEC)
        label, found = await self._race(
            {
                "reply": self._actions.wait_for(
                    lambda s, _p: bool(getattr(s, "is_mudae", True))
                    and toggle_result(_text_of(s)) is not None,
                    timeout=timeout,
                ),
                "cross": self._actions.wait_for_mudae_cross(message_id, timeout=timeout),
            }
        )
        if label == "cross":
            return "stop", f"Mudae refused {command} (❌)"
        if label is None:
            return "unconfirmed", "no reply"
        self._log(f"{command}: answered after {self._took()}")
        await self._sleep(self._gap)
        now_on = toggle_result(_text_of(found[0]))
        if turn_on is not None and now_on != turn_on:
            return "wrong", f"{command} turned it {'on' if now_on else 'off'}, the preset wants it {'on' if turn_on else 'off'}"
        return "ok", ""

    async def run(
        self,
        plan: dict[str, Any],
        *,
        nitro: bool = False,
        toggles: list[Any] | None = None,
        skip_clear: bool = False,
    ) -> SendOutcome:
        """Clear (unless ``skip_clear``: the list is known to be empty), add, toggle.

        ``skip_clear`` exists for ``$sdl``: ``$serverenableall`` on an empty
        server disablelist gets **no answer at all**, so the caller checks first
        and skips the clear when Mudae says "List empty!".
        """
        outcome = SendOutcome()
        if plan.get("error"):
            outcome.reason = str(plan["error"])
            return outcome
        clear = None if skip_clear else (plan.get("clear") or {}).get("text")
        adds = [c["text"] for c in (plan.get("nitro") if nitro else plan.get("regular")) or []]
        steps = len(adds) + len(toggles or []) + (1 if clear else 0)
        done = 0

        if clear:
            self._progress(f"clearing ({clear})")
            why = await self.clear(clear)
            if why:
                outcome.reason = why
                return outcome
            outcome.sent.append(clear)
            done += 1

        for text in adds:
            done += 1
            self._progress(f"adding {done}/{steps}")
            status, detail = await self.add(text)
            if status == "stop":
                outcome.reason = detail
                return outcome
            outcome.sent.append(text)
            if status == "traded":
                outcome.trades.append(detail)
            if status == "unconfirmed":
                outcome.unconfirmed.append(text)
                self._log(f"no tick for {text[:50]}… — carrying on; the re-read will check it")

        # Each toggle: a command, or {"text", "on"} with the state it should
        # end in (so Mudae's reply can be checked against it).
        for item in toggles or []:
            text = item.get("text") if isinstance(item, dict) else str(item)
            turn_on = item.get("on") if isinstance(item, dict) else None
            done += 1
            self._progress(f"toggle {text} ({done}/{steps})")
            status, detail = await self.toggle(text, turn_on=turn_on)
            if status == "stop":
                outcome.reason = detail
                return outcome
            outcome.sent.append(text)
            if status == "unconfirmed":
                outcome.unconfirmed.append(text)
            if status == "wrong":
                outcome.warnings.append(detail)
                self._log(detail)

        outcome.ok = True
        return outcome


def starwish_trade_rule(wl_max: int | None, wishes_needed: int) -> StarwishTrade:
    """Answer Mudae's offer to trade wishlist slots for more starwish slots.

    Accept when the wishlist still has room for every wish in the preset
    afterwards — 1,324 slots minus 1,122 leaves 202, enough for 168 wishes, so
    yes; refuse when it would not, or when the wishlist size is unknown
    (``wl_max`` comes from the server's last `$wl` capture). An accepted trade
    lowers the remembered size, since Mudae may ask again.
    """
    size = {"wl_max": wl_max}

    def decide(fields: dict[str, Any]) -> tuple[bool, str]:
        cost = fields.get("sacrifice_slots")
        gain = fields.get("gain")
        limit = fields.get("starwish_limit")
        if cost is None:
            return False, "Mudae offered a starwish trade that could not be read — answered n."
        offer = f"trade {int(cost):,} wishlist slots for +{gain} starwish slots (limit {limit})"
        current = size["wl_max"]
        if current is None:
            return False, (
                f"Mudae offered to {offer}, but this server's wishlist size is unknown — "
                "answered n. Fetch $wl, then send again."
            )
        after = int(current) - int(cost)
        if after < wishes_needed:
            return False, (
                f"Mudae offered to {offer}, which would leave {after:,} wishlist slots — "
                f"fewer than the preset's {wishes_needed} wishes. Answered n."
            )
        size["wl_max"] = after
        return True, (
            f"Accepted Mudae's offer to {offer}: wishlist {int(current):,} → {after:,} slots, "
            f"room for the preset's {wishes_needed} wishes"
        )

    return decide


def compare_list(kind: str, wanted: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """What differs between the preset and the list Mudae now shows.

    Names compare without case (Mudae prints its own capitalisation). `$wl`
    compares order and wish type too; `$dl` / `$adl` compare membership, and
    `$dl` its toggles.
    """

    def names(rows: Any) -> list[str]:
        return [str(r.get("name") if isinstance(r, dict) else r).strip() for r in rows or []]

    problems: list[str] = []
    want_names, got_names = names(wanted.get("entries")), names(got.get("entries"))
    want_keys = [n.lower() for n in want_names]
    got_keys = [n.lower() for n in got_names]
    missing = [n for n in want_names if n.lower() not in got_keys]
    extra = [n for n in got_names if n.lower() not in want_keys]
    if missing:
        problems.append(f"missing {len(missing)}: " + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))
    if extra:
        problems.append(f"unexpected {len(extra)}: " + ", ".join(extra[:8]) + ("…" if len(extra) > 8 else ""))
    if kind == "wl" and not missing and not extra:
        if want_keys != got_keys:
            first = next(i for i, (a, b) in enumerate(zip(want_keys, got_keys)) if a != b)
            problems.append(f"order differs from #{first + 1} ({want_names[first]} expected, {got_names[first]} found)")
        got_rows = {str(r.get("name")).lower(): r for r in got.get("entries") or [] if isinstance(r, dict)}
        wrong = []
        for row in wanted.get("entries") or []:
            if not isinstance(row, dict):
                continue
            seen = got_rows.get(str(row.get("name")).lower()) or {}
            for flag in ("starwish", "locked", "kakera_wish"):
                if bool(row.get(flag)) != bool(seen.get(flag)):
                    wrong.append(f"{row.get('name')} ({flag})")
        if wrong:
            problems.append("wrong wish type: " + ", ".join(wrong[:8]) + ("…" if len(wrong) > 8 else ""))
    if kind == "dl":
        want_t = {t.get("command") for t in wanted.get("toggles") or []}
        got_t = {t.get("command") for t in got.get("toggles") or []}
        if want_t != got_t:
            problems.append(
                "toggles differ: wanted " + (", ".join(sorted(want_t)) or "none")
                + ", found " + (", ".join(sorted(got_t)) or "none")
            )
    return problems
