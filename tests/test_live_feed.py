"""Text-only Discord/Mudae mirror used by the Run live feed."""

from __future__ import annotations

from mudae.live_feed import flatten_discord_text, format_live_feed, format_roll_line
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult


def _snapshot(
    *,
    content: str = "",
    edited: bool = False,
    buttons: list | None = None,
    author: str = "Rem",
    series: str = "Re:Zero",
) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=1,
        channel_id=99,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content=content,
        embeds=[{"author": author, "description": series, "footer": ""}],
        buttons=buttons or [],
        created_at="12:00:00",
        edited=edited,
    )


def test_flatten_discord_text_keeps_emoji_names():
    assert (
        flatten_discord_text("<:kakeraT:123> **TestUser +546** ($k)")
        == ":kakeraT: TestUser +546 ($k)"
    )


def test_format_roll_line_shows_reacts_and_owner():
    line = format_roll_line(
        {
            "character_name": "Nazuna Nanakusa",
            "series": "Yofukashi no Uta",
            "total_kakera": 875,
            "claimed": True,
            "owner": "lukazade234",
            "can_claim": False,
            "buttons": [
                {"emoji": "spY", "kind": "sphere", "is_sphere": True, "disabled": False},
                {"emoji": "kakeraO", "kind": "kakera", "is_kakera": True, "disabled": False},
                {"emoji": "kakeraY", "kind": "kakera", "is_kakera": True, "disabled": False},
            ],
            "keys": [{"type": "chaos", "level": 24}, {"type": "chaos", "level": 25}],
        }
    )
    assert line.startswith("Nazuna Nanakusa · Yofukashi no Uta · 875 ka")
    assert ":kakeraO:" in line
    assert ":kakeraY:" in line
    assert ":spY:" in line
    assert line.count(":kakeraO:") == 1
    assert line.count(":kakeraY:") == 1
    assert "belongs to lukazade234" in line
    assert ":chaoskey: 24" in line
    assert ":chaoskey: 25" in line
    assert "kakera skip" not in line


def test_format_roll_line_keeps_duplicate_kakera_reacts():
    line = format_roll_line(
        {
            "character_name": "Rem",
            "total_kakera": 400,
            "buttons": [
                {"emoji": "kakeraY", "kind": "kakera", "is_kakera": True},
                {"emoji": "kakeraY", "kind": "kakera", "is_kakera": True},
                {"emoji": {"name": "kakeraO"}, "kind": "kakera", "is_kakera": True},
            ],
        }
    )
    assert line.count(":kakeraY:") == 2
    assert line.count(":kakeraO:") == 1
    line = format_roll_line(
        {
            "character_name": "Akame",
            "total_kakera": 518,
            "omega_keys": [{"gain": 6}],
        }
    )
    assert ":omegakey: +6" in line


def test_format_roll_line_unclaimed_omits_missing_reacts():
    line = format_roll_line(
        {
            "character_name": "Spice Girl",
            "series": "JoJo",
            "total_kakera": 57,
            "can_claim": True,
            "claimed": False,
            "buttons": [
                {"emoji": "💖", "kind": "claim", "is_claim": True, "disabled": False},
            ],
        }
    )
    assert line == "Spice Girl · JoJo · 57 ka · unclaimed"


def test_format_roll_line_starwish_and_bku():
    reset = format_roll_line(
        {
            "character_name": "Lucy",
            "total_kakera": 400,
            "starwish": True,
            "bku": 17760,
            "bku_reset": True,
        }
    )
    assert ":starwish:" in reset
    assert ":bku: +17,760" in reset

    gain = format_roll_line(
        {
            "character_name": "Patty",
            "total_kakera": 197,
            "bku": 197,
        }
    )
    assert ":bku:" in gain
    assert ":bku: +" not in gain
    assert ":starwish:" not in gain


def test_flatten_discord_text_starwish_and_bku():
    assert flatten_discord_text("<:sw:1> starred") == ":sw: starred"
    assert flatten_discord_text("<:bku:2> $bku completed") == ":bku: $bku completed"


OWN = ["lukazade234", "LukaZade"]


