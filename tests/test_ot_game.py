"""The ``$ot`` game loop, driven against a fake Mudae that answers clicks.

A scripted deque cannot test this loop: which cells get clicked depends on what
the solver deduces, so the fake has to *respond* — reveal the clicked cell,
edit the grid, and post a reward line — exactly as Mudae does.
"""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace

import pytest

from macro.minigame_board import GRID_CELLS
from macro.ot_game import OtSphereGame, is_ot_grid_message, is_ot_game_over
from macro.ot_replay import KNOWN_BOARDS, ship_sp
from macro.ot_solver import OT_CELL_SP

GRID_TEXT = (
    "You can click 4 times on the buttons below (2 minutes).\n"
    "All colors are free (they don't consume clicks) except for the blue spheres\n"
    "Identical colors follow one another on the same row or column. For example, "
    "there is a line or a column having ALL the green spheres following one another.\n"
    "Spheres to find: teal = 4, green = 3, yellow = 3, rarer spheres = 2.\n"
    "\n"
    "Number of different colors: 6\n"
)

_LETTER_TO_EMOJI = {
    "B": "spB", "T": "spT", "G": "spG", "Y": "spY", "O": "spO",
    "L": "spL", "D": "spD", "R": "spR", "W": "spW",
}
_GRID_ID = 4242


def _btn(index: int, emoji: str = "spU", *, disabled: bool = False) -> dict:
    return {
        "label": "",
        "emoji": emoji,
        "custom_id": f"cmd s{index}",
        "kind": "sphere",
        "disabled": disabled,
    }


class _FakeMudae:
    """Answers clicks against a hidden board, the way the real bot does."""

    def __init__(self, cells: str, *, budget: int = 4, colours: int | None = None):
        self.cells = cells
        self.budget = budget
        self.revealed: dict[int, str] = {}
        self.blues = 0
        self.clicks: list[int] = []
        self.reward_lines: list[str] = []
        self.command: tuple[str, str | None] | None = None
        self.over = False
        self._colours = colours if colours is not None else len(set(cells))
        self._queue: deque = deque([self._grid()])

    # --- what the player sees ---
    def _buttons(self) -> list[dict]:
        return [
            _btn(index, _LETTER_TO_EMOJI[self.revealed[index]], disabled=True)
            if index in self.revealed
            else _btn(index, disabled=self.over)
            for index in range(GRID_CELLS)
        ]

    def _grid(self):
        text = GRID_TEXT.replace(
            "Number of different colors: 6",
            f"Number of different colors: {self._colours}",
        ).replace("click 4 times", f"click {self.budget} times")
        return SimpleNamespace(
            message_id=_GRID_ID, is_mudae=True, content=text, buttons=self._buttons()
        )

    def _reward(self, colour: str):
        """Mudae keeps ONE reward message and appends a line per click.

        The loop's helpers diff that growing list, so a fake that replaced the
        content each time would hand them nothing and quietly skip the
        light/dark handling this file exists to test.
        """
        # Light pays out as a bundle of *other* colours, which is exactly the
        # trap the loop has to avoid reading as the cell's own identity.
        if colour == "L":
            line = "<:spL:1> breaks down into <:spB:1> + <:spY:1> => **+65**"
        elif colour == "D":
            line = "<:spD:1> turns into <:spO:1> **+90**"
        else:
            line = f"<:{_LETTER_TO_EMOJI[colour]}:1> **+{int(OT_CELL_SP[colour])}**"
        self.reward_lines.append(line)
        return SimpleNamespace(
            message_id=9000,
            is_mudae=True,
            content="\n".join(self.reward_lines),
            buttons=[],
        )

    # --- the actions interface the game uses ---
    def drain_queue(self) -> None:
        return None

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        self.command = (command, prefix)

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        index = int(str(custom_id).split("s")[1])
        colour = self.cells[index]
        self.clicks.append(index)
        self.revealed[index] = colour
        if colour == "B":
            self.blues += 1
            if self.blues >= self.budget:
                self.over = True
                self.revealed = {i: c for i, c in enumerate(self.cells)}
        self._queue.append(self._reward(colour))
        self._queue.append(self._grid())
        return True

    async def wait_for(self, predicate, *, timeout: float = 10.0):
        while self._queue:
            snapshot = self._queue.popleft()
            if predicate(snapshot, None):
                return snapshot, None
        return None


