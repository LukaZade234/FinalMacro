"""Play the Mudae ``$oc`` sphere deduction minigame.

Unlike ``$oh`` (pure chance), ``$oc`` hides exactly one red sphere on a 5×5
grid with deterministic colour-placement rules.  The macro tracks every reveal,
feeds observations into :mod:`macro.oc_solver`, and clicks the cell with the
best expected payout — prioritising the red sphere once its location is known,
then the surrounding orange and yellow cells.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Callable
from typing import Any

from macro.minigame_util import minigame_command
from macro.minigame_board import (
    board_emojis,
    build_session,
    cell_index,
    make_click,
    revealed_click_emoji,
)
from macro.oc_solver import (
    choose_oc_click,
    emoji_to_oc_color,
    format_solver_stats,
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

_OC_GRID_RE = re.compile(r"red sphere.*find", re.IGNORECASE)


def _emoji(button: dict[str, Any]) -> str:
    return (button.get("emoji") or "").strip()


def _sphere_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in buttons if (b.get("kind") == "sphere") or _emoji(b).startswith("sp")]


def _is_clickable(button: dict[str, Any]) -> bool:
    return bool(button.get("custom_id")) and not button.get("disabled")


def is_oc_grid_message(snapshot: Any) -> bool:
    """True when ``snapshot`` is the ``$oc`` grid (initial post or an edit)."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    content = (getattr(snapshot, "content", "") or "").lower()
    spheres = _sphere_buttons(getattr(snapshot, "buttons", []) or [])
    if len(spheres) < _MIN_GRID_BUTTONS:
        return False
    if "buttons below" not in content:
        return False
    return bool(_OC_GRID_RE.search(content))


def is_oc_game_over(buttons: list[dict[str, Any]]) -> bool:
    spheres = _sphere_buttons(buttons)
    if len(spheres) < _MIN_GRID_BUTTONS:
        return True
    return not any(_is_clickable(button) for button in spheres)


