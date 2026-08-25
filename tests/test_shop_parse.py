"""``$shop`` parse against live LVL 0 / mixed / mid upgrade dumps."""

from __future__ import annotations

from mudae.commands import detect_command_from_response, detect_command_from_snapshot
from mudae.message_text import flatten_component_text
from mudae.parsers.pipeline import format_entry_for_gui, parse_message
from mudae.parsers.shop import parse_shop
from mudae.parsers.shop_catalog import fields_to_shop_display_dict, perk9_click_max
from mudae.types import MessageKind, MudaeMessageSnapshot
from tests.mudae_sheet_fixtures import (
    SHOP_REPLY_LVL0,
    SHOP_REPLY_MID,
    SHOP_REPLY_MIXED,
    SHOP_REPLY_MIXED_LIVE,
)

MUDAE_ALT_ID = 432610292342587392


def _snap(*, content: str = "", components: list | None = None) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=40,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=content,
        embeds=[],
        buttons=[],
        created_at="00:52:00",
        components=list(components or []),
    )


def test_flatten_component_text_walks_container_section():
    payload = [
        {
            "type": 17,
            "components": [
                {"type": 10, "content": "Upgrade bonuses given by ouroperks."},
                {
                    "type": 9,
                    "components": [{"type": 10, "content": "You have 13,549 :sp:"}],
                    "accessory": {"type": 11, "media": {"url": "https://example"}},
                },
                {"type": 10, "content": "[LVL 0]  perk 9 text"},
            ],
        }
    ]
    text = flatten_component_text(payload)
    assert "Upgrade bonuses given by ouroperks." in text
    assert "You have 13,549 :sp:" in text
    assert "[LVL 0]  perk 9 text" in text


def test_parse_shop_all_zero():
    result = parse_shop(SHOP_REPLY_LVL0)
    assert result.kind == MessageKind.SHOP
    assert result.fields["spheres"] == 13549
    assert result.fields["max_level"] == 10
    assert result.fields["level_cost_step"] == 4000
    assert result.fields["perk_count"] == 10
    perks = result.fields["perks"]
    assert perks["1"]["level"] == 0
    assert perks["1"]["spawn_share_pct"] == 0
    assert perks["1"]["next_spawn_share_pct"] == 10
    assert perks["2"]["megasphere_rewards"] == 0
    assert perks["2"]["next_megasphere_rewards"] == 3
    assert perks["5"]["ot_chance_pct"] == 0
    assert perks["5"]["next_ot_chance_pct"] == 0.014
    assert perks["6"]["wishlist_claim_pct"] == 0
    assert perks["6"]["owned_omega_key_pct"] == 0
    assert perks["6"]["next_owned_omega_key_pct"] == 50
    assert perks["9"]["extra_clicks"] == 0
    assert perks["9"]["next_extra_clicks"] == 1
    assert perks["9"]["sphere_value_pct"] == 0
    assert perks["9"]["next_sphere_value_pct"] == 10
    assert perks["10"]["ot_chance_pct"] == 0
    assert perks["10"]["next_ot_chance_pct"] == 0.25
    assert result.fields["perk9_extra_clicks"] == 0
    assert result.fields["perk9_click_max"] == 10
    assert result.fields["perk2_megasphere_rewards"] == 0
    assert not result.warnings


def test_parse_shop_mixed_max():
    result = parse_shop(SHOP_REPLY_MIXED)
    perks = result.fields["perks"]
    assert result.fields["spheres"] == 15660
    assert perks["1"]["level"] == 5
    assert perks["1"]["spawn_share_pct"] == 50
    assert perks["5"]["level"] == 10
    assert perks["5"]["maxed"] is True
    assert perks["5"]["ot_chance_pct"] == 0.14
    assert "next_ot_chance_pct" not in perks["5"]
    assert perks["6"]["owned_omega_key_pct"] == 250
    assert perks["6"]["next_owned_omega_key_pct"] == 300
    assert perks["8"]["level"] == 6
    assert perks["8"]["kakera_boost_pct"] == 30
    assert perks["9"]["maxed"] is True
    assert perks["9"]["extra_clicks"] == 10
    assert perks["9"]["sphere_value_pct"] == 100
    assert "next_extra_clicks" not in perks["9"]
    assert perks["10"]["level"] == 8
    assert perks["10"]["ot_chance_pct"] == 2
    assert perks["10"]["next_ot_chance_pct"] == 2.25
    assert result.fields["perk9_click_max"] == 20
    assert result.fields["perk9_sphere_value_pct"] == 100
    assert not result.warnings


def test_parse_shop_live_discord_markdown():
    """Debug dump uses [**LVL 5**] / **15,660** <:sp:id>, not the copy-paste form."""
    result = parse_shop(SHOP_REPLY_MIXED_LIVE)
    assert not result.warnings
    assert result.fields["spheres"] == 15660
    assert result.fields["level_cost_step"] == 4000
    assert result.fields["perk_count"] == 10
    perks = result.fields["perks"]
    assert perks["1"]["level"] == 5
    assert perks["1"]["spawn_share_pct"] == 50
    assert perks["1"]["next_spawn_share_pct"] == 60
    assert perks["5"]["maxed"] is True
    assert perks["5"]["ot_chance_pct"] == 0.14
    assert perks["9"]["extra_clicks"] == 10
    assert perks["9"]["sphere_value_pct"] == 100
    assert perks["10"]["ot_chance_pct"] == 2
    assert perks["10"]["next_ot_chance_pct"] == 2.25
    assert result.fields["perk9_click_max"] == 20
    via_pipeline = parse_message(_snap(content=SHOP_REPLY_MIXED_LIVE), reply_to_command="shop")
    assert via_pipeline.fields["perk9_click_max"] == 20
    assert via_pipeline.fields["spheres"] == 15660


