"""Play the Mudae ``$oq`` (Orb Quest) sphere minigame.

Four purple spheres hide on a 5×5 grid. Revealed numbers count adjacent purples
(Minesweeper-style). Find 3 purples within 7 paid clicks; Mudae then auto-reveals
the 4th as a clickable red (or rainbow). Remaining clicks harvest high-value orbs.
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
    make_click,
    revealed_click_emoji,
)
from macro.oq_solver import (
    CLICK_BUDGET,
    OQ_RED_EMOJIS,
    TARGET_PURPLES,
    choose_oq_click,
    emoji_to_oq_state,
    format_solver_stats,
    is_paid_reveal,
    merge_observations,
    observations_from_buttons,
)
from macro.sphere_game import (
    FIRST_CLICK_DELAY_SEC,
    _MIN_GRID_BUTTONS,
    _disable_button,
    grid_signature,
    is_oh_reward_message,
    new_reward_line_types,
    parse_clicks_allowed,
    reward_has_entries,
    total_reward_from_content,
    wait_for_final_grid,
    wait_for_minigame_click_ack,
)

_OQ_GRID_RE = re.compile(
    r"find\s+3\s+purple|3\s+purple\s+sphere|purple\s+sphere.*find",
    re.IGNORECASE,
)


def _emoji(button: dict[str, Any]) -> str:
    return (button.get("emoji") or "").strip()


def _sphere_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in buttons if (b.get("kind") == "sphere") or _emoji(b).startswith("sp")]


def _is_clickable(button: dict[str, Any]) -> bool:
    return bool(button.get("custom_id")) and not button.get("disabled")


def _has_clickable_red(buttons: list[dict[str, Any]]) -> bool:
    return any(
        _is_clickable(button) and _emoji(button) in OQ_RED_EMOJIS
        for button in _sphere_buttons(buttons)
    )


def is_oq_grid_message(snapshot: Any) -> bool:
    """True when ``snapshot`` is the ``$oq`` grid (initial post or an edit)."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    content = (getattr(snapshot, "content", "") or "").lower()
    spheres = _sphere_buttons(getattr(snapshot, "buttons", []) or [])
    if len(spheres) < _MIN_GRID_BUTTONS:
        return False
    if "buttons below" not in content:
        return False
    return bool(_OQ_GRID_RE.search(content))


def is_oq_game_over(buttons: list[dict[str, Any]]) -> bool:
    spheres = _sphere_buttons(buttons)
    if len(spheres) < _MIN_GRID_BUTTONS:
        return True
    return not any(_is_clickable(button) for button in spheres)


