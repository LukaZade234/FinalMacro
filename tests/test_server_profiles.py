"""Server profile store."""

from gui.bridge import profile_fields_from_parse, profile_kind_from_parse
from gui.server_profiles import ServerProfileStore
from mudae.types import MessageKind, ParseResult


def test_legacy_channel_migrates_to_default_server() -> None:
    store = ServerProfileStore()
    store.load_from_settings({"channel_id": "123456789012345678"})
    assert len(store.servers) == 1
    assert store.servers[0].channels[0].channel_id == "123456789012345678"
    assert store.active_discord_channel_id() == "123456789012345678"


def test_apply_settings_updates_channel() -> None:
    store = ServerProfileStore()
    sid = store.add_server("Test Guild")
    cid = store.add_channel(sid, "mudae", "999")
    assert cid
    store.apply_parsed(
        999,
        kind="settings",
        fields={"setrolls": 10, "gamemode": 1},
        summary="Settings parsed",
        guild_id=42,
        guild_name="My Guild",
        channel_name="mudae",
    )
    ch = store.find_channel(sid, cid)
    assert ch is not None
    assert ch.settings["setrolls"] == 10
    assert ch.settings_summary == "Settings parsed"
    assert store.find_server(sid).guild_id == "42"


def test_find_by_discord_id() -> None:
    store = ServerProfileStore()
    sid = store.add_server("S")
    store.add_channel(sid, "a", "111")
    found = store.find_channel_by_discord_id(111)
    assert found is not None


def test_command_response_settings_maps_to_profile() -> None:
    parsed = ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary="$settings · Premium 2",
        fields={
            "parser_command": "settings",
            "setrolls": 10,
            "gamemode": 1,
            "command": "settings",
        },
    )
    assert profile_kind_from_parse(parsed) == "settings"
    fields = profile_fields_from_parse(parsed, "settings")
    assert fields["setrolls"] == 10
    assert "command" not in fields


def test_command_response_shop_maps_to_profile() -> None:
    parsed = ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary="$shop · 10 perks",
        fields={
            "command": "shop",
            "response_label": "$shop response",
            "perk9_click_max": 15,
            "perk9_extra_clicks": 5,
        },
    )
    assert profile_kind_from_parse(parsed) == "shop"
    fields = profile_fields_from_parse(parsed, "shop")
    assert fields["perk9_click_max"] == 15
    assert "command" not in fields
    assert "response_label" not in fields


def test_apply_shop_updates_channel() -> None:
    store = ServerProfileStore()
    sid = store.add_server("Test Guild")
    cid = store.add_channel(sid, "mudae", "999")
    store.apply_parsed(
        999,
        kind="shop",
        fields={"perk9_click_max": 15, "spheres": 55613},
        summary="$shop · perk 9 +5",
    )
    ch = store.find_channel(sid, cid)
    assert ch is not None
    assert ch.shop["perk9_click_max"] == 15
    assert ch.shop_summary == "$shop · perk 9 +5"
