"""Shared pytest fixtures.

Integration tests simulate full macro loops (many rolls). Production code
uses real-time waits (roll delay, perk-6 spawn poll, $tu settle, etc.).
Those are irrelevant to what the tests assert, so we zero them globally.
"""

from __future__ import annotations

from pathlib import Path

import pytest


async def _instant_sleep(*_args, **_kwargs) -> None:
    return None


@pytest.fixture(autouse=True)
def isolate_event_log(tmp_path: Path) -> None:
    """Keep Statistics logs out of the developer's data/ folder during tests."""
    from mudae import event_log
    from mudae import kakera_log, key_log, soulmate_log, sphere_log

    event_log.reset_for_tests(tmp_path / "events.jsonl")
    kakera_log._bind_events()
    sphere_log._bind_events()
    key_log._bind_events()
    soulmate_log._bind_events()


@pytest.fixture(autouse=True)
def fast_macro_timers(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop wall-clock waits that dominate suite runtime (~2 min → ~15 s)."""
    if request.node.get_closest_marker("slow"):
        return
    # Every roll polls up to _PERK6_SPAWN_WAIT_SEC (0.5 s) for a spawn follow-up.
    monkeypatch.setattr("macro.roll_cycle._PERK6_SPAWN_WAIT_SEC", 0.0)
    monkeypatch.setattr("macro.roll_cycle._PERK6_SPAWN_POLL_SEC", 0.0)
    monkeypatch.setattr("macro.roll_cycle._COMMAND_SETTLE_SEC", 0.0)
    monkeypatch.setattr("macro.roll_cycle._PERK6_POST_SETTLE_SEC", 0.0)
    monkeypatch.setattr("macro.roll_cycle._US_ADD_SETTLE_SEC", 0.0)

    monkeypatch.setattr("macro.roll_cycle.asyncio.sleep", _instant_sleep)
    monkeypatch.setattr("macro.kakera_reactor.asyncio.sleep", _instant_sleep)

    # Tests that build MacroConfig() inherit a zero roll delay (prod min is 0.6).
    from macro.config import MacroConfig

    _orig_init = MacroConfig.__init__

    def _init_with_fast_delay(self, *args, **kwargs):
        kwargs.setdefault("roll_delay_sec", 0.0)
        kwargs.setdefault("us_add_delay_sec", 0.0)
        kwargs.setdefault("us_read_before_add_delay_sec", 0.0)
        kwargs.setdefault("us_roll_timeout_retry_sec", 0.0)
        _orig_init(self, *args, **kwargs)

    monkeypatch.setattr(MacroConfig, "__init__", _init_with_fast_delay)
