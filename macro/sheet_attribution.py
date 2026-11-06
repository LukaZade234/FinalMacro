"""Whose sheet is this? ``$bonus`` / ``$shop`` / ``$ov`` / ``$limroul`` replies.

None of these replies names its player: ``$bonus`` opens "Player Bonuses",
``$ov`` "Player Settings", ``$shop`` "Upgrade bonuses given by ouroperks". So
a sheet can only be credited to whoever typed the command it answers.

That used to be assumed to be the run account. With alts in the channel it
is not: an alt's ``$bonus`` would overwrite the main's stored sheet, and the
main would then price its kakera clicks and ``$dk`` with the alt's upgrades.
The same was already true of any other player typing ``$bonus`` there.

:class:`SheetAskers` remembers who last typed each sheet command in the
channel. :func:`attribute_sheet` turns that into an account id, or ``None``
when the sheet is someone else's and must not be filed at all. ``$settings``
is server-wide, so it is filed whoever asked.
"""

from __future__ import annotations

import time
from typing import Callable, Mapping

# The parser ids whose replies are sheets (``profile_kind_from_parse``).
SHEET_COMMANDS = frozenset({"bonus", "shop", "ov", "limroul", "settings"})
# Sheets describing one player. ``$settings`` describes the server.
ACCOUNT_SHEETS = frozenset({"bonus", "shop", "ov", "limroul"})
# Mudae answers within seconds; a two-part ``$bonus`` arrives a moment apart.
ASK_WINDOW_SEC = 20.0


class SheetAskers:
    def __init__(self, *, window: float = ASK_WINDOW_SEC, clock: Callable[[], float] = time.monotonic) -> None:
        self._window = window
        self._clock = clock
        self._last: dict[str, tuple[int, float]] = {}

    def observe(self, command: str, author_id: int | None) -> None:
        """A user message typed ``$<command>`` (its canonical parser id)."""
        kind = str(command or "").lower().lstrip("$")
        if kind in SHEET_COMMANDS and author_id is not None:
            self._last[kind] = (int(author_id), self._clock())

    def asker(self, kind: str) -> int | None:
        entry = self._last.get(kind)
        if entry is None or self._clock() - entry[1] > self._window:
            return None
        return entry[0]


def attribute_sheet(
    kind: str,
    *,
    asker: int | None,
    scope_account: str,
    run_account: str,
    main_user_id: int | None,
    alt_user_ids: Mapping[int, str],
) -> str | None:
    """The account a sheet reply belongs to, or ``None`` to drop it.

    * A scope fetch holding the connection names its own account.
    * Otherwise the last asker decides: the main's own user → the run
      account, an alt's user → that alt.
    * Another player's account sheet is dropped; ``$settings`` is kept.
    * No asker seen (the command was missed) keeps the old behaviour — the
      run account — unless alts share the channel, when guessing could hand
      the main an alt's upgrades, so it is dropped.
    """
    if scope_account:
        return scope_account
    if asker is None:
        if kind in ACCOUNT_SHEETS and alt_user_ids:
            return None
        return run_account
    if main_user_id is not None and int(asker) == int(main_user_id):
        return run_account
    if int(asker) in alt_user_ids:
        return alt_user_ids[int(asker)]
    return run_account if kind not in ACCOUNT_SHEETS else None
