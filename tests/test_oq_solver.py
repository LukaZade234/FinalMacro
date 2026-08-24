"""Tests for the $oq (Orb Quest) sphere minigame solver."""

from __future__ import annotations

from macro.oq_replay import auto_reveal_fourth_purple, reveal_oq_cell
from macro.oq_solver import (
    CLICK_BUDGET,
    DEFAULT_OPENING_CELL,
    choose_oq_click,
    emoji_to_oq_state,
    filter_worlds,
    get_game_state,
    harvest_ranking,
    heuristic_analysis,
    is_paid_reveal,
    locate_mine_candidates_from,
    observations_from_buttons,
    states_from_observations,
)
import macro.oq_worlds as oq_worlds
from macro.oq_worlds import ensure_built


def _btn(index: int, emoji: str = "spU", *, disabled: bool = False) -> dict:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


def _board_from_world(world_index: int) -> dict[int, str]:
    ensure_built()
    outcome = oq_worlds.WORLD_OUTCOMES[world_index]
    mapping = {-1: "t", 0: "0", 1: "1", 2: "2", 3: "3", 4: "4"}
    return {index: mapping[value] for index, value in enumerate(outcome)}


def _simulate_clicks(grid: dict[int, str], *, budget: int = CLICK_BUDGET) -> list[int]:
    obs: dict[int, str] = {}
    clicked: set[int] = set()
    clicks: list[int] = []
    paid = 0
    emoji_of = {
        "t": "spP",
        "r": "sp",
        "0": "spB",
        "1": "spT",
        "2": "spG",
        "3": "spY",
        "4": "spO",
    }
    for _ in range(budget + 4):
        auto_reveal_fourth_purple(grid, obs)
        buttons = [_btn(i, "spU") for i in range(25)]
        for idx, color in obs.items():
            buttons[idx] = _btn(idx, emoji_of[color], disabled=idx in clicked)
        choice = choose_oq_click(
            buttons,
            obs,
            clicks_spent=paid,
            clicks_budget=budget,
        )
        if choice is None:
            break
        index = int(choice["custom_id"].split("s")[1])
        clicks.append(index)
        reveal = reveal_oq_cell(grid, obs, index)
        obs[index] = reveal
        clicked.add(index)
        if is_paid_reveal(reveal):
            paid += 1
        if paid >= budget:
            break
    return clicks


def test_emoji_to_oq_state():
    assert emoji_to_oq_state("spP") == "t"
    assert emoji_to_oq_state("sp") == "r"
    assert emoji_to_oq_state("spR") == "r"
    assert emoji_to_oq_state("spW") == "r"
    assert emoji_to_oq_state("spB") == "0"
    assert emoji_to_oq_state("spT") == "1"
    assert emoji_to_oq_state("spG") == "2"
    assert emoji_to_oq_state("spY") == "3"
    assert emoji_to_oq_state("spO") == "4"
    assert emoji_to_oq_state("spU") is None


def test_observations_from_red_sp_emoji():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[15] = _btn(15, "sp")
    assert observations_from_buttons(buttons) == {15: "r"}


def test_observations_from_rainbow_spw_emoji():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[15] = _btn(15, "spW")
    assert observations_from_buttons(buttons) == {15: "r"}


def test_filter_worlds_empty_board():
    ensure_built()
    valid = filter_worlds(states_from_observations({}))
    assert len(valid) == len(oq_worlds.ALL_WORLDS) == 12_650


def test_opening_cell_is_colblitz_inner():
    assert DEFAULT_OPENING_CELL == 6
    buttons = [_btn(i) for i in range(25)]
    choice = choose_oq_click(buttons, {})
    assert choice is not None
    assert choice["custom_id"] == f"cmd s{DEFAULT_OPENING_CELL}"


def test_purple_reveal_is_free():
    assert is_paid_reveal("t") is False
    assert is_paid_reveal("0") is True
    assert is_paid_reveal("r") is True


def test_observations_from_buttons():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[7] = _btn(7, "spT", disabled=True)
    obs = observations_from_buttons(buttons)
    assert obs == {7: "1"}


def test_blue_observation_narrows_worlds():
    obs = {DEFAULT_OPENING_CELL: "0"}
    valid = filter_worlds(states_from_observations(obs))
    assert 0 < len(valid) < 12_650


def test_solver_finds_three_purples_on_sample_board():
    ensure_built()
    grid = _board_from_world(0)
    purples = {index for index, color in grid.items() if color == "t"}
    clicks = _simulate_clicks(grid)
    found = [index for index in clicks if grid[index] == "t"]
    assert len(found) == 4
    assert found[:3]  # three purples first, then the auto-red 4th
    assert set(found) == purples


def test_choose_does_not_search_when_three_purples_and_no_red():
    """The 4th becomes visible red on the grid — do not probe hidden cells."""
    buttons = [_btn(i) for i in range(25)]
    for index in (0, 5, 10):
        buttons[index] = _btn(index, "spP", disabled=True)
    obs = {0: "t", 5: "t", 10: "t"}
    choice = choose_oq_click(buttons, obs, clicks_spent=4, clicks_budget=CLICK_BUDGET)
    assert choice is None


