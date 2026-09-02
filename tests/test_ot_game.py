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
from macro.ot_game import (
    _MAX_ACK_RECOVERIES,
    OtSphereGame,
    is_ot_game_over,
    is_ot_grid_message,
)
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

    def __init__(
        self,
        cells: str,
        *,
        budget: int = 4,
        colours: int | None = None,
        extra_chance: bool = True,
    ):
        self.cells = cells
        self.budget = budget
        # Extra Chance: a blue only ends the board once this many ship cells
        # have been clicked. `False` replays the pre-2026-08-30 reading.
        self.extra_chance = extra_chance
        self.extra_chance_hits = 5
        self.revealed: dict[int, str] = {}
        self.blues = 0
        self.hits = 0
        self.extras = 0
        # Refuse the Nth click *attempt* (1-based), the way an exhausted retry
        # does. With `fail_forever`, every attempt from there on is refused.
        # Counting attempts rather than successes matters: a refusal does not
        # advance the board, so the loop's next attempt is the same ordinal.
        self.fail_click_number: int | None = None
        self.fail_click_count = 1
        self.fail_forever = False
        # The nastier failure: the interaction reaches Mudae and pays out, but
        # the response never comes back, so the caller is told it failed.
        self.fail_but_land = False
        self.attempts = 0
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

    def _reward(self, colour: str, *, extra_chance: bool = False):
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
            tag = " (Extra chance)" if extra_chance else ""
            line = (
                f"<:{_LETTER_TO_EMOJI[colour]}:1>{tag} "
                f"**+{int(OT_CELL_SP[colour])}**"
            )
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
        self.attempts += 1
        if self.fail_click_number is not None and (
            self.attempts >= self.fail_click_number
            if self.fail_forever
            else self.fail_click_number
            <= self.attempts
            < self.fail_click_number + self.fail_click_count
        ):
            # The monitor has already retried and given up. Either nothing
            # happened, or — the case seen live on 2026-08-30 — the click landed
            # and paid out and only the reply was lost.
            if self.fail_but_land:
                self._land(index)
            return False
        self._land(index)
        return True

    def _land(self, index: int) -> None:
        """Apply a click on Mudae's side: reveal, pay out, maybe end the game."""
        colour = self.cells[index]
        self.clicks.append(index)
        self.revealed[index] = colour
        granted = False
        if colour == "B":
            self.blues += 1
            spent = self.blues >= self.budget
            # A blue at or past the budget is granted rather than fatal while
            # the board is still under its ship-hit limit — and the grid stays
            # clickable, which is how the real thing was caught.
            granted = spent and self.extra_chance and self.hits < self.extra_chance_hits
            self.extras += 1 if granted else 0
            if spent and not granted:
                self.over = True
                self.revealed = {i: c for i, c in enumerate(self.cells)}
        else:
            self.hits += 1
        self._queue.append(self._reward(colour, extra_chance=granted))
        self._queue.append(self._grid())

    async def fetch_message_snapshot(self, message_id: int):
        """Re-read the grid straight from Discord, bypassing the queue."""
        return self._grid() if message_id == _GRID_ID else None

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
    # Under Extra Chance the blues themselves can pass the budget, so the bound
    # is the board, not the 4.
    assert result["clicks_paid"] == mudae.blues
    assert result["clicks"] == len(mudae.clicks) > result["clicks_paid"]
    assert result["clicks"] <= GRID_CELLS
    assert len(set(mudae.clicks)) == len(mudae.clicks), "clicked a cell twice"
    # Whichever way it ended, it ended the way Mudae ends it.
    assert mudae.over or len(mudae.clicks) == GRID_CELLS


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


