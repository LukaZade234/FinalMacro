"""Unit tests for macro.rule_eval decisions and the budget/migration paths."""

from __future__ import annotations

from macro.config import (
    CharacterClaimRules,
    KakeraReactionRules,
    LowPowerOverride,
    MacroConfig,
    SphereReactionRules,
)
from macro.rule_eval import (
    passes_character_claim,
    passes_kakera_reaction,
    passes_sphere_reaction,
)
from macro.state import AccountState


# ---------------------------------------------------------------------------
# Migration


def test_legacy_macro_dict_migrates_to_character_claim():
    raw = {
        "roll_command": "wa",
        "auto_claim_wish": True,
        "claim_best_at_claim_reset": True,
        "rolls_left_stop": 3,
    }
    cfg = MacroConfig.from_dict(raw)
    assert cfg.character_claim.enabled is True
    assert cfg.character_claim.claim_on_wish_ping is True
    assert cfg.character_claim.only_final_hour is True
    assert cfg.kakera_reaction.enabled is False
    assert cfg.sphere_reaction.enabled is False
    assert cfg.rolls_left_stop == 3


def test_legacy_auto_claim_maps_to_enabled():
    raw = {"auto_claim": False, "auto_claim_wish": False}
    cfg = MacroConfig.from_dict(raw)
    assert cfg.character_claim.enabled is False
    assert cfg.character_claim.claim_on_wish_ping is False


def test_round_trip_preserves_all_blocks():
    cfg = MacroConfig(
        kakera_reaction=KakeraReactionRules(
            enabled=True,
            types_allowed=["kakeraR", "kakeraW"],
            require_perk_8=True,
            low_power=LowPowerOverride(below_percent=25, types_allowed=["kakeraR"]),
            perk_8_budget_mode=True,
            daily_click_budget=20,
        ),
        sphere_reaction=SphereReactionRules(
            enabled=True,
            types_allowed=["spY", "spB"],
        ),
    )
    restored = MacroConfig.from_dict(cfg.to_dict())
    assert restored.kakera_reaction.types_allowed == ["kakeraR", "kakeraW"]
    assert restored.kakera_reaction.require_perk_8 is True
    assert restored.kakera_reaction.low_power is not None
    assert restored.kakera_reaction.low_power.below_percent == 25
    assert restored.kakera_reaction.low_power.types_allowed == ["kakeraR"]
    assert restored.kakera_reaction.perk_8_budget_mode is True
    assert restored.kakera_reaction.daily_click_budget == 20
    assert restored.sphere_reaction.types_allowed == ["spY", "spB"]


# ---------------------------------------------------------------------------
# Character claim


def _claim_fields(**overrides):
    base = {
        "can_claim": True,
        "claimed": False,
        "total_kakera": 0,
        "claim_rank": None,
        "like_rank": None,
        "spheres": None,
        "keys": [],
        "wished_by": None,
    }
    base.update(overrides)
    return base


def test_character_claim_wish_ping_is_immediate():
    fields = _claim_fields(wished_by=[222])
    rules = CharacterClaimRules(enabled=False, claim_on_wish_ping=True)
    state = AccountState(claim_available=True)
    decision = passes_character_claim(
        fields, rules, state, final_hour=False, wished_pinged=True
    )
    assert decision.should_claim is True
    assert decision.immediate is True
    assert "wish" in decision.reason


def test_character_claim_min_kakera_instant_trigger():
    fields = _claim_fields(total_kakera=600)
    rules = CharacterClaimRules(enabled=True, claim_on_wish_ping=False, min_kakera=500)
    state = AccountState(claim_available=True)
    decision = passes_character_claim(
        fields, rules, state, final_hour=False, wished_pinged=False
    )
    assert decision.should_claim is True
    assert decision.immediate is True
    assert "600" in decision.reason


