"""Play the Mudae ``$ot`` battleship minigame.

The grid message states the fleet up front (``Number of different colors: N``
⇒ ``N - 4`` length-2 ships), so :mod:`macro.ot_solver` knows exactly which
ships are hidden before the first click and reasons about *where* they are.

Four things make the loop different from ``$oc`` / ``$oq``:

* **Only blue costs a click.** Ship cells are free, so the budget is spent by
  mistakes, not by clicks. The loop counts blues, not clicks, and a good game
  ends with far more clicks than its 4-click budget.
* **The board can outlive the budget.** Under Extra Chance a blue taken with
  fewer than 5 ship hits is granted rather than fatal, so ``blues_spent`` runs
  past ``clicks_budget`` and the loop must not stop itself there — the version
  that did walked away from a live board on 2026-08-30 with 18 cells unclicked.
  The grid lock and :func:`macro.ot_solver.ot_game_over` are the two ways out;
  a full 25 clicks is the backstop. That makes games longer — 12 to 25 clicks
  where the old rule managed 12 to 20 — but they still fit the 2-minute board
  timer with room to spare: replaying all 16 known boards from a cold cache
  costs at most **0.88s of solver time for an entire game**, so the wall clock
  is the click delay (~2.1s a click as logged, so ~53s at 25 clicks).
* **A refused click is not the end of the board.** The cells still hidden can
  be hundreds of SP of certain ships, which are free and riskless, so one
  refusal must not throw them away — the first Extra Chance board did exactly
  that, stopping with six of them left. The loop refreshes the grid instead
  (which also recovers a click that *landed* and only lost its reply, the case
  that actually happened), skips a cell that refuses twice, and says what it
  abandoned if it does give up. Transport retries live in
  :meth:`mudae.discord_reader.ChannelMonitor.click_button`.
* **The clicked cell's colour comes from the grid, not the reward line.** A
  light ship pays out as a bundle of *other* colours ("breaks down into"), so
  reading the reward line as the cell's identity would tell the solver a
  rainbow cell was blue. :func:`macro.minigame_board.classify_oh_click`
  already untangles that for ``$oh``; the same call does it here.

``$ot`` is in ``PLAYABLE_MINIGAMES`` (:mod:`macro.minigame_daily`) and runs
through play-all / after-refill auto-play the same as ``$oh`` / ``$oc`` /
``$oq``, once the solver had been tried on real boards under the Extra Chance
rules (100.2% of the all-ships ceiling across 27 real boards). The Run-page
button still exists for an on-demand single play.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Callable
from typing import Any

from mudae.macro_activity import enter_macro_activity, exit_macro_activity
from macro.minigame_util import (
    empty_minigame_result,
    log_minigame_exhausted,
    minigame_command,
    snapshot_is_minigame_exhausted,
    wait_for_grid_or_exhausted,
)
from macro.minigame_board import (
    board_emojis,
    build_session,
    cell_index,
    classify_oh_click,
    make_click,
)
from macro.ot_solver import (
    BLUE,
    DEFAULT_PROBE_POLICY,
    EXTRA_CHANCE,
    GRID_CELLS,
    OtFleet,
    choose_ot_click,
    emoji_to_ot_color,
    format_solver_stats,
    observations_from_buttons,
    ot_game_over,
    parse_ot_fleet,
    solver_stats,
)
from macro.sphere_game import (
    FIRST_CLICK_DELAY_SEC,
    _MIN_GRID_BUTTONS,
    _disable_button,
    grid_signature,
    is_oh_reward_message,
    new_reward_outcome_types,
    parse_clicks_allowed,
    reward_has_entries,
    total_reward_from_content,
    wait_for_final_grid,
    wait_for_minigame_click_ack,
)

# "Spheres to find: teal = 4, green = 3, yellow = 3, rarer spheres = 2."
_OT_GRID_RE = re.compile(r"spheres\s+to\s+find", re.IGNORECASE)
# ":spB: (Extra chance) +56" — Mudae's own name for a blue that did not end the
# board. `sphere_game._PAYOUT_RE` already tolerates the tag, so the amount is
# still counted; this only reads it back for the log.
_EXTRA_CHANCE_RE = re.compile(r"\(\s*extra\s+chance\s*\)", re.IGNORECASE)

# Consecutive failed clicks before the board is written off. The monitor
# already retries the transport three times, so this is about a grid that has
# moved under us, not about flaky networking.
_MAX_CLICK_FAILURES = 3

# Clicks in one board whose acknowledgement had to be fetched over HTTP before
# the gateway is declared dead. One is ordinary — Discord drops the odd edit.
# Two, with nothing at all arriving in between, is a zombie socket:
# `is_connected` says yes, HTTP works, and no event ever comes. Each one costs
# a full `edit_timeout`, which turned a 22-click board into five minutes.
_MAX_ACK_RECOVERIES = 2
# ...but only when the gateway really has gone quiet. A busy channel that is
# merely slow keeps delivering *something*, so a recent event means the edit
# was late rather than the socket dead, and a reconnect would not help.
_GATEWAY_SILENCE_SEC = 25.0


def _reward_says_extra_chance(before: str, after: str) -> bool:
    """True when the lines Mudae just appended carry an ``(Extra chance)`` tag.

    Mudae keeps **one** reward message per game and appends a line per click, so
    the new content is whatever sits past the lines already seen — the same
    cumulative diff `new_reward_outcome_types` does.
    """
    previous = len((before or "").splitlines())
    fresh = (after or "").splitlines()[previous:]
    return any(_EXTRA_CHANCE_RE.search(line) for line in fresh)


def _emoji(button: dict[str, Any]) -> str:
    return (button.get("emoji") or "").strip()


def _sphere_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in buttons if (b.get("kind") == "sphere") or _emoji(b).startswith("sp")]


def _is_clickable(button: dict[str, Any]) -> bool:
    return bool(button.get("custom_id")) and not button.get("disabled")


def is_ot_grid_message(snapshot: Any) -> bool:
    """True when ``snapshot`` is the ``$ot`` grid (initial post or an edit)."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    content = getattr(snapshot, "content", "") or ""
    spheres = _sphere_buttons(getattr(snapshot, "buttons", []) or [])
    if len(spheres) < _MIN_GRID_BUTTONS:
        return False
    return bool(_OT_GRID_RE.search(content))


