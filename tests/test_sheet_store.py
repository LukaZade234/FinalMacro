"""``$bonus`` / ``$shop`` belong to an account, not to a channel.

Both sheets were stored once per ``ChannelProfile`` with no account key, while
``daily_resets`` one field below was already keyed by account id. With several
accounts on one channel — the live config has three sharing ``#mudae-w`` —
whichever fetched last won, and ``macro.sheet_caps.apply_sheet_caps`` then fed
that account's ``power_max_percent`` and ``perk9_click_max`` into whoever was
actually running. Those are the numbers the perk-8 reserve and the perk-9 EV bar
spend the day on.

``$settings`` stays flat on purpose: it is the server's rule sheet.
"""

from __future__ import annotations

from gui.server_profiles import ServerProfileStore
from gui.sheet_store import read_sheet, write_sheet

MAIN = "acct_main"
ALT = "acct_alt"


def _store() -> tuple[ServerProfileStore, str, str]:
    store = ServerProfileStore()
    store.main_account_id = MAIN
    server_id = store.add_server("Key Server 0")
    channel_id = store.add_channel(server_id, "mudae-w", "999")
    return store, server_id, channel_id


def _channel(store: ServerProfileStore, server_id: str, channel_id: str):
    channel = store.find_channel(server_id, channel_id)
    assert channel is not None
    return channel


# --- the leak this closes ---------------------------------------------------


def test_two_accounts_keep_their_own_shop_on_one_channel():
    store, sid, cid = _store()
    store.apply_parsed(
        999, kind="shop", fields={"perk9_click_max": 20}, summary="", account_id=MAIN
    )
    store.apply_parsed(
        999, kind="shop", fields={"perk9_click_max": 15}, summary="", account_id=ALT
    )
    channel = _channel(store, sid, cid)

    assert store.account_sheet(channel, "shop", account_id=MAIN).fields == {
        "perk9_click_max": 20
    }
    assert store.account_sheet(channel, "shop", account_id=ALT).fields == {
        "perk9_click_max": 15
    }


def test_an_account_with_no_sheet_gets_nothing_not_someone_elses():
    """The alt must read empty, not inherit the main account's perks."""
    store, sid, cid = _store()
    store.apply_parsed(
        999, kind="bonus", fields={"power_max_percent": 155}, summary="", account_id=MAIN
    )
    channel = _channel(store, sid, cid)

    assert store.account_sheet(channel, "bonus", account_id=ALT).fields == {}
    assert store.account_sheet(channel, "bonus", account_id=ALT).present is False


def test_settings_stay_shared_because_they_are_the_servers():
    store, sid, cid = _store()
    store.apply_parsed(
        999, kind="settings", fields={"setrolls": 7}, summary="", account_id=MAIN
    )
    channel = _channel(store, sid, cid)
    assert channel.settings == {"setrolls": 7}


# --- migrating a pre-split sheet --------------------------------------------


def test_a_pre_split_sheet_is_read_by_the_main_account_and_flagged():
    store, sid, cid = _store()
    channel = _channel(store, sid, cid)
    channel.shop = {"perk9_click_max": 15}
    channel.shop_summary = "$shop"

    main = store.account_sheet(channel, "shop", account_id=MAIN)
    assert main.fields == {"perk9_click_max": 15}
    assert main.inferred is True
    assert main.summary == "$shop"


def test_a_pre_split_sheet_is_not_handed_to_other_accounts():
    """Sharing the unattributed sheet round is the bug, not the migration."""
    store, sid, cid = _store()
    channel = _channel(store, sid, cid)
    channel.shop = {"perk9_click_max": 15}

    alt = store.account_sheet(channel, "shop", account_id=ALT)
    assert alt.fields == {}
    assert alt.inferred is False


def test_a_real_fetch_replaces_the_inferred_sheet_and_clears_the_blob():
    store, sid, cid = _store()
    channel = _channel(store, sid, cid)
    channel.shop = {"perk9_click_max": 15}

    store.apply_parsed(
        999, kind="shop", fields={"perk9_click_max": 20}, summary="", account_id=MAIN
    )
    channel = _channel(store, sid, cid)

    fresh = store.account_sheet(channel, "shop", account_id=MAIN)
    assert fresh.fields == {"perk9_click_max": 20}
    assert fresh.inferred is False
    # The blob must go, or it can be inferred a second time later.
    assert channel.shop == {}


