"""Parser unit tests (no Discord connection required)."""

from mudae.command_context import CommandContextTracker, PendingReply, extract_command
from mudae.parsers.bonus import parse_bonus
from mudae.commands import detect_command_from_response, normalize_command, resolve_command
from mudae.parsers.kakera import parse_kakera_claim
from mudae.parsers.marriage import parse_marriage
from mudae.parsers.pipeline import format_entry_for_gui, parse_message, parse_mudae_message
from mudae.parsers.settings import parse_settings
from mudae.parsers.tu import parse_tu
from mudae.types import MessageKind, MudaeMessageSnapshot

MUDAE_ALT_ID = 432610292342587392
TU_REPLY = (
    "**lukazade234**, you __can__ claim right now! The next claim reset is in **12** min.\n"
    "You have **29** rolls (+**5** $mk) left. Next rolls reset in **12** min.\n"
    "Power: **92%**\n\n"
    "$rt is available!\n"
    "**1** $dk available. Next in **8h 23** min.\n\n"
    "Next $daily reset in **17h 13** min.\n"
    "You may vote again in **9h 14** min."
)


def test_parse_tu_full_en():
    content = (
        "**Luki**, you __can__ claim right now! "
        "The next claim reset is in **26** min. "
        "You have **29** rolls (+**5** $mk) left. "
        "Next rolls reset in **26** min. "
        "Power: **88%**. "
        "$rt is available! "
        "**1** $dk available. Next in **8h 37** min."
    )
    result = parse_tu(content)
    assert result.kind == MessageKind.TU
    assert result.fields["claim_available"] is True
    assert result.fields["next_claim_reset_minutes"] == 26
    assert result.fields["rolls_left"] == 29
    assert result.fields["rolls_mk_bonus"] == 5
    assert result.fields["rolls_reset_minutes"] == 26
    assert result.fields["power_percent"] == 88
    assert result.fields["rt_available"] is True
    assert result.fields["dk_stock"] == 1
    assert result.fields["dk_next_minutes"] == 8 * 60 + 37
    assert "29 rolls" in result.summary
    assert "can claim" in result.summary


def test_parse_tu_with_us_bonus():
    content = (
        "**User**, you can't claim for another **30** min. "
        "You have **0** rolls (+**20** $us) left. "
        "Next rolls reset in **42** min."
    )
    result = parse_tu(content)
    assert result.fields["rolls_left"] == 0
    assert result.fields["rolls_us_bonus"] == 20
    assert "rolls_mk_bonus" not in result.fields
    assert result.fields["rolls_reset_minutes"] == 42


def test_parse_tu_rolls_reset_not_daily_reset():
    """Rolls reset is hourly; must not pick ``Next $daily reset in **7h 57** min``."""
    content = (
        "**lukazade234**, you __can__ claim right now! "
        "The next claim reset is in **44** min.\n"
        "You have **0** rolls (+**2** $mk) left. Next rolls reset in **44** min.\n"
        "Next $daily reset in **7h 57** min.\n"
        "You can react to kakera right now!\n"
        "Power: **31%**"
    )
    result = parse_tu(content)
    assert result.fields["next_claim_reset_minutes"] == 44
    assert result.fields["rolls_reset_minutes"] == 44
    assert result.fields["rolls_left"] == 0
    assert result.fields["rolls_mk_bonus"] == 2
    assert "477" not in result.summary


def test_parse_tu_us_bonus_without_left_keyword():
    content = "**User**, you __can__ claim! You have **0** rolls (+**13** $us)."
    result = parse_tu(content)
    assert result.fields["rolls_left"] == 0
    assert result.fields["rolls_us_bonus"] == 13


def test_parse_roll_limit_message():
    from mudae.parsers.roll_limit import is_roll_limit_message, parse_roll_limit

    content = (
        "lukazade234, the roulette is limited to 30 uses per hour. 34 min left.\n"
        "Upvote Mudae to reset the timer: $vote. Website: https://mudae.net/\n"
        "Get a bonus when rolling with slash commands: type $search slash"
    )
    assert is_roll_limit_message(content) is True
    result = parse_roll_limit(content)
    assert result.kind == MessageKind.ROLL_LIMIT
    assert result.fields["rolls_left"] == 0
    assert result.fields["rolls_exhausted"] is True
    assert result.fields["hourly_roll_limit"] == 30
    assert result.fields["rolls_reset_minutes"] == 34
    assert "refill in 34m" in result.summary


def test_roll_limit_wins_over_roll_command_context():
    content = (
        "lukazade234, the roulette is limited to 30 uses per hour. 34 min left."
    )
    snapshot = MudaeMessageSnapshot(
        message_id=8,
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
        created_at="12:00:00",
    )
    result = parse_message(snapshot, reply_to_command="wa")
    assert result.kind == MessageKind.ROLL_LIMIT
    assert result.fields["rolls_reset_minutes"] == 34


def test_parse_minigame_exhausted_message():
    from mudae.parsers.minigame_exhausted import (
        format_exhausted_activity,
        is_minigame_exhausted_message,
        parse_minigame_exhausted,
    )

    content = (
        "You don't have enough $oh for today. "
        "Time to wait before the refill: 3h 08 min."
    )
    assert is_minigame_exhausted_message(content) is True
    result = parse_minigame_exhausted(content)
    assert result.kind == MessageKind.MINIGAME_EXHAUSTED
    assert result.fields["game"] == "oh"
    assert result.fields["exhausted"] is True
    assert result.fields["refill_minutes"] == 3 * 60 + 8
    assert result.summary == "$oh: out of minigames for today · refill in 3h 08 min"
    assert format_exhausted_activity(result.fields) == result.summary


def test_parse_minigame_exhausted_oc_oq_ot():
    from mudae.parsers.minigame_exhausted import parse_minigame_exhausted

    for game in ("oc", "oq", "ot"):
        content = (
            f"You don't have enough ${game} for today. "
            "Time to wait before the refill: 45 min."
        )
        result = parse_minigame_exhausted(content)
        assert result.fields["game"] == game
        assert result.fields["refill_minutes"] == 45
        assert f"${game}: out of minigames for today" in result.summary


def test_minigame_exhausted_wins_over_oh_command_context():
    content = (
        "You don't have enough $oh for today. "
        "Time to wait before the refill: 3h 08 min."
    )
    snapshot = MudaeMessageSnapshot(
        message_id=9,
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
        created_at="12:00:00",
    )
    result = parse_message(snapshot, reply_to_command="oh")
    assert result.kind == MessageKind.MINIGAME_EXHAUSTED
    assert result.fields["game"] == "oh"
    assert result.fields["refill_minutes"] == 188


def test_parse_us_stack_response():
    from mudae.parsers.us import is_us_stack_response, parse_us, parse_us_stacked

    content = (
        "<:rollstack:633217516461883404> You have **7,872.8** rolls stacked.\n"
        "Syntax: **$us <number of stacked rolls to use>**\n"
        "(Value between 1 and 20)"
    )
    assert parse_us_stacked(content) == 7872.8
    assert is_us_stack_response(content) is True
    assert is_us_stack_response("plain message") is False

    result = parse_us(content)
    assert result.fields["us_stacked"] == 7872.8


def test_us_response_detected_in_pipeline():
    content = "<:rollstack:1> You have **5** rolls stacked. (Value between 1 and 20)"
    snapshot = MudaeMessageSnapshot(
        message_id=7,
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
        created_at="12:00:00",
    )
    result = parse_message(snapshot, reply_to_command="us")
    assert result.fields["us_stacked"] == 5.0


def test_parse_tu_without_optional_fields():
    content = (
        "**User**, you __can__ claim! "
        "You have **12** rolls left. "
        "Power: **100%**."
    )
    result = parse_tu(content)
    assert result.fields["rolls_left"] == 12
    assert result.fields["claim_available"] is True
    assert "rt_available" not in result.fields
    assert "rolls_mk_bonus" not in result.fields
    assert "dk_stock" not in result.fields


def test_parse_tu_dk_available_without_count():
    content = "**User**, you __can__ claim! You have **3** rolls left. $dk available."
    result = parse_tu(content)
    assert result.fields["dk_stock"] == 1