def test_parse_shop_mid_levels():
    result = parse_shop(SHOP_REPLY_MID)
    perks = result.fields["perks"]
    assert result.fields["spheres"] == 55613
    assert perks["5"]["level"] == 1
    assert perks["5"]["ot_chance_pct"] == 0.014
    assert perks["5"]["next_ot_chance_pct"] == 0.028
    assert perks["8"]["level"] == 3
    assert perks["8"]["kakera_boost_pct"] == 15
    assert perks["9"]["level"] == 5
    assert perks["9"]["extra_clicks"] == 5
    assert perks["9"]["next_extra_clicks"] == 6
    assert perks["9"]["sphere_value_pct"] == 50
    assert perks["9"]["next_sphere_value_pct"] == 60
    assert result.fields["perk9_click_max"] == 15
    assert result.fields["perk8_kakera_boost_pct"] == 15
    assert result.fields["perk10_ot_chance_pct"] == 0
    assert not result.warnings


def test_perk9_click_max_formula():
    assert perk9_click_max(0) == 10
    assert perk9_click_max(5) == 15
    assert perk9_click_max(10) == 20


def test_shop_display_dict_has_cap_row():
    result = parse_shop(SHOP_REPLY_MID)
    display = fields_to_shop_display_dict(result.fields)
    assert display["field_count"] >= 12
    titles = [section["title"] for section in display["sections"]]
    assert titles == ["Stock", "Ouroperks"]
    cap = [row for row in display["sections"][1]["rows"] if row["field"] == "perk9_click_max"]
    assert cap and cap[0]["display"] == "15/day"


def test_empty_content_components_v2_parses_via_pipeline():
    snapshot = _snap(
        content="",
        components=[{"type": 17, "components": [{"type": 10, "content": SHOP_REPLY_MID}]}],
    )
    result = parse_message(snapshot, reply_to_command="shop")
    assert result.fields["response_label"] == "$shop response"
    assert result.fields["perk9_extra_clicks"] == 5
    assert result.fields["perk9_click_max"] == 15
    gui = format_entry_for_gui(snapshot, result)
    assert gui["rawContent"] == "(no plain text)"
    assert "perk 9" in gui["rawComponents"]


def test_detect_shop_from_flattened_text():
    assert detect_command_from_response(SHOP_REPLY_LVL0) == "shop"
    snapshot = _snap(content="", components=[{"type": 10, "content": SHOP_REPLY_LVL0}])
    assert detect_command_from_snapshot(snapshot, user_input="shop") == "shop"


def test_snapshot_from_message_uses_raw_components():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from mudae.serialization import snapshot_from_message

    channel = SimpleNamespace(id=99, name="mudae")
    guild = SimpleNamespace(id=1, name="srv")
    author = SimpleNamespace(
        id=MUDAE_ALT_ID,
        display_name="Mudae",
        name="Mudae",
    )
    message = SimpleNamespace(
        id=41,
        channel=channel,
        guild=guild,
        author=author,
        content="",
        embeds=[],
        components=[],
        created_at=datetime(2026, 8, 25, 0, 53, tzinfo=timezone.utc),
        _raw_components=[{"type": 10, "content": SHOP_REPLY_LVL0}],
    )
    snapshot = snapshot_from_message(message)
    assert "You have 13,549 :sp:" in snapshot.content
    assert snapshot.components[0]["type"] == 10
    result = parse_message(snapshot, reply_to_command="shop")
    assert result.fields["perk9_click_max"] == 10


def test_component_patch_does_not_write_slotted_message():
    import discord
    from mudae.serialization import raw_components_for

    class Slotted:
        __slots__ = ("id", "components")

        def __init__(self) -> None:
            self.id = 88
            self.components = None

    message = Slotted()
    discord.Message._handle_components(message, [{"type": 10, "content": "shop body"}])
    assert raw_components_for(message) == [{"type": 10, "content": "shop body"}]


def test_raw_components_cache_does_not_need_message_slots():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from mudae.serialization import remember_raw_components, snapshot_from_message

    remember_raw_components(77, [{"type": 10, "content": SHOP_REPLY_MID}])
    message = SimpleNamespace(
        id=77,
        channel=SimpleNamespace(id=99, name="mudae"),
        guild=SimpleNamespace(id=1, name="srv"),
        author=SimpleNamespace(id=MUDAE_ALT_ID, display_name="Mudae", name="Mudae"),
        content="",
        embeds=[],
        components=[],
        created_at=datetime(2026, 8, 25, 0, 53, tzinfo=timezone.utc),
    )
    snapshot = snapshot_from_message(message)
    assert "You have 55,613 :sp:" in snapshot.content
    result = parse_message(snapshot, reply_to_command="shop")
    assert result.fields["perk9_click_max"] == 15
