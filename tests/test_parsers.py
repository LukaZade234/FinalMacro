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


def test_parse_kakera_claim():
    content = "<:kakeraT:123> TestUser +546 ($k)"
    result = parse_kakera_claim(content)
    assert result.fields["amount"] == 546
    assert result.fields["claimed_by"] == "TestUser"
    assert result.fields["kakera_type"] == "kakeraT"
    assert "Kakera claim" in result.summary


def test_kakera_claim_parses_spheres():
    content = (
        "<:kakeraO:605112954391887888>**lukazade234 +3,828** ($k) "
        "**+46** <:sp:1437140700604137554>"
    )
    result = parse_kakera_claim(content)
    assert result.fields["amount"] == 3828
    assert result.fields["spheres"] == 46


def test_kakera_claim_parses_spheres_3618():
    content = (
        "<:kakeraO:605112954391887888>**lukazade234 +3,618** ($k) "
        "**+46** <:sp:1437140700604137554>"
    )
    result = parse_kakera_claim(content)
    assert result.fields == {
        "raw_content": content,
        "kakera_type": "kakeraO",
        "amount": 3618,
        "spheres": 46,
        "claimed_by": "lukazade234",
    }


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
    assert "7,000 $wa" in result.fields["servlimroul"]
    assert result.fields["channelinstance"] == 1
    assert result.fields["toggleslash"] is True
    assert result.fields["toggleclaimrank"] is True
    assert result.fields["togglelikerank"] is True
    assert result.fields["togglerolls"] == "claims and likes"
    assert result.fields["removecopylimit"] is False
    assert result.fields["togglebutton"] == "for all your rolls"
    assert result.fields["claimreact"] is False
    assert result.fields["haremlimit"] == 12000
    assert result.fields["togglesnipe"] == 0
    assert result.fields["togglekakerasnipe"] == 0
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
        assert result.fields["claimed"] is True
        assert result.fields["owner"] == "lukazade234"
        assert result.fields["series"] == "Gachiakuta"
        assert "new soulmate" in result.summary

        assert log_path.is_file()
        logged = json.loads(log_path.read_text())
        assert len(logged) == 1
        assert logged[0]["character_name"] == "Mildretta"
        assert logged[0]["guild_name"] == "Test Guild"
        assert logged[0]["series"] == "Gachiakuta"


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