def test_parse_tu_legacy_en():
    content = (
        "**User**, you __can__ claim! You have **12** rolls left. "
        "$rt is available. You __can__ react to kakera. "
        "**3** $dk available. Power: **100%**."
    )
    result = parse_tu(content)
    assert result.kind == MessageKind.TU
    assert result.fields["rolls_left"] == 12
    assert result.fields["claim_available"] is True
    assert result.fields["rt_available"] is True
    assert result.fields["kakera_react_available"] is True
    assert result.fields["dk_stock"] == 3


def test_parse_sphere_click():
    from mudae.parsers.classify import classify_message
    from mudae.parsers.sphere import parse_sphere_click

    content = "<:spB:1437140639987929108> **lukazade234 +72**  (1/15)"
    snapshot = MudaeMessageSnapshot(
        message_id=101,
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
        created_at="01:05:00",
    )
    assert classify_message(snapshot) == MessageKind.SPHERE_CLICK
    result = parse_sphere_click(content)
    assert result.fields["sphere_type"] == "spB"
    assert result.fields["claimed_by"] == "lukazade234"
    assert result.fields["amount"] == 72


def test_parse_sphere_click_megasphere():
    from mudae.parsers.sphere import parse_sphere_click

    content = "<:spM:1473308463441379428> **player +120**  (2/15)"
    result = parse_sphere_click(content)
    assert result.fields["sphere_type"] == "spM"
    assert result.fields["amount"] == 120
    assert result.fields["daily_used"] == 2
    assert result.fields["daily_max"] == 15


def test_parse_kakera_claim():
    content = "<:kakeraT:123> TestUser +546 ($k)"
    result = parse_kakera_claim(content)
    assert result.fields["amount"] == 546
    assert result.fields["claimed_by"] == "TestUser"
    assert result.fields["kakera_type"] == "kakeraT"
    assert "Kakera claim" in result.summary
    assert result.fields["earn_method"] == "kakera_click"


def test_kakera_claim_parses_spheres():
    content = (
        "<:kakeraO:605112954391887888>**lukazade234 +3,828** ($k) "
        "**+46** <:sp:1437140700604137554>"
    )
    result = parse_kakera_claim(content)
    assert result.fields["amount"] == 3828
    assert result.fields["spheres"] == 46


def test_kakera_claim_white_breakdown():
    content = (
        "<:kakeraL:815961697918779422>breaks down into"
        "<:kakeraT:609264180851376132>+<:kakera:469791929106956298>"
        "+<:kakera:469791929106956298>+<:kakeraG:609264166381027329>"
        " => **lukazade234 +5,934** ($k)"
    )
    result = parse_kakera_claim(content)
    assert result.fields["kakera_type"] == "kakeraL"
    assert result.fields["amount"] == 5934
    assert result.fields["claimed_by"] == "lukazade234"
    assert result.fields["earn_method"] == "kakera_click"
    assert "raw_content" not in result.fields


def test_kakera_claim_white_breakdown_with_spheres():
    content = (
        "<:kakeraL:815961697918779422>breaks down into<:kakeraT:123>+<:kakera:456>"
        " => **lukazade234 +100** ($k) **+12** <:sp:1437140700604137554>"
    )
    result = parse_kakera_claim(content)
    assert result.fields["kakera_type"] == "kakeraL"
    assert result.fields["amount"] == 100
    assert result.fields["claimed_by"] == "lukazade234"
    assert result.fields["spheres"] == 12


def test_kakera_claim_parses_spheres_3618():
    content = (
        "<:kakeraO:605112954391887888>**lukazade234 +3,618** ($k) "
        "**+46** <:sp:1437140700604137554>"
    )
    result = parse_kakera_claim(content)
    assert result.fields == {
        "earn_method": "kakera_click",
        "kakera_type": "kakeraO",
        "amount": 3618,
        "spheres": 46,
        "claimed_by": "lukazade234",
    }
    assert "raw_content" not in result.fields


def test_kakera_claim_gui_label():
    from mudae.parsers.classify import classify_message

    content = (
        "<:kakeraO:605112954391887888>**lukazade234 +3,828** ($k) "
        "**+46** <:sp:1437140700604137554>"
    )
    snapshot = MudaeMessageSnapshot(
        message_id=70,
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
        created_at="12:05:00",
    )
    assert classify_message(snapshot) == MessageKind.KAKERA_CLAIM
    parsed = parse_mudae_message(snapshot)
    assert parsed.kind == MessageKind.KAKERA_CLAIM
    assert parsed.fields["amount"] == 3828
    gui = format_entry_for_gui(snapshot, parsed)
    assert gui["kind"] == "kakera claim"


def test_parse_marriage():
    content = "💖 Winner and Rem are now married!"
    result = parse_marriage(content)
    assert result.fields["winner"] == "Winner"
    assert result.fields["character"] == "Rem"
    assert "raw_content" not in result.fields
    assert "kakera" not in result.fields
    assert "spheres" not in result.fields


def test_parse_custom_claim_arbitrary_text_sums_kakera():
    from mudae.parsers.claim import parse_claim
    from mudae.parsers.classify import classify_message

    content = (
        "**lukazade234** yoinked **Evernight Goddess**\n"
        "**+59**<:kakera:469835869059153940>(Emerald IV bonus) +**30** <:sp:1437140700604137554>\n"
        "**+575**<:kakera:469835869059153940>(Bronze IV bonus)"
    )
    snapshot = MudaeMessageSnapshot(
        message_id=90,
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
        created_at="12:20:00",
    )
    assert classify_message(snapshot) == MessageKind.CLAIM
    result = parse_claim(content)
    assert result.kind == MessageKind.CLAIM
    assert result.fields["winner"] == "lukazade234"
    assert result.fields["character"] == "Evernight Goddess"
    assert result.fields["kakera"] == 634
    assert result.fields["spheres"] == 30
    assert len(result.fields["kakera_bonuses"]) == 2
    assert "claim_style" not in result.fields


def test_parse_custom_claim_names_anywhere_in_sentence():
    from mudae.parsers.claim import parse_claim, is_custom_claim

    content = (
        "Finally! After years of searching, **lukazade234** has secured "
        "**Evernight Goddess** for the collection!"
    )
    assert is_custom_claim(content)
    result = parse_claim(content)
    assert result.fields["winner"] == "lukazade234"
    assert result.fields["character"] == "Evernight Goddess"


def test_parse_roll_wished_by():
    from mudae.parsers.roll import parse_roll

    embed = {
        "title": "",
        "author": "Evernight Goddess",
        "description": (
            "Lord of the Mysteries\n"
            "Claims: #11,237\n"
            "Likes: #12,653\n"
            "**51**<:kakera:469835869059153940>"
        ),
        "footer": "Evernight Goddess / Lord of the - 51 ka",
        "image_url": "https://mudae.net/uploads/8799063/q56ROpr~8fLxgmJ.png",
    }
    snapshot = MudaeMessageSnapshot(
        message_id=91,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="Wished by <@554009750375890945>",
        embeds=[embed],
        buttons=[
            {
                "label": "",
                "emoji": "\ud83d\udc98",
                "custom_id": "1506071029863157850p1378357044624494662p0",
                "kind": "other",
                "disabled": False,
            }
        ],
        created_at="12:19:00",
    )
    result = parse_roll(snapshot)
    assert result.fields["wished_by"] == [554009750375890945]
    assert result.fields["can_claim"] is True
    assert result.fields["has_claim_button"] is True
    assert "wished by 1" in result.summary


def test_parse_roll_five_wishers():
    from mudae.parsers.roll import parse_roll

    wishers = [
        111111111111111111,
        222222222222222222,
        333333333333333333,
        444444444444444444,
        555555555555555555,
    ]
    pings = " ".join(f"<@{user_id}>" for user_id in wishers)
    snapshot = MudaeMessageSnapshot(
        message_id=92,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=f"Wished by {pings}",
        embeds=[
            {
                "author": "Evernight Goddess",
                "description": "Lord of the Mysteries\n**51**<:kakera:469835869059153940>",
                "footer": "",
            }
        ],
        buttons=[],
        created_at="12:19:30",
    )
    result = parse_roll(snapshot)
    assert result.fields["wished_by"] == wishers
    assert "wished by 5" in result.summary


