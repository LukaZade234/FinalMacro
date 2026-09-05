"""``$bonus`` meaning-key parse against the live Key Server 0 dump."""

from mudae.parsers.bonus import merge_bonus_fields, parse_bonus
from mudae.parsers.bonus_catalog import LATER_BONUS_KEYS, BONUS_MEANING_KEYS
from mudae.parsers.pipeline import parse_message
from mudae.types import MudaeMessageSnapshot
from tests.mudae_sheet_fixtures import BONUS_REPLY_PART1, BONUS_REPLY_PART2

MUDAE_ALT_ID = 432610292342587392


def test_bonus_catalog_marks_later_fields():
    assert "kakera_max_power" in LATER_BONUS_KEYS
    assert "additional_spheres" in LATER_BONUS_KEYS
    assert "sphere_double_chance_pct" in LATER_BONUS_KEYS
    assert "rolls_per_hour" in LATER_BONUS_KEYS
    assert "power_cost_per_kakera_button" in LATER_BONUS_KEYS
    assert "kakera_button_bonus_pct" in BONUS_MEANING_KEYS
    assert "kakera_button_bonus_pct" not in LATER_BONUS_KEYS
    assert "rolls_per_hour_penalty_bw" not in BONUS_MEANING_KEYS


def test_parse_bonus_player_sheet():
    from mudae.channel_cache import remember_settings

    remember_settings(101, {"setrolls": 21})
    result = parse_bonus(BONUS_REPLY_PART1, part=1, parts=2, channel_id=101)
    assert result.fields["line_count"] == 17
    rolls = result.fields["rolls_per_hour"]
    assert rolls["net"] == 62
    assert rolls["bonus"] == 121
    assert rolls["base"] == 21
    assert rolls["sources"] == {"k": 6, "kl": 95, "kt": 10, "premium": 10}
    assert rolls["penalties"] == {"bw": 40, "bk": 40}
    assert result.fields["wishlist_slots"] == 207
    assert result.fields["wishseries_slots"] == 10
    assert result.fields["wish_spawn_bonus_pct"] == 650
    assert result.fields["starwish_spawn_bonus_pct"] == 665
    # The unbolded "(= 1,315%)" that closes the bullet, and the reason we know
    # the field above is the extra on top of wish rather than the total.
    assert result.fields["starwish_spawn_bonus_total_pct"] == 1315
    assert result.fields["wish_spawn_bonus_pct"] + 665 == 1315
    assert result.fields["starwish_slots"] == 15
    assert result.fields["wishprotect_spawn_chance"] == "1/499"
    assert result.fields["rt_cooldown"] == "5h"
    assert result.fields["limroul_animanga"] == -10501
    assert result.fields["limroul_game"] == -7114
    assert result.fields["rank_kakera_bonus_pct"] == 90
    assert result.fields["kakera_earned_bonus_pct"] == {
        "premium_slash": 15,
        "server_premium": 100,
    }
    assert result.fields["kakera_gold_keys_bonus"] == 12360
    assert result.fields["dk_cooldown"] == "10h"
    assert result.fields["mk_per_hour"] == 2
    assert result.fields["kakera_max_power"] == 175
    assert result.fields["power_cost_per_kakera_button"] == 30
    assert "k" not in result.fields
    assert "kt" not in result.fields
    assert "kl" not in result.fields
    assert "unparsed_lines" not in result.fields
    assert not result.warnings


