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
    session = result["session"]
    assert session["game"] == "oq"
    assert session["clicks"][0]["cell"] == DEFAULT_OPENING_CELL
    assert session["clicks"][0]["emoji"] == "spT"
    assert session["clicks"][0]["base_sp"] == 20


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


def test_oq_game_claims_rainbow_then_harvests():
    """Rainbow replaces red; macro must claim it then keep harvesting."""
    grid0 = _grid_snapshot([_btn(i) for i in range(25)])
    # Three purples found; rainbow spawned at 15, still clickable.
    grid1 = [_btn(i, "spU") for i in range(25)]
    for index in (0, 5, 10):
        grid1[index] = _btn(index, "spP", disabled=True)
    grid1[15] = _btn(15, "spW")
    grid1_snap = _grid_snapshot(grid1)
    # After claiming rainbow, one hidden harvest cell at 16.
    grid2 = [_btn(i, "spU") for i in range(25)]
    for index in (0, 5, 10, 15):
        grid2[index] = _btn(index, "spP" if index != 15 else "spW", disabled=True)
    grid2[16] = _btn(16, "spY")
    grid2_snap = _grid_snapshot(grid2)
    scripted = [
        grid0,
        _reward_snapshot("<:spT:1> **+20**"),
        grid1_snap,
        _reward_snapshot("<:spT:1> **+20**\n<:spW:2> **+500**"),
        grid2_snap,
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    clicks: list[str] = []

    async def track_click(message_id: int, custom_id: str) -> bool:
        clicks.append(custom_id)
        return True

    actions.click_button = track_click  # type: ignore[method-assign]
    game = OqSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))

    assert f"cmd s{DEFAULT_OPENING_CELL}" in clicks
    assert "cmd s15" in clicks  # rainbow claimed
    assert result["clicks"] >= 2


def test_oq_game_waits_for_auto_revealed_red():
    """After 3 purples, wait for Mudae's red edit instead of probing hidden cells."""
    grid0 = _grid_snapshot([_btn(i) for i in range(25)])
    after_opening = [_btn(i, "spU") for i in range(25)]
    after_opening[DEFAULT_OPENING_CELL] = _btn(DEFAULT_OPENING_CELL, "spT", disabled=True)
    for index in (0, 5, 10):
        after_opening[index] = _btn(index, "spP", disabled=True)
    after_opening_snap = _grid_snapshot(after_opening)

    with_red = [_btn(i, "spU") for i in range(25)]
    with_red[DEFAULT_OPENING_CELL] = _btn(DEFAULT_OPENING_CELL, "spT", disabled=True)
    for index in (0, 5, 10):
        with_red[index] = _btn(index, "spP", disabled=True)
    with_red[15] = _btn(15, "sp")
    with_red_snap = _grid_snapshot(with_red)

    claimed = [_btn(i, "spU") for i in range(25)]
    claimed[DEFAULT_OPENING_CELL] = _btn(DEFAULT_OPENING_CELL, "spT", disabled=True)
    for index in (0, 5, 10):
        claimed[index] = _btn(index, "spP", disabled=True)
    claimed[15] = _btn(15, "sp", disabled=True)
    claimed_snap = _grid_snapshot(claimed)

    scripted = [
        grid0,
        _reward_snapshot("<:spT:1> **+20**"),
        after_opening_snap,
        with_red_snap,
        _reward_snapshot("<:spT:1> **+20**\n<:sp:2> **+150**"),
        claimed_snap,
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    clicks: list[str] = []

    async def track_click(message_id: int, custom_id: str) -> bool:
        clicks.append(custom_id)
        return True

    actions.click_button = track_click  # type: ignore[method-assign]
    game = OqSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))

    assert clicks[0] == f"cmd s{DEFAULT_OPENING_CELL}"
    assert clicks[1] == "cmd s15"
    assert result["clicks"] >= 2


def test_oq_game_handles_exhausted_uses():
    snap = SimpleNamespace(
        message_id=9,
        is_mudae=True,
        content=(
            "You don't have enough $oq for today. "
            "Time to wait before the refill: 3h 08 min."
        ),
        buttons=[],
    )
    logs: list[str] = []
    actions = _FakeActions([snap])
    monitor = SimpleNamespace(macro_active=False)
    game = OqSphereGame(actions, monitor, log=logs.append, click_delay=0.0)
    result = asyncio.run(game.play())
    assert result["reason"] == "exhausted"
    assert result["game"] == "oq"
    assert result["refill_minutes"] == 188
    assert any("out of minigames for today" in line for line in logs)