def test_the_solver_beats_the_scores_these_boards_actually_got():
    """End to end, not just in the replay harness.

    ``logged_sp`` is what each board really paid — by hand for ``log-*``, by the
    pre-Extra-Chance solver for ``run-10xx``, and by *this* policy for the later
    ``run-*`` boards, which is why the margin is modest. Only the aggregate is
    meaningful:
    those runs were a different build (older rare weights among other things),
    so a single board can differ for reasons that have nothing to do with this
    change. `tests/test_ot_replay.py` does the apples-to-apples per-board
    comparison by replaying both readings through today's code.
    """
    scored_total = logged_total = 0.0
    for entry in KNOWN_BOARDS:
        if entry["logged_sp"] is None:
            continue
        result, _mudae, _logs = _play(entry["cells"])
        scored = sum(
            OT_CELL_SP[entry["cells"][click["cell"]]]
            for click in result["session"]["clicks"]
        )
        # The whole board is the ceiling now: Extra Chance can hand back every
        # cell, blues included, so `ship_sp + 4 blues` is no longer the bound.
        assert scored <= sum(OT_CELL_SP[c] for c in entry["cells"]), entry["name"]
        scored_total += scored
        logged_total += entry["logged_sp"]

    assert scored_total > logged_total * 1.05, (
        f"scored {scored_total:.0f} against {logged_total:.0f} actually paid"
    )


def test_the_log_reports_the_fleet_and_the_blue_budget():
    _result, _mudae, logs = _play(KNOWN_BOARDS[0]["cells"])
    opening = next(line for line in logs if "grid ready" in line)
    assert "6 colours" in opening
    assert "11 blue cells" in opening
    assert "4 blue clicks" in opening
    assert any("blue 1/4" in line for line in logs)


def test_extra_chance_shows_up_in_the_log_when_mudae_grants_one():
    """The tag is the only way a future log can contradict the model.

    Before this the loop stopped at the 4th blue, so it never saw one.
    """
    board = next(e for e in KNOWN_BOARDS if e["name"] == "run-1032")
    result, mudae, logs = _play(board["cells"])
    assert mudae.extras, "this board no longer reaches an Extra Chance"
    assert result["clicks_paid"] > mudae.budget
    assert sum("(Extra chance)" in line for line in logs) == mudae.extras
    assert any("(+" in line and "extra)" in line for line in logs)


def test_mudae_granting_a_blue_we_thought_was_fatal_keeps_the_game_going():
    """Mudae's tag outranks our predicate, not the other way round.

    If the real limit were ever more generous than ``EXTRA_CHANCE_SHIP_HITS``,
    trusting the model would stop on a live board — which is exactly the bug
    this whole change exists to fix. So a granted blue means play on, and the
    mismatch is logged rather than silently absorbed.
    """
    board = next(e for e in KNOWN_BOARDS if e["name"] == "run-1032")
    mudae = _FakeMudae(board["cells"])
    mudae.extra_chance_hits = 99  # a Mudae that never stops granting
    logs: list[str] = []
    game = OtSphereGame(
        mudae, SimpleNamespace(macro_active=False), log=logs.append, click_delay=0.0
    )
    result = asyncio.run(game.play())

    # Nothing can end it, so it clears the board instead of stopping at 5 hits.
    assert result["clicks"] == GRID_CELLS
    assert not mudae.over
    assert any("check EXTRA_CHANCE_SHIP_HITS" in line for line in logs)


def test_one_refused_click_does_not_abandon_the_board():
    """The 2026-08-30 stall, from the loop's side.

    A board died at ``click failed — stopping`` with six certain ships still on
    it. Those are free and riskless, so giving up on the first refusal is a pure
    loss; the loop now refreshes the grid and carries on.
    """
    board = next(e for e in KNOWN_BOARDS if e["name"] == "run-1032")
    mudae = _FakeMudae(board["cells"])
    mudae.fail_click_number = 6  # one refusal, mid-game
    logs: list[str] = []
    game = OtSphereGame(
        mudae, SimpleNamespace(macro_active=False), log=logs.append, click_delay=0.0
    )
    result = asyncio.run(game.play())

    assert any("refreshing the grid" in line for line in logs)
    assert result["reason"] == "done"
    # It kept playing: more clicks after the failure than before it.
    assert result["clicks"] > 6
    assert mudae.over or result["clicks"] == GRID_CELLS


