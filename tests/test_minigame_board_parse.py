"""Sphere-minigame grids are grids, not claims.

Observed live: a ``$oc`` and a ``$oq`` played by hand in the channel while the
roll macro was connected printed their whole board text into the Run feed as
``claim``-severity lines — 17 of them in one minute, because Mudae edits the
same grid message after every click. ``is_custom_claim`` only asks for two
bold names, and the board prose has plenty.

The same misreading also made a stray board able to satisfy
``MacroActions.wait_for_claim``, which matches any ``CLAIM``/``MARRIAGE``.
"""

from __future__ import annotations

from mudae.live_feed import format_live_feed
from mudae.parsers.classify import classify_message
from mudae.parsers.minigame import is_minigame_board
from mudae.parsers.pipeline import parse_message
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

# Real text, from data/session_logs/2026-09-02_000025_hourly_lukazade234.json.
OC_BOARD = (
    "You can click **5** times on the buttons below (2 minutes). "
    "**1 red sphere** to find (never at the center) along with **2 orange** "
    "(always next to the red sphere), **3 yellow** (always diagonal to the red "
    "sphere), **4 green** (in the same row or column as red), teal (in the same "
    "row, column or diagonal as red) and blue (NEVER in the same row, column nor "
    "diagonal from red). ​ Multiplier: **2x**"
)
OQ_BOARD = (
    "You can click **7** times on the buttons below (2 minutes). Find **3 purple "
    "spheres** (out of 4) to turn the 4th purple into a **red sphere** or more. "
    "Colors define the number of neighboring purples (8 tiles around). "
    "Blue = 0, teal = 1, green = 2, yellow = 3, orange = 4 ​ Multiplier: **4x**"
)
OT_BOARD = "**2 rare ships** and 11 blue cells. **4** spheres to find on the grid below."


def _grid_buttons(count: int = 25) -> list[dict[str, object]]:
    return [
        {
            "label": "",
            "emoji": "spU",
            "custom_id": f"cell{index}",
            "kind": "sphere",
            "disabled": False,
        }
        for index in range(count)
    ]


def _snapshot(content: str, *, buttons: list | None = None) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=7,
        channel_id=99,
        channel_name="mudae-w",
        guild_id=1,
        guild_name="Key Server 0",
        author_id=432610292342587392,
        author_name="Mudae",
        is_mudae=True,
        content=content,
        embeds=[],
        buttons=_grid_buttons() if buttons is None else buttons,
        created_at="00:00:32",
    )


def test_board_text_is_recognised_for_every_sphere_game():
    for content in (OC_BOARD, OQ_BOARD, OT_BOARD):
        assert is_minigame_board(_snapshot(content)) is True


def test_a_manual_oc_board_is_not_classified_as_a_claim():
    snapshot = _snapshot(OC_BOARD)
    assert classify_message(snapshot) is MessageKind.MINIGAME_BOARD
    assert parse_message(snapshot).kind is MessageKind.MINIGAME_BOARD


def test_a_manual_oq_board_is_not_classified_as_a_claim():
    snapshot = _snapshot(OQ_BOARD)
    assert classify_message(snapshot) is MessageKind.MINIGAME_BOARD
    assert parse_message(snapshot).kind is MessageKind.MINIGAME_BOARD


def test_a_board_never_reaches_the_live_feed():
    snapshot = _snapshot(OQ_BOARD)
    assert format_live_feed(snapshot, parse_message(snapshot)) is None


def test_a_lone_sphere_react_on_a_roll_is_not_a_board():
    """One perk-9 button is not a grid, whatever the message says."""
    snapshot = _snapshot(OC_BOARD, buttons=_grid_buttons(1))
    assert is_minigame_board(snapshot) is False


def test_a_real_claim_still_classifies_as_a_claim():
    snapshot = _snapshot(
        "💖 **lukazade234** and **Mayano Top Gun** are now married! 💖",
        buttons=[],
    )
    assert classify_message(snapshot) is MessageKind.MARRIAGE


def test_the_feed_drops_a_claim_it_could_not_name():
    """The bold-name heuristic also fires on Mudae's character-info embeds.

    Those messages carry their text in an embed, so ``parse_claim`` — which
    reads ``snapshot.content`` — found nobody, and the feed printed the macro's
    own placeholder summary "Claim · ? → ?" straight into the channel mirror.
    """
    snapshot = _snapshot("", buttons=[])
    parsed = ParseResult(kind=MessageKind.CLAIM, summary="Claim · ? → ?", fields={})
    assert format_live_feed(snapshot, parsed) is None


def test_the_feed_keeps_a_claim_it_could_name():
    snapshot = _snapshot(
        "💖 **lukazade234** and **Mayano Top Gun** are now married! 💖",
        buttons=[],
    )
    parsed = parse_message(snapshot)
    text, severity = format_live_feed(snapshot, parsed)
    assert "are now married" in text
    assert severity == "claim"
