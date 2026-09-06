"""``$ov`` — the player's own settings sheet.

The live dump this is built on was captured on Key Server 0. Its ``$persrare``
reads ``none``, which is the value **one** rather than a missing value — the
setting is a rarity multiplier, and Mudae writes one as ``none`` because
multiplying by one changes nothing. A set one prints as ``x2``.
"""

from __future__ import annotations

import pytest

from gui.bridge import profile_fields_from_parse, profile_kind_from_parse
from gui.server_profiles import ServerProfileStore
from macro.advisor import bw_advisory
from mudae.commands import detect_command_from_response
from mudae.parsers.classify import classify_message
from mudae.parsers.ov import (
    is_ov_response,
    parse_ov,
    parse_persrare,
    persrare_rerolls,
)
from mudae.parsers.ov_catalog import (
    OV_FIELD_KEYS,
    fields_to_ov_display_dict,
    format_ov_value,
    format_persrare,
)
from mudae.parsers.pipeline import parse_message
from mudae.types import MessageKind, MudaeMessageSnapshot
from tests.mudae_sheet_fixtures import BONUS_REPLY_PART1, OV_REPLY, SETTINGS_REPLY

MUDAE_ID = 432610292342587392


def _snapshot(content: str) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=1,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ID,
        author_name="Mudae",
        is_mudae=True,
        content=content,
        embeds=[],
        buttons=[],
        created_at="19:45:01",
    )


# --- the live sheet ---------------------------------------------------------


def test_the_live_sheet_parses_every_line_with_no_warnings():
    result = parse_ov(OV_REPLY)
    assert result.kind == MessageKind.OV
    assert result.warnings == []
    missing = [key for key in OV_FIELD_KEYS if result.fields.get(key) is None]
    assert missing == []


def test_the_header_supplies_player_premium():
    assert parse_ov(OV_REPLY).fields["player_premium"] == 2


def test_values_coerce_by_shape():
    fields = parse_ov(OV_REPLY).fields
    assert fields["kakeradm"] is True
    assert fields["toggleletters"] is False
    # `$persrare` is a multiplier whose lowest setting is 1, which Mudae writes
    # as "none" because multiplying by one changes nothing — so this is a value,
    # not a missing one.
    assert fields["persrare"] == 1
    # A row of per-wish-kind flags, not one value.
    assert fields["wishdm"] == ["n", "n", "n"]
    # Phrases stay phrases: nothing here is a number in disguise.
    assert fields["rollsleft"] == "below the image"
    assert fields["perstogglebutton"] == "depend on the $togglebutton value"


def test_the_three_rdmimg_toggles_stay_three_fields():
    """The reason ``$ov`` cannot key a field on its command suffix.

    Random images, GIF/WebP and custom images all print ``($rdmimg)``. Keying on
    the command would collapse them to one field holding whichever came last —
    and they do not even agree, so the collapse would be visible as a wrong
    answer rather than a harmless one.
    """
    fields = parse_ov(OV_REPLY).fields
    assert fields["rdmimg_random"] is False
    assert fields["rdmimg_gif_webp"] is True
    assert fields["rdmimg_custom"] is True


def test_a_command_given_as_a_value_still_resolves():
    """``· Character pool limits: see $limroul`` has no ``($cmd)`` suffix."""
    assert parse_ov(OV_REPLY).fields["limroul"] == "see $limroul"


def test_the_summary_names_the_field_that_matters():
    summary = parse_ov(OV_REPLY).summary
    assert summary.startswith("$ov")
    assert "$persrare none" in summary
    assert "17/17 fields" in summary


# --- telling it apart from the other sheets ---------------------------------


def test_the_detector_accepts_the_player_sheet_and_nothing_else():
    assert is_ov_response(OV_REPLY)
    assert not is_ov_response(SETTINGS_REPLY)
    assert not is_ov_response(BONUS_REPLY_PART1)
    assert not is_ov_response("")


def test_the_header_alone_is_not_enough():
    """Narrow on purpose: the sheet is quotable and the classifier runs on text."""
    assert not is_ov_response("Player Settings are over there")


def test_the_player_sheet_is_no_longer_read_as_a_claim():
    """The regression this parser exists to fix.

    Before it, ``$ov`` fell through to ``is_custom_claim`` — a wall of bold
    values reads as a wall of bold names — and the live capture classified as
    ``claim`` with a ``winner`` of "Player Settings".
    """
    assert classify_message(_snapshot(OV_REPLY)) == MessageKind.OV


def test_the_sheet_is_detected_as_the_ov_command():
    assert detect_command_from_response(OV_REPLY) == "ov"


def test_the_pipeline_parses_it_as_a_reply_to_the_command_we_sent():
    result = parse_message(_snapshot(OV_REPLY), reply_to_command="ov")
    assert result.kind == MessageKind.COMMAND_RESPONSE
    assert result.fields["persrare"] == 1
    assert result.fields["command"] == "ov"