def test_parse_bonus_kakera_sphere_sheet():
    result = parse_bonus(BONUS_REPLY_PART2, part=2, parts=2)
    assert result.fields["line_count"] == 13
    assert result.fields["kakera_button_bonus_pct"] == 65
    assert result.fields["kakera_button_starwish_bonus_pct"] == 64
    assert result.fields["random_kakera"] == {"min": 13, "max": 14}
    assert result.fields["kakera_red_rainbow_bonus"] == 2250
    assert result.fields["kakera_chaos_bonus"] == 1329
    assert result.fields["chaos_kakera_rarity_mult"] == 1.03
    assert result.fields["bku_complete_chance_pct"] == {
        "value": 476,
        "this_interval_pct": 486,
    }
    assert result.fields["extra_key_wish_chance_pct"] == 76
    assert result.fields["sphere_double_chance_pct"] == 2.5
    assert result.fields["additional_sphere_sources"] == {
        "claims": 44,
        "dk": 44,
        "bronze_iv": 34,
        "rolls": 24,
    }
    assert "additional_sphere_sources_claims" not in result.fields
    assert result.fields["additional_spheres"] == 18
    assert result.fields["oh_daily"] == {"spheres": 2800, "oq_pct": 150, "ot_pct": 32}
    assert result.fields["megaspheres"] == {"rewards": 15, "free_pct": 16}
    assert result.fields["source_tags"]["kakera_button_bonus_pct"] == "bk"
    assert "shop_primary" not in result.fields
    assert "kt" not in result.fields
    assert "unparsed_lines" not in result.fields
    assert not result.warnings


def test_merge_bonus_parts_no_command_collision():
    from mudae.channel_cache import remember_settings

    remember_settings(102, {"setrolls": 21})
    p1 = parse_bonus(BONUS_REPLY_PART1, part=1, parts=2, channel_id=102)
    p2 = parse_bonus(BONUS_REPLY_PART2, part=2, parts=2)
    merged = merge_bonus_fields(p1.fields, p2.fields)
    assert merged["kakera_button_bonus_pct"] == 65
    assert merged["rolls_per_hour"]["penalties"]["bk"] == 40
    assert merged["kakera_max_power"] == 175
    assert merged["additional_spheres"] == 18
    assert merged["sphere_double_chance_pct"] == 2.5
    assert merged["rolls_per_hour"]["net"] == 62
    assert "part" not in merged
    assert merged["line_count"] == p1.fields["line_count"] + p2.fields["line_count"]


def test_bonus_display_dict_matches_settings_shape():
    from mudae.channel_cache import remember_settings
    from mudae.parsers.bonus_catalog import fields_to_bonus_display_dict

    remember_settings(103, {"setrolls": 21})
    p1 = parse_bonus(BONUS_REPLY_PART1, part=1, parts=2, channel_id=103)
    p2 = parse_bonus(BONUS_REPLY_PART2, part=2, parts=2)
    merged = merge_bonus_fields(p1.fields, p2.fields)
    display = fields_to_bonus_display_dict(merged)
    assert display["field_count"] > 10
    titles = [section["title"] for section in display["sections"]]
    assert "Rolls & wishes" in titles
    assert "Kakera" in titles
    assert "Spheres" in titles
    rolls = next(
        row
        for section in display["sections"]
        for row in section["rows"]
        if row["field"] == "rolls_per_hour"
    )
    assert rolls["has_value"]
    assert "62/h" in rolls["display"]
    assert "-40 $bw" in rolls["display"]


def test_unknown_bonus_line_warns_and_stores_by_label():
    result = parse_bonus("· Completely new bonus: **99** ($xyz)")
    assert any("Unknown bonus line" in w for w in result.warnings)
    assert result.fields["completely_new_bonus"] == 99
    assert "xyz" not in result.fields
    assert result.fields["unparsed_lines"]


def test_parse_bonus_two_message_labels():
    snapshot = MudaeMessageSnapshot(
        message_id=20,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=BONUS_REPLY_PART2,
        embeds=[],
        buttons=[],
        created_at="12:00:10",
    )
    r1 = parse_message(snapshot, reply_to_command="bonus", reply_part=1, reply_parts=2)
    r2 = parse_message(snapshot, reply_to_command="bonus", reply_part=2, reply_parts=2)
    assert r1.fields["response_label"] == "$bonus response (1/2)"
    assert r2.fields["response_label"] == "$bonus response (2/2)"
    assert r1.fields["kakera_button_bonus_pct"] == 65
