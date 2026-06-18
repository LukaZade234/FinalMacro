"""Tests for the $oh sphere minigame logic and player loop."""

from __future__ import annotations

import asyncio
import json
import random
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from macro.sphere_game import (
    OhSphereGame,
    choose_oh_click,
    is_oh_grid_message,
    is_oh_reward_message,
    parse_clicks_allowed,
    total_reward_from_content,
)

_FIXTURE = Path(__file__).resolve().parent.parent / "data" / "oh_log.json"
_GRID_TEXT = (
    "You can click **5** times on the buttons below (for 2 minutes. Only you can click).\n"
    "Spheres buttons have different values depending on their color, like kakera."
)


def _btn(index: int, emoji: str, *, disabled: bool = False) -> dict:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


def _grid_snapshot(buttons: list[dict], *, message_id: int = 1000, content: str = _GRID_TEXT):
    return SimpleNamespace(
        message_id=message_id,
        is_mudae=True,
        content=content,
        buttons=buttons,
    )


def _reward_snapshot(content: str, *, message_id: int = 2000):
    return SimpleNamespace(
        message_id=message_id,
        is_mudae=True,
        content=content,
        buttons=[],
    )


def test_parse_clicks_allowed():
    assert parse_clicks_allowed(_GRID_TEXT) == 5
    assert parse_clicks_allowed("You can click **3** times") == 3
    assert parse_clicks_allowed("no number here") == 5


def test_total_reward_from_content():
    content = "<:spY:1> **+59**\n<:spB:2> **+14**\n<:spT:3> **+1,200** (Stock: **5**)"
    assert total_reward_from_content(content) == 59 + 14 + 1200


def test_is_oh_grid_message_requires_grid_and_text():
    spheres = [_btn(i, "spU") for i in range(25)]
    assert is_oh_grid_message(_grid_snapshot(spheres)) is True
    # Too few buttons (a roll's lone sphere react) is not a grid.
    assert is_oh_grid_message(_grid_snapshot([_btn(0, "spU")])) is False
    # No grid text.
    assert is_oh_grid_message(_grid_snapshot(spheres, content="something else")) is False
    # Non-mudae author.
    snap = _grid_snapshot(spheres)
    snap.is_mudae = False
    assert is_oh_grid_message(snap) is False


def test_is_oh_reward_message():
    assert is_oh_reward_message(_reward_snapshot("<:spY:1> **+59**")) is True
    assert is_oh_reward_message(_reward_snapshot("plain text")) is False


def test_choose_prefers_value_sphere_over_hidden():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[10]["emoji"] = "spY"  # yellow, clickable
    buttons[12]["emoji"] = "spT"  # teal, skip
    buttons[16]["emoji"] = "spB"  # blue, skip
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spY"
    assert choice["custom_id"] == "cmd s10"


def test_choose_skips_blue_and_teal_clicks_hidden():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[3]["emoji"] = "spB"  # blue, skip
    buttons[7]["emoji"] = "spT"  # teal, skip
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    # No value sphere revealed → must pick a hidden (spU) button.
    assert choice["emoji"] == "spU"


def test_choose_picks_highest_value_rank():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[1]["emoji"] = "spG"  # green, rank 1
    buttons[2]["emoji"] = "spR"  # red, rank 4 (best)
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spR"


def test_choose_returns_none_when_all_disabled():
    buttons = [_btn(i, "spU", disabled=True) for i in range(25)]
    assert choose_oh_click(buttons) is None


def test_choose_on_real_initial_grid_picks_yellow():
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    grid_entry = next(
        e for e in data["entries"] if "buttons below" in (e.get("rawContent") or "").lower()
    )
    buttons = json.loads(grid_entry["rawButtons"])
    choice = choose_oh_click(buttons, rng=random.Random(1))
    assert choice is not None
    # The only revealed value spheres in the opening grid are the two yellows.
    assert choice["emoji"] == "spY"


class _FakeActions:
    def __init__(self, scripted: list) -> None:
        self._scripted = deque(scripted)
        self.sent: list[tuple[str, str | None]] = []
        self.clicks: list[tuple[int, str]] = []
        self.drained = 0

    def drain_queue(self) -> None:
        self.drained += 1

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        self.sent.append((command, prefix))

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        self.clicks.append((message_id, custom_id))
        return True

    async def wait_for(self, predicate, *, timeout: float = 10.0):
        while self._scripted:
            snapshot = self._scripted.popleft()
            if predicate(snapshot, None):
                return snapshot, None
        return None


def test_oh_game_plays_until_clicks_exhausted():
    grid0 = _grid_snapshot(
        [_btn(i, "spY" if i in (10, 19) else "spU") for i in range(25)],
        content="You can click **2** times on the buttons below.",
    )
    grid1 = _grid_snapshot(
        [_btn(i, "spY" if i in (10, 19) else "spU", disabled=(i == 0)) for i in range(25)],
        content="You can click **2** times on the buttons below.",
    )
    grid2 = _grid_snapshot(
        [_btn(i, "spY" if i in (10, 19) else "spU", disabled=(i in (0, 1))) for i in range(25)],
        content="You can click **2** times on the buttons below.",
    )
    scripted = [
        grid0,
        _reward_snapshot("<:spY:1> **+59**"),
        grid1,
        _reward_snapshot("<:spY:1> **+59**\n<:spB:2> **+14**"),
        grid2,
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    logs: list[str] = []

    game = OhSphereGame(
        actions,
        monitor,
        log=logs.append,
        rng=random.Random(0),
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))

    assert actions.sent == [("oh", "$")]
    assert len(actions.clicks) == 2
    assert result["clicks"] == 2
    assert result["reward"] == 59 + 14
    assert monitor.macro_active is False  # restored after play


def test_oh_game_handles_missing_grid():
    actions = _FakeActions([])
    monitor = SimpleNamespace(macro_active=False)
    game = OhSphereGame(actions, monitor, log=lambda _t: None, click_delay=0.0)
    result = asyncio.run(game.play())
    assert result["clicks"] == 0
    assert result["reason"] == "no grid"