def test_choose_clickable_revealed_red():
    """After the 4th purple becomes red on the grid, click the revealed ``sp``."""
    buttons = [_btn(i, "spU") for i in range(25)]
    for index in (0, 5, 10):
        buttons[index] = _btn(index, "spP", disabled=True)
    buttons[15] = _btn(15, "sp")  # spawned red, still clickable
    obs = {0: "t", 5: "t", 10: "t", 15: "r"}
    choice = choose_oq_click(buttons, obs, clicks_spent=5, clicks_budget=CLICK_BUDGET)
    assert choice is not None
    assert choice["custom_id"] == "cmd s15"


def test_choose_clickable_revealed_rainbow():
    """When the 4th purple becomes rainbow instead of red, claim ``spW`` first."""
    buttons = [_btn(i, "spU") for i in range(25)]
    for index in (0, 5, 10):
        buttons[index] = _btn(index, "spP", disabled=True)
    buttons[15] = _btn(15, "spW")  # spawned rainbow, still clickable
    obs = {0: "t", 5: "t", 10: "t", 15: "r"}
    choice = choose_oq_click(buttons, obs, clicks_spent=5, clicks_budget=CLICK_BUDGET)
    assert choice is not None
    assert choice["custom_id"] == "cmd s15"


def test_revealed_red_before_harvest_cells():
    """Red must be collected before opening hidden harvest orbs."""
    buttons = [_btn(i, "spU") for i in range(25)]
    for index in (0, 5, 10):
        buttons[index] = _btn(index, "spP", disabled=True)
    buttons[15] = _btn(15, "sp")
    obs = {0: "t", 5: "t", 10: "t", 15: "r", 1: "0", 2: "1"}
    choice = choose_oq_click(buttons, obs, clicks_spent=4, clicks_budget=CLICK_BUDGET)
    assert choice is not None
    assert choice["custom_id"] == "cmd s15"


def test_revealed_rainbow_before_harvest_cells():
    """Rainbow must be collected before opening hidden harvest orbs."""
    buttons = [_btn(i, "spU") for i in range(25)]
    for index in (0, 5, 10):
        buttons[index] = _btn(index, "spP", disabled=True)
    buttons[15] = _btn(15, "spW")
    obs = {0: "t", 5: "t", 10: "t", 15: "r", 1: "0", 2: "1"}
    choice = choose_oq_click(buttons, obs, clicks_spent=4, clicks_budget=CLICK_BUDGET)
    assert choice is not None
    assert choice["custom_id"] == "cmd s15"


def test_harvest_prefers_most_adjacent_mines():
    """Rank hidden cells by purple+red neighbours (user example pattern)."""
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[0] = _btn(0, "spP", disabled=True)
    buttons[6] = _btn(6, "spP", disabled=True)
    buttons[24] = _btn(24, "spP", disabled=True)
    buttons[11] = _btn(11, "sp", disabled=True)  # red below-left of center
    obs = {0: "t", 6: "t", 24: "t", 11: "r"}
    ranking = harvest_ranking(buttons, obs)
    top_adj, _payout, top_cell = ranking[0]
    assert top_adj >= 2
    choice = choose_oq_click(buttons, obs, clicks_spent=3, clicks_budget=CLICK_BUDGET)
    assert choice is not None
    assert choice["custom_id"] == f"cmd s{top_cell}"


def test_harvest_counts_rainbow_as_mine():
    """Rainbow on the grid counts toward harvest adjacency like red."""
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[0] = _btn(0, "spP", disabled=True)
    buttons[6] = _btn(6, "spP", disabled=True)
    buttons[24] = _btn(24, "spP", disabled=True)
    buttons[11] = _btn(11, "spW", disabled=True)  # rainbow below-left of center
    obs = {0: "t", 6: "t", 24: "t", 11: "r"}
    ranking = harvest_ranking(buttons, obs)
    top_adj, _payout, top_cell = ranking[0]
    assert top_adj >= 2
    choice = choose_oq_click(buttons, obs, clicks_spent=3, clicks_budget=CLICK_BUDGET)
    assert choice is not None
    assert choice["custom_id"] == f"cmd s{top_cell}"


def test_game_state_red_visible_is_not_a_spent_click():
    obs = {0: "t", 5: "t", 10: "t", 15: "r", 1: "0", 2: "1"}
    phase, clicks, targets = get_game_state(states_from_observations(obs))
    assert phase.value == "bonus_harvest"
    assert targets == 3
    assert clicks == 2


def test_heuristic_last_click_uses_paid_remain_not_board_size():
    """Passing remaining paid clicks must not collapse to last-click early."""
    ensure_built()
    states = ["?"] * 25
    states[0] = states[5] = states[10] = "t"
    valid = filter_worlds(states)
    allowed = locate_mine_candidates_from(valid, states)
    _cell, reason = heuristic_analysis(
        valid, states, clicks_remain=3, allowed=allowed
    )
    assert not reason.startswith("last click")
    _cell, last = heuristic_analysis(
        valid, states, clicks_remain=1, allowed=allowed
    )
    assert last.startswith("last click")