def test_claim_context_confirms_matching_embed_edit():
    from mudae.claim_context import ClaimContextTracker

    tracker = ClaimContextTracker()
    assert (
        tracker.try_confirm_embed(
            99,
            character_name="Evernight Goddess",
            owner="lukazade234",
        )
        is None
    )
    tracker.register(99, winner="lukazade234", character="Evernight Goddess")
    confirmed = tracker.try_confirm_embed(
        99,
        character_name="Evernight Goddess",
        owner="lukazade234",
    )
    assert confirmed is not None
    assert confirmed.winner == "lukazade234"
    assert (
        tracker.try_confirm_embed(
            99,
            character_name="Evernight Goddess",
            owner="lukazade234",
        )
        is None
    )


def test_claim_context_rejects_wrong_owner():
    from mudae.claim_context import ClaimContextTracker

    tracker = ClaimContextTracker()
    tracker.register(99, winner="lukazade234", character="Evernight Goddess")
    assert (
        tracker.try_confirm_embed(
            99,
            character_name="Evernight Goddess",
            owner="someone_else",
        )
        is None
    )
    assert (
        tracker.try_confirm_embed(
            99,
            character_name="Evernight Goddess",
            owner="lukazade234",
        )
        is not None
    )


def test_parse_roll_ownership_embed_edit():
    from mudae.parsers.classify import classify_message
    from mudae.parsers.roll import parse_roll_ownership

    embed = {
        "author": "Evernight Goddess",
        "description": "Lord of the Mysteries\nClaims: #11,237",
        "footer": "Belongs to lukazade234",
    }
    snapshot = MudaeMessageSnapshot(
        message_id=91,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[embed],
        buttons=[],
        created_at="12:21:00",
        edited=True,
    )
    assert classify_message(snapshot) == MessageKind.ROLL_OWNERSHIP
    result = parse_roll_ownership(snapshot)
    assert result.fields["owner"] == "lukazade234"
    assert result.fields["via_embed_edit"] is True


def test_parse_marriage_kakera_and_spheres():
    content = (
        "💖 **lukazade234** and **Saya Kisaragi** are now married! 💖\n"
        "**+248**<:kakera:469835869059153940>(Emerald IV bonus) +**68** <:sp:1437140700604137554>"
    )
    result = parse_marriage(content)
    assert result.fields["winner"] == "lukazade234"
    assert result.fields["character"] == "Saya Kisaragi"
    assert result.fields["kakera"] == 248
    assert result.fields["spheres"] == 68
    assert "raw_content" not in result.fields
    assert "+248 kakera" in result.summary
    assert "+68 sp" in result.summary


def test_parse_claim_interval():
    from mudae.parsers.claim_interval import parse_claim_interval
    from mudae.parsers.classify import classify_message

    content = (
        "<@554009750375890945>, For this server, you can claim once per interval of 1h. "
        "The next interval begins in **24** min."
    )
    snapshot = MudaeMessageSnapshot(
        message_id=80,
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
        created_at="12:10:00",
    )
    assert classify_message(snapshot) == MessageKind.CLAIM_INTERVAL
    result = parse_claim_interval(content)
    assert result.fields["user_id"] == 554009750375890945
    assert result.fields["interval_hours"] == 1
    assert result.fields["next_interval_minutes"] == 24


def test_parse_claim_interval_three_hours():
    from mudae.parsers.claim_interval import parse_claim_interval

    content = (
        "<@111222333444555666>, For this server, you can claim once per interval of 3h. "
        "The next interval begins in **90** min."
    )
    result = parse_claim_interval(content)
    assert result.fields["user_id"] == 111222333444555666
    assert result.fields["interval_hours"] == 3
    assert result.fields["next_interval_minutes"] == 90


def test_parse_marriage_strips_markdown():
    content = "💖 **lukazade234** and **Spice Girl** are now married! 💖"
    result = parse_marriage(content)
    assert result.fields["winner"] == "lukazade234"
    assert result.fields["character"] == "Spice Girl"


def test_extract_command():
    assert extract_command("$tu") == "tu"
    assert extract_command("$daily foo") == "daily"
    assert extract_command("hello") is None


def test_command_aliases():
    assert normalize_command("setting") == "settings"
    assert normalize_command("settings") == "settings"


def test_detect_settings_from_response():
    assert detect_command_from_response(SETTINGS_REPLY) == "settings"


def test_setting_alias_uses_settings_parser():
    snapshot = MudaeMessageSnapshot(
        message_id=4,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=SETTINGS_REPLY,
        embeds=[],
        buttons=[],
        created_at="12:00:03",
    )
    result = parse_message(snapshot, reply_to_command="setting")
    assert result.fields["command"] == "setting"
    assert result.fields["parser_command"] == "settings"
    assert result.fields["response_label"] == "$setting response"
    assert result.fields["setrolls"] == 21


def test_detect_tu_when_user_typed_unknown_alias():
    snapshot = MudaeMessageSnapshot(
        message_id=5,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=TU_REPLY,
        embeds=[],
        buttons=[],
        created_at="12:00:04",
    )
    result = parse_message(snapshot, reply_to_command="time")
    assert result.fields["command"] == "time"
    assert result.fields["parser_command"] == "tu"
    assert result.fields["detected_command"] == "tu"
    assert result.fields["rolls_left"] == 29


def test_settings_detected_without_pending_command():
    snapshot = MudaeMessageSnapshot(
        message_id=6,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=SETTINGS_REPLY,
        embeds=[],
        buttons=[],
        created_at="12:00:05",
    )
    result = parse_message(snapshot)
    assert result.fields.get("setrolls") == 21 or "setrolls" in str(result.fields)
    resolved = resolve_command(None, SETTINGS_REPLY, known_parsers=frozenset({"tu", "settings"}))
    assert resolved is not None
    assert resolved.parser == "settings"


def test_command_context_links_reply():
    tracker = CommandContextTracker()
    user = MudaeMessageSnapshot(
        message_id=1,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=111,
        author_name="luki",
        is_mudae=False,
        content="$tu",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )
    tracker.observe(user)
    first = tracker.consume(99)
    assert isinstance(first, PendingReply)
    assert first.command == "tu"
    assert first.part == 1
    assert tracker.consume(99) is None


def test_bonus_multipart_tracking():
    tracker = CommandContextTracker()
    user = MudaeMessageSnapshot(
        message_id=10,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=111,
        author_name="luki",
        is_mudae=False,
        content="$bonus",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )
    tracker.observe(user)
    p1 = tracker.consume(99)
    p2 = tracker.consume(99)
    assert p1 == PendingReply(command="bonus", part=1, parts=2)
    assert p2 == PendingReply(command="bonus", part=2, parts=2)
    assert tracker.consume(99) is None


def test_parse_tu_reply_via_command_context():
    snapshot = MudaeMessageSnapshot(
        message_id=2,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=TU_REPLY,
        embeds=[],
        buttons=[],
        created_at="12:00:01",
    )
    result = parse_message(snapshot, reply_to_command="tu")
    assert result.fields["response_label"] == "$tu response"
    assert result.fields["rolls_left"] == 29
    assert result.fields["power_percent"] == 92
    assert result.fields["next_claim_reset_minutes"] == 12
    gui = format_entry_for_gui(snapshot, result)
    assert gui["kind"] == "$tu response"
    assert "29 rolls" in gui["summary"]
    assert "rolls_left" in gui["parsedFields"]