class OcSphereGame:
    """Drive a single ``$oc`` session end to end."""

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

    async def play(self, *, prefix: str = "$", uses: int = 1) -> dict[str, Any]:
        previously_active = getattr(self._monitor, "macro_active", False)
        self._monitor.macro_active = True
        clicks_spent = 0
        try:
            self._actions.drain_queue()
            cmd = minigame_command("oc", uses)
            label = f"${cmd}" if uses > 1 else "$oc"
            self._log(f"{label}: starting sphere game")
            await self._actions.send_command(cmd, prefix=prefix)

            grid = await self._wait_for_grid()
            if grid is None:
                self._log(f"{label}: grid did not appear (timeout)")
                return {"clicks": 0, "reward": 0, "reason": "no grid"}

            grid_id = grid.message_id
            buttons = list(grid.buttons)
            clicks_budget = parse_clicks_allowed(grid.content)
            session_clicks: list[dict[str, Any]] = []
            self._observations = observations_from_buttons(buttons)
            self._log(
                f"{label}: grid ready · {clicks_budget} clicks · {format_solver_stats(self._observations)}"
            )
            await asyncio.sleep(FIRST_CLICK_DELAY_SEC)

            while not is_oc_game_over(buttons):
                if clicks_spent >= clicks_budget:
                    self._log("$oc: click budget spent")
                    break

                choice = choose_oc_click(
                    buttons,
                    self._observations,
                    clicks_spent=clicks_spent,
                    clicks_budget=clicks_budget,
                    rng=self._rng,
                )
                if choice is None:
                    self._log("$oc: no hidden cell to click — stopping")
                    break

                custom_id = choice["custom_id"]
                clicked_index = cell_index(buttons, custom_id)
                before_sig = grid_signature(buttons)
                before_reward = self._reward_content

                ok = await self._actions.click_button(grid_id, custom_id)
                if not ok:
                    self._log("$oc: click failed — stopping")
                    break

                clicks_spent += 1
                self._log(
                    f"$oc: click {clicks_spent}/{clicks_budget} → cell "
                    f"{self._cell_label(clicked_index)} · "
                    f"{format_solver_stats(self._observations)}"
                )

                updated, reward_content = await self._wait_for_click_resolution(
                    grid_id,
                    before_sig,
                    before_reward,
                    custom_id=custom_id,
                    clicked_index=clicked_index,
                )
                if updated is None and reward_content == before_reward:
                    self._log("$oc: click ack timeout — stopping")
                    break

                if updated is None and reward_content != before_reward:
                    self._log("$oc: continuing from reward line (grid edit pending)")

                self._reward_content = reward_content
                if updated is not None:
                    buttons = list(updated.buttons)
                else:
                    buttons = _disable_button(buttons, custom_id)

                self._sync_observations(
                    buttons,
                    reward_content,
                    clicked_index=clicked_index,
                    before_reward=before_reward,
                )
                reveal_emoji = revealed_click_emoji(
                    reward_types=new_reward_line_types(before_reward, reward_content),
                    buttons=buttons,
                    clicked_index=clicked_index,
                    fallback=(
                        self._observations.get(clicked_index, "")
                        if clicked_index is not None
                        else ""
                    ),
                )
                session_clicks.append(
                    make_click(clicked_index, reveal_emoji, paid=True)
                )
                self._log(f"$oc: {format_solver_stats(self._observations)}")
                await asyncio.sleep(self._click_delay)

            if is_oc_game_over(buttons):
                self._log("$oc: grid locked — minigame finished")

            buttons = await wait_for_final_grid(
                self._actions,
                grid_id=grid_id,
                buttons=buttons,
                is_grid_message=is_oc_grid_message,
                get_reward_content=lambda: self._reward_content,
                set_reward_content=lambda content: setattr(self, "_reward_content", content),
            )
            session = build_session(
                "oc",
                session_clicks,
                board_emojis(buttons),
                clicks_paid=clicks_spent,
                clicks_budget=clicks_budget,
                reason="done",
            )

            reward = total_reward_from_content(self._reward_content)
            reward_note = f" · +{reward} spheres" if reward else ""
            self._log(f"{label}: finished · {clicks_spent} clicks{reward_note}")
            return {
                "clicks": clicks_spent,
                "reward": reward,
                "reason": "done",
                "session": session,
            }
        finally:
            self._monitor.macro_active = previously_active

    def _sync_observations(
        self,
        buttons: list[dict[str, Any]],
        reward_content: str,
        *,
        clicked_index: int | None,
        before_reward: str,
    ) -> None:
        grid_obs = observations_from_buttons(buttons)
        reward_obs: dict[int, str] = {}
        if clicked_index is not None:
            for emoji_name in new_reward_line_types(before_reward, reward_content):
                color = emoji_to_oc_color(emoji_name)
                if color:
                    reward_obs[clicked_index] = color
        try:
            self._observations = merge_observations(
                self._observations,
                grid_obs,
                reward_obs,
            )
        except ValueError:
            self._observations = merge_observations(self._observations, grid_obs)

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

    async def _wait_for_grid(self) -> Any | None:
        result = await self._actions.wait_for(
            self._make_predicate(lambda snapshot: is_oc_grid_message(snapshot)),
            timeout=self._grid_timeout,
        )
        return result[0] if result else None

    async def _wait_for_click_resolution(
        self,
        grid_id: int,
        before_sig: tuple,
        before_reward: str,
        *,
        custom_id: str,
        clicked_index: int | None,
    ) -> tuple[Any | None, str]:
        del clicked_index  # reserved for future per-cell ack hints

        async def _retry_click() -> None:
            ok = await self._actions.click_button(grid_id, custom_id)
            if ok:
                self._log("$oc: resending click")
            else:
                self._log("$oc: retry click send failed")

        return await wait_for_minigame_click_ack(
            self._actions,
            monitor=self._monitor,
            grid_id=grid_id,
            before_sig=before_sig,
            before_reward=before_reward,
            is_grid_message=is_oc_grid_message,
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