def _play(cells: str, **kwargs) -> tuple[dict, _FakeMudae, list[str]]:
    mudae = _FakeMudae(cells, **kwargs)
    logs: list[str] = []
    game = OtSphereGame(
        mudae,
        SimpleNamespace(macro_active=False),
        log=logs.append,
        click_delay=0.0,
    )
    return asyncio.run(game.play(prefix="$")), mudae, logs


# --- Grid detection ---------------------------------------------------------


def test_is_ot_grid_message():
    buttons = [_btn(i) for i in range(GRID_CELLS)]
    grid = SimpleNamespace(
        message_id=1, is_mudae=True, content=GRID_TEXT, buttons=buttons
    )
    assert is_ot_grid_message(grid) is True

    # An $oc grid must not be mistaken for one.
    oc = SimpleNamespace(
        message_id=2,
        is_mudae=True,
        content="**1 red sphere** to find. Click the buttons below.",
        buttons=buttons,
    )
    assert is_ot_grid_message(oc) is False
    # Nor a lone sphere react button on a roll.
    assert is_ot_grid_message(
        SimpleNamespace(message_id=3, is_mudae=True, content=GRID_TEXT, buttons=[_btn(0)])
    ) is False


def test_is_ot_game_over():
    buttons = [_btn(i) for i in range(GRID_CELLS)]
    assert is_ot_game_over(buttons) is False
    assert is_ot_game_over([dict(b, disabled=True) for b in buttons]) is True


# --- Playing ----------------------------------------------------------------


@pytest.mark.parametrize("entry", KNOWN_BOARDS, ids=lambda e: e["name"])
def test_the_loop_plays_a_real_board_to_the_end(entry):
    cells = entry["cells"]
    result, mudae, _logs = _play(cells)

    assert result["reason"] == "done"
    assert mudae.command == ("ot", "$")
    # Only blue costs a click, so a good game clicks far more than its budget.
    assert result["clicks_paid"] == mudae.blues <= 4
    assert result["clicks"] == len(mudae.clicks) > result["clicks_paid"]
    assert len(set(mudae.clicks)) == len(mudae.clicks), "clicked a cell twice"


@pytest.mark.parametrize("entry", KNOWN_BOARDS, ids=lambda e: e["name"])
def test_the_session_row_matches_what_was_actually_clicked(entry):
    cells = entry["cells"]
    result, mudae, _logs = _play(cells)
    session = result["session"]

    assert session["game"] == "ot"
    assert session["clicks_budget"] == 4
    assert session["clicks_paid"] == mudae.blues
    assert [click["cell"] for click in session["clicks"]] == mudae.clicks
    # Blue clicks are the paid ones; every ship cell is free.
    for click in session["clicks"]:
        assert click["paid"] is (cells[click["cell"]] == "B")
    assert session["board"] == [_LETTER_TO_EMOJI[c] for c in cells]


@pytest.mark.parametrize("entry", KNOWN_BOARDS, ids=lambda e: e["name"])
def test_every_click_is_logged_as_the_cell_it_actually_hit(entry):
    """The trap: light and dark pay out in *other* colours.

    Light's reward line reads "breaks down into blue + yellow". Taking that as
    the cell's identity would tell the solver a light ship was blue, corrupting
    both the deduction and the click budget. The grid, not the reward line, is
    the authority — this asserts it for every cell of every real board.
    """
    cells = entry["cells"]
    result, mudae, _logs = _play(cells)
    for click in result["session"]["clicks"]:
        assert click["emoji"] == _LETTER_TO_EMOJI[cells[click["cell"]]]
    assert mudae.blues == result["clicks_paid"]


def test_a_transforming_ship_keeps_its_own_identity_and_its_payout():
    """Light on a board the solver actually finishes."""
    cells = KNOWN_BOARDS[5]["cells"]  # log-1: light at 23 and 24
    result, _mudae, _logs = _play(cells)

    light = [c for c in result["session"]["clicks"] if cells[c["cell"]] == "L"]
    assert light, "the solver never reached the light ship"
    for click in light:
        assert click["emoji"] == "spL"
        assert click["paid"] is False
        assert click["resolved"], "the payout colours were dropped"


def test_the_solver_beats_the_hand_played_score_through_the_real_loop():
    """End to end, not just in the replay harness."""
    for entry in KNOWN_BOARDS:
        if entry["logged_sp"] is None:
            continue
        result, _mudae, _logs = _play(entry["cells"])
        scored = sum(
            OT_CELL_SP[entry["cells"][click["cell"]]]
            for click in result["session"]["clicks"]
        )
        assert scored > entry["logged_sp"], entry["name"]
        assert scored <= ship_sp(entry["cells"]) + 4 * OT_CELL_SP["B"]