def test_a_click_that_lands_but_reports_failure_is_picked_up_by_the_refresh():
    """What actually happened on 2026-08-30, reconstructed from the reward line.

    The macro logged ``+1188`` spheres, but its own twelve clicks account for
    only 1042 — a difference of exactly one ``spY (+146)``. The cell it was
    about to press was (4,3), ``pB=0% ev=55.0``: a certain yellow. So the click
    reached Mudae and paid out, and only the reply was lost.

    Re-pressing that button would be pointless — it is already spent — so the
    recovery has to come from re-reading the grid, which shows the cell revealed
    and lets the solver move on with it counted.
    """
    board = next(e for e in KNOWN_BOARDS if e["name"] == "run-1032")
    mudae = _FakeMudae(board["cells"])
    mudae.fail_click_number = 6
    mudae.fail_but_land = True
    logs: list[str] = []
    game = OtSphereGame(
        mudae, SimpleNamespace(macro_active=False), log=logs.append, click_delay=0.0
    )
    result = asyncio.run(game.play())

    assert any("refreshing the grid" in line for line in logs)
    assert result["reason"] == "done"
    # The board was finished, and no cell was pressed twice.
    assert len(set(mudae.clicks)) == len(mudae.clicks)
    assert mudae.over or len(mudae.clicks) == GRID_CELLS
    # The lost cell is still absent from our own click list — we never saw its
    # result — but it must not be clicked again either.
    assert result["clicks"] == len(mudae.clicks) - 1


def test_a_cell_that_refuses_twice_is_skipped_rather_than_retried_forever():
    """Asking a third time for the same button cannot help.

    One skipped cell is a far smaller loss than an abandoned board, so the
    solver is told to pick somewhere else instead.
    """
    board = next(e for e in KNOWN_BOARDS if e["name"] == "run-1032")
    mudae = _FakeMudae(board["cells"])
    mudae.fail_click_number = 6
    mudae.fail_click_count = 2  # the refresh-and-retry is refused too
    logs: list[str] = []
    game = OtSphereGame(
        mudae, SimpleNamespace(macro_active=False), log=logs.append, click_delay=0.0
    )
    result = asyncio.run(game.play())

    assert any("keeps refusing — skipping it" in line for line in logs), logs
    assert result["reason"] == "done"
    assert result["clicks"] > 6, "it should have carried on elsewhere"


def test_the_log_says_why_the_transport_refused():
    """`on_status` only reaches the GUI status bar, which nothing keeps.

    The 2026-08-30 board stopped at "click failed — stopping" with no reason
    recorded anywhere, which is what made it guesswork to diagnose.
    """
    board = next(e for e in KNOWN_BOARDS if e["name"] == "run-1032")
    mudae = _FakeMudae(board["cells"])
    mudae.fail_click_number = 4
    mudae.fail_forever = True
    monitor = SimpleNamespace(
        macro_active=False,
        last_transport_error="HTTPException: 429 Too Many Requests",
    )
    logs: list[str] = []
    game = OtSphereGame(mudae, monitor, log=logs.append, click_delay=0.0)
    asyncio.run(game.play())

    assert any("429 Too Many Requests" in line for line in logs), logs


def test_a_board_that_keeps_refusing_says_what_it_cost():
    """Giving up is allowed; giving up quietly is not."""
    board = next(e for e in KNOWN_BOARDS if e["name"] == "run-1032")
    mudae = _FakeMudae(board["cells"])
    mudae.fail_click_number = 4
    mudae.fail_forever = True
    logs: list[str] = []
    game = OtSphereGame(
        mudae, SimpleNamespace(macro_active=False), log=logs.append, click_delay=0.0
    )
    asyncio.run(game.play())

    stop = next(line for line in logs if "stopping" in line)
    assert "refused" in stop and "cells left" in stop, stop