SETTINGS_REPLY = (
    "\U0001f6e0\ufe0f __**Server Settings**__ \U0001f6e0\ufe0f\n"
    "\U0001f31f\U0001f31f\U0001f31f Server Premium 3 \U0001f31f\U0001f31f\U0001f31f\n\n"
    "\u00b7 Prefix: **$** ($prefix)\n"
    "\u00b7 Lang: **en** ($lang)\n"
    "\u00b7 Claim reset: every **60** min. ($setclaim)\n"
    "\u00b7 Exact minute of the reset: xx:**00** ($setinterval)\n"
    "\u00b7 Reset shifted: by +**0** min. ($shifthour)\n"
    "\u00b7 Rolls per hour: **21** ($setrolls)\n"
    "\u00b7 Time before the claim reaction expires: **45** sec. ($settimer)\n"
    "\u00b7 Spawn rarity multiplier for already claimed characters: **10** ($setrare)\n"
    "\u00b7 % kakera bonus: **+100** ($setkakerabonus)\n"
    "\u00b7 % sphere bonus: **+100** ($setspherebonus)\n"
    "\u00b7 Game mode: **2** ($gamemode)\n"
    "\u00b7 $servlimroul = 7,000 $wa, 7,000 $ha, 5,000 $wg, 5,000 $hg\n"
    "\u00b7 This channel instance: **1** ($channelinstance)\n"
    "\u00b7 Slash commands: enabled ($toggleslash)\n\n"
    "\u00b7 Ranking: enabled ($toggleclaimrank/$togglelikerank)\n"
    "\u00b7 Ranks displayed during rolls: claims and likes ($togglerolls)\n"
    "\u00b7 NSFW series: enabled ($togglensfw)\n"
    "\u00b7 Disturbing imagery series: enabled ($toggledisturbing)\n"
    "\u00b7 Child characters: enabled ($togglechildtag)\n"
    "\u00b7 Rolls sniping: 0 ($togglesnipe)\n"
    "\u00b7 Kakera sniping: 0 ($togglekakerasnipe)\n"
    "\u00b7 Limit of characters per collection: **12,000** ($haremlimit)\n"
    "\u00b7 $haremcopy/$kakeracopy/$soulcopy limit: ****disabled**** ($removecopylimit)\n"
    "\u00b7 Claim buttons: ****for all your rolls**** ($togglebutton)\n"
    "\u00b7 Custom buttons: no ($claimreact)\n"
    "\u00b7 Kakera buttons more recognizable: no ($kakerabutton switchset)\n"
    "\u00b7 Sphere buttons more recognizable: no ($spherebutton switchset)\n\n"
    "\u00b7 Kakera trading: enabled ($togglekakeratrade)\n"
    "\u00b7 Kakera calculation: claim and like ranks (and number of claimed characters) "
    "($togglekakeraclaim/$togglekakeralike)\n"
    "\u00b7 Kakera value displayed during rolls: enabled ($togglekakerarolls)\n"
    "\u00b7 $kakeraloots & $ouroperks wishprotect: enabled ($togglewishprotect)\n"
    "\u00b7 $ouroshop freewish: enabled ($togglewishfree)\n"
    "\u00b7 Spheres trading: enabled ($togglespheretrade)"
)


SETTINGS_GM1_PLAIN = (
    "\U0001f6e0\ufe0f Server Settings \U0001f6e0\ufe0f\n"
    "\U0001f31f\U0001f31f\U0001f31f Server Premium 3 \U0001f31f\U0001f31f\U0001f31f\n\n"
    "\u00b7 Prefix: $ ($prefix)\n"
    "\u00b7 Lang: en ($lang)\n"
    "\u00b7 Claim reset: every 60 min. ($setclaim)\n"
    "\u00b7 Exact minute of the reset: xx:00 ($setinterval)\n"
    "\u00b7 Reset shifted: by +0 min. ($shifthour)\n"
    "\u00b7 Rolls per hour: 21 ($setrolls)\n"
    "\u00b7 Time before the claim reaction expires: 45 sec. ($settimer)\n"
    "\u00b7 Spawn rarity multiplier for already claimed characters: 10 ($setrare)\n"
    "\u00b7 % kakera bonus: +100 ($setkakerabonus)\n"
    "\u00b7 % sphere bonus: +100 ($setspherebonus)\n"
    "\u00b7 Game mode: 1 ($gamemode)\n"
    "\u00b7 This channel instance: 1 ($channelinstance)\n"
    "\u00b7 Slash commands: enabled ($toggleslash)\n\n"
    "\u00b7 Ranking: enabled ($toggleclaimrank/$togglelikerank)\n"
    "\u00b7 Ranks displayed during rolls: claims and likes ($togglerolls)\n"
    "\u00b7 NSFW series: enabled ($togglensfw)\n"
    "\u00b7 Disturbing imagery series: enabled ($toggledisturbing)\n"
    "\u00b7 Child characters: enabled ($togglechildtag)\n"
    "\u00b7 Rolls sniping: 0 ($togglesnipe)\n"
    "\u00b7 Kakera sniping: 0 ($togglekakerasnipe)\n"
    "\u00b7 Limit of characters per collection: 12,000 ($haremlimit)\n"
    "\u00b7 $haremcopy/$kakeracopy/$soulcopy limit: disabled ($removecopylimit)\n"
    "\u00b7 Claim buttons: for all your rolls ($togglebutton)\n"
    "\u00b7 Custom buttons: no ($claimreact)\n"
    "\u00b7 Kakera buttons more recognizable: no ($kakerabutton switchset)\n"
    "\u00b7 Sphere buttons more recognizable: no ($spherebutton switchset)\n\n"
    "\u00b7 Kakera trading: enabled ($togglekakeratrade)\n"
    "\u00b7 Kakera calculation: claim and like ranks (and number of claimed characters) "
    "($togglekakeraclaim/$togglekakeralike)\n"
    "\u00b7 Kakera value displayed during rolls: enabled ($togglekakerarolls)\n"
    "\u00b7 $kakeraloots & $ouroperks wishprotect: enabled ($togglewishprotect)\n"
    "\u00b7 $ouroshop freewish: enabled ($togglewishfree)\n"
    "\u00b7 Spheres trading: enabled ($togglespheretrade)"
)


def test_parse_settings_gamemode1_plain():
    result = parse_settings(SETTINGS_GM1_PLAIN)
    assert detect_command_from_response(SETTINGS_GM1_PLAIN) == "settings"
    assert result.fields["gamemode"] == 1
    assert result.fields["servlimroul"] is None
    assert result.fields["setrolls"] == 21
    assert result.fields["togglewishfree"] is True
    assert result.fields["haremlimit"] == 12000


def test_parse_settings_full():
    result = parse_settings(SETTINGS_REPLY)
    assert result.fields["server_premium"] == 3
    assert result.fields["prefix"] == "$"
    assert result.fields["lang"] == "en"
    assert result.fields["setclaim"] == 60
    assert result.fields["setinterval"] == 0
    assert result.fields["shifthour"] == 0
    assert result.fields["setrolls"] == 21
    assert result.fields["settimer"] == 45
    assert result.fields["setrare"] == 10
    assert result.fields["setkakerabonus"] == 100
    assert result.fields["setspherebonus"] == 100
    assert result.fields["gamemode"] == 2
    assert result.fields["servlimroul"] == {
        "wa": 7000,
        "ha": 7000,
        "wg": 5000,
        "hg": 5000,
    }
    assert result.fields["channelinstance"] == 1
    assert result.fields["toggleslash"] is True
    assert result.fields["toggleclaimrank"] is True
    assert result.fields["togglelikerank"] is True
    assert result.fields["togglerolls"] == "claims and likes"
    assert result.fields["toggleclaimrolls"] is True
    assert result.fields["togglelikerolls"] is True
    assert result.fields["removecopylimit"] is False
    assert result.fields["togglebutton"] == 2
    assert result.fields["claimreact"] is False
    assert result.fields["haremlimit"] == 12000
    assert result.fields["togglesnipe"] == {"mode": 0, "seconds": None}
    assert result.fields["togglekakerasnipe"] == {"mode": 0, "seconds": None}
    assert result.fields["togglespheretrade"] is True


def test_settings_command_response_caches_setrolls():
    from mudae.channel_cache import get_setrolls

    snapshot = MudaeMessageSnapshot(
        message_id=30,
        channel_id=42,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=SETTINGS_GM1_PLAIN,
        embeds=[],
        buttons=[],
        created_at="12:01:00",
    )
    result = parse_message(snapshot, reply_to_command="settings")
    assert result.fields["setrolls"] == 21
    assert get_setrolls(42) == 21