def test_the_pipeline_parses_it_unprompted_too():
    """A sheet someone fetched by hand arrives with no command paired to it."""
    result = parse_message(_snapshot(OV_REPLY))
    assert result.fields.get("persrare") == 1


# --- $persrare, the one field with consequences -----------------------------


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        # One is printed as "none", not "x1".
        ("none", 1),
        ("None", 1),
        ("x2", 2),
        ("X10", 10),
        # Tolerated for a sheet that arrives without the multiplier sign.
        ("3", 3),
        # Unrecognised wording abstains rather than guessing a number.
        ("low", None),
        ("x", None),
        ("", None),
    ],
)
def test_persrare_reads_mudaes_own_wording(printed, expected):
    assert parse_persrare(printed) == expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [(1, 1), (4, 4), ("none", 1), ("x2", 2), (0, None), (None, None), ("low", None)],
)
def test_a_stored_persrare_converts_for_the_sweep(stored, expected):
    assert persrare_rerolls(stored) == expected


def test_a_set_persrare_reads_as_its_multiplier():
    text = OV_REPLY.replace(
        "Increased rarity for owned characters: **none** ($persrare)",
        "Increased rarity for owned characters: **x2** ($persrare)",
    )
    result = parse_ov(text)
    assert result.warnings == []
    assert result.fields["persrare"] == 2


def test_persrare_renders_back_to_mudaes_wording():
    """Stored as a number so the sweep can use it, shown as Mudae prints it so
    the panel still reads like the sheet."""
    assert format_persrare(1) == "none"
    assert format_persrare(2) == "x2"
    assert format_ov_value("persrare", 1) == "none"
    assert format_ov_value("persrare", 4) == "x4"


def test_a_persrare_we_do_not_recognise_is_kept_verbatim():
    text = OV_REPLY.replace(
        "Increased rarity for owned characters: **none** ($persrare)",
        "Increased rarity for owned characters: **quite a lot** ($persrare)",
    )
    fields = parse_ov(text).fields
    assert fields["persrare"] == "quite a lot"
    assert persrare_rerolls(fields["persrare"]) is None


# --- when Mudae rewords the sheet -------------------------------------------


def test_an_unknown_label_under_a_unique_command_still_lands():
    text = OV_REPLY.replace(
        "Kakera badges notifications:", "Kakera badge alerts:"
    )
    result = parse_ov(text)
    assert result.fields["kakeradm"] is True
    assert result.warnings == []


def test_an_unknown_label_under_a_shared_command_is_positional_and_says_so():
    text = OV_REPLY.replace(
        "GIFs and WebP displayed when you roll:", "Animated images:"
    )
    result = parse_ov(text)
    # They print in a fixed order, so the second $rdmimg line is still the
    # second field — but the reader is told the match was by position.
    assert result.fields["rdmimg_gif_webp"] is True
    assert any("read positionally" in w for w in result.warnings)


def test_a_line_naming_a_command_we_do_not_know_warns_instead_of_vanishing():
    text = OV_REPLY + "\n· Something brand new: **enabled** ($somethingnew)"
    result = parse_ov(text)
    assert any("$somethingnew" in w for w in result.warnings)
    # And nothing else is disturbed.
    assert result.fields["persrare"] == 1


def test_a_sheet_with_no_bullets_abstains():
    result = parse_ov("**⚒️ __Player Settings__** ⚒️\n($persrare)")
    assert result.warnings
    assert all(value is None for value in result.fields.values())


# --- display ----------------------------------------------------------------


def test_the_display_dict_groups_the_sheet_and_counts_what_arrived():
    payload = fields_to_ov_display_dict(parse_ov(OV_REPLY).fields)
    assert payload["field_count"] == len(OV_FIELD_KEYS)
    titles = [section["title"] for section in payload["sections"]]
    assert titles == ["Account", "Spawns", "Wishes and notifications", "Roll display"]


def test_an_unfetched_sheet_renders_every_row_as_unset():
    """Unlike ``$bonus``, a missing ``$ov`` row is news — the sheet prints a
    fixed list, so a blank one means Mudae stopped printing it."""
    payload = fields_to_ov_display_dict({})
    assert payload["field_count"] == 0
    rows = [row for section in payload["sections"] for row in section["rows"]]
    assert len(rows) == len(OV_FIELD_KEYS)
    assert all(row["display"] == "—" for row in rows)


def test_booleans_and_flag_rows_format_for_a_reader():
    assert format_ov_value("kakeradm", True) == "enabled"
    assert format_ov_value("toggleletters", False) == "disabled"
    assert format_ov_value("wishdm", ["n", "n", "n"]) == "n n n"


# --- storage ----------------------------------------------------------------


def test_the_sheet_is_stored_per_account_and_never_shared():
    store = ServerProfileStore()
    sid = store.add_server("Key Server 0")
    cid = store.add_channel(sid, "mudae-w", "999")
    store.apply_parsed(
        999,
        kind="ov",
        fields=parse_ov(OV_REPLY).fields,
        summary="$ov · Premium 2",
        account_id="main",
    )
    channel = store.find_channel(sid, cid)
    assert channel is not None
    assert store.account_sheet(channel, "ov", account_id="main").fields["persrare"] == 1
    # A second account on the same channel has its own $ov, which it has not
    # fetched — and nothing infers one for it.
    other = store.account_sheet(channel, "ov", account_id="alt")
    assert other.present is False
    assert other.inferred is False


