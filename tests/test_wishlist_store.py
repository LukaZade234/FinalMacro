"""Tests for the app-only wishlist storage shape (gui/wishlist_store.py)."""

from __future__ import annotations

import json

from gui.wishlist_store import Wishlist, WishlistEntries, scope_key


def test_scope_key_needs_both_halves():
    assert scope_key("acc", "chan") == "acc|chan"
    assert scope_key("acc", "") == ""
    assert scope_key("", "chan") == ""


def test_from_dict_empty_defaults_to_global():
    wl = Wishlist.from_dict(None)
    assert wl.is_global is True
    assert wl.entries.characters == []
    assert wl.entries.series == []


def test_from_dict_cleans_blanks_and_dedupes_case_insensitively():
    wl = Wishlist.from_dict(
        {"characters": ["Rem", "  ", "rem", "Emilia"], "series": ["Re:Zero", ""]}
    )
    assert wl.entries.characters == ["Rem", "Emilia"]
    assert wl.entries.series == ["Re:Zero"]


def test_round_trip_through_settings_fragment():
    wl = Wishlist(is_global=False, entries=WishlistEntries(characters=["Rem"]))
    wl.entries_for("acc", "chan").add_characters(["Alice"])
    restored = Wishlist.from_dict(wl.to_settings_fragment()["wishlist"])
    assert restored.is_global is False
    assert restored.entries.characters == ["Rem"]
    assert restored.scoped["acc|chan"].characters == ["Alice"]


def test_add_characters_is_bulk_and_reports_new_count():
    entries = WishlistEntries()
    assert entries.add_characters(["Rem", "Alice"]) == 2
    assert entries.add_characters(["rem", "Audrey"]) == 1  # Rem already there
    assert entries.characters == ["Rem", "Alice", "Audrey"]


def test_remove_is_case_insensitive_and_reports_whether_it_existed():
    entries = WishlistEntries(characters=["Rem"], series=["Re:Zero"])
    assert entries.remove_character("REM") is True
    assert entries.remove_character("Rem") is False
    assert entries.remove_series("re:zero") is True
    assert entries.series == []


def test_global_toggle_picks_which_list_the_macro_matches():
    wl = Wishlist(is_global=True, entries=WishlistEntries(characters=["Global"]))
    wl.scoped["acc|chan"] = WishlistEntries(characters=["Scoped"])

    assert wl.match_lists_for("acc", "chan") == (["Global"], [])
    # Another pair sees the same global list.
    assert wl.match_lists_for("other", "elsewhere") == (["Global"], [])

    wl.is_global = False
    assert wl.match_lists_for("acc", "chan") == (["Scoped"], [])
    # A pair with nothing of its own matches nothing — it does not fall back
    # to the global list, which is the point of turning the toggle off.
    assert wl.match_lists_for("other", "elsewhere") == ([], [])


def test_flipping_the_toggle_keeps_both_lists():
    wl = Wishlist(is_global=True, entries=WishlistEntries(characters=["Global"]))
    wl.is_global = False
    wl.entries_for("acc", "chan").add_characters(["Scoped"])
    wl.is_global = True
    assert wl.entries_for("acc", "chan").characters == ["Global"]
    wl.is_global = False
    assert wl.entries_for("acc", "chan").characters == ["Scoped"]


def test_match_lists_never_creates_a_scope():
    """The roll loop asks on every roll — it must not grow the settings file."""
    wl = Wishlist(is_global=False)
    assert wl.match_lists_for("acc", "chan") == ([], [])
    assert wl.scoped == {}


def test_half_a_scope_edits_a_throwaway_list():
    wl = Wishlist(is_global=False)
    wl.entries_for("acc", "").add_characters(["Nowhere"])
    assert wl.scoped == {}


def test_bridge_wishlist_slots_add_remove_and_persist(tmp_path, monkeypatch):
    """End to end through AppBridge: Qt slots, persistence, and the engine read."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr("gui.settings.SETTINGS_PATH", path)

    from gui.bridge import AppBridge

    bridge = AppBridge()
    bridge._run_account_id = "acc"
    bridge._run_channel_profile_id = "chan"

    # Bulk add in one box, in each accepted separator style.
    assert bridge.addWishlistCharacters("Rem$Alice$Audrey", "acc", "chan") == 3
    assert bridge.addWishlistCharacters("Rem, Chika", "acc", "chan") == 1
    assert bridge.addWishlistSeries("Re:Zero $Overlord", "acc", "chan") == 2

    on_disk = json.loads(path.read_text())["wishlist"]
    assert on_disk["global"] is True
    assert on_disk["characters"] == ["Rem", "Alice", "Audrey", "Chika"]
    assert on_disk["series"] == ["Re:Zero", "Overlord"]

    assert bridge._wishlist_snapshot() == (
        ["Rem", "Alice", "Audrey", "Chika"],
        ["Re:Zero", "Overlord"],
    )

    payload = json.loads(bridge.wishlistFor("acc", "chan"))
    assert payload["global"] is True
    assert payload["characters"] == ["Rem", "Alice", "Audrey", "Chika"]

    assert bridge.removeWishlistCharacter("rem", "acc", "chan") is True
    assert json.loads(path.read_text())["wishlist"]["characters"] == [
        "Alice",
        "Audrey",
        "Chika",
    ]

    reloaded = AppBridge()
    assert reloaded._wishlist.entries.series == ["Re:Zero", "Overlord"]


def test_bridge_scoped_toggle_isolates_pairs(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("gui.settings.SETTINGS_PATH", path)

    from gui.bridge import AppBridge

    bridge = AppBridge()
    bridge.setWishlistGlobal(False)
    bridge.addWishlistCharacters("Rem", "acc-a", "chan-1")
    bridge.addWishlistCharacters("Alice", "acc-b", "chan-1")

    bridge._run_account_id, bridge._run_channel_profile_id = "acc-a", "chan-1"
    assert bridge._wishlist_snapshot() == (["Rem"], [])

    bridge._run_account_id, bridge._run_channel_profile_id = "acc-b", "chan-1"
    assert bridge._wishlist_snapshot() == (["Alice"], [])

    # Same account, different server: its own list, not the other channel's.
    bridge._run_account_id, bridge._run_channel_profile_id = "acc-a", "chan-2"
    assert bridge._wishlist_snapshot() == ([], [])
