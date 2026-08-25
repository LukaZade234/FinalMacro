"""Parsers for account-global ``$p`` and ``$daily`` replies."""

from mudae.commands import detect_command_from_response
from mudae.parsers.p_daily import (
    is_daily_cooldown_response,
    is_p_response,
    parse_daily,
    parse_p,
)
from mudae.parsers.pipeline import parse_message
from mudae.types import MessageKind, MudaeMessageSnapshot

MUDAE_ID = 432610292342587392

P_WIN = (
    ":wooper::wooper::wooper:   \U0001f514\n"
    ":deino::vulpix::clefairy:   \u274c\n"
    ":carnivine::beautifly::dracovish:   \u274c\n"
    "lukijade: :pokenew: You won :wooper: Wooper"
)
P_WIN_LIVE = (
    "<:Shelmet:1><:Shelmet:2><:Shelmet:3>   \U0001f514\n"
    "<:Mewtwo:4><:Spiritomb:5><:Gengar:6>   \u274c\n"
    "lukazade234: You won \U0001f41a Shelmet"
)
P_COOLDOWN = "Remaining time before your next $p: 1h 41 min."
P_COOLDOWN_BOLD = "Remaining time before your next $p: **1h 41** min."
DAILY_COOLDOWN = "Next $daily reset in 20h 00 min."
DAILY_COOLDOWN_BOLD = "Next $daily reset in **20h 00** min."
TU_WITH_DAILY = (
    "**lukazade234**, you __can__ claim right now! The next claim reset is in **12** min.\n"
    "You have **29** rolls left. Next rolls reset in **12** min.\n"
    "Next $daily reset in **17h 13** min.\n"
)


def _snap(content: str) -> MudaeMessageSnapshot:
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
        created_at="01:19:00",
    )


def test_parse_p_win():
    result = parse_p(P_WIN)
    assert result.kind == MessageKind.P
    assert result.fields["p_success"] is True
    assert "p_cooldown_minutes" not in result.fields
    assert is_p_response(P_WIN)


def test_parse_p_win_live_custom_emojis():
    result = parse_p(P_WIN_LIVE)
    assert result.fields["p_success"] is True
    assert is_p_response(P_WIN_LIVE)


def test_parse_p_cooldown_plain_and_bold():
    for text in (P_COOLDOWN, P_COOLDOWN_BOLD):
        result = parse_p(text)
        assert result.fields["p_success"] is False
        assert result.fields["p_cooldown_minutes"] == 1 * 60 + 41


def test_parse_daily_cooldown_plain_and_bold():
    for text in (DAILY_COOLDOWN, DAILY_COOLDOWN_BOLD):
        result = parse_daily(text)
        assert result.kind == MessageKind.DAILY
        assert result.fields["daily_success"] is False
        assert result.fields["daily_cooldown_minutes"] == 20 * 60
        assert is_daily_cooldown_response(text)


def test_daily_cooldown_is_not_a_tu_blob():
    assert is_daily_cooldown_response(TU_WITH_DAILY) is False
    assert detect_command_from_response(TU_WITH_DAILY) == "tu"
    assert detect_command_from_response(DAILY_COOLDOWN) == "daily"
    assert detect_command_from_response(P_COOLDOWN) == "p"


def test_pipeline_parses_p_and_daily_from_command_context():
    p_result = parse_message(_snap(P_WIN), reply_to_command="p")
    assert p_result.fields["p_success"] is True
    assert (p_result.fields.get("command") or "").lower() == "p"

    daily_result = parse_message(_snap(DAILY_COOLDOWN), reply_to_command="daily")
    assert daily_result.fields["daily_cooldown_minutes"] == 1200
    assert (daily_result.fields.get("command") or "").lower() == "daily"


def test_pipeline_classifies_unsolicited_p_cooldown():
    result = parse_message(_snap(P_COOLDOWN))
    assert result.fields["p_cooldown_minutes"] == 101
    assert result.fields.get("p_success") is False
