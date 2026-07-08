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
    grid_signature,
    is_free_oh_click,
    is_oh_game_over,
    is_oh_grid_message,
    is_oh_reward_message,
    new_reward_line_types,
    parse_clicks_allowed,
    reward_has_entries,
    reward_line_types,
    total_reward_from_content,
    wait_for_minigame_click_ack,
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


def test_wait_for_minigame_click_ack_retries_before_giving_up():
    before = [_btn(i, "spU") for i in range(25)]
    after = [_btn(16, "spB", disabled=True)] + [_btn(i, "spU") for i in range(25) if i != 16]
    before_snap = _grid_snapshot(before, message_id=1000)
    after_snap = _grid_snapshot(after, message_id=1000)
    reward = "<:spB:1> **+14**"
    reward_snap = _reward_snapshot(reward)

    class _Actions:
        def __init__(self) -> None:
            self.attempts = 0

        async def wait_for(self, predicate, *, timeout: float = 10.0):
            self.attempts += 1
            if self.attempts == 1:
                return None
            for snapshot in (reward_snap, after_snap):
                if predicate(snapshot, None):
                    return snapshot, None
            return None

    holder = {"content": ""}

    async def _run():
        return await wait_for_minigame_click_ack(
            _Actions(),
            monitor=None,
            grid_id=1000,
            before_sig=grid_signature(before),
            before_reward="",
            is_grid_message=is_oh_grid_message,
            get_reward_content=lambda: holder["content"],
            set_reward_content=lambda value: holder.__setitem__("content", value),
            edit_timeout=0.01,
            retry_timeout=0.01,
            max_retries=1,
        )

    grid, content = asyncio.run(_run())
    assert grid is not None
    assert content == reward


def test_wait_for_minigame_click_ack_resends_click_on_retry():
    before = [_btn(i, "spU") for i in range(25)]
    after = [_btn(0, "spL", disabled=True)] + [_btn(i, "spU") for i in range(1, 25)]
    reward = "<:spL:1> **+22**"
    reward_snap = _reward_snapshot(reward)
    after_snap = _grid_snapshot(after, message_id=1000)
    retry_clicks: list[str] = []

    class _Actions:
        def __init__(self) -> None:
            self.attempts = 0

        async def wait_for(self, predicate, *, timeout: float = 10.0):
            self.attempts += 1
            if self.attempts <= 2:
                return None
            for snapshot in (reward_snap, after_snap):
                if predicate(snapshot, None):
                    return snapshot, None
            return None

    async def _retry_click() -> None:
        retry_clicks.append("sent")

    async def _run():
        return await wait_for_minigame_click_ack(
            _Actions(),
            monitor=None,
            grid_id=1000,
            before_sig=grid_signature(before),
            before_reward="",
            is_grid_message=is_oh_grid_message,
            get_reward_content=lambda: "",
            set_reward_content=lambda _value: None,
            edit_timeout=0.01,
            retry_timeout=0.01,
            max_retries=2,
            on_retry_click=_retry_click,
        )

    grid, content = asyncio.run(_run())
    assert retry_clicks == ["sent", "sent"]
    assert grid is not None
    assert content == reward


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


def test_is_free_oh_click():
    assert is_free_oh_click(_btn(0, "spP")) is True
    assert is_free_oh_click(_btn(0, "spY")) is False


def test_choose_prefers_free_purple_over_value_sphere():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[2]["emoji"] = "spR"
    buttons[5]["emoji"] = "spP"
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spP"


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
    buttons[1]["emoji"] = "spG"  # green, rank 3
    buttons[2]["emoji"] = "spR"  # red, rank 8
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spR"


def test_choose_prefers_rainbow_over_red():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[1]["emoji"] = "spR"
    buttons[2]["emoji"] = "spW"
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spW"


def test_choose_prefers_value_over_blue_when_both_revealed():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[3]["emoji"] = "spB"  # skip
    buttons[7]["emoji"] = "spY"
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spY"