class OqSphereGame:
    """Drive a single ``$oq`` session end to end."""

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
    ) -> None:
        self._actions = actions
        self._monitor = monitor
        self._log = log
        self._rng = rng or random.Random()
        self._grid_timeout = grid_timeout
        self._edit_timeout = edit_timeout
        self._click_delay = click_delay
        self._reward_content = ""
        self._observations: dict[int, str] = {}
        self._paid_clicks = 0

    async def play(self, *, prefix: str = "$", uses: int = 1) -> dict[str, Any]:
        enter_macro_activity(self._monitor)
        paid_clicks = 0
        try:
            self._actions.drain_queue()
            cmd = minigame_command("oq", uses)
            label = f"${cmd}" if uses > 1 else "$oq"
            self._log(f"{label}: starting sphere game")
            await self._actions.send_command(cmd, prefix=prefix)

            grid, exhausted = await self._wait_for_grid()
            if exhausted is not None:
                log_minigame_exhausted(self._log, exhausted)
                return empty_minigame_result("exhausted", exhausted=exhausted)
            if grid is None:
                self._log(f"{label}: grid did not appear (timeout)")
                return empty_minigame_result("no grid")

            grid_id = grid.message_id
            buttons = list(grid.buttons)
            clicks_budget = parse_clicks_allowed(grid.content) or CLICK_BUDGET
            session_clicks: list[dict[str, Any]] = []
            self._observations = observations_from_buttons(buttons)
            self._paid_clicks = 0
            self._log(
                f"{label}: grid ready · {clicks_budget} paid clicks · "
                f"{format_solver_stats(self._observations, clicks_spent=0)}"
            )
            await asyncio.sleep(FIRST_CLICK_DELAY_SEC)

            awaited_red = False
            while not is_oq_game_over(buttons):
                try:
                    self._observations = merge_observations(
                        self._observations,
                        observations_from_buttons(buttons),
                    )
                except ValueError:
                    pass

                choice = choose_oq_click(
                    buttons,
                    self._observations,
                    clicks_spent=paid_clicks,
                    clicks_budget=clicks_budget,
                )
                if choice is None:
                    n_purple = sum(
                        1 for state in self._observations.values() if state == "t"
                    )
                    if (
                        paid_clicks < clicks_budget
                        and n_purple >= TARGET_PURPLES
                        and not _has_clickable_red(buttons)
                        and not awaited_red
                    ):
                        self._log("$oq: waiting for the 4th purple to become red")
                        buttons = await wait_for_final_grid(
                            self._actions,
                            grid_id=grid_id,
                            buttons=buttons,
                            is_grid_message=is_oq_grid_message,
                            get_reward_content=lambda: self._reward_content,
                            set_reward_content=lambda content: setattr(
                                self, "_reward_content", content
                            ),
                            timeout=self._edit_timeout,
                        )
                        awaited_red = True
                        continue
                    if paid_clicks >= clicks_budget:
                        self._log("$oq: click budget spent")
                    else:
                        self._log("$oq: no cell to click — stopping")
                    break

                custom_id = choice["custom_id"]
                clicked_index = cell_index(buttons, custom_id)
                before_sig = grid_signature(buttons)
                before_reward = self._reward_content

                ok = await self._actions.click_button(grid_id, custom_id)
                if not ok:
                    self._log("$oq: click failed — stopping")
                    break

                updated, reward_content = await self._wait_for_click_resolution(
                    grid_id,
                    before_sig,
                    before_reward,
                    custom_id=custom_id,
                    clicked_index=clicked_index,
                )
                if updated is None and reward_content == before_reward:
                    self._log("$oq: click ack timeout — stopping")
                    break

                if updated is None and reward_content != before_reward:
                    self._log("$oq: continuing from reward line (grid edit pending)")

                self._reward_content = reward_content
                if updated is not None:
                    buttons = list(updated.buttons)
                else:
                    buttons = _disable_button(buttons, custom_id)

                reveal_state = self._sync_observations(
                    buttons,
                    reward_content,
                    clicked_index=clicked_index,
                    before_reward=before_reward,
                )
                paid = is_paid_reveal(reveal_state)
                if paid:
                    paid_clicks += 1
                reveal_emoji = revealed_click_emoji(
                    reward_types=new_reward_line_types(before_reward, reward_content),
                    buttons=buttons,
                    clicked_index=clicked_index,
                    fallback=reveal_state if reveal_state not in {"?", ""} else "",
                )
                session_clicks.append(
                    make_click(clicked_index, reveal_emoji, paid=paid)
                )

                self._log(
                    f"$oq: click {paid_clicks}/{clicks_budget} paid → cell "
                    f"{self._cell_label(clicked_index)} · "
                    f"{format_solver_stats(self._observations, clicks_spent=paid_clicks)}"
                )
                await asyncio.sleep(self._click_delay)

            if is_oq_game_over(buttons):
                self._log("$oq: grid locked — minigame finished")

            buttons = await wait_for_final_grid(
                self._actions,
                grid_id=grid_id,
                buttons=buttons,
                is_grid_message=is_oq_grid_message,
                get_reward_content=lambda: self._reward_content,
                set_reward_content=lambda content: setattr(self, "_reward_content", content),
            )
            session = build_session(
                "oq",
                session_clicks,
                board_emojis(buttons),
                clicks_paid=paid_clicks,
                clicks_budget=clicks_budget,
                reason="done",
                uses=uses,
            )

            reward = total_reward_from_content(self._reward_content)
            reward_note = f" · +{reward} spheres" if reward else ""
            self._log(f"{label}: finished · {paid_clicks} paid clicks{reward_note}")
            return {
                "clicks": paid_clicks,
                "reward": reward,
                "reason": "done",
                "session": session,
            }
        finally:
            exit_macro_activity(self._monitor)

    def _sync_observations(
        self,
        buttons: list[dict[str, Any]],
        reward_content: str,
        *,
        clicked_index: int | None,
        before_reward: str,
    ) -> str:
        grid_obs = observations_from_buttons(buttons)
        reward_obs: dict[int, str] = {}
        reveal_state = "?"
        if clicked_index is not None:
            for emoji_name in new_reward_line_types(before_reward, reward_content):
                state = emoji_to_oq_state(emoji_name)
                if state:
                    reward_obs[clicked_index] = state
                    reveal_state = state
        if clicked_index is not None and clicked_index in grid_obs:
            reveal_state = grid_obs[clicked_index]
        try:
            self._observations = merge_observations(
                self._observations,
                grid_obs,
                reward_obs,
            )
        except ValueError:
            self._observations = merge_observations(self._observations, grid_obs)
        return reveal_state

    @staticmethod
    def _cell_index(buttons: list[dict[str, Any]], custom_id: str) -> int | None:
        for index, button in enumerate(_sphere_buttons(buttons)):
            if button.get("custom_id") == custom_id:
                return index
        return None

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
                lambda snapshot: is_oq_grid_message(snapshot)
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
        clicked_index: int | None,
    ) -> tuple[Any | None, str]:
        del clicked_index

        async def _retry_click() -> None:
            ok = await self._actions.click_button(grid_id, custom_id)
            if ok:
                self._log("$oq: resending click")
            else:
                self._log("$oq: retry click send failed")

        return await wait_for_minigame_click_ack(
            self._actions,
            monitor=self._monitor,
            grid_id=grid_id,
            before_sig=before_sig,
            before_reward=before_reward,
            is_grid_message=is_oq_grid_message,
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
