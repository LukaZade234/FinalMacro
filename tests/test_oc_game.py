"""Tests for the $oc sphere deduction minigame."""

from __future__ import annotations

import asyncio
import random
from collections import deque
from types import SimpleNamespace

from macro.oc_game import OcSphereGame, is_oc_grid_message
from macro.oc_solver import (
    CENTER_INDEX,
    OPENING_CELL_INDEX,
    _SECOND_PROBE_INDEX,
    choose_oc_click,
    constraint_red_candidates,
    emoji_to_oc_color,
    filter_boards,
    observations_from_buttons,
    red_information_gain,
)

_OC_GRID_TEXT = (
    "You can click **5** times on the buttons below (2 minutes).\n"
    "**1 red sphere** to find (never at the center) along with **2 orange** "
    "(always next to the red sphere), **3 yellow** (always diagonal to the red "
    "sphere), **4 green** (in the same row or column as red), **teal** (in the "
    "same row, column or diagonal as red) and **blue** (NEVER in the same row, "
    "column nor diagonal from red).\n"
)

# User session board — red at (2, 4) → index 8.
_RED_AT_8 = {
    0: "B", 1: "B", 2: "T", 3: "O", 4: "Y",
    5: "G", 6: "G", 7: "G", 8: "R", 9: "T",
    10: "B", 11: "B", 12: "Y", 13: "O", 14: "Y",
    15: "B", 16: "T", 17: "B", 18: "T", 19: "B",
    20: "T", 21: "B", 22: "B", 23: "G", 24: "B",
}

# User session board — red at (1, 1) → index 0 (from attached screenshot).
_RED_AT_0 = {
    0: "R", 1: "O", 2: "G", 3: "B", 4: "G",
    5: "O", 6: "Y", 7: "B", 8: "B", 9: "B",
    10: "B", 11: "B", 12: "B", 13: "B", 14: "B",
    15: "G", 16: "B", 17: "B", 18: "Y", 19: "B",
    20: "G", 21: "B", 22: "B", 23: "B", 24: "Y",
}


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
        content=_OC_GRID_TEXT,
        buttons=buttons,
    )


def _reward_snapshot(content: str, *, message_id: int = 6000):
    return SimpleNamespace(
        message_id=message_id,
        is_mudae=True,
        content=content,
        buttons=[],
    )


def _simulate_clicks(grid: dict[int, str], *, budget: int = 5) -> list[int]:
    obs: dict[int, str] = {}
    clicks: list[int] = []
    for _ in range(budget):
        buttons = [_btn(i, "spU") for i in range(25)]
        for idx, color in obs.items():
            emoji = {
                "R": "sp", "O": "spO", "Y": "spY", "G": "spG", "T": "spT", "B": "spB",
            }[color]
            buttons[idx] = _btn(idx, emoji, disabled=True)
        choice = choose_oc_click(buttons, obs, clicks_spent=len(clicks), clicks_budget=budget)
        if choice is None:
            break
        index = int(choice["custom_id"].split("s")[1])
        clicks.append(index)
        obs[index] = grid[index]
    return clicks


def test_is_oc_grid_message():
    buttons = [_btn(i) for i in range(25)]
    assert is_oc_grid_message(_grid_snapshot(buttons)) is True
    snap = _grid_snapshot(buttons)
    snap.content = (
        "You can click **5** times on the buttons below.\n"
        "Spheres buttons have different values depending on their color."
    )
    assert is_oc_grid_message(snap) is False


def test_emoji_to_oc_color():
    assert emoji_to_oc_color("sp") == "R"
    assert emoji_to_oc_color("spY") == "Y"
    assert emoji_to_oc_color("spU") is None


def test_red_at_8_still_viable_red_position():
    assert 8 in constraint_red_candidates({})


def test_red_at_0_still_viable_red_position():
    assert 0 in constraint_red_candidates({})


def test_teal_observations_compatible_with_red_at_8():
    obs = {16: "T", 20: "T"}
    assert 8 in constraint_red_candidates(obs)


def test_two_blue_probes_narrow_to_corners():
    obs = {OPENING_CELL_INDEX: "B", _SECOND_PROBE_INDEX: "B"}
    reds = constraint_red_candidates(obs)
    assert reds == [0, 24]


def test_green_and_orange_pin_red_at_corner():
    obs = {OPENING_CELL_INDEX: "B", 15: "G", 5: "O"}
    assert constraint_red_candidates(obs) == [0]


def test_opening_cell_is_4_2():
    assert OPENING_CELL_INDEX == 16
    buttons = [_btn(i) for i in range(25)]
    choice = choose_oc_click(buttons, {}, rng=random.Random(0))
    assert choice is not None
    assert choice["custom_id"] == f"cmd s{OPENING_CELL_INDEX}"


def test_second_probe_after_opening():
    buttons = [_btn(i) for i in range(25)]
    obs = {OPENING_CELL_INDEX: "B"}
    choice = choose_oc_click(buttons, obs, rng=random.Random(0))
    assert choice is not None
    assert choice["custom_id"] == f"cmd s{_SECOND_PROBE_INDEX}"


