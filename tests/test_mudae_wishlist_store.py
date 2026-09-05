"""Tests for the captured-`$wl` store (gui/mudae_wishlist_store.py).

The load-bearing part is the sphere ladder: each character's cost is derived
from its roster rather than read back, so it can be checked against the figure
Mudae prints. Those checks are pinned against real rows.
"""

from __future__ import annotations

import json

from gui.mudae_wishlist_store import (
    FULL_COST,
    MudaeWishlist,
    MudaeWishlistStore,
    sphere_cost,
)
from mudae.parsers.wishlist import parse_wishlist_page


def test_ladder_reproduces_real_rows():
    """Perks 1-5 cost 200/400/600/800/1000/2000; perks 6-10 are 1000 flat."""
    assert sphere_cost({5: 5, 6: 1, 8: 1, 9: 1, 10: 1}) == 7000
    assert sphere_cost({5: 6, 6: 1, 8: 1, 9: 1, 10: 1}) == 9000
    assert sphere_cost({4: 2, 5: 5, 6: 1, 8: 1, 9: 1, 10: 1}) == 7600


def test_full_is_every_perk_maxed_at_thirty_thousand():
    assert FULL_COST == 30000
    assert sphere_cost({}, full=True) == 30000
    # 5 perks × 5,000 to max, plus 5 unlocks at 1,000.
    assert sphere_cost({p: 6 for p in (1, 2, 3, 4, 5)}) + 5 * 1000 == FULL_COST


def test_cost_matches_flag_is_computed_per_row():
    listing = MudaeWishlist.from_dict(
        {
            "entries": [
                {"name": "Right", "spheres": 7000, "upgrades": {5: 5, 6: 1, 8: 1, 9: 1, 10: 1}},
                {"name": "Wrong", "spheres": 1234, "upgrades": {5: 5}},
            ]
        }
    )
    rows = {row["name"]: row for row in listing.to_client_dict()["entries"]}
    assert rows["Right"]["cost_matches"] is True
    assert rows["Wrong"]["cost_matches"] is False
    assert rows["Wrong"]["derived_cost"] == 3000


def test_real_listing_round_trips_with_no_cost_mismatches():
    page = parse_wishlist_page(
        "lukazade234's Wishlist - 160/162 $wl, 16/16 $sw\n"
        "Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full\n"
        "Shizuku Murasaki ✅ 🔐 · 7,000 sp - 5 (x5), 6, 8, 9, 10\n"
        "Evil Neuro ✅ 🔐 · 9,000 sp - 5 (x6), 6, 8, 9, 10\n"
        "Tanya Degurechaff ✅ 🔐 · 7,600 sp - 4 (x2), 5 (x5), 6, 8, 9, 10"
    )
    listing = MudaeWishlist.from_dict({**page, "complete": True, "route": "dm"})
    payload = listing.to_client_dict()

    assert [row["cost_matches"] for row in payload["entries"]] == [True] * 4
    assert payload["total_spheres"] == 30000 + 7000 + 9000 + 7600
    assert payload["wl_used"] == 160
    assert listing.starwishes == 1


def test_perk_keys_survive_a_json_round_trip_as_ints():
    """JSON turns dict keys into strings; the ladder needs ints back."""
    listing = MudaeWishlist.from_dict(
        {"entries": [{"name": "Rem", "spheres": 7000, "upgrades": {5: 5, 6: 1, 8: 1, 9: 1, 10: 1}}]}
    )
    restored = MudaeWishlist.from_dict(json.loads(json.dumps(listing.to_dict())))
    assert restored.entries[0]["upgrades"] == {5: 5, 6: 1, 8: 1, 9: 1, 10: 1}
    assert restored.to_client_dict()["entries"][0]["cost_matches"] is True


