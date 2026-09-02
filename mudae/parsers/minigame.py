"""Recognise the sphere-minigame grids (``$oh`` / ``$oc`` / ``$oq`` / ``$ot``).

Mudae posts one 5×5 grid of sphere buttons per game and then *edits* that same
message after every click, so a single game is a dozen near-identical
messages. None of them is a claim — but the board text is a wall of bold
phrases ("You can click **5** times…", "**1 red sphere** to find…"), and
:func:`mudae.parsers.claim.is_custom_claim` only asks for two bold names. So
without this predicate a game played by hand in the channel while the macro
was connected classified as ``CLAIM``: the whole board text was mirrored into
the Run feed once per click, and a board landing inside a claim wait could
satisfy :meth:`macro.actions.MacroActions.wait_for_claim`.

The macro's *own* games do not go through here — their first grid is the reply
to the ``$oc`` the macro sent, so it resolves as a command response before
classification runs. This is about grids nobody asked the macro for.
"""

from __future__ import annotations

import re

from mudae.buttons import is_sphere_button
from mudae.message_text import snapshot_visible_text
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

# "You can click 5 times on the buttons below" ($oh / $oc / $oq) and
# "N spheres to find" ($ot). Kept as prose fragments rather than per-game
# regexes: the point here is only "this is a grid", never which game it is.
_BOARD_TEXT_RE = re.compile(
    r"buttons\s+below|spheres\s+buttons|spheres\s+to\s+find",
    re.IGNORECASE,
)

# A grid is 25 sphere buttons. Ten is the same floor the game drivers use
# (``macro.sphere_game._MIN_GRID_BUTTONS``) and is well clear of a roll's lone
# perk-9 sphere react.
_MIN_GRID_BUTTONS = 10


def is_minigame_board(snapshot: MudaeMessageSnapshot) -> bool:
    """True for a sphere-minigame grid message (first post or a click edit)."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    spheres = sum(
        1 for button in (snapshot.buttons or []) if is_sphere_button(button)
    )
    if spheres < _MIN_GRID_BUTTONS:
        return False
    return bool(_BOARD_TEXT_RE.search(snapshot_visible_text(snapshot)))


def parse_minigame_board(snapshot: MudaeMessageSnapshot) -> ParseResult:
    """Name the grid without reading it.

    The game drivers read boards straight off the snapshot buttons, so nothing
    downstream needs the cells here — this exists so the grid stops being
    mistaken for something else.
    """
    return ParseResult(
        kind=MessageKind.MINIGAME_BOARD,
        summary="Minigame board",
        fields={"button_count": len(snapshot.buttons or [])},
        warnings=[],
    )
