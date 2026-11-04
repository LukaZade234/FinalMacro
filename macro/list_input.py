"""Read what a user types into a list preset's Add box.

Plain names (``A$B$C``, or one per line) are added as they are. A line that
starts with ``$`` is read as the Mudae command that would build that part of
the list, so a user can paste the commands they already use:

* ``$togglewestern`` / ``$toggleirl`` — a whole-category toggle (``$dl`` only);
* the wish family — ``$wish``, ``$sw`` / ``$starwish`` — with Mudae's option
  letters, combinable in any order:

  ``l`` locked (``$wishl``), ``k`` kakera wish (``$wishk``), ``i`` insert at a
  position or after a reference character (``$wishli 4$x$y``,
  ``$wishi Reze$x``), ``d`` delete your message (no effect on the list).

  ``$swl reze$lucy`` therefore adds Reze and Lucy as locked starwishes.

Names are separated by ``$`` as Mudae separates them; commas are not
separators because names contain them. A ``$`` line this module does not
recognise (``$wishremove``, a typo) is reported back, never added as a name.

Pure: no store, no Qt. `gui/mudae_lists_store.py` applies the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Whole-category toggles Mudae prints on `$dld`, by command → the label it uses.
KNOWN_TOGGLES: dict[str, str] = {
    "$togglewestern": "Western animanga series",
    "$toggleirl": "IRL series",
}

# `$wish…` / `$sw…` / `$starwish…` followed by option letters only. Anchored so
# `$wishremove`, `$wishlist`, `$wl` and friends never read as an add.
_WISH_CMD_RE = re.compile(r"^(?P<base>starwish|wish|sw)(?P<opts>[ildk=]*)$", re.IGNORECASE)
_TOGGLE_RE = re.compile(r"^toggle[a-z]+$", re.IGNORECASE)
_LEADING_WORD_RE = re.compile(r"^\s*\$(?P<word>[a-z=]+)\s*(?P<rest>.*)$", re.IGNORECASE | re.DOTALL)


def _names(chunks: list[str]) -> list[str]:
    out: list[str] = []
    for chunk in chunks:
        name = " ".join(chunk.split())
        if name:
            out.append(name)
    return out


@dataclass
class WishBatch:
    """One wish command's names and the type they are added as."""

    names: list[str]
    starwish: bool = False
    locked: bool = False
    kakera_wish: bool = False
    # 1-based position, or a reference character to insert after; None appends.
    position: int | None = None
    after: str | None = None


@dataclass
class ListInput:
    batches: list[WishBatch] = field(default_factory=list)
    toggles: list[str] = field(default_factory=list)  # commands, e.g. "$toggleirl"
    ignored: list[str] = field(default_factory=list)  # `$` lines not understood


def _toggle_command(chunk: str) -> str | None:
    word = chunk.strip().lstrip("$").strip().lower()
    if _TOGGLE_RE.match(word):
        return "$" + word
    return None


def parse_list_input(kind: str, text: str) -> ListInput:
    """Split the Add box into name batches and toggles.

    ``kind`` is ``dl`` / ``adl`` / ``wl``: toggles only mean something on a
    disablelist, wish commands only on a wishlist.
    """
    result = ListInput()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lead = _LEADING_WORD_RE.match(line)
        if lead is None:
            # Plain names. A `$toggle…` chunk inside a `$`-joined line still
            # counts as a toggle on a disablelist.
            names: list[str] = []
            for chunk in line.split("$"):
                toggle = _toggle_command(chunk) if kind == "dl" else None
                if toggle:
                    result.toggles.append(toggle)
                else:
                    names.extend(_names([chunk]))
            if names:
                result.batches.append(WishBatch(names=names))
            continue

        word = lead.group("word").lower()
        rest = lead.group("rest")

        if _TOGGLE_RE.match(word):
            if kind != "dl":
                result.ignored.append(line)
                continue
            result.toggles.append("$" + word)
            # `$togglewestern$toggleirl` on one line.
            for chunk in rest.split("$"):
                toggle = _toggle_command(chunk)
                if toggle:
                    result.toggles.append(toggle)
                elif chunk.strip():
                    result.ignored.append(chunk.strip())
            continue

        wish = _WISH_CMD_RE.match(word)
        if wish is None or kind != "wl":
            result.ignored.append(line)
            continue
        base = wish.group("base").lower()
        opts = wish.group("opts").lower()
        chunks = rest.split("$")
        batch = WishBatch(
            names=[],
            starwish=base in ("sw", "starwish"),
            locked="l" in opts,
            kakera_wish="k" in opts,
        )
        if "i" in opts and chunks:
            anchor = " ".join(chunks.pop(0).split())
            if anchor.isdigit():
                batch.position = int(anchor)
            elif anchor:
                batch.after = anchor
        batch.names = _names(chunks)
        if batch.names:
            result.batches.append(batch)
        else:
            result.ignored.append(line)
    return result