def test_the_log_reports_the_fleet_and_the_blue_budget():
    _result, _mudae, logs = _play(KNOWN_BOARDS[0]["cells"])
    opening = next(line for line in logs if "grid ready" in line)
    assert "6 colours" in opening
    assert "11 blue cells" in opening
    assert "4 blue clicks" in opening
    assert any("blue 1/4" in line for line in logs)


# --- Failure paths ----------------------------------------------------------


def test_out_of_uses_is_reported_as_exhausted():
    snap = SimpleNamespace(
        message_id=9,
        is_mudae=True,
        content=(
            "You don't have enough $ot for today. "
            "Time to wait before the refill: 3h 08 min."
        ),
        buttons=[],
    )

    class _OneShot(_FakeMudae):
        def __init__(self):
            super().__init__("B" * GRID_CELLS)
            self._queue = deque([snap])

    logs: list[str] = []
    game = OtSphereGame(
        _OneShot(), SimpleNamespace(macro_active=False), log=logs.append, click_delay=0.0
    )
    result = asyncio.run(game.play())
    assert result["reason"] == "exhausted"
    assert result["game"] == "ot"
    assert result["refill_minutes"] == 188


def test_an_unreadable_fleet_stops_instead_of_guessing():
    """No colour count means no fleet, and no fleet means nothing to solve."""
    buttons = [_btn(i) for i in range(GRID_CELLS)]
    broken = SimpleNamespace(
        message_id=_GRID_ID,
        is_mudae=True,
        content="Spheres to find: teal = 4, green = 3, yellow = 3.\n",
        buttons=buttons,
    )

    class _Broken(_FakeMudae):
        def __init__(self):
            super().__init__("B" * GRID_CELLS)
            self._queue = deque([broken])

    mudae = _Broken()
    logs: list[str] = []
    game = OtSphereGame(
        mudae, SimpleNamespace(macro_active=False), log=logs.append, click_delay=0.0
    )
    result = asyncio.run(game.play())
    assert result["reason"] == "no fleet"
    assert not mudae.clicks
    assert any("could not read the fleet" in line for line in logs)


def test_a_missing_grid_times_out_cleanly():
    class _Silent(_FakeMudae):
        def __init__(self):
            super().__init__("B" * GRID_CELLS)
            self._queue = deque()

    mudae = _Silent()
    game = OtSphereGame(
        mudae, SimpleNamespace(macro_active=False), log=lambda _t: None, click_delay=0.0
    )
    result = asyncio.run(game.play())
    assert result["reason"] == "no grid"
    assert not mudae.clicks


def test_the_macro_activity_flag_is_released_afterwards():
    monitor = SimpleNamespace(macro_active=False)
    game = OtSphereGame(
        _FakeMudae(KNOWN_BOARDS[0]["cells"]),
        monitor,
        log=lambda _t: None,
        click_delay=0.0,
    )
    asyncio.run(game.play())
    assert monitor.macro_active is False


# --- Manual only ------------------------------------------------------------
#
# $ot is wired to a button and nothing else: it must not run inside play-all,
# and it must not start itself when the daily uses refill. These pin that.


def test_ot_is_not_a_self_playing_minigame():
    """The daily loop plays only what is in PLAYABLE_MINIGAMES."""
    from macro.minigame_daily import PLAYABLE_MINIGAMES

    assert "ot" not in PLAYABLE_MINIGAMES
    assert set(PLAYABLE_MINIGAMES) == {"oh", "oc", "oq"}


def test_play_all_never_reaches_for_the_ot_game():
    """Play-all counts $ot uses but has no way to spend them."""
    import macro.minigames as minigames

    assert not hasattr(minigames, "OtSphereGame")
    source = __import__("inspect").getsource(minigames.PlayAllMinigames.play)
    assert "OtSphereGame" not in source


def test_the_bridge_treats_a_running_ot_as_minigame_busy():
    """Otherwise Start, play-all or another minigame could land on top of it."""
    from gui.bridge import AppBridge

    bridge = AppBridge()
    assert bridge._minigames_busy() is False
    bridge._ot_running = True
    try:
        assert bridge._minigames_busy() is True
        assert bridge._manual_minigame_blocked_status(game="oh")
        assert bridge._manual_minigame_blocked_status(game=None)
    finally:
        bridge._ot_running = False


def test_play_ot_refuses_before_connecting():
    from gui.bridge import AppBridge

    bridge = AppBridge()
    bridge.playOtSphere()
    assert bridge._ot_running is False