def test_bonus_uses_cached_settings_after_command_response():
    from mudae.channel_cache import remember_settings

    channel_id = 77
    remember_settings(channel_id, {"setrolls": 21, "gamemode": 1})
    line = (
        "Rolls per hour: +91 (6 $k + 69 $kl + 6 $kt + 10 premium) "
        "-60 ($bw) -22 ($bk)"
    )
    snapshot = MudaeMessageSnapshot(
        message_id=31,
        channel_id=channel_id,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=f"· {line}",
        embeds=[],
        buttons=[],
        created_at="12:01:01",
    )
    result = parse_message(snapshot, reply_to_command="bonus", reply_part=1, reply_parts=2)
    assert result.fields.get("cached_settings") is True
    assert result.fields["rolls_per_hour"] == 30
    assert result.fields["bk"] == 22
    assert result.fields["bw"] == 60


def test_parse_settings_via_command_context():
    snapshot = MudaeMessageSnapshot(
        message_id=3,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=SETTINGS_REPLY,
        embeds=[],
        buttons=[],
        created_at="12:00:02",
    )
    result = parse_message(snapshot, reply_to_command="settings")
    assert result.fields["response_label"] == "$settings response"
    assert result.fields["setrolls"] == 21
    gui = format_entry_for_gui(snapshot, result)
    assert gui["kind"] == "$settings response"
    assert "setrolls" in gui["parsedFields"]


BONUS_REPLY_PART1 = (
    "<:morekakera:633217512057864192> \u00b7 Additional bonus for kakera buttons: **+47%** ($bk)\n"
    "<:morekakera:633217512057864192> \u00b7 Additional bonus for kakera buttons on starwishes: **+52%** ($sw)\n"
    "<:kakeraL:815961697918779422> \u00b7 Random kakera per light kakera: **10-11** (7 $kt)\n"
    "<:kakeraR:605112980295647242> \u00b7 Additional kakera on the final value of red and rainbow: **750** ($kt)\n"
    "<:kakeraC:1441097472587075758> \u00b7 Additional kakera on the initial value of chaos: **825** ($kt)\n"
    "<:bku:1163913181920497755> \u00b7 Chance to complete + reset $bku on $sw: **+236%** ($kl) (this interval: 15.38%)\n"
    "<:chaoskey:690110264166842421> \u00b7 Chance to get an additional key: **+45%** ($kt)\n"
    "<:sp:1437140700604137554> \u00b7 Additional sphere sources: claims = **34**, $dk = **34**, Bronze IV = **24**, $rolls = **14** ($kt)\n"
    "<:sp:1437140700604137554> \u00b7 Additional spheres: **+14** (spheres clicked + premium)\n"
    "<:sp:1437140700604137554> \u00b7 $oh daily bonus: **+2,552** spheres, **134.5%** to get 1 $oq ($op) and **3%** $ot ($shop)\n"
    "<:spM:1473308463441379428> \u00b7 Megaspheres: **15** rewards and **12**% chance to be free ($shop)"
)


def test_parse_rolls_per_hour_bonus_line():
    from mudae.channel_cache import remember_settings

    remember_settings(99, {"setrolls": 21})
    line = (
        "Rolls per hour: +91 (6 $k + 69 $kl + 6 $kt + 10 premium) "
        "-60 ($bw) -22 ($bk)"
    )
    result = parse_bonus(f"· {line}", channel_id=99)
    assert result.fields["bw"] == 60
    assert result.fields["bk"] == 22
    assert result.fields["rolls_per_hour"] == 30
    assert result.fields["setrolls_base"] == 21
    assert result.fields["rolls_per_hour_bonus_sum"] == 91


def test_parse_bonus_lines():
    result = parse_bonus(BONUS_REPLY_PART1, part=1, parts=2)
    assert result.fields["line_count"] == 11
    assert result.fields["part"] == 1
    assert result.fields["bk"] == 47
    assert result.fields["sw"] == 52
    assert result.fields["kl"] == 236
    assert result.fields["additional_sphere_sources_claims"] == 34
    assert result.fields["additional_sphere_sources_dk"] == 34
    assert result.fields["additional_sphere_sources_bronze_iv"] == 24
    assert result.fields["additional_sphere_sources_rolls"] == 14
    assert "entries" not in result.fields
    assert "by_command" not in result.fields


def test_parse_bonus_two_messages():
    snapshot = MudaeMessageSnapshot(
        message_id=20,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content=BONUS_REPLY_PART1,
        embeds=[],
        buttons=[],
        created_at="12:00:10",
    )
    r1 = parse_message(snapshot, reply_to_command="bonus", reply_part=1, reply_parts=2)
    r2 = parse_message(snapshot, reply_to_command="bonus", reply_part=2, reply_parts=2)
    assert r1.fields["response_label"] == "$bonus response (1/2)"
    assert r2.fields["response_label"] == "$bonus response (2/2)"
    assert r1.fields["bk"] == 47


def test_user_command_message_label():
    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=111,
        author_name="luki",
        is_mudae=False,
        content="$tu",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
    )
    result = parse_message(snapshot)
    assert result.kind == MessageKind.COMMAND
    assert result.summary == "$tu"


VIOLET_ROLL_EMBED = {
    "title": "",
    "author": "Violet Evergarden",
    "description": (
        "Violet Evergarden\n"
        "<:chaoskey:690110264166842421> (**77**) +5% kakera value\n"
        "Claims: #20\n"
        "Likes: #33\n"
        "**5,762**<:kakera:469835869059153940>"
    ),
    "footer": "(\ud83d\udd1177)  \u00b7 Belongs to lukazade234",
    "image_url": "https://cdn.imgchest.com/files/ab7cf283ddd7.png",
}


def test_roll_command_aliases():
    from mudae.commands import is_roll_command, normalize_command

    assert normalize_command("wa") == "roll"
    assert normalize_command("wx") == "roll"
    assert normalize_command("hb") == "roll"
    assert is_roll_command("ma")


def test_parse_wa_roll_response():
    snapshot = MudaeMessageSnapshot(
        message_id=40,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[VIOLET_ROLL_EMBED],
        buttons=[
            {
                "label": "",
                "emoji": "kakeraO",
                "custom_id": "1506016781930725398k1473101129184186552k0",
                "kind": "kakera",
                "disabled": False,
            }
        ],
        created_at="12:02:00",
    )
    result = parse_message(snapshot, reply_to_command="wa")
    assert result.fields["response_label"] == "$wa response"
    assert result.fields["parser_command"] == "roll"
    assert result.fields["character_name"] == "Violet Evergarden"
    assert result.fields["total_kakera"] == 5762
    assert result.fields["claim_rank"] == 20
    assert result.fields["like_rank"] == 33
    assert result.fields["keys"] == [{"type": "chaos", "level": 77}]
    assert result.fields["claimed"] is True
    assert result.fields["owner"] == "lukazade234"
    assert result.fields["has_claim_button"] is False
    assert result.fields["series"] == "Violet Evergarden"
    assert "description" not in result.fields
    assert "kakera_bonus_percent" not in result.fields
    assert "individual_kakera" not in result.fields


SAKI_ROLL_EMBED = {
    "title": "",
    "author": "Saki Tenma",
    "description": (
        "Project SEKAI: Colorful Stage!\n"
        "<:chaoskey:690110264166842421> (**17**) +5% kakera value\n"
        "Claims: #1,734\n"
        "Likes: #1,578\n"
        "**346**<:kakera:469835869059153940>"
    ),
    "footer": "(\ud83d\udd1117)  \u00b7 Belongs to lukazade234",
    "image_url": "https://mudae.net/uploads/1019129/CvUFQCr~32ZFh93.png",
}


LUCY_ROLL_EMBED = {
    "title": "",
    "author": "Lucy",
    "description": (
        "Cyberpunk: Edgerunners <:sw:1163913219782492220>\n"
        "<:bku:1163913181920497755> $bku completed and reset!\n"
        "**61.5%** chance to happen again if you roll\n"
        "another starwish before the next $bku reset.\n"
        "**+17,760**<:kakera:469835869059153940>\n"
        "<:chaoskey:690110264166842421> (**241**) +5% kakera value\n"
        "Claims: #91\n"
        "Likes: #170\n"
        "**13,781**<:kakera:469835869059153940>"
    ),
    "footer": "Belongs to lukazade234",
    "image_url": "https://cdn.imgchest.com/files/b36c7a9a3196.png",
}


