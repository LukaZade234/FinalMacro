"""Tests for the `$bw` page's per-pair inputs.

Three of the sweep's inputs are answers only the user can give, and every one of
them is scope-specific: base pool follows the server's game mode, and the
wishlist it is weighed against follows the account. So the property that matters
most here is the one that is easiest to lose — a pair reads back **its own**
answers or the defaults, never a neighbour's.
"""

from __future__ import annotations

from gui.bw_options_store import (
    MAX_BASE_POOL,
    MAX_PERSRARE_N,
    MIN_BASE_POOL,
    BwOptions,
    BwOptionsStore,
)
from macro.bw_calc import DEFAULT_BASE_POOL


def test_an_untouched_pair_reads_back_the_documented_defaults():
    options = BwOptionsStore().get("acc-a", "chan-1")
    assert options.base_pool == DEFAULT_BASE_POOL
    # $ov has no parser, and at one reroll the model is the no-persrare one.
    assert options.persrare_n == 1
    assert options.claimed_pool == 0
    # The macro rolls with the $ prefix.
    assert options.uses_slash is False


def test_one_pairs_answers_never_show_up_under_another():
    store = BwOptionsStore()
    store.set("acc-a", "chan-1", BwOptions(base_pool=500, persrare_n=3))

    assert store.get("acc-a", "chan-1").base_pool == 500
    # Same account, different server.
    assert store.get("acc-a", "chan-2").base_pool == DEFAULT_BASE_POOL
    # Same server, different account.
    assert store.get("acc-b", "chan-1").base_pool == DEFAULT_BASE_POOL
    assert store.get("acc-b", "chan-1").persrare_n == 1


def test_half_a_scope_stores_nothing_and_reads_defaults():
    store = BwOptionsStore()
    store.set("", "chan-1", BwOptions(base_pool=500))
    store.set("acc-a", "", BwOptions(base_pool=500))
    assert store.by_scope == {}
    assert store.get("", "chan-1").base_pool == DEFAULT_BASE_POOL


def test_options_survive_a_settings_round_trip():
    store = BwOptionsStore()
    store.set(
        "acc-a",
        "chan-1",
        BwOptions(
            base_pool=4200,
            persrare_n=3,
            claimed_pool=1200,
            uses_slash=True,
            focus_name="Rebecca",
        ),
    )
    fragment = store.to_settings_fragment()
    assert set(fragment) == {"bw_options"}

    reloaded = BwOptionsStore()
    reloaded.load_from_settings(fragment)
    assert reloaded.get("acc-a", "chan-1") == store.get("acc-a", "chan-1")


def test_nonsense_input_falls_back_rather_than_producing_a_meaningless_curve():
    assert BwOptions.from_dict({"base_pool": "twenty"}).base_pool == DEFAULT_BASE_POOL
    assert BwOptions.from_dict({"base_pool": 0}).base_pool == MIN_BASE_POOL
    assert BwOptions.from_dict({"base_pool": 10**9}).base_pool == MAX_BASE_POOL
    assert BwOptions.from_dict({"persrare_n": -4}).persrare_n == 1
    assert BwOptions.from_dict({"persrare_n": 999}).persrare_n == MAX_PERSRARE_N
    assert BwOptions.from_dict({"claimed_pool": -1}).claimed_pool == 0
    assert BwOptions.from_dict({"focus_name": "  Rebecca "}).focus_name == "Rebecca"


def test_a_malformed_settings_blob_loads_as_empty():
    store = BwOptionsStore()
    store.load_from_settings({"bw_options": "not a dict"})
    assert store.by_scope == {}
    store.load_from_settings({"bw_options": {"": {"base_pool": 5}}})
    assert store.by_scope == {}