def test_second_probe_after_teal_opening():
    buttons = [_btn(i) for i in range(25)]
    obs = {OPENING_CELL_INDEX: "T"}
    choice = choose_oc_click(buttons, obs, rng=random.Random(0))
    assert choice is not None
    index = int(choice["custom_id"].split("s")[1])
    assert index != _SECOND_PROBE_INDEX
    assert index != OPENING_CELL_INDEX


def test_after_two_blues_clicks_red_candidate():
    buttons = [_btn(i) for i in range(25)]
    obs = {OPENING_CELL_INDEX: "B", _SECOND_PROBE_INDEX: "B"}
    choice = choose_oc_click(buttons, obs, rng=random.Random(0))
    assert choice is not None
    assert choice["custom_id"] in {"cmd s0", "cmd s24"}


def test_after_orange_opening_clicks_red_candidate_not_corner():
    """Orange at (4,2) → red is adjacent; must not waste clicks on blue corners."""
    buttons = [_btn(i) for i in range(25)]
    obs = {16: "O"}
    choice = choose_oc_click(buttons, obs, rng=random.Random(0))
    assert choice is not None
    assert choice["custom_id"] in {"cmd s11", "cmd s15", "cmd s17", "cmd s21"}
    assert choice["custom_id"] not in {"cmd s0", "cmd s4", "cmd s20", "cmd s24"}


def test_collect_skips_ortho_after_two_oranges():
    """Once both oranges beside red are found, target yellows not extra ortho cells."""
    obs = {8: "R", 3: "O", 13: "O"}
    buttons = [_btn(i, "spU") for i in range(25)]
    for idx, color in obs.items():
        emoji = {"R": "sp", "O": "spO"}[color]
        buttons[idx] = _btn(idx, emoji, disabled=True)
    choice = choose_oc_click(buttons, obs, clicks_spent=3, clicks_budget=5)
    assert choice is not None
    index = int(choice["custom_id"].split("s")[1])
    assert index not in {7, 9}  # remaining ortho neighbours of red at (2, 4)
    assert index in {2, 4, 14, 15, 19, 20}  # diagonal-line cells from red


def test_collect_gets_second_orange_before_yellow():
    obs = {0: "R", 1: "O"}
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[0] = _btn(0, "sp", disabled=True)
    buttons[1] = _btn(1, "spO", disabled=True)
    choice = choose_oc_click(buttons, obs, clicks_spent=2, clicks_budget=5)
    assert choice is not None
    assert choice["custom_id"] == "cmd s5"  # second orange ortho neighbour


def test_mudae_helper_sequence_red_at_0():
    """Match public solver: (4,2) B → (2,4) B → (1,1) R → oranges → yellow."""
    clicks = _simulate_clicks(_RED_AT_0)
    assert clicks[0] == OPENING_CELL_INDEX
    assert clicks[1] == _SECOND_PROBE_INDEX
    assert clicks[2] == 0
    assert 0 in clicks[:3]
    assert 1 in clicks or 5 in clicks  # orange neighbours after red


def test_red_at_8_board_finds_red_within_budget():
    clicks = _simulate_clicks(_RED_AT_8)
    assert 8 in clicks


def test_red_information_gain_positive_for_unknown_cell():
    assert red_information_gain(0, {}) > 0


def test_filter_boards_returns_red_candidates():
    boards = filter_boards({})
    assert len(boards) == 24


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


def test_oc_game_plays_one_click():
    one_click_text = (
        "You can click **1** times on the buttons below (2 minutes).\n"
        "**1 red sphere** to find (never at the center) along with **2 orange** "
        "(always next to the red sphere), **3 yellow** (always diagonal to the red "
        "sphere), **4 green** (in the same row or column as red), **teal** (in the "
        "same row, column or diagonal as red) and **blue** (NEVER in the same row, "
        "column nor diagonal from red).\n"
    )
    grid0 = _grid_snapshot([_btn(i) for i in range(25)])
    grid0.content = one_click_text
    grid1 = [_btn(16, "spT", disabled=True)] + [_btn(i) for i in range(25) if i != 16]
    grid1_snap = _grid_snapshot(grid1)
    grid1_snap.content = one_click_text
    scripted = [
        grid0,
        _reward_snapshot("<:spT:1> **+24**"),
        grid1_snap,
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    game = OcSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        rng=random.Random(0),
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))
    assert result["clicks"] == 1
    assert actions.clicks[0][1] == f"cmd s{OPENING_CELL_INDEX}"
    assert CENTER_INDEX == 12


def test_oc_game_handles_exhausted_uses():
    snap = SimpleNamespace(
        message_id=9,
        is_mudae=True,
        content=(
            "You don't have enough $oc for today. "
            "Time to wait before the refill: 3h 08 min."
        ),
        buttons=[],
    )
    logs: list[str] = []
    actions = _FakeActions([snap])
    monitor = SimpleNamespace(macro_active=False)
    game = OcSphereGame(actions, monitor, log=logs.append, click_delay=0.0)
    result = asyncio.run(game.play())
    assert result["reason"] == "exhausted"
    assert result["game"] == "oc"
    assert result["refill_minutes"] == 188
    assert any("out of minigames for today" in line for line in logs)