def test_store_is_keyed_by_scope_and_round_trips():
    store = MudaeWishlistStore()
    store.set("acc-a", "chan-1", MudaeWishlist.from_dict({"owner": "A", "wl_used": 5}))
    store.set("acc-b", "chan-1", MudaeWishlist.from_dict({"owner": "B", "wl_used": 9}))

    fragment = store.to_settings_fragment()
    assert set(fragment["mudae_wishlists"]) == {"acc-a|chan-1", "acc-b|chan-1"}

    reloaded = MudaeWishlistStore()
    reloaded.load_from_settings(fragment)
    assert reloaded.get("acc-a", "chan-1").owner == "A"
    assert reloaded.get("acc-b", "chan-1").wl_used == 9


def test_a_scope_never_borrows_another_scopes_rows():
    """Switching either half of the scope shows that pair's own capture."""
    store = MudaeWishlistStore()
    store.set(
        "acc-a",
        "chan-1",
        MudaeWishlist.from_dict(
            {"owner": "A", "entries": [{"name": "Rem", "spheres": 0, "upgrades": {}}]}
        ),
    )

    # Same account, different server.
    assert store.get("acc-a", "chan-2").entries == []
    # Same server, different account.
    assert store.get("acc-b", "chan-1").entries == []
    # Half a scope is not a scope.
    assert store.get("acc-a", "").entries == []
    assert store.get("", "chan-1").entries == []
    # And an uncaptured pair reads as blank rather than raising.
    assert store.get("acc-b", "chan-2").to_client_dict()["captured"] is False


def test_bridge_exposes_and_persists_a_capture(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("gui.settings.SETTINGS_PATH", path)

    from gui.bridge import AppBridge

    bridge = AppBridge()
    bridge._run_account_id = "acc-a"
    bridge._run_channel_profile_id = "chan-1"
    bridge._mudae_wishlists.set(
        "acc-a",
        "chan-1",
        MudaeWishlist.from_dict(
            {
                "owner": "lukazade234",
                "wl_used": 160,
                "wl_max": 162,
                "complete": True,
                "route": "dm",
                "entries": [
                    {"name": "Rem", "spheres": 7000, "upgrades": {5: 5, 6: 1, 8: 1, 9: 1, 10: 1}}
                ],
            }
        ),
    )
    bridge._persist()

    payload = json.loads(bridge.mudaeWishlistFor("acc-a", "chan-1"))
    assert payload["captured"] is True
    assert payload["owner"] == "lukazade234"
    assert payload["entries"][0]["cost_matches"] is True
    assert payload["fetching"] is False

    # Another scope on the same account is blank, not a copy.
    other = json.loads(bridge.mudaeWishlistFor("acc-a", "chan-2"))
    assert other["captured"] is False
    assert other["entries"] == []

    on_disk = json.loads(path.read_text())["mudae_wishlists"]["acc-a|chan-1"]
    assert on_disk["wl_used"] == 160
    assert AppBridge()._mudae_wishlists.get("acc-a", "chan-1").owner == "lukazade234"


def test_the_perk_one_bonus_reads_under_either_field_name():
    """`sphere_percent` is the stored name and stays the stored name.

    It is really the character's perk-1 spawn bonus, and a build briefly renamed
    it to `perk1_spawn_pct`. That is unsafe here: `data/` is Syncthing-shared,
    an instance on an older build round-trips the file, and not recognising the
    key made it write the row back with the value gone — 160 of them at once.
    So the legacy name is what gets written, and both are read.
    """
    listing = MudaeWishlist.from_dict(
        {
            "owner": "lukazade234",
            "entries": [
                {"name": "Rebecca", "sphere_percent": 188, "spheres": 30000,
                 "upgrades_full": True, "upgrades": {}},
                {"name": "Reze", "perk1_spawn_pct": 313, "spheres": 30000,
                 "upgrades_full": True, "upgrades": {}},
            ],
        }
    )
    assert [entry["sphere_percent"] for entry in listing.entries] == [188, 313]
    # Written back under the name every build understands.
    stored = listing.to_dict()["entries"][1]
    assert stored["sphere_percent"] == 313
    assert "perk1_spawn_pct" not in stored
