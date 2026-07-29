"""Tests for live preset updates reaching the macro engine."""

from __future__ import annotations

from types import SimpleNamespace

from gui.presets import PresetStore
from macro.config import KakeraReactionRules, MacroConfig, UsRollKakeraRules
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState


def test_update_config_replaces_running_snapshot():
    original = MacroConfig(
        kakera_reaction=KakeraReactionRules(enabled=True, types_allowed=["kakeraC"]),
    )
    engine = RollCycleEngine(
        SimpleNamespace(),
        original,
        AccountState(),
        SimpleNamespace(macro_active=False),
    )

    store = PresetStore()
    store.presets["default"] = original
    store.presets["default"] = MacroConfig(
        kakera_reaction=KakeraReactionRules(enabled=True, types_allowed=["kakeraP"]),
        us_roll_kakera=UsRollKakeraRules(override=True, types_allowed=["kakeraP"]),
    )

    engine.update_config(store.presets["default"])

    us_rules = engine._config.kakera_rules_for_roll(us_roll=True)
    assert us_rules.types_allowed == ["kakeraP"]
    assert "kakeraC" not in us_rules.types_allowed
