"""``$limroul`` — how many characters each roulette can roll.

The line that matters is `Current $limroul: …`. It is the `$bw` sweep's base
pool, which `docs/TODO.md` had listed as the sweep's one guessed input and "the
thing that decides which `$bw` wins".
"""

from __future__ import annotations

import pytest

from gui.bridge import profile_fields_from_parse, profile_kind_from_parse
from gui.bw_options_store import BwOptions
from gui.server_profiles import ServerProfileStore
from macro.advisor import bw_advisory
from mudae.commands import detect_command_from_response
from mudae.parsers.classify import classify_message
from mudae.parsers.limroul import (
    ROULETTES,
    is_limroul_response,
    limits_agree,
    parse_limroul,
)
from mudae.parsers.limroul_catalog import fields_to_limroul_display_dict, pool_size
from mudae.parsers.pipeline import parse_message
from mudae.types import MessageKind, MudaeMessageSnapshot
from tests.mudae_sheet_fixtures import (
    LIMROUL_REPLY,
    OV_REPLY,
    SETTINGS_REPLY,
)

MUDAE_ID = 432610292342587392


def _snapshot(content: str) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=2,
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
        created_at="21:17:00",
    )


def _mixed() -> str:
    """The same sheet with four different limits, which is the case that needs
    a roulette named before a pool can be taken."""
    return LIMROUL_REPLY.replace(
        "Current $limroul: 2,000 $wa, 2,000 $ha, 2,000 $wg, 2,000 $hg",
        "Current $limroul: 7,000 $wa, 4,000 $ha, 5,000 $wg, 1,500 $hg",
    )


# --- the live sheet ---------------------------------------------------------


def test_the_current_line_gives_a_pool_size_per_roulette():
    result = parse_limroul(LIMROUL_REPLY)
    assert result.kind == MessageKind.LIMROUL
    assert result.warnings == []
    assert result.fields["limits"] == {"wa": 2000, "ha": 2000, "wg": 2000, "hg": 2000}


def test_the_example_command_is_read_as_the_servers_ceiling():
    """`$limroul 7000 7000 5000 5000` is the cap, not the player's setting —
    and it is the same figure `$settings` reports as `servlimroul`."""
    fields = parse_limroul(LIMROUL_REPLY).fields
    assert fields["server_max"] == {"wa": 7000, "ha": 7000, "wg": 5000, "hg": 5000}
    assert "7,000 $wa, 7,000 $ha, 5,000 $wg, 5,000 $hg" in SETTINGS_REPLY


def test_the_top_lines_carry_local_and_global_rank():
    """The gap between them is the *server's* disable list: local #2,000 sitting
    at global #3,405 means 1,405 more popular characters are off here."""
    tops = parse_limroul(LIMROUL_REPLY).fields["tops"]
    assert tops["wa"] == {"rank": 2000, "global_rank": 3405}
    assert tops["hg"] == {"rank": 2000, "global_rank": 11077}


def test_four_equal_limits_answer_on_their_own():
    assert parse_limroul(LIMROUL_REPLY).fields["limits_agree"] == 2000


def test_four_different_limits_refuse_to_be_averaged():
    fields = parse_limroul(_mixed()).fields
    assert fields["limits"] == {"wa": 7000, "ha": 4000, "wg": 5000, "hg": 1500}
    assert fields["limits_agree"] is None


def test_the_summary_says_which_case_it_is():
    assert parse_limroul(LIMROUL_REPLY).summary == "$limroul · 2,000 in every roulette"
    assert "7,000 $wa" in parse_limroul(_mixed()).summary


def test_a_sheet_with_no_current_line_abstains_loudly():
    text = LIMROUL_REPLY.replace("Current $limroul:", "Former $limroul:")
    result = parse_limroul(text)
    assert result.fields["limits"] is None
    assert any("Current $limroul" in w for w in result.warnings)
    assert "no pool limits" in result.summary