MIKU_ROLL_EMBED = {
    "title": "",
    "author": "Hatsune Miku",
    "description": (
        "VOCALOID <:sw:1163913219782492220>\n"
        "<:bku:1163913181920497755> $bku completed and reset!\n"
        "**3.84%** chance to happen again if you roll\n"
        "another starwish before the next $bku reset.\n"
        "**+8,880**<:kakera:469835869059153940>\n"
        "<:chaoskey:690110264166842421> (**169**) +5% kakera value\n"
        "<:chaoskey:690110264166842421> (**170**) +5% kakera value\n"
        "**+5** default kakera value\n"
        "<:omegakey:1473308158263951582> **+1** \n"
        "Claims: #1\n"
        "Likes: #4\n"
        "**15,998**<:kakera:469835869059153940>"
    ),
    "footer": "23\ud83d\udd34 \u2611\ufe0f  (\u2b50170)  \u2013  3.84% \u00b7 Belongs to lukazade234",
    "image_url": "https://cdn.imgchest.com/files/c37946253974.png",
}


def test_parse_lucy_starwish_and_bku():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=60,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[LUCY_ROLL_EMBED],
        buttons=[],
        created_at="12:04:00",
    )
    result = parse_roll(snapshot)
    assert result.fields["series"] == "Cyberpunk: Edgerunners"
    assert result.fields["starwish"] is True
    assert result.fields["bku"] == 17760
    assert result.fields["bku_reset"] is True
    assert result.fields["total_kakera"] == 13781
    assert result.fields["claim_rank"] == 91


def test_parse_miku_omega_keys():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=61,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[MIKU_ROLL_EMBED],
        buttons=[],
        created_at="12:04:30",
    )
    result = parse_roll(snapshot)
    assert result.fields["keys"] == [
        {"type": "chaos", "level": 169},
        {"type": "chaos", "level": 170},
    ]
    assert result.fields["omega_keys"] == [{"gain": 1}]
    assert result.fields["starwish"] is True
    assert result.fields["bku"] == 8880
    assert result.fields["bku_reset"] is True
    assert result.fields["total_kakera"] == 15998
    assert result.fields["spheres"] == 23
    assert "omega +1" in result.summary


PATTY_BKU_ROLL_EMBED = {
    "title": "",
    "author": "Patty Thompson",
    "description": (
        "Soul Eater\n"
        "**+197**<:kakera:469835869059153940>\n"
        "<:goldkey:689475859429720211> (**9**) +10% kakera value\n"
        "Claims: #1,644\n"
        "Likes: #2,250"
    ),
    "footer": "Belongs to lukazade234",
    "image_url": "https://mudae.net/uploads/5704019/r_Qvkbk~83a1b398ffee.png",
}


SPICE_GIRL_UNCLAIMED_EMBED = {
    "title": "",
    "author": "Spice Girl",
    "description": (
        "JoJo's Bizarre Adventure: Golden\n"
        "Wind\n"
        "Claims: #3,338\n"
        "Likes: #16,447\n"
        "**57**<:kakera:469835869059153940>"
    ),
    "footer": "",
    "image_url": "https://mudae.net/uploads/2511192/OyMAzWh~KxbkBbF.png",
}

SPICE_GIRL_CLAIM_BUTTON = {
    "label": "",
    "emoji": "\U0001f496",
    "custom_id": "1506031651548037344p1473101129184186552p0",
    "kind": "other",
    "disabled": False,
}


NAMI_ROLL_EMBED = {
    "title": "",
    "author": "Nami",
    "description": (
        "One Piece\n"
        "<:chaoskey:690110264166842421> (**57**) +5% kakera value\n"
        "<:chaoskey:690110264166842421> (**58**) +5% kakera value\n"
        "Claims: #8\n"
        "Likes: #6\n"
        "**5,281**<:kakera:469835869059153940>\n"
        "9<:sp:1437140700604137554>"
    ),
    "footer": "Belongs to lukazade234",
    "image_url": "https://cdn.imgchest.com/files/c1a08ec9fc10.png",
}


TWO_B_ROLL_EMBED = {
    "title": "",
    "author": "2B",
    "description": (
        "NieR: Automata <:sw:1163913219782492220>\n"
        "<:chaoskey:690110264166842421> (**69**) +5% kakera value\n"
        "Claims: #11\n"
        "Likes: #26\n"
        "**6,494**<:kakera:469835869059153940>"
    ),
    "footer": (
        "23\ud83d\udd34 \u2611\ufe0f \u26a0\ufe0f 2 ROLLS LEFT \u26a0\ufe0f "
        "(\u2b5069)  \u00b7 Belongs to lukazade234"
    ),
    "image_url": "https://cdn.imgchest.com/files/3f32ffdf8b03.png",
}


MILDRETTA_SOULMATE_EMBED = {
    "title": "",
    "author": "Mildretta",
    "description": (
        "Gachiakuta\n"
        "Now your **SOULMATE**!\n"
        "<:chaoskey:690110264166842421> (**10**) Kakera button costs are halved\n"
        "on __this__ character for you!\n"
        "**+15** default kakera value\n"
        "Claims: #10,093\n"
        "Likes: #15,239\n"
        "**83**<:kakera:469835869059153940>"
    ),
    "footer": "\u26a0\ufe0f 2 ROLLS LEFT \u26a0\ufe0f \u00b7 Belongs to lukazade234",
    "image_url": "https://mudae.net/uploads/2175234/PPHbCJn~ki4bILE.png",
}


def test_parse_2b_rolls_left_warning_in_footer():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=64,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[TWO_B_ROLL_EMBED],
        buttons=[
            {
                "label": "",
                "emoji": "kakeraY",
                "custom_id": "1506066968577577080k1473101129184186552k0",
                "kind": "kakera",
                "disabled": False,
            }
        ],
        created_at="12:06:30",
    )
    result = parse_roll(snapshot)
    assert result.fields["rolls_left"] == 2
    assert result.fields["spheres"] == 23
    assert result.fields["starwish"] is True
    assert result.fields["character_name"] == "2B"
    assert result.fields["total_kakera"] == 6494
    assert "2 rolls left" in result.summary


def test_parse_mildretta_new_soulmate():
    import json
    import tempfile
    from pathlib import Path

    from mudae.parsers.roll import parse_roll
    import mudae.soulmate_log as soulmate_log

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "soulmate_log.json"
        soulmate_log._LOG_PATH = log_path
        soulmate_log._events = []
        soulmate_log.set_recording_account("roller1", "Main Roller")

        snapshot = MudaeMessageSnapshot(
            message_id=65,
            channel_id=99,
            channel_name="mudae",
            guild_id=42,
            guild_name="Test Guild",
            author_id=MUDAE_ALT_ID,
            author_name="Mudae",
            is_mudae=True,
            content="",
            embeds=[MILDRETTA_SOULMATE_EMBED],
            buttons=[
                {
                    "label": "",
                    "emoji": "kakeraY",
                    "custom_id": "1506037113039093943k1473101129184186552k0",
                    "kind": "kakera",
                    "disabled": False,
                }
            ],
            created_at="12:07:00",
        )
        result = parse_roll(snapshot)
        assert result.fields["new_soulmate"] is True
        assert result.fields["rolls_left"] == 2
        assert result.fields["claimed"] is True
        assert result.fields["owner"] == "lukazade234"
        assert result.fields["series"] == "Gachiakuta"
        assert "new soulmate" in result.summary
        assert "2 rolls left" in result.summary

        assert log_path.is_file()
        logged = json.loads(log_path.read_text())
        assert len(logged) == 1
        assert logged[0]["character_name"] == "Mildretta"
        assert logged[0]["guild_name"] == "Test Guild"
        assert logged[0]["series"] == "Gachiakuta"
        assert logged[0]["account_id"] == "roller1"
        assert logged[0]["account_name"] == "Main Roller"
        soulmate_log.clear_recording_account()


