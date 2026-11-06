"""Multi-account foundation: preset scopes, turn-taking, alt rules and store.

Clashes between accounts are the thing these guard against: one owner per
trigger, the same turn order for everyone, one command lane, $us main-only,
and session settings that follow the main.
"""

from __future__ import annotations

import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from gui.alts_store import AltsStore
from macro import preset_scope
from macro.alt_rules import AltRules, rules_for_tier, tier_of
from macro.config import MacroConfig
from macro.turns import ChannelCoordinator, claim_key, kakera_key


# ---- preset scope ----------------------------------------------------------


def test_every_macro_config_field_has_a_scope():
    assert preset_scope.unclassified_fields() == []
    sets = [preset_scope.ACCOUNT, preset_scope.SESSION, preset_scope.MAIN_ONLY]
    names = {f.name for f in dataclasses.fields(MacroConfig)}
    for a in range(3):
        for b in range(a + 1, 3):
            assert not sets[a] & sets[b], "a field may be in one scope only"
        assert sets[a] <= names, "scope names a field MacroConfig doesn't have"


def _main() -> MacroConfig:
    main = MacroConfig(roll_command="wa", notification_mode=True, roll_delay_sec=1.2)
    main.us_schedule_enabled = True
    main.us_keep_draining = True
    main.force_divorce.target_override = "Lucy"
    main.character_claim.enabled = True
    return main


def test_alt_without_a_preset_inherits_the_mains_account_fields():
    main = _main()
    alt = preset_scope.alt_config(main)
    assert alt.roll_command == "wa"
    assert alt.character_claim == main.character_claim
    assert alt.character_claim is not main.character_claim  # a copy, not shared


def test_alt_with_its_own_preset_keeps_its_roll_command_but_follows_main_session():
    own = MacroConfig(roll_command="hg", notification_mode=False, roll_delay_sec=3.0)
    alt = preset_scope.alt_config(_main(), own)
    assert alt.roll_command == "hg"
    assert alt.notification_mode is True  # the main's
    assert alt.roll_delay_sec == 1.2  # the main's
    assert alt.force_divorce.target_override == "Lucy"


def test_alts_never_get_us():
    alt = preset_scope.alt_config(_main())
    assert alt.us_schedule_enabled is False
    assert alt.us_keep_draining is False


# ---- turns -----------------------------------------------------------------


def _coord(**kw):
    return ChannelCoordinator("main", ["a1", "a2", "a3"], **kw)


def test_roster_is_main_then_alts_in_order_without_repeats():
    coord = ChannelCoordinator("main", ["a2", "a1", "main", "a2", ""])
    assert coord.roster == ["main", "a2", "a1"]


def test_one_owner_per_trigger_whoever_asks():
    coord = _coord()
    key = claim_key(10)
    first = coord.assign(key, lambda acc: acc != "main", alts_only=True)
    assert first == "a1"
    # Every later ask — even with a predicate that would pick someone else —
    # gets the same owner.
    assert coord.assign(key, lambda acc: acc == "a3") == "a1"
    assert coord.owns(key, "a1") and not coord.owns(key, "a2")


def test_first_eligible_in_order_and_main_first_when_allowed():
    coord = _coord()
    assert coord.assign(claim_key(1), lambda acc: True) == "main"
    assert coord.assign(claim_key(2), lambda acc: acc in {"a2", "a3"}) == "a2"
    assert coord.assign(claim_key(3), lambda acc: False) is None


def test_pass_on_hands_the_trigger_to_the_next_alt_never_back():
    coord = _coord()
    key = kakera_key(5, "btn")
    assert coord.assign(key, lambda acc: True, alts_only=True) == "a1"
    coord.pass_on(key, "a1")
    assert coord.owner(key) is None
    assert coord.assign(key, lambda acc: True, alts_only=True) == "a2"
    coord.pass_on(key, "a2")
    coord.pass_on(key, "a3")
    assert coord.assign(key, lambda acc: True, alts_only=True) is None


def test_us_is_main_only():
    coord = _coord()
    assert coord.may_roll_us("main")
    assert not any(coord.may_roll_us(acc) for acc in coord.alts)


def test_force_divorce_alts_in_order_then_main_last():
    coord = _coord()
    ready = {"main", "a1", "a3"}
    assert coord.force_divorce_claimers(lambda acc: acc in ready) == ["a1", "a3", "main"]
    # Main without a slot: alts only, the caller must not divorce for nothing.
    assert coord.force_divorce_claimers(lambda acc: acc == "a2") == ["a2"]


