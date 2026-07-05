"""Tests for perk-6 spawn follow-up handling in RollCycleEngine."""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

from macro.config import CharacterClaimRules, MacroConfig
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult


def _embed(name: str, *, spawned_by: str | None = None, message_id: int = 1):
    description = "Series\n**100**<:kakera:1>\n"
    if spawned_by:
        description += f"<:spG:1> **[SPAWNED BY {spawned_by}]**"
    return {
        "author": name,
        "description": description,
        "footer": "",
    }


def _snapshot(message_id: int, name: str, *, spawned_by: str | None = None):
    return MudaeMessageSnapshot(
        message_id=message_id,
        channel_id=1,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[_embed(name, spawned_by=spawned_by, message_id=message_id)],
        buttons=[
            {
                "label": "",
                "emoji": "kakeraR",
                "custom_id": f"k{message_id}",
                "kind": "kakera",
                "is_kakera": True,
                "disabled": False,
            }
        ],
        created_at="12:00:00",
    )


def _parsed(name: str, *, spawned_by: str | None = None):
    fields = {
        "character_name": name,
        "total_kakera": 100,
        "buttons": [
            {
                "label": "",
                "emoji": "kakeraR",
                "custom_id": "k1",
                "kind": "kakera",
                "is_kakera": True,
                "disabled": False,
            }
        ],
    }
    if spawned_by:
        fields["perk_6"] = True
        fields["spawned_by"] = spawned_by
        fields["is_perk_6_spawn"] = True
    return ParseResult(kind=MessageKind.ROLL, summary=f"$roll · {name}", fields=fields)


class _Perk6Actions:
    def __init__(self) -> None:
        self._rolls = deque([
            (_snapshot(1, "Power"), _parsed("Power")),
            (_snapshot(2, "Akame", spawned_by="POWER"), _parsed("Akame", spawned_by="POWER")),
        ])
        self._spawns = deque([
            (_snapshot(2, "Akame", spawned_by="POWER"), _parsed("Akame", spawned_by="POWER")),
        ])
        self.sent: list[str] = []

    def drain_queue(self) -> None:
        pass

    async def send_command(self, command: str, *, prefix: str | None = None) -> None:
        self.sent.append(command)

    async def wait_for_roll(self, *, roll_command: str, timeout: float = 20.0):
        return self._rolls.popleft() if self._rolls else None

    async def wait_for_perk6_spawn(self, *, parent_character: str, timeout: float = 5.0):
        return self._spawns.popleft() if self._spawns else None

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        return True

    async def wait_for_kakera_outcome(self, *, timeout: float = 8.0):
        return None

    async def wait_for_claim(self, *, timeout: float = 8.0):
        return None


async def _fast_sleep(_delay: float) -> None:
    return None


def test_perk6_spawn_wait_is_short_when_no_spawn():
    config = MacroConfig(
        roll_command="wa",
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
    )
    state = AccountState()
    actions = _Perk6Actions()
    actions._spawns.clear()
    timeouts: list[float] = []

    async def fake_wait(*, parent_character: str, timeout: float = 0.8):
        timeouts.append(timeout)
        return None

    actions.wait_for_perk6_spawn = fake_wait  # type: ignore[method-assign]
    engine = RollCycleEngine(actions, config, state, SimpleNamespace(macro_active=False))

    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        outcome = asyncio.run(
            engine._perform_roll("wa", 1, [], us_roll=False, stop_on_interrupt=True)
        )

    assert outcome.ok is True
    assert timeouts == [0.8]


def test_perk6_spawn_is_processed_after_parent_roll():
    config = MacroConfig(
        roll_command="wa",
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
        kakera_reaction=MacroConfig().kakera_reaction,
    )
    state = AccountState()
    engine = RollCycleEngine(_Perk6Actions(), config, state, SimpleNamespace(macro_active=False))

    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        outcome = asyncio.run(
            engine._perform_roll("wa", 1, [], us_roll=False, stop_on_interrupt=True)
        )

    assert outcome.ok is True
    perk6_logs = [entry.text for entry in state.activity_log if "perk 6" in entry.text.lower()]
    assert any("Akame spawned by POWER" in text for text in perk6_logs)
    assert any("perk 6 · → Akame" in text for text in perk6_logs)
    assert any("settled" in text for text in perk6_logs)
    assert any(entry.block == "perk_6" for entry in state.rule_trace)