NACCHAN_ROLL_EMBED = {
    "title": "",
    "author": "Nacchan",
    "description": (
        "Futsu no KuraNata <:sw:1163913219782492220>\n"
        "<:chaoskey:690110264166842421> (**208**) +5% kakera value\n"
        "<:chaoskey:690110264166842421> (**209**) +5% kakera value\n"
        "Claims: #6,750\n"
        "Likes: #5,051\n"
        "**5,473**<:kakera:469835869059153940>"
    ),
    "footer": "23\ud83d\udd34 \u2611\ufe0f  (\u2b50209)  \u00b7 Belongs to lukazade234",
    "image_url": "https://mudae.net/uploads/4811159/OScfpJA~t2wZc7Z.png",
}


NAZUNA_PERK8_EMBED = {
    "title": "",
    "author": "Nazuna Nanakusa",
    "description": (
        "Yofukashi no Uta\n"
        "**+875**<:kakera:469835869059153940>\n"
        "<:chaoskey:690110264166842421> (**24**) +5% kakera value\n"
        "<:chaoskey:690110264166842421> (**25**) +5% kakera value\n"
        "**+10** default kakera value\n"
        "A **second kakera** button has 25% chance\n"
        "to appear under this character!\n"
        "Claims: #229\n"
        "Likes: #383"
    ),
    "footer": "\U0001f48e/2 \u200b  (\U0001f51125)  \u00b7 Belongs to lukazade234",
    "image_url": "https://mudae.net/uploads/6633892/E0Pbvye~iC98YWr.png",
}

NAZUNA_PERK8_BUTTONS = [
    {
        "label": "",
        "emoji": "spY",
        "custom_id": "1506055193668620328s1378357044624494662s0",
        "kind": "other",
        "disabled": False,
    },
    {
        "label": "",
        "emoji": "kakeraO",
        "custom_id": "1506055193668620328k1378357044624494662k1",
        "kind": "kakera",
        "disabled": False,
    },
    {
        "label": "",
        "emoji": "kakeraY",
        "custom_id": "1506055193668620328k1378357044624494662k2",
        "kind": "kakera",
        "disabled": False,
    },
]


def test_parse_perk_6_spawn():
    from mudae.parsers.pipeline import parse_mudae_message

    embed = {
        "title": "",
        "author": "Han Ah-Reun",
        "description": (
            "My Bias Gets on the Last Train\n"
            "<:chaoskey:690110264166842421> (**54**) +5% kakera value\n"
            "<:omegakey:1473308158263951582> **+6** \n"
            "Claims: #25,917\n"
            "Likes: #54,275\n"
            "**518**<:kakera:469835869059153940>\n"
            "<:spG:1437140664193126441> **[SPAWNED BY TRISSY]**"
        ),
        "footer": "(\ud83d\udd1154)  \u00b7 Belongs to lukazade234",
        "image_url": "https://mudae.net/uploads/9939054/YjFUoYh~6fYqsaPcE.png",
    }
    snapshot = MudaeMessageSnapshot(
        message_id=100,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[embed],
        buttons=[
            {
                "label": "",
                "emoji": "kakeraL",
                "custom_id": "1506078075027193967wk1473101129184186552k0",
                "kind": "kakera",
                "disabled": False,
            }
        ],
        created_at="23:36:34",
    )
    result = parse_mudae_message(snapshot)
    assert result.fields["perk_6"] is True
    assert result.fields["spawned_by"] == "TRISSY"
    assert result.fields["character_name"] == "Han Ah-Reun"
    assert result.fields["omega_keys"] == [{"gain": 6}]
    assert result.fields["total_kakera"] == 518
    assert "perk 6 spawn" in result.summary
    assert "TRISSY" in result.summary
    assert "Han Ah-Reun" in result.summary
    assert "Kakera Buttons" not in result.summary


def test_parse_omega_keys_ignores_pr_profile_inventory():
    from mudae.parsers.kakera import parse_omega_keys

    pr_desc = (
        "Collection size: 1,617 (100%:female: 0% :male:)\n"
        "Keys: 3,154:bronzekey: 4,656:silverkey: 5,877:goldkey: 33,122:chaoskey:\n"
        "84 :omegakey:\n\n711 :sp:\n"
        "Mudapins: 2,347/2,347\n"
    )
    assert parse_omega_keys(pr_desc) == []


def test_parse_omega_keys_ignores_ohu8_sphere_stock():
    from mudae.parsers.kakera import parse_omega_keys

    ohu_desc = (
        "0 $oh left for today, 0 $oc, 0 $oq and 0 $ot (+3 stored).\n"
        "Stock: 711 :sp:\n"
        "(Perk 8) Clicked today: 40/40. Rolled today: 37/123\n"
    )
    assert parse_omega_keys(ohu_desc) == []


def test_parse_perk_6_akame_spawned_by_power():
    from mudae.parsers.kakera import parse_keys, parse_omega_keys
    from mudae.parsers.pipeline import parse_mudae_message
    from mudae.parsers.roll import perk6_spawner_matches

    embed = {
        "author": "Akame",
        "description": (
            "Akame ga Kill!\n"
            ":chaoskey: (98) +5% kakera value\n"
            ":omegakey: +6\n"
            "Claims: #29\n"
            "Likes: #30\n"
            "7,033:kakera:\n"
            "<:spG:1437140664193126441> **[SPAWNED BY POWER]**"
        ),
        "footer": "",
    }
    snapshot = MudaeMessageSnapshot(
        message_id=101,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[embed],
        buttons=[],
        created_at="20:00:00",
    )
    assert parse_keys(embed["description"]) == [{"type": "chaos", "level": 98}]
    assert parse_omega_keys(embed["description"]) == [{"gain": 6}]
    result = parse_mudae_message(snapshot)
    assert result.fields["perk_6"] is True
    assert result.fields["spawned_by"] == "POWER"
    assert result.fields["is_perk_6_spawn"] is True
    assert result.fields["character_name"] == "Akame"
    assert result.fields["keys"] == [{"type": "chaos", "level": 98}]
    assert result.fields["omega_keys"] == [{"gain": 6}]
    assert perk6_spawner_matches("POWER", "Power") is True
    assert perk6_spawner_matches("POWER", "Akame") is False


def test_parse_keys_supports_comma_separated_levels():
    from macro.rule_eval import passes_kakera_reaction
    from macro.config import KakeraReactionRules
    from macro.state import AccountState
    from mudae.parsers.kakera import parse_keys

    desc = (
        "Chainsaw Man\n"
        ":chaoskey: (1,004) +5% kakera value\n"
        ":chaoskey: (1,005) +5% kakera value\n"
        "Claims: #34\n"
        "Likes: #47\n"
        "76,363:kakera:\n"
    )
    keys = parse_keys(desc)
    assert keys == [
        {"type": "chaos", "level": 1004},
        {"type": "chaos", "level": 1005},
    ]

    embed = {
        "author": "Reze",
        "description": desc,
        "footer": "23🔴 ☑️  (⭐1,005)  · Belongs to lukazade234",
    }
    fields = {
        "character_name": embed["author"],
        "keys": keys,
        "buttons": [
            {
                "emoji": "kakeraR",
                "is_kakera": True,
                "disabled": False,
                "custom_id": "k1",
            }
        ],
    }

    rules = KakeraReactionRules(enabled=True, require_chaos_key=True)
    decision = passes_kakera_reaction(
        fields,
        rules,
        AccountState(),
    )
    assert decision.should_click


def test_perk6_spawner_name_matching():
    from mudae.parsers.roll import perk6_spawner_matches

    assert perk6_spawner_matches("TRISSY", "Trissy") is True
    assert perk6_spawner_matches("POWER", "power") is True
    assert perk6_spawner_matches(None, "Power") is False


def test_parse_nazuna_perk_8_and_sphere_button():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=67,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[NAZUNA_PERK8_EMBED],
        buttons=NAZUNA_PERK8_BUTTONS,
        created_at="12:12:00",
    )
    result = parse_roll(snapshot)
    assert result.fields["perk_8"] is True
    assert result.fields["spheres"] is None
    assert result.fields["bku"] == 875
    assert result.fields["claimed"] is True
    assert result.fields["has_sphere_button"] is True
    buttons = result.fields["buttons"]
    assert buttons[0]["kind"] == "sphere"
    assert buttons[0]["is_sphere"] is True
    assert buttons[0]["emoji"] == "spY"
    assert buttons[1]["is_kakera"] is True
    assert buttons[1]["is_sphere"] is False