def test_a_partial_current_line_keeps_what_it_has_and_names_what_it_lost():
    text = LIMROUL_REPLY.replace(
        "Current $limroul: 2,000 $wa, 2,000 $ha, 2,000 $wg, 2,000 $hg",
        "Current $limroul: 2,000 $wa, 2,000 $ha",
    )
    result = parse_limroul(text)
    assert result.fields["limits"] == {"wa": 2000, "ha": 2000}
    assert any("$wg" in w and "$hg" in w for w in result.warnings)


@pytest.mark.parametrize("roulette", ROULETTES)
def test_pool_size_reads_one_roulette(roulette):
    limits = parse_limroul(LIMROUL_REPLY).fields["limits"]
    assert pool_size(limits, roulette) == 2000


def test_limits_agree_needs_all_four():
    assert limits_agree({"wa": 2000, "ha": 2000, "wg": 2000}) is None


# --- telling it apart -------------------------------------------------------


def test_the_detector_wants_the_sheet_not_just_the_word():
    assert is_limroul_response(LIMROUL_REPLY)
    # `$settings` names it as `$servlimroul` and `$ov` points at it; neither is
    # this sheet.
    assert not is_limroul_response(SETTINGS_REPLY)
    assert not is_limroul_response(OV_REPLY)
    assert not is_limroul_response("")


def test_it_classifies_and_detects_as_limroul():
    assert classify_message(_snapshot(LIMROUL_REPLY)) == MessageKind.LIMROUL
    assert detect_command_from_response(LIMROUL_REPLY) == "limroul"


def test_the_pipeline_parses_it_both_ways():
    prompted = parse_message(_snapshot(LIMROUL_REPLY), reply_to_command="limroul")
    assert prompted.fields["limits"]["wa"] == 2000
    unprompted = parse_message(_snapshot(LIMROUL_REPLY))
    assert unprompted.fields["limits"]["wa"] == 2000


# --- storage and display ----------------------------------------------------


def test_it_is_stored_per_account_like_the_other_player_sheets():
    store = ServerProfileStore()
    sid = store.add_server("Key Server 0")
    cid = store.add_channel(sid, "mudae-w", "999")
    store.apply_parsed(
        999,
        kind="limroul",
        fields=parse_limroul(LIMROUL_REPLY).fields,
        summary="$limroul",
        account_id="main",
    )
    channel = store.find_channel(sid, cid)
    assert store.account_sheet(channel, "limroul", account_id="main").fields[
        "limits"
    ] == {"wa": 2000, "ha": 2000, "wg": 2000, "hg": 2000}
    assert store.account_sheet(channel, "limroul", account_id="alt").present is False


def test_a_parsed_limroul_routes_to_its_own_slot():
    parsed = parse_limroul(LIMROUL_REPLY)
    assert profile_kind_from_parse(parsed) == "limroul"
    fields = profile_fields_from_parse(parsed, "limroul")
    assert set(fields) <= {"limits", "server_max", "tops", "limits_agree"}


def test_the_display_puts_one_roulette_on_each_row():
    payload = fields_to_limroul_display_dict(parse_limroul(LIMROUL_REPLY).fields)
    rows = payload["sections"][0]["rows"]
    assert [row["field"] for row in rows] == list(ROULETTES)
    assert rows[0]["display"] == "2,000"
    # The server's own disable list and the ceiling, on the same line.
    assert "global #3,405" in rows[0]["detail"]
    assert "cap 7,000" in rows[0]["detail"]
    assert payload["limits_agree"] == 2000


def test_the_roulette_option_only_accepts_a_real_roulette():
    assert BwOptions.from_dict({"limroul_pool": "$WG"}).limroul_pool == "wg"
    assert BwOptions.from_dict({"limroul_pool": "waifu"}).limroul_pool == ""
    assert BwOptions.from_dict({}).limroul_pool == ""


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