def test_format_live_feed_kakera_and_sphere():
    kakera = format_live_feed(
        _snapshot(content="<:kakeraT:123> **lukazade234 +546** ($k)"),
        ParseResult(
            kind=MessageKind.KAKERA_CLAIM,
            summary="Kakera claim",
            fields={"claimed_by": "lukazade234"},
        ),
        own_usernames=OWN,
    )
    assert kakera == (":kakeraT: lukazade234 +546 ($k)", "click")

    sphere = format_live_feed(
        _snapshot(content="<:spB:1> **lukazade234 +72**  (1/15)"),
        ParseResult(
            kind=MessageKind.SPHERE_CLICK,
            summary="Sphere click",
            fields={"claimed_by": "lukazade234"},
        ),
        own_usernames=OWN,
    )
    assert sphere == (":spB: lukazade234 +72 (1/15)", "click")


def test_format_live_feed_skips_someone_elses_click():
    """Another player's payout in the same channel is not part of our run."""
    assert (
        format_live_feed(
            _snapshot(content="<:spB:1> **Someone +72**  (1/15)"),
            ParseResult(
                kind=MessageKind.SPHERE_CLICK,
                summary="Sphere click",
                fields={"claimed_by": "Someone"},
            ),
            own_usernames=OWN,
        )
        is None
    )


def test_format_live_feed_skips_mudae_prose_that_names_nobody():
    """The bug this gate exists for: help and panel text classified as events.

    ``$ou``'s upgrade panel carries sphere emoji beside ``(n/m)`` fractions, so
    ``is_sphere_click_message`` calls it a payout; a ``Syntax:`` reply has two
    bold runs, so ``is_custom_claim`` calls it a claim. Neither names an
    account, and both flooded the feed while the user typed commands by hand.
    """
    panel = _snapshot(
        content="<:spB:1> Upgrade the perks of the selected character. (3/5)",
    )
    assert (
        format_live_feed(
            panel,
            ParseResult(kind=MessageKind.SPHERE_CLICK, summary="Sphere click", fields={}),
            own_usernames=OWN,
        )
        is None
    )

    syntax = _snapshot(content="**Syntax**: $kakeracopy <other server ID>\n**Premium**")
    assert (
        format_live_feed(
            syntax,
            ParseResult(
                kind=MessageKind.CLAIM,
                summary="Claim · Syntax → Premium",
                fields={"winner": "Syntax", "character": "Premium"},
            ),
            own_usernames=OWN,
        )
        is None
    )


def test_format_live_feed_needs_account_names_to_mirror_a_follow_up():
    """With no names to match against, abstain rather than print everything."""
    assert (
        format_live_feed(
            _snapshot(content="<:spB:1> **lukazade234 +72**  (1/15)"),
            ParseResult(
                kind=MessageKind.SPHERE_CLICK,
                summary="Sphere click",
                fields={"claimed_by": "lukazade234"},
            ),
        )
        is None
    )


def test_format_live_feed_never_mirrors_a_roll():
    """Roll cards come from the roll cycle, which only logs what it rolls.

    Nobody is named on a roll, so it cannot be attributed to the account the
    way every other feed line is; a mirrored card is therefore either a copy of
    one the roll cycle already logged or a roll the user made by hand.
    """
    parsed = ParseResult(
        kind=MessageKind.ROLL,
        summary="$roll · Rem",
        fields={"character_name": "Rem", "total_kakera": 1321},
    )
    assert format_live_feed(_snapshot(edited=False), parsed, own_usernames=OWN) is None
    # The formatter itself is still what the roll cycle logs through.
    assert format_roll_line(parsed.fields) == "Rem · 1,321 ka"


def test_format_live_feed_skips_edits():
    # A re-rendered panel repeats itself once per click, so an edit is never a
    # new feed line.
    assert (
        format_live_feed(
            _snapshot(content="<:spB:1> **lukazade234 +72**  (1/15)", edited=True),
            ParseResult(
                kind=MessageKind.SPHERE_CLICK,
                summary="Sphere click",
                fields={"claimed_by": "lukazade234"},
            ),
            own_usernames=OWN,
        )
        is None
    )


def test_format_live_feed_ignores_tu_and_settings():
    snap = _snapshot(content="you can claim")
    assert (
        format_live_feed(
            snap,
            ParseResult(kind=MessageKind.TU, summary="$tu", fields={}),
            own_usernames=OWN,
        )
        is None
    )
    assert (
        format_live_feed(
            snap,
            ParseResult(kind=MessageKind.SETTINGS, summary="$settings", fields={}),
            own_usernames=OWN,
        )
        is None
    )