def test_character_claim_chaos_and_spheres_are_not_factors():
    """Chaos keys / sphere counts are intentionally NOT factors for character claims."""
    fields = _claim_fields(total_kakera=900, keys=[{"type": "gold"}], spheres=0)
    rules = CharacterClaimRules(
        enabled=True, claim_on_wish_ping=False, min_kakera=500
    )
    state = AccountState(claim_available=True)
    decision = passes_character_claim(
        fields, rules, state, final_hour=True, wished_pinged=False
    )
    assert decision.should_claim is True
    assert decision.immediate is True


def test_character_claim_instant_at_claim_rank_and_below():
    fields = _claim_fields(claim_rank=150)
    rules = CharacterClaimRules(
        enabled=True, claim_on_wish_ping=False, max_claim_rank=200
    )
    state = AccountState(claim_available=True)
    decision = passes_character_claim(
        fields, rules, state, final_hour=False, wished_pinged=False
    )
    assert decision.should_claim is True
    assert decision.immediate is True
    assert "claim rank" in decision.reason

    fields_high = _claim_fields(claim_rank=250)
    decision = passes_character_claim(
        fields_high, rules, state, final_hour=False, wished_pinged=False
    )
    assert decision.immediate is False


def test_character_claim_only_final_hour_defers_outside_window():
    fields = _claim_fields(total_kakera=10)
    rules = CharacterClaimRules(enabled=True, claim_on_wish_ping=False, only_final_hour=True)
    state = AccountState(claim_available=True)
    decision = passes_character_claim(
        fields, rules, state, final_hour=False, wished_pinged=False
    )
    assert decision.should_claim is False
    assert decision.reason == "saving claim for final hour"


def test_character_claim_skips_on_cooldown():
    fields = _claim_fields()
    rules = CharacterClaimRules(enabled=True, claim_on_wish_ping=True)
    state = AccountState(claim_available=False)
    decision = passes_character_claim(
        fields, rules, state, final_hour=True, wished_pinged=True
    )
    assert decision.should_claim is False
    assert "cooldown" in decision.reason


# ---------------------------------------------------------------------------
# Kakera reaction


def _kakera_buttons(*emojis: str) -> list[dict]:
    return [
        {
            "is_kakera": True,
            "is_sphere": False,
            "disabled": False,
            "custom_id": f"cid-{i}-{emoji}",
            "emoji": emoji,
            "kind": "kakera",
        }
        for i, emoji in enumerate(emojis)
    ]


def _kakera_fields(buttons, **overrides):
    base = {
        "character_name": "Char",
        "buttons": buttons,
        "perk_8": None,
        "spheres": None,
        "keys": [],
    }
    base.update(overrides)
    return base


def test_kakera_reaction_disabled_returns_no_buttons():
    fields = _kakera_fields(_kakera_buttons("kakeraR"))
    rules = KakeraReactionRules(enabled=False)
    state = AccountState()
    decision = passes_kakera_reaction(fields, rules, state)
    assert decision.buttons == []
    assert decision.reason == "kakera reaction off"


def test_kakera_color_filter_includes_only_allowed():
    fields = _kakera_fields(_kakera_buttons("kakeraR", "kakeraT", "kakeraW"))
    rules = KakeraReactionRules(enabled=True, types_allowed=["kakeraR", "kakeraW"])
    state = AccountState()
    decision = passes_kakera_reaction(fields, rules, state)
    chosen = sorted(b.emoji for b in decision.buttons)
    assert chosen == ["kakeraR", "kakeraW"]


def test_kakera_chaos_required_blocks_without_key():
    fields = _kakera_fields(_kakera_buttons("kakeraR"))
    rules = KakeraReactionRules(enabled=True, require_chaos_key=True)
    state = AccountState()
    decision = passes_kakera_reaction(fields, rules, state)
    assert decision.buttons == []
    assert "chaos" in decision.reason