def test_choose_respects_click_budget():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[1]["emoji"] = "spY"
    assert choose_oh_click(buttons, clicks_spent=5, clicks_budget=5) is None
    buttons[4]["emoji"] = "spP"
    choice = choose_oh_click(buttons, clicks_spent=5, clicks_budget=5, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spP"


def test_reward_line_parsing():
    content = (
        "<:spY:1> **+59**\n"
        "<:spY:1> **+59**\n"
        "<:spP:2> **+42**"
    )
    assert reward_line_types(content) == ["spY", "spY", "spP"]
    assert reward_has_entries(content) is True
    assert reward_has_entries("(Rewards appear here)") is False
    before = "<:spY:1> **+59**"
    assert new_reward_line_types(before, content) == ["spY", "spP"]


def test_grid_signature_detects_disabled_change():
    before = [_btn(0, "spD")]
    after = [_btn(0, "spD", disabled=True)]
    assert grid_signature(before) != grid_signature(after)


def test_is_oh_game_over_when_all_disabled():
    buttons = [_btn(i, "spU", disabled=True) for i in range(25)]
    assert is_oh_game_over(buttons) is True


def test_is_oh_game_over_false_while_clickable_remain():
    buttons = [_btn(i, "spU", disabled=(i == 0)) for i in range(25)]
    assert is_oh_game_over(buttons) is False


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


def test_choose_prefers_yellow_over_green_when_both_revealed():
    buttons = [_btn(i, "spU") for i in range(25)]
    buttons[10]["emoji"] = "spY"
    buttons[15]["emoji"] = "spG"
    choice = choose_oh_click(buttons, rng=random.Random(0))
    assert choice is not None
    assert choice["emoji"] == "spY"


def test_oh_game_waits_for_grid_when_reward_arrives_first():
    """Reward lines often beat the grid edit; must not choose on stale buttons."""
    grid0 = _grid_snapshot(
        [_btn(i, "spU") for i in range(25)],
        content="You can click **2** times on the buttons below.",
    )
    # Hidden click on s8 unveils yellow (s11) and green (s15); reward lands first.
    grid1 = _grid_snapshot(
        [
            _btn(
                i,
                "spY" if i == 11 else "spG" if i == 15 else "spU",
                disabled=(i == 12),
            )
            for i in range(25)
        ],
        content="You can click **2** times on the buttons below.",
    )
    grid2 = _grid_snapshot(
        [
            _btn(
                i,
                "spY" if i == 11 else "spG" if i == 15 else "spU",
                disabled=(i in (12, 11)),
            )
            for i in range(25)
        ],
        content="You can click **2** times on the buttons below.",
    )
    scripted = [
        grid0,
        _reward_snapshot("<:spU:1> **+1**"),
        grid1,
        _reward_snapshot("<:spU:1> **+1**\n<:spY:2> **+59**"),
        grid2,
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    clicks: list[str] = []

    async def track_click(message_id: int, custom_id: str) -> bool:
        clicks.append(custom_id)
        return True

    actions.click_button = track_click  # type: ignore[method-assign]

    game = OhSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        rng=random.Random(0),
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))

    assert clicks == ["cmd s12", "cmd s11"]
    assert result["clicks"] == 2


def test_oh_game_plays_until_clicks_exhausted():
    grid0 = _grid_snapshot(
        [_btn(i, "spY" if i in (10, 19) else "spU") for i in range(25)],
        content="You can click **2** times on the buttons below.",
    )
    grid1 = _grid_snapshot(
        [_btn(i, "spY" if i in (10, 19) else "spU", disabled=(i == 10)) for i in range(25)],
        content="You can click **2** times on the buttons below.",
    )
    grid2 = _grid_snapshot(
        [_btn(i, "spY" if i in (10, 19) else "spU", disabled=(i in (10, 19))) for i in range(25)],
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
    assert result.get("free_clicks", 0) == 0
    assert result["reward"] == 59 + 14
    assert monitor.macro_active is False  # restored after play


def test_oh_game_free_purple_does_not_consume_budget():
    grid0 = _grid_snapshot(
        [_btn(i, "spP" if i == 3 else ("spY" if i == 10 else "spU")) for i in range(25)],
        content="You can click **1** times on the buttons below.",
    )
    grid1 = _grid_snapshot(
        [
            _btn(i, "spP" if i == 3 else ("spY" if i == 10 else "spU"), disabled=(i == 3))
            for i in range(25)
        ],
        content="You can click **1** times on the buttons below.",
    )
    grid2 = _grid_snapshot(
        [
            _btn(
                i,
                "spP" if i in (3, 7) else ("spY" if i == 10 else "spU"),
                disabled=(i in (3, 10)),
            )
            for i in range(25)
        ],
        content="You can click **1** times on the buttons below.",
    )
    grid3 = _grid_snapshot(
        [
            _btn(
                i,
                "spP" if i in (3, 7) else ("spY" if i == 10 else "spU"),
                disabled=(i in (3, 7, 10)),
            )
            for i in range(25)
        ],
        content="You can click **1** times on the buttons below.",
    )
    scripted = [
        grid0,
        grid1,
        _reward_snapshot("<:spP:1> **+10**"),
        grid2,
        _reward_snapshot("<:spY:1> **+59**"),
        grid3,
        _reward_snapshot("<:spP:1> **+12**"),
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    game = OhSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        rng=random.Random(0),
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))

    assert len(actions.clicks) == 3
    assert result["clicks"] == 1
    assert result["free_clicks"] == 2


def test_oh_game_dark_purple_bonus_from_reward_tracker():
    grid0 = _grid_snapshot(
        [_btn(i, "spD" if i == 5 else "spU") for i in range(25)],
        content="You can click **1** times on the buttons below.",
    )
    scripted = [
        grid0,
        _reward_snapshot("<:spP:1> **+42**"),
    ]
    actions = _FakeActions(scripted)
    monitor = SimpleNamespace(macro_active=False)
    game = OhSphereGame(
        actions,
        monitor,
        log=lambda _t: None,
        rng=random.Random(0),
        click_delay=0.0,
    )
    result = asyncio.run(game.play(prefix="$"))

    assert len(actions.clicks) == 1
    assert result["clicks"] == 1
    assert result["free_clicks"] == 1


def test_oh_game_handles_missing_grid():
    actions = _FakeActions([])
    monitor = SimpleNamespace(macro_active=False)
    game = OhSphereGame(actions, monitor, log=lambda _t: None, click_delay=0.0)
    result = asyncio.run(game.play())
    assert result["clicks"] == 0
    assert result["reason"] == "no grid"