def test_a_sheet_with_no_account_to_credit_is_dropped_rather_than_guessed():
    """``$ov`` has no pre-split blob to fall back on, so there is nowhere honest
    to file an unattributed sheet."""
    store = ServerProfileStore()
    sid = store.add_server("S")
    cid = store.add_channel(sid, "mudae", "999")
    store.apply_parsed(999, kind="ov", fields={"persrare": 1}, summary="$ov")
    channel = store.find_channel(sid, cid)
    assert channel is not None
    assert channel.ov_by_account == {}


def test_the_stored_sheet_survives_a_settings_round_trip():
    store = ServerProfileStore()
    sid = store.add_server("S")
    store.add_channel(sid, "mudae", "999")
    store.apply_parsed(
        999, kind="ov", fields={"persrare": 3}, summary="$ov", account_id="main"
    )
    reloaded = ServerProfileStore()
    reloaded.load_from_settings(store.to_settings_fragment())
    channel = reloaded.find_channel_by_discord_id(999)[1]
    assert reloaded.account_sheet(channel, "ov", account_id="main").fields == {
        "persrare": 3
    }


def test_a_parsed_ov_routes_to_the_ov_slot_of_the_profile_store():
    parsed = parse_ov(OV_REPLY)
    assert profile_kind_from_parse(parsed) == "ov"
    fields = profile_fields_from_parse(parsed, "ov")
    assert fields["persrare"] == 1
    assert "command" not in fields
    assert "response_label" not in fields


def test_the_command_response_form_routes_there_too():
    parsed = parse_message(_snapshot(OV_REPLY), reply_to_command="ov")
    assert profile_kind_from_parse(parsed) == "ov"
    assert profile_fields_from_parse(parsed, "ov")["persrare"] == 1


# --- what the $bw page does with it -----------------------------------------


def _bonus() -> dict:
    return {
        "rolls_per_hour": {
            "base": 21,
            "bonus": 121,
            "net": 83,
            "penalties": {"bw": 19, "bk": 40},
        },
        "wish_spawn_bonus_pct": 440.0,
        "starwish_spawn_bonus_pct": 457.0,
        "extra_key_wish_chance_pct": 79.0,
    }


def _wishlist() -> dict:
    return {
        "entries": [
            {"name": "Lucy", "starwish": True, "sphere_percent": 313, "upgrades": {"4": 6}},
            {"name": "Tanya Degurechaff", "starwish": False, "sphere_percent": 0},
        ],
        "wl_used": 2,
        "complete": True,
    }


def test_the_sweep_takes_persrare_from_the_sheet_over_the_typed_value():
    result = bw_advisory(
        _bonus(),
        wishlist=_wishlist(),
        ov={"persrare": 4},
        options={"persrare_n": 1},
    )
    assert result["options"]["persrare_n"] == 4
    assert result["options"]["persrare_source"] == "ov"
    # And it says the typed value was overruled, rather than changing under you.
    assert any("$persrare is 4" in note for note in result["notes"])


def test_an_unset_persrare_still_comes_from_the_sheet():
    """``none`` is an answer, not a gap: it is a multiplier of one."""
    result = bw_advisory(_bonus(), wishlist=_wishlist(), ov={"persrare": 1})
    assert result["options"]["persrare_n"] == 1
    assert result["options"]["persrare_source"] == "ov"
    assert result["inputs"]["ov"]["ready"] is True


def test_without_the_sheet_the_typed_value_stands():
    result = bw_advisory(_bonus(), wishlist=_wishlist(), options={"persrare_n": 3})
    assert result["options"]["persrare_n"] == 3
    assert result["options"]["persrare_source"] == "manual"
    assert result["inputs"]["ov"]["ready"] is False
    assert result["inputs"]["ov"]["required"] is False


def test_a_persrare_we_cannot_read_keeps_the_typed_value_and_says_why():
    result = bw_advisory(
        _bonus(),
        wishlist=_wishlist(),
        ov={"persrare": "somewhat"},
        options={"persrare_n": 2},
    )
    assert result["options"]["persrare_n"] == 2
    assert result["options"]["persrare_source"] == "manual"
    assert any("does not" in note and "somewhat" in note for note in result["notes"])


def test_ov_is_never_required_for_a_curve():
    """At N = 1 the reroll correction is the identity, so an unfetched ``$ov``
    costs the model nothing — which is why it is not in ``REQUIRED_SHEETS``."""
    without = bw_advisory(_bonus(), wishlist=_wishlist())
    with_none = bw_advisory(_bonus(), wishlist=_wishlist(), ov={"persrare": 1})
    assert without["available"] is True
    assert without["optimum"] == with_none["optimum"]
    assert without["sweep"]["points"] == with_none["sweep"]["points"]