def _wishlist(count: int = 4) -> dict:
    return {
        "entries": [
            {"name": f"C{i}", "starwish": i == 0, "sphere_percent": 0}
            for i in range(count)
        ],
        "wl_used": count,
        "complete": True,
    }


def _limroul(**limits) -> dict:
    return {"limits": limits or {"wa": 2000, "ha": 2000, "wg": 2000, "hg": 2000}}


def test_the_base_pool_is_the_limit_flat():
    """The wishlist is part of the roulette's pool, not something taken out of
    it — the figure goes in exactly as $limroul reports it."""
    out = bw_advisory(_bonus(), wishlist=_wishlist(4), limroul=_limroul())
    assert out["options"]["base_pool"] == 2000
    assert out["options"]["base_pool_source"] == "limroul"
    assert out["options"]["limroul_limit"] == 2000
    assert any("2,000 characters" in note and "$wa" in note for note in out["notes"])


def test_a_wishlist_of_any_size_does_not_move_the_pool():
    small = bw_advisory(_bonus(), wishlist=_wishlist(2), limroul=_limroul())
    large = bw_advisory(_bonus(), wishlist=_wishlist(120), limroul=_limroul())
    assert small["options"]["base_pool"] == large["options"]["base_pool"] == 2000


def test_agreeing_roulettes_need_no_choice_and_are_not_echoed_as_one():
    out = bw_advisory(_bonus(), wishlist=_wishlist(), limroul=_limroul())
    assert out["options"]["limroul_needs_pick"] is False
    assert out["options"]["limroul_agree"] == 2000
    # The stored choice stays blank so the picker does not show an explicit
    # selection nobody made; the roulette actually read is reported separately.
    assert out["options"]["limroul_pool"] == ""
    assert out["options"]["limroul_pool_used"] == "wa"


def test_differing_roulettes_ask_rather_than_average():
    limroul = _limroul(wa=7000, ha=4000, wg=5000, hg=1500)
    out = bw_advisory(
        _bonus(), wishlist=_wishlist(), limroul=limroul, options={"base_pool": 2000}
    )
    assert out["options"]["base_pool_source"] == "manual"
    assert out["options"]["base_pool"] == 2000
    assert out["options"]["limroul_needs_pick"] is True
    assert any("differs by roulette" in note for note in out["notes"])


def test_naming_the_roulette_settles_it():
    limroul = _limroul(wa=7000, ha=4000, wg=5000, hg=1500)
    out = bw_advisory(
        _bonus(),
        wishlist=_wishlist(4),
        limroul=limroul,
        options={"limroul_pool": "hg"},
    )
    assert out["options"]["base_pool"] == 1500
    assert out["options"]["limroul_pool"] == "hg"
    assert out["options"]["limroul_pool_used"] == "hg"
    assert out["options"]["base_pool_source"] == "limroul"


def test_without_the_sheet_the_typed_pool_stands():
    out = bw_advisory(_bonus(), wishlist=_wishlist(), options={"base_pool": 3500})
    assert out["options"]["base_pool"] == 3500
    assert out["options"]["base_pool_source"] == "manual"
    assert out["inputs"]["limroul"]["ready"] is False
    assert out["inputs"]["limroul"]["required"] is False
    assert "$limroul" in out["inputs"]["limroul"]["why"]


def test_a_smaller_pool_concentrates_the_wishlist_and_moves_the_optimum():
    """The pool is what decides which `$bw` wins, which is why reading it beats
    guessing it."""
    small = bw_advisory(
        _bonus(), wishlist=_wishlist(), limroul=_limroul(wa=500, ha=500, wg=500, hg=500)
    )
    large = bw_advisory(
        _bonus(),
        wishlist=_wishlist(),
        limroul=_limroul(wa=20000, ha=20000, wg=20000, hg=20000),
    )
    assert small["optimum"] < large["optimum"]
