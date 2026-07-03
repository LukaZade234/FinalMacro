"""Play the Mudae ``$oh`` sphere minigame.

The ``$oh`` command posts a 5x5 grid of clickable sphere buttons. Some are
already revealed (a colored sphere), the rest are face-down (``spU``). Clicking
a sphere claims its value; blue/teal spheres additionally unveil more hidden
buttons (3 and 1 respectively). The grid lives in a single message that Mudae
*edits* after every click, so the engine must wait for each edit to land before
deciding its next move.

Purple spheres (``spP``) are **free**: they do not consume the click allowance.
Dark spheres (``spD``) use a paid click; if they resolve to purple, that outcome
appears only in the **reward tracker message** below the grid (the grid button
emoji does not flip to ``spP``). Those purple payout lines are free as well.

Strategy (per the user's spec):
    * always take free purple (``spP``) when available;
    * never click an already-revealed blue (``spB``) or teal (``spT``) — they
      are worth so little that a face-down click is preferable;
    * otherwise click the highest-value revealed paid sphere available;
    * if no worthwhile revealed sphere remains, click a random face-down button.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Callable
from typing import Any

from mudae.constants import (
    SPHERE_FREE_EMOJIS,
    SPHERE_HIDDEN_EMOJI,
    SPHERE_REVEAL_EMOJIS,
    SPHERE_VALUE_RANK,
)

def sphere_value_rank(emoji: str) -> int:
    """Paid-click value for a revealed sphere emoji (higher = click first)."""
    return SPHERE_VALUE_RANK.get(emoji.strip(), 0)


def _button_sort_key(buttons: list[dict[str, Any]], button: dict[str, Any]) -> tuple[int, int]:
    rank = sphere_value_rank(_emoji(button))
    for index, candidate in enumerate(buttons):
        if candidate.get("custom_id") == button.get("custom_id"):
            return rank, -index
    return rank, 0

# "You can click **5** times on the buttons below ..."
_CLICKS_ALLOWED_RE = re.compile(r"click\s*\*{0,2}(\d+)\*{0,2}\s*times", re.IGNORECASE)
# Reward lines look like "<:spY:123> **+59**" or "<:spP:123> **+42**".
_REWARD_AMOUNT_RE = re.compile(r"\*\*\+\s*([\d,]+)")
_REWARD_LINE_EMOJI_RE = re.compile(r"<:([^:>]+):\d+>\s*\*\*\+")
_DEFAULT_CLICKS_ALLOWED = 5
# Minimum sphere buttons that distinguishes the $oh grid from a roll's lone
# sphere react button.
_MIN_GRID_BUTTONS = 10


def _emoji(button: dict[str, Any]) -> str:
    return (button.get("emoji") or "").strip()


def _sphere_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in buttons if (b.get("kind") == "sphere") or _emoji(b).startswith("sp")]


def _is_clickable(button: dict[str, Any]) -> bool:
    return bool(button.get("custom_id")) and not button.get("disabled")


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


def reward_line_types(content: str) -> list[str]:
    """Emoji names from each payout line in the reward tracker message."""
    return _REWARD_LINE_EMOJI_RE.findall(content or "")


def new_reward_line_types(before: str, after: str) -> list[str]:
    """Emoji names added to the reward tracker since ``before``."""
    prev = reward_line_types(before)
    curr = reward_line_types(after)
    if len(curr) <= len(prev):
        return []
    return curr[len(prev):]


def reward_has_entries(content: str) -> bool:
    if not content or "rewards appear here" in content.lower():
        return False
    return bool(reward_line_types(content))


def disabled_count(buttons: list[dict[str, Any]]) -> int:
    return sum(1 for b in buttons if b.get("disabled"))


def grid_signature(buttons: list[dict[str, Any]]) -> tuple[tuple[str, str, bool], ...]:
    """Stable fingerprint of the grid for detecting Mudae edits."""
    sig: list[tuple[str, str, bool]] = []
    for button in _sphere_buttons(buttons):
        sig.append((
            str(button.get("custom_id") or ""),
            _emoji(button),
            bool(button.get("disabled")),
        ))
    return tuple(sig)


def is_oh_game_over(buttons: list[dict[str, Any]]) -> bool:
    """True when Mudae has ended the session (no sphere buttons left to press)."""
    spheres = _sphere_buttons(buttons)
    if len(spheres) < _MIN_GRID_BUTTONS:
        return True
    return not any(_is_clickable(button) for button in spheres)


def _disable_button(buttons: list[dict[str, Any]], custom_id: str) -> list[dict[str, Any]]:
    """Optimistic grid state when Mudae updates the reward tracker first."""
    out: list[dict[str, Any]] = []
    for button in buttons:
        copy = dict(button)
        if copy.get("custom_id") == custom_id:
            copy["disabled"] = True
        out.append(copy)
    return out


def is_free_oh_click(button: dict[str, Any]) -> bool:
    return _emoji(button) in SPHERE_FREE_EMOJIS


def choose_oh_click(
    buttons: list[dict[str, Any]],
    *,
    clicks_spent: int = 0,
    clicks_budget: int = _DEFAULT_CLICKS_ALLOWED,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Pick the next button to click, or ``None`` when no legal move remains.

    Preference order:
        1. any revealed free purple (``spP``);
        2. highest-value revealed paid sphere (never blue/teal — prefer ``spU``);
        3. a random face-down (``spU``) button — only while budget remains.
    """
    chooser = rng or random
    budget_left = clicks_spent < clicks_budget

    free_purples: list[dict[str, Any]] = []
    value_spheres: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []

    for button in buttons:
        if not _is_clickable(button):
            continue
        emoji = _emoji(button)
        if not emoji.startswith("sp"):
            continue
        if emoji in SPHERE_FREE_EMOJIS:
            free_purples.append(button)
        elif emoji == SPHERE_HIDDEN_EMOJI:
            if budget_left:
                hidden.append(button)
        elif emoji in SPHERE_REVEAL_EMOJIS:
            continue  # blue / teal: too low value — prefer face-down spU
        elif budget_left:
            value_spheres.append(button)

    if free_purples:
        return max(free_purples, key=lambda b: _button_sort_key(buttons, b))
    if value_spheres:
        return max(value_spheres, key=lambda b: _button_sort_key(buttons, b))
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
        clicks_spent = 0
        free_clicks = 0
        try:
            self._actions.drain_queue()
            self._log("$oh: starting sphere game")
            await self._actions.send_command("oh", prefix=prefix)

            grid = await self._wait_for_grid()
            if grid is None:
                self._log("$oh: grid did not appear (timeout)")
                return {"clicks": 0, "free_clicks": 0, "reward": 0, "reason": "no grid"}

            grid_id = grid.message_id
            buttons = list(grid.buttons)
            clicks_budget = parse_clicks_allowed(grid.content)
            self._log(f"$oh: grid ready · {clicks_budget} paid clicks allowed")

            while not is_oh_game_over(buttons):
                choice = choose_oh_click(
                    buttons,
                    clicks_spent=clicks_spent,
                    clicks_budget=clicks_budget,
                    rng=self._rng,
                )
                if choice is None:
                    if clicks_spent < clicks_budget:
                        self._log("$oh: no clickable sphere left — stopping")
                    else:
                        self._log("$oh: paid clicks used · no free purples left")
                    break

                custom_id = choice["custom_id"]
                emoji = _emoji(choice)
                free = is_free_oh_click(choice)
                kind = "free purple" if free else (
                    "hidden" if emoji == SPHERE_HIDDEN_EMOJI else emoji
                )
                before_sig = grid_signature(buttons)
                before_reward = self._reward_content

                ok = await self._actions.click_button(grid_id, custom_id)
                if not ok:
                    self._log(f"$oh: click failed ({kind}) — stopping")
                    break

                if free:
                    free_clicks += 1
                    self._log(f"$oh: free click → {kind} ({free_clicks} free)")
                else:
                    clicks_spent += 1
                    self._log(
                        f"$oh: click {clicks_spent}/{clicks_budget} → {kind}"
                    )

                updated, reward_content = await self._wait_for_click_resolution(
                    grid_id,
                    before_sig,
                    before_reward,
                )
                if updated is None and reward_content == before_reward:
                    self._log("$oh: click ack timeout — stopping")
                    break

                self._reward_content = reward_content
                for outcome in new_reward_line_types(before_reward, reward_content):
                    if outcome == "spP" and not free:
                        free_clicks += 1
                        self._log(
                            f"$oh: reward → purple (free bonus, {free_clicks} free)"
                        )

                if updated is not None:
                    buttons = list(updated.buttons)
                else:
                    buttons = _disable_button(buttons, custom_id)
                await asyncio.sleep(self._click_delay)

            if is_oh_game_over(buttons):
                self._log("$oh: grid locked — minigame finished")

            reward = total_reward_from_content(self._reward_content)
            reward_note = f" · +{reward} spheres" if reward else ""
            self._log(
                f"$oh: finished · {clicks_spent} paid"
                + (f", {free_clicks} free" if free_clicks else "")
                + reward_note
            )
            return {
                "clicks": clicks_spent,
                "free_clicks": free_clicks,
                "reward": reward,
                "reason": "done",
            }
        finally:
            self._monitor.macro_active = previously_active

    async def _wait_for_grid(self) -> Any | None:
        result = await self._actions.wait_for(
            self._make_predicate(lambda s: is_oh_grid_message(s)),
            timeout=self._grid_timeout,
        )
        return result[0] if result else None

    async def _wait_for_click_resolution(
        self,
        grid_id: int,
        before_sig: tuple,
        before_reward: str,
    ) -> tuple[Any | None, str]:
        """Wait for Mudae to acknowledge a click via grid edit and/or reward line."""
        latest_grid: Any | None = None
        latest_reward = before_reward

        def matches(snapshot: Any) -> bool:
            nonlocal latest_grid, latest_reward
            if is_oh_reward_message(snapshot):
                content = getattr(snapshot, "content", "") or ""
                if reward_has_entries(content) and content != before_reward:
                    latest_reward = content
                    self._reward_content = content
                    return True
            if (
                snapshot.message_id == grid_id
                and is_oh_grid_message(snapshot)
                and grid_signature(snapshot.buttons) != before_sig
            ):
                latest_grid = snapshot
                latest_reward = self._reward_content
                return True
            return False

        result = await self._actions.wait_for(
            self._make_predicate(matches),
            timeout=self._edit_timeout,
        )
        if not result:
            return None, before_reward

        if latest_grid is not None and latest_reward == before_reward:
            bonus = await self._actions.wait_for(
                self._make_predicate(
                    lambda snapshot: (
                        is_oh_reward_message(snapshot)
                        and reward_has_entries(getattr(snapshot, "content", "") or "")
                        and (getattr(snapshot, "content", "") or "") != before_reward
                    )
                ),
                timeout=2.0,
            )
            if bonus:
                latest_reward = self._reward_content

        if latest_grid is not None:
            return latest_grid, latest_reward
        return None, latest_reward

    def _make_predicate(
        self, matches: Callable[[Any], bool]
    ) -> Callable[[Any, Any], bool]:
        """Wrap a snapshot predicate, keeping reward message content in sync."""

        def predicate(snapshot: Any, _parsed: Any) -> bool:
            if is_oh_reward_message(snapshot):
                content = getattr(snapshot, "content", "") or ""
                if reward_has_entries(content):
                    self._reward_content = content
            return matches(snapshot)

        return predicate