def test_command_lane_spaces_different_accounts_and_serialises():
    now = {"t": 0.0}
    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(round(seconds, 3))
        now["t"] += seconds

    coord = ChannelCoordinator("main", ["a1"], clock=lambda: now["t"], sleep=fake_sleep)
    order: list[str] = []

    async def send(acc, label):
        async with coord.command_lane(acc):
            order.append(f"{label}+")
            await asyncio.sleep(0)
            order.append(f"{label}-")

    async def run():
        await send("main", "m1")
        now["t"] += 0.3
        await send("main", "m2")  # same account: its own pacing, no lane wait
        now["t"] += 0.2
        await send("a1", "x")  # different account: waits the rest of 1 s
        await asyncio.gather(send("main", "p"), send("a1", "q"))

    asyncio.run(run())
    assert waits[0] == 0.8
    # Never two accounts inside the lane at once.
    for i in range(0, len(order), 2):
        assert order[i].endswith("+") and order[i + 1].endswith("-")
        assert order[i][:-1] == order[i + 1][:-1]


# ---- alt rules -------------------------------------------------------------


@pytest.mark.parametrize("tier", ["support", "shared", "independent"])
def test_tier_round_trips_and_is_recognised(tier):
    rules = rules_for_tier(tier)
    assert tier_of(rules) == tier
    again = AltRules.from_dict(rules.to_dict())
    assert again == rules and tier_of(again) == tier


def test_changing_a_part_makes_it_custom_but_reserves_dont():
    rules = rules_for_tier("support")
    rules.kakera.keep = 50_000
    rules.claims.own_preset_id = "p1"
    assert tier_of(rules) == "support"
    rules.claims.snipe_guard = True
    assert tier_of(rules) == "custom"


def test_support_alts_do_not_roll():
    assert not rules_for_tier("support").rolls
    assert rules_for_tier("shared").rolls and rules_for_tier("independent").rolls


def test_bad_values_fall_back_to_defaults():
    rules = AltRules.from_dict({"claims": {"source": "everyone"}, "kakera": {"keep": -5, "pass_mode": "x"}})
    assert rules.claims.source == "main"
    assert rules.kakera.keep == 0 and rules.kakera.pass_mode == "session"


# ---- store -----------------------------------------------------------------


def _acc(acc_id, kind="Alt"):
    return SimpleNamespace(id=acc_id, type=kind)


def test_store_order_follows_accounts_and_round_trips():
    store = AltsStore()
    store.load_from_settings({"alts": {"order": ["gone", "b", "a"], "rules": {"a": rules_for_tier("shared").to_dict()}}})
    accounts = [_acc("main", "Main"), _acc("a"), _acc("b"), _acc("c")]
    assert store.alt_ids(accounts) == ["b", "a", "c"]
    assert store.sync(accounts) is True
    assert store.tier("a") == "shared"
    assert store.tier("c") == "support"  # default for a new alt
    assert store.move("c", 0) and store.order == ["c", "b", "a"]
    again = AltsStore()
    again.load_from_settings(store.to_settings_fragment())
    assert again.order == store.order and again.tier("a") == "shared"


def test_apply_tier_keeps_the_users_reserves_and_preset():
    store = AltsStore()
    rules = store.get("a")
    rules.kakera.keep = 1000
    rules.claims.own_preset_id = "p9"
    rules.enabled = False
    store.apply_tier("a", "independent")
    after = store.get("a")
    assert store.tier("a") == "independent"
    assert (after.kakera.keep, after.claims.own_preset_id, after.enabled) == (1000, "p9", False)


def test_disabled_alts_are_left_out_of_the_running_order():
    store = AltsStore()
    accounts = [_acc("a"), _acc("b")]
    store.set_enabled("a", False)
    assert store.enabled_alt_ids(accounts) == ["b"]


def test_kakera_colours_are_the_users_choice_not_the_tier():
    rules = rules_for_tier("support")
    rules.kakera.main_roll_types = ["kakeraC"]
    assert tier_of(rules) == "support"
    store = AltsStore()
    store.set_rules("a", rules.to_dict())
    store.apply_tier("a", "shared")
    assert store.get("a").kakera.main_roll_types == ["kakeraC"]
    assert store.tier("a") == "shared"


def test_pass_timing_is_not_part_of_the_tier():
    rules = rules_for_tier("support")
    rules.kakera.pass_mode = "daily"
    rules.spheres.pass_mode = "session"
    assert tier_of(rules) == "support"
    rules.kakera.on_main_rolls = False  # behaviour still counts
    assert tier_of(rules) == "custom"