def test_a_sheet_with_no_account_at_all_is_kept_not_dropped():
    """No accounts configured yet is not a reason to lose the fetch."""
    store = ServerProfileStore()
    server_id = store.add_server("Key Server 0")
    channel_id = store.add_channel(server_id, "mudae-w", "999")
    store.apply_parsed(999, kind="shop", fields={"perk9_click_max": 15}, summary="$shop")

    channel = _channel(store, server_id, channel_id)
    assert channel.shop == {"perk9_click_max": 15}


# --- $bonus arrives in two parts --------------------------------------------


def test_bonus_parts_merge_within_one_account():
    store, sid, cid = _store()
    store.apply_parsed(
        999, kind="bonus", fields={"part": 1, "wishlist_slots": 220}, summary="",
        account_id=MAIN,
    )
    store.apply_parsed(
        999, kind="bonus", fields={"part": 2, "power_max_percent": 155}, summary="",
        account_id=MAIN,
    )
    channel = _channel(store, sid, cid)

    merged = store.account_sheet(channel, "bonus", account_id=MAIN).fields
    assert merged["wishlist_slots"] == 220
    assert merged["power_max_percent"] == 155


def test_bonus_parts_do_not_merge_across_accounts():
    store, sid, cid = _store()
    store.apply_parsed(
        999, kind="bonus", fields={"wishlist_slots": 220}, summary="", account_id=MAIN
    )
    store.apply_parsed(
        999, kind="bonus", fields={"power_max_percent": 100}, summary="", account_id=ALT
    )
    channel = _channel(store, sid, cid)

    alt = store.account_sheet(channel, "bonus", account_id=ALT).fields
    assert "wishlist_slots" not in alt
    assert alt["power_max_percent"] == 100


# --- persistence -------------------------------------------------------------


def test_per_account_sheets_survive_a_save_load_round_trip():
    store, _sid, _cid = _store()
    store.apply_parsed(
        999, kind="shop", fields={"perk9_click_max": 20}, summary="", account_id=MAIN
    )
    store.apply_parsed(
        999, kind="shop", fields={"perk9_click_max": 15}, summary="", account_id=ALT
    )

    reloaded = ServerProfileStore()
    reloaded.main_account_id = MAIN
    reloaded.load_from_settings(store.to_settings_fragment())
    found = reloaded.find_channel_by_discord_id(999)
    assert found is not None
    channel = found[1]

    assert reloaded.account_sheet(channel, "shop", account_id=MAIN).fields == {
        "perk9_click_max": 20
    }
    assert reloaded.account_sheet(channel, "shop", account_id=ALT).fields == {
        "perk9_click_max": 15
    }


def test_a_write_stamps_when_it_was_read():
    store, sid, cid = _store()
    store.apply_parsed(
        999, kind="shop", fields={"perk9_click_max": 20}, summary="", account_id=MAIN
    )
    channel = _channel(store, sid, cid)
    assert store.account_sheet(channel, "shop", account_id=MAIN).read_at != ""


# --- the store helpers on their own -----------------------------------------


def test_write_sheet_leaves_other_accounts_alone():
    first = write_sheet({}, account_id=MAIN, fields={"a": 1})
    both = write_sheet(first, account_id=ALT, fields={"b": 2})
    assert both[MAIN]["fields"] == {"a": 1}
    assert both[ALT]["fields"] == {"b": 2}


def test_write_sheet_without_an_account_changes_nothing():
    existing = write_sheet({}, account_id=MAIN, fields={"a": 1})
    assert write_sheet(existing, account_id="", fields={"b": 2}) == existing


def test_read_sheet_ignores_malformed_entries():
    assert read_sheet({MAIN: "nonsense"}, account_id=MAIN).fields == {}
    assert read_sheet({MAIN: {"no_fields": 1}}, account_id=MAIN).fields == {}
