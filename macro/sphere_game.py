"""Play the Mudae ``$oh`` sphere minigame.

The ``$oh`` command posts a 5x5 grid of clickable sphere buttons. Some are
already revealed (a colored sphere), the rest are face-down (``spU``). Clicking
a sphere claims its value; blue/teal spheres additionally unveil more hidden
buttons (3 and 1 respectively). The grid lives in a single message that Mudae
*edits* after every click, so the engine must wait for each edit to land before
deciding its next move.

Strategy (per the user's spec):
    * never click an already-revealed blue (``spB``) or teal (``spT``) sphere;
    * otherwise click the best revealed value sphere available;
    * if no value sphere is revealed, click a random face-down button.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Callable
from typing import Any

from mudae.constants import (
    SPHERE_HIDDEN_EMOJI,
    SPHERE_REVEAL_EMOJIS,
    SPHERE_VALUE_RANK,
)

# "You can click **5** times on the buttons below ..."
_CLICKS_ALLOWED_RE = re.compile(r"click\s*\*{0,2}(\d+)\*{0,2}\s*times", re.IGNORECASE)
# Reward lines look like "<:spY:123> **+59**" or "<:spU:123> **+1 $oc**".
_REWARD_AMOUNT_RE = re.compile(r"\*\*\+\s*([\d,]+)")
_DEFAULT_CLICKS_ALLOWED = 5
# Minimum sphere buttons that distinguishes the $oh grid from a roll's lone
# sphere react button.
_MIN_GRID_BUTTONS = 10


def _emoji(button: dict[str, Any]) -> str:
    return (button.get("emoji") or "").strip()


def _sphere_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in buttons if (b.get("kind") == "sphere") or _emoji(b).startswith("sp")]


def is_oh_grid_message(snapshot: Any) -> bool:
    """True when ``snapshot`` is the ``$oh`` grid (initial post or an edit)."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    content = (getattr(snapshot, "content", "") or "").lower()
    spheres = _sphere_buttons(getattr(snapshot, "buttons", []) or [])
    if len(spheres) < _MIN_GRID_BUTTONS:
        return False
    return "buttons below" in content or "spheres buttons" in content


def is_oh_reward_message(snapshot: Any) -> bool:
    """True for the side message that lists per-click sphere payouts."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    if getattr(snapshot, "buttons", None):
        return False
    content = getattr(snapshot, "content", "") or ""
    return "<:sp" in content and "+" in content


def parse_clicks_allowed(content: str) -> int:
    match = _CLICKS_ALLOWED_RE.search(content or "")
    if not match:
        return _DEFAULT_CLICKS_ALLOWED
    return max(1, int(match.group(1)))


def total_reward_from_content(content: str) -> int:
    total = 0
    for raw in _REWARD_AMOUNT_RE.findall(content or ""):
        total += int(raw.replace(",", ""))
    return total


def disabled_count(buttons: list[dict[str, Any]]) -> int:
    return sum(1 for b in buttons if b.get("disabled"))


def choose_oh_click(
    buttons: list[dict[str, Any]],
    *,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Pick the next button to click, or ``None`` when no legal move remains.

    Preference order:
        1. highest-value revealed sphere that is not blue/teal;
        2. a random face-down (``spU``) button.
    """
    chooser = rng or random
    value_spheres: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []

    for button in buttons:
        if button.get("disabled") or not button.get("custom_id"):
            continue
        emoji = _emoji(button)
        if not emoji.startswith("sp"):
            continue
        if emoji == SPHERE_HIDDEN_EMOJI:
            hidden.append(button)
        elif emoji in SPHERE_REVEAL_EMOJIS:
            continue  # blue / teal: never click once revealed
        else:
            value_spheres.append(button)

    if value_spheres:
        best_rank = max(SPHERE_VALUE_RANK.get(_emoji(b), 0) for b in value_spheres)
        best = [b for b in value_spheres if SPHERE_VALUE_RANK.get(_emoji(b), 0) == best_rank]
        return chooser.choice(best)
    if hidden:
        return chooser.choice(hidden)
    return None


class OhSphereGame:
    """Drive a single ``$oh`` session end to end."""

    def __init__(
        self,
        actions: Any,
        monitor: Any,
        *,
        log: Callable[[str], None],
        rng: random.Random | None = None,
        grid_timeout: float = 12.0,
        edit_timeout: float = 8.0,
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

    async def play(self, *, prefix: str = "$") -> dict[str, Any]:
        previously_active = getattr(self._monitor, "macro_active", False)
        self._monitor.macro_active = True
        clicks_done = 0
        try:
            self._actions.drain_queue()
            self._log("$oh: starting sphere game")
            await self._actions.send_command("oh", prefix=prefix)

            grid = await self._wait_for_grid()
            if grid is None:
                self._log("$oh: grid did not appear (timeout)")
                return {"clicks": 0, "reward": 0, "reason": "no grid"}

            grid_id = grid.message_id
            buttons = list(grid.buttons)
            clicks_allowed = parse_clicks_allowed(grid.content)
            self._log(f"$oh: grid ready · {clicks_allowed} clicks allowed")

            while clicks_done < clicks_allowed:
                choice = choose_oh_click(buttons, rng=self._rng)
                if choice is None:
                    self._log("$oh: no clickable sphere left — stopping")
                    break

                custom_id = choice["custom_id"]
                emoji = _emoji(choice)
                kind = "hidden" if emoji == SPHERE_HIDDEN_EMOJI else emoji
                before = disabled_count(buttons)

                ok = await self._actions.click_button(grid_id, custom_id)
                if not ok:
                    self._log(f"$oh: click failed ({kind}) — stopping")
                    break
                clicks_done += 1
                self._log(f"$oh: click {clicks_done}/{clicks_allowed} → {kind}")

                updated = await self._wait_for_grid_update(grid_id, before)
                if updated is None:
                    self._log("$oh: grid edit timeout — stopping")
                    break
                buttons = list(updated.buttons)
                await asyncio.sleep(self._click_delay)

            reward = total_reward_from_content(self._reward_content)
            reward_note = f" · +{reward} spheres" if reward else ""
            self._log(f"$oh: finished after {clicks_done} click(s){reward_note}")
            return {"clicks": clicks_done, "reward": reward, "reason": "done"}
        finally:
            self._monitor.macro_active = previously_active

    async def _wait_for_grid(self) -> Any | None:
        result = await self._actions.wait_for(
            self._make_predicate(lambda s: is_oh_grid_message(s)),
            timeout=self._grid_timeout,
        )
        return result[0] if result else None

    async def _wait_for_grid_update(self, grid_id: int, before: int) -> Any | None:
        def matches(snapshot: Any) -> bool:
            return (
                snapshot.message_id == grid_id
                and is_oh_grid_message(snapshot)
                and disabled_count(snapshot.buttons) > before
            )

        result = await self._actions.wait_for(
            self._make_predicate(matches),
            timeout=self._edit_timeout,
        )
        return result[0] if result else None

    def _make_predicate(
        self, matches: Callable[[Any], bool]
    ) -> Callable[[Any, Any], bool]:
        """Wrap a snapshot predicate, capturing reward messages as a side effect."""

        def predicate(snapshot: Any, _parsed: Any) -> bool:
            if is_oh_reward_message(snapshot):
                self._reward_content = snapshot.content
            return matches(snapshot)

        return predicate