def test_kakera_perk_8_required():
    fields = _kakera_fields(_kakera_buttons("kakeraR"), perk_8=None)
    rules = KakeraReactionRules(enabled=True, require_perk_8=True)
    state = AccountState()
    assert passes_kakera_reaction(fields, rules, state).buttons == []

    fields = _kakera_fields(_kakera_buttons("kakeraR"), perk_8=True)
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1


def test_kakera_low_power_override_replaces_filter():
    fields = _kakera_fields(_kakera_buttons("kakeraR", "kakeraW"))
    rules = KakeraReactionRules(
        enabled=True,
        types_allowed=["kakeraR", "kakeraW"],
        low_power=LowPowerOverride(below_percent=30, types_allowed=["kakeraW"]),
    )
    state = AccountState(power_percent=20)
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1
    assert decision.buttons[0].emoji == "kakeraW"
    assert "low-power" in decision.reason


def test_kakera_low_power_inactive_above_threshold():
    fields = _kakera_fields(_kakera_buttons("kakeraR", "kakeraW"))
    rules = KakeraReactionRules(
        enabled=True,
        types_allowed=["kakeraR", "kakeraW"],
        low_power=LowPowerOverride(below_percent=30, types_allowed=["kakeraW"]),
    )
    state = AccountState(power_percent=70)
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 2


def test_kakera_perk_8_budget_blocks_when_exhausted_and_not_perk_8():
    fields = _kakera_fields(_kakera_buttons("kakeraR"))
    rules = KakeraReactionRules(
        enabled=True, perk_8_budget_mode=True, daily_click_budget=2
    )
    state = AccountState()
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 2
    decision = passes_kakera_reaction(fields, rules, state)
    assert decision.buttons == []
    assert "budget" in decision.reason.lower()


def test_kakera_perk_8_budget_allows_perk_8_when_exhausted():
    fields = _kakera_fields(_kakera_buttons("kakeraR"), perk_8=True)
    rules = KakeraReactionRules(
        enabled=True, perk_8_budget_mode=True, daily_click_budget=2
    )
    state = AccountState()
    state.kakera_clicks_today = 2
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1


def test_account_state_daily_budget_rollover():
    state = AccountState()
    state.rollover_kakera_budget_if_needed()
    state.kakera_clicks_today = 5
    assert state.remaining_kakera_budget(10) == 5
    state.record_kakera_clicks(3)
    assert state.kakera_clicks_today == 8

    # Simulate previous day → next call resets.
    state.kakera_clicks_day = "1999-01-01"
    state.rollover_kakera_budget_if_needed()
    assert state.kakera_clicks_today == 0


# ---------------------------------------------------------------------------
# Sphere reaction


def _sphere_buttons(*emojis: str) -> list[dict]:
    return [
        {
            "is_kakera": False,
            "is_sphere": True,
            "disabled": False,
            "custom_id": f"sphere-{i}-{emoji}",
            "emoji": emoji,
            "kind": "sphere",
        }
        for i, emoji in enumerate(emojis)
    ]


def test_sphere_reaction_off_returns_nothing():
    fields = {"buttons": _sphere_buttons("spY")}
    rules = SphereReactionRules(enabled=False)
    decision = passes_sphere_reaction(fields, rules, AccountState())
    assert decision.buttons == []


def test_sphere_reaction_color_filter():
    fields = {"buttons": _sphere_buttons("spY", "spR"), "keys": []}
    rules = SphereReactionRules(enabled=True, types_allowed=["spY"])
    decision = passes_sphere_reaction(fields, rules, AccountState())
    assert len(decision.buttons) == 1
    assert decision.buttons[0].emoji == "spY"


def test_sphere_reaction_no_filter_matches_any():
    fields = {"buttons": _sphere_buttons("spY", "spR"), "keys": []}
    rules = SphereReactionRules(enabled=True, types_allowed=[])
    decision = passes_sphere_reaction(fields, rules, AccountState())
    assert len(decision.buttons) == 2