def test_parse_nacchan_spheres_in_footer():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=66,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[NACCHAN_ROLL_EMBED],
        buttons=[],
        created_at="12:11:00",
    )
    result = parse_roll(snapshot)
    assert result.fields["spheres"] == 23
    assert result.fields["starwish"] is True
    assert result.fields["total_kakera"] == 5473


def test_parse_nami_spheres():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=64,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[NAMI_ROLL_EMBED],
        buttons=[
            {
                "label": "",
                "emoji": "kakeraY",
                "custom_id": "1506035986860216351k1473101129184186552k0",
                "kind": "kakera",
                "disabled": False,
            }
        ],
        created_at="12:06:00",
    )
    result = parse_roll(snapshot)
    assert result.fields["series"] == "One Piece"
    assert result.fields["total_kakera"] == 5281
    assert result.fields["spheres"] == 9
    assert result.fields["claimed"] is True
    assert result.fields["owner"] == "lukazade234"
    assert len(result.fields["keys"]) == 2


def test_parse_spice_girl_unclaimed():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=62,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[SPICE_GIRL_UNCLAIMED_EMBED],
        buttons=[SPICE_GIRL_CLAIM_BUTTON],
        created_at="12:05:00",
    )
    result = parse_roll(snapshot)
    assert result.fields["claimed"] is False
    assert result.fields["owner"] is None
    assert result.fields["can_claim"] is True
    assert result.fields["has_claim_button"] is True
    assert result.fields["total_kakera"] == 57
    assert len(result.fields["buttons"]) == 1
    btn = result.fields["buttons"][0]
    assert btn["is_claim"] is True
    assert btn["kind"] == "claim"
    assert btn["emoji"] == "\U0001f496"
    assert btn["custom_id"] == SPICE_GIRL_CLAIM_BUTTON["custom_id"]
    assert btn["interaction"] == "click"


def test_parse_spice_girl_claimed_footer():
    from mudae.parsers.roll import parse_roll

    embed = dict(SPICE_GIRL_UNCLAIMED_EMBED)
    embed["footer"] = "Belongs to lukazade234"
    snapshot = MudaeMessageSnapshot(
        message_id=63,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[embed],
        buttons=[SPICE_GIRL_CLAIM_BUTTON],
        created_at="12:05:30",
    )
    result = parse_roll(snapshot)
    assert result.fields["claimed"] is True
    assert result.fields["owner"] == "lukazade234"
    assert result.fields["can_claim"] is False


def test_parse_patty_bku_without_reset():
    from mudae.parsers.roll import parse_roll

    snapshot = MudaeMessageSnapshot(
        message_id=61,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[PATTY_BKU_ROLL_EMBED],
        buttons=[],
        created_at="12:04:30",
    )
    result = parse_roll(snapshot)
    assert result.fields["series"] == "Soul Eater"
    assert result.fields["bku"] == 197
    assert result.fields["bku_reset"] is None
    assert result.fields["total_kakera"] == 197
    assert result.fields["starwish"] is False


def test_roll_single_part_tracking():
    from mudae.commands import normalize_command

    tracker = CommandContextTracker()
    user = MudaeMessageSnapshot(
        message_id=50,
        channel_id=88,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=111,
        author_name="luki",
        is_mudae=False,
        content="$wa",
        embeds=[],
        buttons=[],
        created_at="12:03:00",
    )
    tracker.observe(user)
    assert normalize_command("wa") == "roll"
    p1 = tracker.consume(88)
    assert p1 is not None and p1.parts == 1 and p1.part == 1
    assert tracker.consume(88) is None


GODZILLA_ROLL_EMBED = {
    "title": "",
    "author": "Godzilla",
    "description": (
        "Godzilla\n"
        "<:chaoskey:690110264166842421> (**20**) +5% kakera value\n"
        "**+10** default kakera value\n"
        "Claims: #131\n"
        "Likes: #374\n"
        "**984**<:kakera:469835869059153940>"
    ),
    "footer": "(\ud83d\udd1120)  \u00b7 Belongs to lukazade234",
    "image_url": "https://mudae.net/uploads/6367496/SyHLQER~BZMBPJI.png",
}


def test_parse_godzilla_roll_trimmed_fields():
    snapshot = MudaeMessageSnapshot(
        message_id=52,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[GODZILLA_ROLL_EMBED],
        buttons=[{"label": "", "emoji": "kakeraY", "kind": "kakera", "disabled": False}],
        created_at="12:03:02",
    )
    result = parse_message(snapshot, reply_to_command="wa")
    assert result.fields["response_label"] == "$wa response"
    assert result.fields["series"] == "Godzilla"
    assert result.fields["total_kakera"] == 984
    assert "default_kakera_bonus" not in result.fields
    assert result.fields["claim_rank"] == 131
    assert result.fields["keys"] == [{"type": "chaos", "level": 20}]
    assert result.fields["claimed"] is True
    assert result.fields["owner"] == "lukazade234"
    assert "description" not in result.fields
    assert "footer" not in result.fields
    assert "image_url" not in result.fields
    assert "individual_kakera" not in result.fields
    assert "chaos_keys" not in result.fields
    assert "kakera_bonus_percent" not in result.fields


def test_edited_roll_embed_not_ownership_update():
    """Footer edits on roll embeds (owned chars) must stay a roll, not ownership update."""
    from mudae.parsers.classify import classify_message

    embed = {
        "title": "",
        "author": "Kagamine Rin",
        "description": (
            "VOCALOID\n"
            "<:chaoskey:690110264166842421> (**27**) +5% kakera value\n"
            "Claims: #145\n"
            "Likes: #229\n"
            "**1,399**<:kakera:469835869059153940>"
        ),
        "footer": "(\ud83d\udd1127)  \u00b7 Belongs to lukazade234",
        "image_url": "https://mudae.net/uploads/8253914/zRuB7UQ~MPuqt25.png",
    }
    snapshot = MudaeMessageSnapshot(
        message_id=51,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[embed],
        buttons=[],
        created_at="12:03:01",
        edited=True,
    )
    assert classify_message(snapshot) == MessageKind.CHARACTER_EMBED
    result = parse_message(snapshot, reply_to_command="wa")
    assert result.fields["character_name"] == "Kagamine Rin"
    assert result.fields["claimed"] is True
    assert result.fields["owner"] == "lukazade234"
    assert result.fields["total_kakera"] == 1399


def test_parse_saki_roll_series_and_ranks():
    snapshot = MudaeMessageSnapshot(
        message_id=41,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=MUDAE_ALT_ID,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[SAKI_ROLL_EMBED],
        buttons=[
            {
                "label": "",
                "emoji": "kakeraY",
                "kind": "kakera",
                "disabled": False,
            }
        ],
        created_at="12:02:01",
    )
    result = parse_message(snapshot, reply_to_command="wa")
    assert result.fields["response_label"] == "$wa response"
    assert result.fields["series"] == "Project SEKAI: Colorful Stage!"
    assert result.fields["claim_rank"] == 1734
    assert result.fields["like_rank"] == 1578
    assert result.fields["total_kakera"] == 346
    assert result.fields["keys"] == [{"type": "chaos", "level": 17}]
    assert result.fields["claimed"] is True
    assert result.fields["owner"] == "lukazade234"
    assert result.fields["can_claim"] is False


def test_character_embed_pipeline():
    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=2,
        channel_name="mudae",
        guild_id=3,
        guild_name="srv",
        author_id=432618578496954900,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[
            {
                "title": "",
                "author": "Rem",
                "description": "**Re:Zero** · **510** <:kakera:123>",
                "footer": "Belongs to **Nobody**",
                "image_url": "",
            }
        ],
        buttons=[{"label": "", "emoji": "kakeraT", "kind": "kakera", "custom_id": "x", "disabled": False}],
        created_at="12:00:00",
    )
    result = parse_mudae_message(snapshot)
    assert result.kind == MessageKind.KAKERA_BUTTONS
    assert result.fields["character_name"] == "Rem"
    assert result.fields["total_kakera"] == 510
    assert result.fields.get("series") == "Re:Zero"