def is_ot_game_over(buttons: list[dict[str, Any]]) -> bool:
    spheres = _sphere_buttons(buttons)
    if len(spheres) < _MIN_GRID_BUTTONS:
        return True
    return not any(_is_clickable(button) for button in spheres)


class OtSphereGame:
    """Drive a single ``$ot`` session end to end."""

    def __init__(
        self,
        actions: Any,
        monitor: Any,
        *,
        log: Callable[[str], None],
        rng: random.Random | None = None,
        grid_timeout: float = 12.0,
        edit_timeout: float = 12.0,
        click_delay: float = 1.2,
        policy: str = DEFAULT_PROBE_POLICY,
        extra_chance: bool = EXTRA_CHANCE,
    ) -> None:
        self._actions = actions
        self._monitor = monitor
        self._log = log
        self._rng = rng or random.Random()
        self._grid_timeout = grid_timeout
        self._edit_timeout = edit_timeout
        self._click_delay = click_delay
        self._policy = policy
        self._extra_chance = extra_chance
        self._reward_content = ""
        self._observations: dict[int, str] = {}
        self._ack_recoveries = 0
        self._reconnected = False

    async def play(self, *, prefix: str = "$", uses: int = 1) -> dict[str, Any]:
        enter_macro_activity(self._monitor)
        blues_spent = 0
        ship_hits = 0
        extra_chances = 0
        click_failures = 0
        last_refused = ""
        try:
            self._actions.drain_queue()
            cmd = minigame_command("ot", uses)
            label = f"${cmd}" if uses > 1 else "$ot"
            self._log(f"{label}: starting battleship game")
            await self._actions.send_command(cmd, prefix=prefix)

            grid, exhausted = await self._wait_for_grid()
            if exhausted is not None:
                log_minigame_exhausted(self._log, exhausted)
                return empty_minigame_result("exhausted", exhausted=exhausted)
            if grid is None:
                self._log(f"{label}: grid did not appear (timeout)")
                return empty_minigame_result("no grid")

            clicks_budget = parse_clicks_allowed(grid.content)
            fleet = parse_ot_fleet(grid.content, clicks_budget=clicks_budget)
            if fleet is None:
                # The colour count is what tells us which ships are hidden;
                # without it there is nothing to solve. Log the message so a
                # wording change is diagnosable instead of silent.
                head = " ".join((grid.content or "").split())[:160]
                self._log(f"{label}: could not read the fleet from the grid — {head}")
                return empty_minigame_result("no fleet")

            grid_id = grid.message_id
            buttons = list(grid.buttons)
            session_clicks: list[dict[str, Any]] = []
            self._observations = observations_from_buttons(buttons)
            self._log(
                f"{label}: grid ready · {fleet.n_colors} colours "
                f"({fleet.two_ships} rare ships, {fleet.blue_cells} blue cells) · "
                f"{clicks_budget} blue clicks · "
                f"{self._stats(fleet, blues_spent, ship_hits)}"
            )
            await asyncio.sleep(FIRST_CLICK_DELAY_SEC)

            finished = False
            while not is_ot_game_over(buttons) and not finished:
                # Extra Chance means blues can run past the budget, so the board
                # is not over until Mudae says so — either by locking the grid or
                # by `ot_game_over` firing on a blue we just clicked. The cell
                # count is a backstop: a wrong model must not spin.
                if len(session_clicks) >= GRID_CELLS:
                    self._log("$ot: every cell clicked — stopping")
                    break

                choice = choose_ot_click(
                    buttons,
                    self._observations,
                    fleet=fleet,
                    blues_spent=blues_spent,
                    ship_hits=ship_hits,
                    policy=self._policy,
                    extra_chance=self._extra_chance,
                    rng=self._rng,
                )
                if choice is None:
                    self._log("$ot: no hidden cell to click — stopping")
                    break

                custom_id = choice["custom_id"]
                clicked_index = cell_index(buttons, custom_id)
                before_sig = grid_signature(buttons)
                before_reward = self._reward_content

                ok = await self._actions.click_button(grid_id, custom_id)
                if not ok:
                    # The monitor has already retried the transport, so this is
                    # a refusal rather than a blip. The cells still on the board
                    # can be worth hundreds of free SP — a single refusal used
                    # to throw all of them away — so recover instead of quitting.
                    click_failures += 1
                    why = self._transport_error()
                    if click_failures >= _MAX_CLICK_FAILURES:
                        self._log(
                            f"$ot: click refused {click_failures}x{why} — stopping"
                            f"{self._abandoned(fleet, buttons)}"
                        )
                        break
                    if custom_id == last_refused:
                        # Twice on the same button: asking a third time will not
                        # help. Take it off our copy of the grid so the solver
                        # picks somewhere else — one skipped cell beats a
                        # abandoned board.
                        buttons = _disable_button(buttons, custom_id)
                        self._log(
                            f"$ot: cell {self._cell_label(clicked_index)} keeps "
                            "refusing — skipping it"
                        )
                    else:
                        self._log(
                            f"$ot: click refused{why} — refreshing the grid "
                            f"({click_failures}/{_MAX_CLICK_FAILURES})"
                        )
                        refreshed = await self._actions.fetch_message_snapshot(grid_id)
                        if refreshed is not None:
                            buttons = list(refreshed.buttons)
                            self._observations.update(
                                observations_from_buttons(buttons)
                            )
                    last_refused = custom_id
                    await asyncio.sleep(self._click_delay)
                    continue
                click_failures = 0
                last_refused = ""

                updated, reward_content = await self._wait_for_click_resolution(
                    grid_id,
                    before_sig,
                    before_reward,
                    custom_id=custom_id,
                )
                if updated is None and reward_content == before_reward:
                    self._log("$ot: click ack timeout — stopping")
                    break
                if updated is None:
                    self._log("$ot: continuing from reward line (grid edit pending)")

                self._reward_content = reward_content
                if updated is not None:
                    buttons = list(updated.buttons)
                else:
                    buttons = _disable_button(buttons, custom_id)

                grid_emoji = ""
                if clicked_index is not None:
                    board_now = board_emojis(buttons)
                    if 0 <= clicked_index < len(board_now):
                        grid_emoji = board_now[clicked_index]
                # The grid is the authority on what the cell *is*; the reward
                # line only says what it paid. Light pays in other colours.
                classified = classify_oh_click(
                    clicked_emoji=grid_emoji,
                    reward_types=new_reward_outcome_types(before_reward, reward_content),
                    grid_emoji=grid_emoji,
                )
                revealed = str(classified["emoji"])
                colour = emoji_to_ot_color(revealed)
                if clicked_index is not None and colour:
                    self._observations[clicked_index] = colour
                self._observations.update(observations_from_buttons(buttons))

                session_clicks.append(
                    make_click(
                        clicked_index,
                        revealed,
                        paid=colour == BLUE,
                        resolved=list(classified.get("resolved") or []),
                    )
                )

                if colour == BLUE:
                    blues_spent += 1
                    # Mudae tags the survivable ones itself. Log what it said
                    # rather than what we predicted: that line is the only way a
                    # future log can contradict the Extra Chance model.
                    granted = _reward_says_extra_chance(before_reward, reward_content)
                    if granted:
                        extra_chances += 1
                    predicted = ot_game_over(
                        blues_spent,
                        ship_hits,
                        budget=clicks_budget,
                        extra_chance=self._extra_chance,
                    )
                    # Mudae's tag outranks the model: if it granted the click,
                    # the board is live no matter what we predicted. Say so —
                    # a disagreement here is the rule changing under us, and
                    # `is_ot_game_over` still catches the other direction.
                    if predicted and granted:
                        self._log(
                            f"$ot: Extra chance granted at {ship_hits} ship hits — "
                            "expected the board to end; check EXTRA_CHANCE_SHIP_HITS"
                        )
                    finished = predicted and not granted
                    note = " (Extra chance)" if granted else ""
                    self._log(
                        f"$ot: blue {blues_spent}/{clicks_budget}{note} at cell "
                        f"{self._cell_label(clicked_index)}"
                    )
                else:
                    ship_hits += 1
                    self._log(
                        f"$ot: free hit {ship_hits} at cell "
                        f"{self._cell_label(clicked_index)} → {revealed or '?'}"
                    )
                if not finished:
                    self._log("$ot: " + self._stats(fleet, blues_spent, ship_hits))
                await asyncio.sleep(self._click_delay)

            if is_ot_game_over(buttons) or finished:
                self._log("$ot: grid locked — minigame finished")

            buttons = await wait_for_final_grid(
                self._actions,
                grid_id=grid_id,
                buttons=buttons,
                is_grid_message=is_ot_grid_message,
                get_reward_content=lambda: self._reward_content,
                set_reward_content=lambda content: setattr(self, "_reward_content", content),
            )
            session = build_session(
                "ot",
                session_clicks,
                board_emojis(buttons),
                clicks_paid=blues_spent,
                clicks_budget=clicks_budget,
                reason="done",
            )

            reward = total_reward_from_content(self._reward_content)
            reward_note = f" · +{reward} spheres" if reward else ""
            extra_note = f" (+{extra_chances} extra)" if extra_chances else ""
            free_clicks = len(session_clicks) - blues_spent
            self._log(
                f"{label}: finished · {free_clicks} free hits, "
                f"{blues_spent}/{clicks_budget} blue{extra_note}{reward_note}"
            )
            return {
                "clicks": len(session_clicks),
                "clicks_paid": blues_spent,
                "reward": reward,
                "reason": "done",
                "session": session,
            }
        finally:
            exit_macro_activity(self._monitor)

    def _transport_error(self) -> str:
        """Why the transport gave up, for the session log.

        The monitor reports failures through ``on_status``, which only reaches
        the GUI status bar — nothing keeps it, so a refused click was still
        unexplained in the log that gets read afterwards.
        """
        detail = str(getattr(self._monitor, "last_transport_error", "") or "").strip()
        return f" ({detail})" if detail else ""

    def _abandoned(self, fleet: OtFleet, buttons: list[dict[str, Any]]) -> str:
        """What giving up here costs, for the log.

        Certain ships are free and riskless, so walking away from them is a
        pure loss and the log should say how big it was rather than leaving
        "click failed — stopping" to look harmless.
        """
        hidden = [
            index
            for index in range(GRID_CELLS)
            if index not in self._observations
        ]
        if not hidden:
            return ""
        stats = solver_stats(
            fleet, self._observations, hidden=hidden, policy=self._policy
        )
        certain = int(stats["certain_ships"])
        if not certain:
            return f" · {len(hidden)} cells left"
        return (
            f" · {len(hidden)} cells left, {certain} of them certain ships"
            f" worth {stats['certain_sp']:.0f} sp"
        )

    def _stats(self, fleet: OtFleet, blues_spent: int, ship_hits: int) -> str:
        return format_solver_stats(
            fleet,
            self._observations,
            policy=self._policy,
            blues_spent=blues_spent,
            ship_hits=ship_hits,
            extra_chance=self._extra_chance,
        )

    @staticmethod
    def _cell_label(index: int | None) -> str:
        if index is None:
            return "?"
        row, col = divmod(index, 5)
        return f"({row + 1},{col + 1})"

    async def _wait_for_grid(self) -> tuple[Any | None, dict[str, Any] | None]:
        return await wait_for_grid_or_exhausted(
            self._actions,
            self._make_predicate(
                lambda snapshot: is_ot_grid_message(snapshot)
                or snapshot_is_minigame_exhausted(snapshot)
            ),
            timeout=self._grid_timeout,
        )

    async def _wait_for_click_resolution(
        self,
        grid_id: int,
        before_sig: tuple,
        before_reward: str,
        *,
        custom_id: str,
    ) -> tuple[Any | None, str]:
        async def _retry_click() -> None:
            ok = await self._actions.click_button(grid_id, custom_id)
            if ok:
                self._log("$ot: resending click")
            else:
                self._log("$ot: retry click send failed")

        return await wait_for_minigame_click_ack(
            self._actions,
            monitor=self._monitor,
            grid_id=grid_id,
            before_sig=before_sig,
            before_reward=before_reward,
            is_grid_message=is_ot_grid_message,
            get_reward_content=lambda: self._reward_content,
            set_reward_content=lambda content: setattr(self, "_reward_content", content),
            edit_timeout=self._edit_timeout,
            log=self._log,
            on_retry_click=_retry_click,
            on_ack_recovered=self._on_ack_recovered,
        )

    async def _on_ack_recovered(self) -> None:
        """Reconnect when the gateway has stopped delivering but claims health.

        Every click acknowledgement arriving by HTTP fetch means the gateway
        gave us nothing, and each one costs a full ``edit_timeout``. When that
        repeats *and* no event of any kind has arrived for a while, the socket
        is a zombie: reconnecting is the only thing that restores normal speed.
        Reconnect at most once a board — if it does not help, the slow path
        still finishes the game.
        """
        self._ack_recoveries += 1
        if self._ack_recoveries < _MAX_ACK_RECOVERIES or self._reconnected:
            return
        silence = 0.0
        seconds_since = getattr(self._monitor, "seconds_since_last_event", None)
        if callable(seconds_since):
            silence = float(seconds_since() or 0.0)
        if silence < _GATEWAY_SILENCE_SEC:
            return
        self._reconnected = True
        self._log(
            f"$ot: no gateway events for {silence:.0f}s and "
            f"{self._ack_recoveries} clicks recovered by fetch — reconnecting"
        )
        reconnect = getattr(self._monitor, "ensure_connected", None) or getattr(
            self._monitor, "force_reconnect", None
        )
        if not callable(reconnect):
            return
        try:
            ok = await reconnect()
        except Exception as exc:  # noqa: BLE001 - surface, never abort the board
            self._log(f"$ot: reconnect failed ({exc}) — continuing on the slow path")
            return
        self._log(
            "$ot: reconnected" if ok else "$ot: reconnect timed out — continuing"
        )
        self._ack_recoveries = 0

    def _make_predicate(
        self, matches: Callable[[Any], bool]
    ) -> Callable[[Any, Any], bool]:
        def predicate(snapshot: Any, _parsed: Any) -> bool:
            if is_oh_reward_message(snapshot):
                content = getattr(snapshot, "content", "") or ""
                if reward_has_entries(content):
                    self._reward_content = content
            return matches(snapshot)

        return predicate
