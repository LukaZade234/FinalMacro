"""Tests for the $oq sphere minigame game loop."""

from __future__ import annotations

import asyncio
import random
from collections import deque
from types import SimpleNamespace

from macro.oq_game import OqSphereGame, is_oq_grid_message
from macro.oq_solver import DEFAULT_OPENING_CELL

_OQ_GRID_TEXT = (
    "You can click **7** times on the buttons below (2 minutes).\n"
    "Find **3 purple spheres** (out of 4) to turn the 4th purple into a red "
    "sphere or more.\n"
)


def _btn(index: int, emoji: str = "spU", *, disabled: bool = False) -> dict:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


def _grid_snapshot(buttons: list[dict], *, message_id: int = 5000):
    return SimpleNamespace(
        message_id=message_id,
        is_mudae=True,
        content=_OQ_GRID_TEXT,
        buttons=buttons,
    )


def _reward_snapshot(content: str, *, message_id: int = 6000):
    return SimpleNamespace(
        message_id=message_id,
        is_mudae=True,
        content=content,
        buttons=[],
    )


def test_is_oq_grid_message():
    buttons = [_btn(i) for i in range(25)]
    assert is_oq_grid_message(_grid_snapshot(buttons)) is True
    snap = _grid_snapshot(buttons)
    snap.content = (
        "You can click **5** times on the buttons below.\n"
        "Spheres buttons have different values depending on their color."
    )
    assert is_oq_grid_message(snap) is False


class _FakeActions:
    def __init__(self, scripted: list) -> None:
        self._scripted = deque(scripted)
        self.clicks: list[tuple[int, str]] = []

    def drain_queue(self) -> None:
        return None

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        self.command = (command, prefix)

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        self.clicks.append((message_id, custom_id))
        return True

    async def wait_for(self, predicate, *, timeout: float = 10.0):
        while self._scripted:
            snapshot = self._scripted.popleft()
            if predicate(snapshot, None):
                return snapshot, None
        return None


def test_oq_game_plays_one_paid_click():
    grid0 = _grid_snapshot([_btn(i) for i in range(25)])
    grid1 = [_btn(7, "spT", disabled=True)] + [_btn(i) for i in range(25) if i != 7]
    grid1_snap = _grid_snapshot(grid1)
    scripted = [
        grid0,
        _reward_snapshot("<:spT:1> **+20**"),
        grid1_snap,
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    game = OqSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        rng=random.Random(0),
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))
    assert result["clicks"] == 1
    assert actions.clicks[0][1] == f"cmd s{DEFAULT_OPENING_CELL}"


def test_oq_game_purple_click_does_not_spend_budget():
    grid0 = _grid_snapshot([_btn(i) for i in range(25)])
    grid1 = [_btn(7, "spP", disabled=True)] + [_btn(i) for i in range(25) if i != 7]
    grid1_snap = _grid_snapshot(grid1)
    scripted = [
        grid0,
        _reward_snapshot("<:spP:1> **+42**"),
        grid1_snap,
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    game = OqSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))
    assert result["clicks"] == 0