def _stalled_game(silence: float, *, reconnects=None):
    """An `$ot` game whose monitor reports a gateway that has gone quiet."""
    monitor = SimpleNamespace(
        macro_active=False,
        seconds_since_last_event=lambda: silence,
    )
    calls: list[bool] = []

    async def _ensure_connected():
        calls.append(True)
        return True if reconnects is None else reconnects

    monitor.ensure_connected = _ensure_connected
    logs: list[str] = []
    game = OtSphereGame(
        _FakeMudae(KNOWN_BOARDS[0]["cells"]),
        monitor,
        log=logs.append,
        click_delay=0.0,
    )
    return game, calls, logs


def test_a_silent_gateway_is_reconnected_rather_than_waited_out():
    """The 18:32 board: 22 clicks, every ack fetched, five minutes, no reward.

    `is_connected` was True the whole time and HTTP worked, so nothing noticed.
    Each recovered ack costs a full `edit_timeout`, so the only fix that
    restores normal speed is reconnecting the socket.
    """
    game, calls, logs = _stalled_game(silence=60.0)

    async def run() -> None:
        for _ in range(_MAX_ACK_RECOVERIES):
            await game._on_ack_recovered()

    asyncio.run(run())
    assert calls == [True]
    assert any("reconnecting" in line for line in logs), logs


def test_one_recovered_ack_is_not_enough_to_reconnect():
    game, calls, _logs = _stalled_game(silence=60.0)
    asyncio.run(game._on_ack_recovered())
    assert calls == []


def test_a_live_gateway_means_the_edit_was_slow_not_the_socket_dead():
    """Events still arriving rules out a zombie, so a reconnect would not help."""
    game, calls, _logs = _stalled_game(silence=2.0)

    async def run() -> None:
        for _ in range(_MAX_ACK_RECOVERIES + 3):
            await game._on_ack_recovered()

    asyncio.run(run())
    assert calls == []


def test_the_board_is_reconnected_at_most_once():
    game, calls, _logs = _stalled_game(silence=60.0)

    async def run() -> None:
        for _ in range(_MAX_ACK_RECOVERIES * 4):
            await game._on_ack_recovered()

    asyncio.run(run())
    assert calls == [True], "one reconnect a board, however bad it gets"


def test_a_failing_reconnect_never_aborts_the_board():
    game, _calls, logs = _stalled_game(silence=60.0)

    async def _boom():
        raise RuntimeError("gateway is on fire")

    game._monitor.ensure_connected = _boom

    async def run() -> None:
        for _ in range(_MAX_ACK_RECOVERIES):
            await game._on_ack_recovered()

    asyncio.run(run())  # must not raise
    assert any("reconnect failed" in line for line in logs), logs


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


# --- Auto-play ---------------------------------------------------------------
#
# $ot was manual-only (Run-page button) while the solver was tried on real
# boards. It measured 100.2% of the all-ships ceiling across 27 real boards
# under Extra Chance, so it now runs inside play-all and after-refill
# auto-play too, the same as $oh / $oc / $oq. The button still exists for an
# on-demand single play.


def test_ot_is_a_self_playing_minigame():
    """The daily loop plays everything in PLAYABLE_MINIGAMES, including $ot."""
    from macro.minigame_daily import PLAYABLE_MINIGAMES

    assert "ot" in PLAYABLE_MINIGAMES
    assert set(PLAYABLE_MINIGAMES) == {"oh", "oc", "oq", "ot"}


def test_play_all_reaches_for_the_ot_game():
    """Play-all spends $ot uses with the same OtSphereGame driver as the button."""
    import macro.minigames as minigames

    assert minigames.OtSphereGame is not None
    source = __import__("inspect").getsource(minigames.PlayAllMinigames.play)
    assert "OtSphereGame" in source


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
