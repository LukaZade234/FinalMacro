"""Play the Mudae ``$ot`` battleship minigame.

The grid message states the fleet up front (``Number of different colors: N``
⇒ ``N - 4`` length-2 ships), so :mod:`macro.ot_solver` knows exactly which
ships are hidden before the first click and reasons about *where* they are.

Two things make the loop different from ``$oc`` / ``$oq``:

* **Only blue costs a click.** Ship cells are free, so the budget is spent by
  mistakes, not by clicks. The loop counts blues, not clicks, and a good game
  ends with far more clicks than its 4-click budget.
* **The clicked cell's colour comes from the grid, not the reward line.** A
  light ship pays out as a bundle of *other* colours ("breaks down into"), so
  reading the reward line as the cell's identity would tell the solver a
  rainbow cell was blue. :func:`macro.minigame_board.classify_oh_click`
  already untangles that for ``$oh``; the same call does it here.

``$ot`` is **manual only** for now — no play-all, and no auto-play after the
daily refill. That is deliberate while the solver is being tried on real
boards: see ``PLAYABLE_MINIGAMES`` in :mod:`macro.minigame_daily`, which does
not list it.
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
    OtFleet,
    choose_ot_click,
    emoji_to_ot_color,
    format_solver_stats,
    observations_from_buttons,
    parse_ot_fleet,
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
    ) -> None:
        self._actions = actions
        self._monitor = monitor
        self._log = log
        self._rng = rng or random.Random()
        self._grid_timeout = grid_timeout
        self._edit_timeout = edit_timeout
        self._click_delay = click_delay
        self._policy = policy
        self._reward_content = ""
        self._observations: dict[int, str] = {}

    async def play(self, *, prefix: str = "$", uses: int = 1) -> dict[str, Any]:
        enter_macro_activity(self._monitor)
        blues_spent = 0
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
                f"{format_solver_stats(fleet, self._observations, policy=self._policy)}"
            )
            await asyncio.sleep(FIRST_CLICK_DELAY_SEC)

            while not is_ot_game_over(buttons):
                if blues_spent >= clicks_budget:
                    self._log("$ot: blue click budget spent")
                    break

                choice = choose_ot_click(
                    buttons,
                    self._observations,
                    fleet=fleet,
                    blues_spent=blues_spent,
                    policy=self._policy,
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
                    self._log("$ot: click failed — stopping")
                    break

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
                    self._log(
                        f"$ot: blue {blues_spent}/{clicks_budget} at cell "
                        f"{self._cell_label(clicked_index)}"
                    )
                else:
                    self._log(
                        f"$ot: free hit at cell {self._cell_label(clicked_index)} "
                        f"→ {revealed or '?'}"
                    )
                self._log(
                    "$ot: "
                    + format_solver_stats(
                        fleet, self._observations, policy=self._policy
                    )
                )
                await asyncio.sleep(self._click_delay)

            if is_ot_game_over(buttons):
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
            free_clicks = len(session_clicks) - blues_spent
            self._log(
                f"{label}: finished · {free_clicks} free hits, "
                f"{blues_spent}/{clicks_budget} blue{reward_note}"
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
        )

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
