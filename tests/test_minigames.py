"""Tests for $ohu minigame availability parsing and play-all orchestration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from macro.minigame_util import minigame_command, minigame_use_batches
from macro.minigames import PlayAllMinigames
from mudae.parsers.ohu import (
    is_ohu_response,
    parse_minigame_availability,
    parse_oh_invested_bonus,
    parse_ohu,
)
from mudae.parsers.ohu8 import parse_ohu8

_OHU_SAMPLE = (
    "**4** $oh left for today (+**3** stored), **2** $oc (+**2** stored), "
    "**1** $oq (+**8** stored) and **0** $ot (+**3** stored).\n"
    "**5h 49** min before the refill. **7/15** buttons clicked.\n"
    "No <:spM:1473308463441379428> left today.\n"
    "Stock: **3,924** <:sp:1437140700604137554>"
)

_OHU_LEGACY = (
    "0 $oh left for today, 0 $oc, 0 $oq and 0 $ot (+1 stored).\n"
    "8h 28 min before the refill. 3/15 buttons clicked.\n"
    "Stock: 2,001 :sp:"
)

_OHU8_SAMPLE = (
    _OHU_SAMPLE
    + "\n\n(Perk 8) Clicked today: **40**/40. Rolled today: **33**/123\n"
    "**2B**, **Akame**"
)

_OH_GRID_WITH_BONUS = (
    "**+2** $oq and **+5,344** <:sp:1437140700604137554> from your invested spheres!\n"
    "You can click **5** times on the buttons below (for 2 minutes. Only you can click).\n"
    "Spheres buttons have different values depending on their color, like kakera.\n"
    "Blue spheres unveil 3 buttons, teal unveil 1."
)

_OH_GRID_WITH_OT = (
    "+2 $oq, +1 $ot and +5,600 :sp: from your invested spheres!\n"
    "You can click 5 times on the buttons below (for 2 minutes. Only you can click).\n"
    "Spheres buttons have different values depending on their color, like kakera.\n"
    "Blue spheres unveil 3 buttons, teal unveil 1.\n"
)


def test_minigame_command_multiplier():
    assert minigame_command("oh", 1) == "oh"
    assert minigame_command("oh", 7) == "oh 7"
    assert minigame_command("oc", 4) == "oc 4"
    assert minigame_command("oq", 0) == "oq"
    assert minigame_command("oq", 11) == "oq 10"


def test_minigame_use_batches():
    assert minigame_use_batches(0) == []
    assert minigame_use_batches(7) == [7]
    assert minigame_use_batches(10) == [10]
    assert minigame_use_batches(11) == [10, 1]
    assert minigame_use_batches(23) == [10, 10, 3]


def test_parse_minigame_availability_per_game_stored():
    fields = parse_minigame_availability(_OHU_SAMPLE)
    assert fields["oh_left"] == 4
    assert fields["oh_stored"] == 3
    assert fields["oh_total"] == 7
    assert fields["oc_left"] == 2
    assert fields["oc_stored"] == 2
    assert fields["oc_total"] == 4
    assert fields["oq_left"] == 1
    assert fields["oq_stored"] == 8
    assert fields["oq_total"] == 9
    assert fields["ot_left"] == 0
    assert fields["ot_stored"] == 3
    assert fields["ot_total"] == 3


def test_parse_minigame_availability_legacy_single_stored():
    fields = parse_minigame_availability(_OHU_LEGACY)
    assert fields["oh_total"] == 0
    assert fields["oc_total"] == 0
    assert fields["oq_total"] == 0
    assert fields["ot_left"] == 0
    assert fields["ot_stored"] == 1
    assert fields["ot_total"] == 1


def test_parse_ohu_summary_and_detection():
    assert is_ohu_response(_OHU_SAMPLE)
    parsed = parse_ohu(_OHU_SAMPLE)
    assert parsed.fields["oh_total"] == 7
    assert parsed.fields["perk8_refill_minutes"] == 5 * 60 + 49
    assert parsed.fields["perk9_clicked_today"] == 7
    assert parsed.fields["perk9_click_max"] == 15
    assert parsed.fields["megasphere_left"] is False
    assert parsed.fields["sphere_stock"] == 3924
    assert "$oh 7" in parsed.summary
    assert "$oq 9" in parsed.summary


def test_parse_ohu8_includes_minigame_totals():
    parsed = parse_ohu8(_OHU8_SAMPLE)
    assert parsed.fields["oh_total"] == 7
    assert parsed.fields["oc_total"] == 4
    assert parsed.fields["oq_total"] == 9
    assert parsed.fields["ot_total"] == 3
    assert parsed.fields["perk8_clicked_today"] == 40
    assert parsed.fields["perk8_click_max"] == 40


def test_parse_oh_invested_bonus():
    bonus = parse_oh_invested_bonus(_OH_GRID_WITH_BONUS)
    assert bonus == {"oq_bonus": 2, "ot_bonus": 0, "spheres_bonus": 5344}
    assert parse_oh_invested_bonus(_OH_GRID_WITH_OT) == {
        "oq_bonus": 2,
        "ot_bonus": 1,
        "spheres_bonus": 5600,
    }
    assert parse_oh_invested_bonus("You can click **5** times") == {
        "oq_bonus": 0,
        "ot_bonus": 0,
        "spheres_bonus": 0,
    }


class _FakeActions:
    def __init__(self, ohu_fields: dict[str, Any]) -> None:
        self.sent: list[tuple[str, str | None]] = []
        self._ohu_fields = ohu_fields

    def drain_queue(self) -> None:
        return None

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        self.sent.append((command, prefix))

    async def wait_for_ohu(self, *, timeout: float = 12.0):
        from mudae.types import MessageKind, ParseResult

        return ParseResult(
            kind=MessageKind.COMMAND_RESPONSE,
            summary="$ohu",
            fields=dict(self._ohu_fields),
            warnings=[],
        )


class _FakeGame:
    def __init__(self, name: str, result: dict[str, Any], sent: list[str]) -> None:
        self._name = name
        self._result = result
        self._sent = sent

    async def play(self, *, prefix: str = "$", uses: int = 1) -> dict[str, Any]:
        self._sent.append(f"{self._name}:{uses}:{prefix}")
        return dict(self._result)


def test_play_all_orders_oh_oc_oq_and_adds_invested_oq(monkeypatch):
    sent: list[str] = []
    rewards: list[tuple[str, int, int]] = []

    monkeypatch.setattr(
        "macro.minigames.OhSphereGame",
        lambda *a, **k: _FakeGame(
            "oh",
            {
                "clicks": 5,
                "reward": 100,
                "oq_bonus": 2,
                "ot_bonus": 1,
                "oc_bonus": 3,
                "spheres_bonus": 5344,
                "reason": "done",
            },
            sent,
        ),
    )
    monkeypatch.setattr(
        "macro.minigames.OcSphereGame",
        lambda *a, **k: _FakeGame("oc", {"clicks": 5, "reward": 50, "reason": "done"}, sent),
    )
    monkeypatch.setattr(
        "macro.minigames.OqSphereGame",
        lambda *a, **k: _FakeGame("oq", {"clicks": 7, "reward": 80, "reason": "done"}, sent),
    )
    monkeypatch.setattr(
        "macro.minigames.OtSphereGame",
        lambda *a, **k: _FakeGame("ot", {"clicks": 3, "reward": 30, "reason": "done"}, sent),
    )

    actions = _FakeActions(
        {
            "oh_left": 4,
            "oh_stored": 3,
            "oh_total": 7,
            "oc_left": 2,
            "oc_stored": 2,
            "oc_total": 4,
            "oq_left": 1,
            "oq_stored": 8,
            "oq_total": 9,
            "ot_left": 0,
            "ot_stored": 3,
            "ot_total": 3,
        }
    )
    logs: list[str] = []
    runner = PlayAllMinigames(
        actions,
        SimpleNamespace(macro_active=False),
        log=logs.append,
        on_game_reward=lambda game, amount, clicks: rewards.append((game, amount, clicks)),
        between_games_sec=0,
    )

    result = asyncio.run(runner.play(prefix="$"))

    assert actions.sent == [("ohu", "$")]
    assert sent == ["oh:7:$", "oc:7:$", "oq:10:$", "oq:1:$", "ot:4:$"]
    assert result["availability"]["oq_total"] == 11
    assert result["availability"]["oc_total"] == 7
    assert result["availability"]["ot_total"] == 4
    assert ("oh", 100, 5) in rewards
    assert ("oh", 5344, 0) not in rewards
    assert ("oc", 50, 5) in rewards
    assert ("oq", 80, 7) in rewards
    assert ("ot", 30, 3) in rewards
    assert any("$ot 3" in line for line in logs)
    assert any("$oc from $oh hidden clicks" in line for line in logs)
    assert any("perk 10 → $ot 4" in line for line in logs)


def test_play_all_skips_zero_uses(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(
        "macro.minigames.OhSphereGame",
        lambda *a, **k: _FakeGame("oh", {"reason": "done", "reward": 0}, sent),
    )
    monkeypatch.setattr(
        "macro.minigames.OcSphereGame",
        lambda *a, **k: _FakeGame("oc", {"reason": "done", "reward": 0}, sent),
    )
    monkeypatch.setattr(
        "macro.minigames.OqSphereGame",
        lambda *a, **k: _FakeGame("oq", {"reason": "done", "reward": 0}, sent),
    )
    monkeypatch.setattr(
        "macro.minigames.OtSphereGame",
        lambda *a, **k: _FakeGame("ot", {"reason": "done", "reward": 0}, sent),
    )
    actions = _FakeActions(
        {
            "oh_total": 0,
            "oc_total": 2,
            "oq_total": 0,
            "ot_total": 1,
            "oh_left": 0,
            "oh_stored": 0,
            "oc_left": 2,
            "oc_stored": 0,
            "oq_left": 0,
            "oq_stored": 0,
            "ot_left": 1,
            "ot_stored": 0,
        }
    )
    runner = PlayAllMinigames(
        actions,
        SimpleNamespace(),
        log=lambda _t: None,
        between_games_sec=0,
    )
    asyncio.run(runner.play())
    assert sent == ["oc:2:$", "ot:1:$"]


def test_play_all_skips_ohu_when_playable_games_exhausted():
    from macro.minigame_daily import (
        MINIGAME_DAILY_KEY,
        MinigameDailyEntry,
        MinigameDailyRecord,
        save_minigame_record,
    )

    store = {"value": {}}
    record = MinigameDailyRecord(
        refill_at="2099-01-01T00:00:00+00:00",
        games={
            "oh": MinigameDailyEntry(exhausted=True, total=0),
            "oc": MinigameDailyEntry(exhausted=True, total=0),
            "oq": MinigameDailyEntry(exhausted=True, total=0),
            "ot": MinigameDailyEntry(exhausted=True, total=0),
        },
    )
    store["value"] = save_minigame_record({}, record)
    sent: list[str] = []
    actions = _FakeActions(
        {
            "oh_total": 4,
            "oc_total": 2,
            "oq_total": 1,
            "ot_total": 2,
            "oh_left": 4,
            "oh_stored": 0,
            "oc_left": 2,
            "oc_stored": 0,
            "oq_left": 1,
            "oq_stored": 0,
            "ot_left": 2,
            "ot_stored": 0,
        }
    )
    logs: list[str] = []
    runner = PlayAllMinigames(
        actions,
        SimpleNamespace(),
        log=logs.append,
        between_games_sec=0,
        daily_get=lambda: store["value"],
        daily_save=lambda daily: store.__setitem__("value", daily),
    )
    result = asyncio.run(runner.play())
    assert actions.sent == []
    assert sent == []
    assert result["reason"] == "skipped until refill"
    assert any("skipped until refill" in line for line in logs)
    assert MINIGAME_DAILY_KEY in store["value"]


def test_play_all_ignore_daily_skip_queries_ohu():
    from macro.minigame_daily import (
        MinigameDailyEntry,
        MinigameDailyRecord,
        save_minigame_record,
    )

    store = {"value": {}}
    record = MinigameDailyRecord(
        refill_at="2099-01-01T00:00:00+00:00",
        games={
            "oh": MinigameDailyEntry(exhausted=True, total=0),
            "oc": MinigameDailyEntry(exhausted=True, total=0),
            "oq": MinigameDailyEntry(exhausted=True, total=0),
        },
    )
    store["value"] = save_minigame_record({}, record)
    actions = _FakeActions(
        {
            "oh_total": 0,
            "oc_total": 0,
            "oq_total": 0,
            "ot_total": 0,
            "oh_left": 0,
            "oh_stored": 0,
            "oc_left": 0,
            "oc_stored": 0,
            "oq_left": 0,
            "oq_stored": 0,
            "ot_left": 0,
            "ot_stored": 0,
        }
    )
    runner = PlayAllMinigames(
        actions,
        SimpleNamespace(),
        log=lambda _t: None,
        between_games_sec=0,
        daily_get=lambda: store["value"],
        daily_save=lambda daily: store.__setitem__("value", daily),
    )
    result = asyncio.run(runner.play(ignore_daily_skip=True))
    assert ("ohu", "$") in actions.sent
    assert result["reason"] == "done"


def test_play_all_persists_ohu_totals(monkeypatch):
    monkeypatch.setattr(
        "macro.minigames.OhSphereGame",
        lambda *a, **k: _FakeGame("oh", {"reason": "done", "reward": 0}, []),
    )
    monkeypatch.setattr(
        "macro.minigames.OcSphereGame",
        lambda *a, **k: _FakeGame("oc", {"reason": "done", "reward": 0}, []),
    )
    monkeypatch.setattr(
        "macro.minigames.OqSphereGame",
        lambda *a, **k: _FakeGame("oq", {"reason": "done", "reward": 0}, []),
    )
    monkeypatch.setattr(
        "macro.minigames.OtSphereGame",
        lambda *a, **k: _FakeGame("ot", {"reason": "done", "reward": 0}, []),
    )
    store = {"value": {}}
    actions = _FakeActions(
        {
            "oh_left": 0,
            "oh_stored": 0,
            "oh_total": 0,
            "oc_left": 0,
            "oc_stored": 0,
            "oc_total": 0,
            "oq_left": 0,
            "oq_stored": 0,
            "oq_total": 0,
            "ot_left": 0,
            "ot_stored": 1,
            "ot_total": 1,
            "perk8_refill_minutes": 120,
            "perk9_clicked_today": 15,
            "perk9_click_max": 15,
        }
    )
    runner = PlayAllMinigames(
        actions,
        SimpleNamespace(),
        log=lambda _t: None,
        between_games_sec=0,
        daily_get=lambda: store["value"],
        daily_save=lambda daily: store.__setitem__("value", daily),
    )
    asyncio.run(runner.play())
    from macro.minigame_daily import load_minigame_record, should_skip_playable_minigames
    from macro.perk9_daily import load_perk9_record

    daily = store["value"]
    minigames = load_minigame_record(daily)
    assert should_skip_playable_minigames(minigames) is True
    assert minigames.entry("ot").total == 0
    perk9 = load_perk9_record(daily)
    assert perk9.last_clicked == 15
    assert perk9.last_click_max == 15
    assert perk9.clicks_exhausted is True
