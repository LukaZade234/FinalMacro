"""Turn a list preset into the Mudae commands that build it.

These are the commands Advisor › Lists offers to copy today, and the ones the
macro will send itself later — so every rule here is written down, and
`tests/test_list_commands.py` replays the output through a model of Mudae's
list behaviour to prove the result is the preset, in order.

Every plan starts by **clearing** the list, with the short form of Mudae's
clear-all command, and then adds the preset back:

    $dl    $eall    ($enableall)        then $d …   ($disable)
    $adl   $aeall   ($antienableall)    then $ad …  ($antidisable)
    $wl    $wrall   ($wishremoveall)    then $wish… / $sw…

so the adds always land on an empty list and their order is exact.

``$adl`` — ``$ad a$b$c``. Order does not matter.

``$dl`` — ``$d a$b$c`` for the disables, then the toggles. A toggle **flips**:
sending ``$togglewestern`` while western is already off turns it back on, and
``$eall`` leaves toggles as they are. The preset's own toggles are always
offered for copying, each saying whether it needs sending (``send``); toggles
on now but not on the preset are sent to turn them off without being shown.
Both are worked out against the server's last ``$dld`` (the macro's send reads
a fresh one first); with no fetch, every toggle the preset wants is marked with
a warning to send it only if it is off now.

``$wl`` — order matters (perk 1 wraps around neighbours) and each wish has a
type, which picks the command:

    base   ``$sw`` for a starwish, ``$wish`` otherwise
    + ``k`` kakera wish, + ``l`` locked, + ``i`` insert at a position

e.g. ``$swl``, ``$wishkl``, ``$wishli 4$x$y``. The plan sends each wish type as
one batch, appending the first to the empty list, then inserts every later
type into the gaps it belongs in — ``$wishli <position>$names`` puts the first
name at ``<position>`` (1-based) and the rest after it. A group that belongs
at the end is appended instead of inserted. The order the types go in is
chosen to need the fewest commands.

Mudae behaviour this relies on (from its help, not yet confirmed by the macro
sending them): an add without ``i`` appends to the end of the list, for both
``$wish`` and ``$sw``; ``i`` with a number inserts at that position; option
letters combine in any order.

Discord caps a message at 2,000 characters (4,000 with Nitro). A batch that
would exceed the cap is split across commands; an insert that is split
continues at the position after the previous part.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Any, Iterable

DISCORD_LIMIT = 2000
NITRO_LIMIT = 4000

# Beyond this many distinct wish types, try a few orders instead of all.
_MAX_PERMUTED_TYPES = 6


@dataclass(frozen=True)
class ListCommand:
    text: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "note": self.note, "chars": len(self.text)}


class CommandTooLong(ValueError):
    """One name alone does not fit in a message — nothing can send it."""


def _pack(prefix_for: Any, names: list[str], limit: int) -> list[tuple[int, list[str]]]:
    """Split ``names`` into message-sized parts.

    ``prefix_for(offset)`` gives the text before the names for a part that
    starts ``offset`` names into the batch (inserts carry a position that moves
    with the offset). Returns ``(offset, names)`` per part, in order.
    """
    parts: list[tuple[int, list[str]]] = []
    offset = 0
    while offset < len(names):
        prefix = prefix_for(offset)
        chunk = [names[offset]]
        if len(prefix) + len(names[offset]) > limit:
            raise CommandTooLong(names[offset])
        length = len(prefix) + len(names[offset])
        for name in names[offset + 1:]:
            if length + 1 + len(name) > limit:
                break
            chunk.append(name)
            length += 1 + len(name)
        parts.append((offset, chunk))
        offset += len(chunk)
    return parts


def _simple(command: str, names: list[str], limit: int, note: str = "") -> list[ListCommand]:
    out = []
    for _offset, chunk in _pack(lambda _o: f"{command} ", names, limit):
        out.append(ListCommand(f"{command} " + "$".join(chunk), note))
    return out


def _names(entries: Iterable[Any]) -> list[str]:
    out = []
    for entry in entries or []:
        name = str((entry.get("name") if isinstance(entry, dict) else entry) or "").strip()
        if name:
            out.append(name)
    return out


# --- $adl -------------------------------------------------------------------


def adl_commands(entries: Iterable[Any], limit: int = DISCORD_LIMIT) -> list[ListCommand]:
    return _simple("$ad", _names(entries), limit, "antidisable these series")


# --- $dl --------------------------------------------------------------------


# The short clear-all command for each list, sent before the adds.
CLEAR_COMMANDS: dict[str, str] = {"dl": "$eall", "adl": "$aeall", "wl": "$wrall"}
_CLEAR_NOTES: dict[str, str] = {
    "dl": "$enableall — empties the disablelist",
    "adl": "$antienableall — empties the antidisablelist",
    "wl": "$wishremoveall — empties the wishlist",
}


def dl_commands(entries: Iterable[Any], limit: int = DISCORD_LIMIT) -> list[ListCommand]:
    """``$d`` batches. Toggles are separate: see :func:`dl_toggle_commands`."""
    return _simple("$d", _names(entries), limit, "disable these")


@dataclass(frozen=True)
class ToggleCommand:
    text: str
    note: str
    # Whether this toggle needs sending to reach the preset's state.
    send: bool

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "note": self.note, "chars": len(self.text), "send": self.send}


def _toggle_set(items: Iterable[Any] | None) -> list[str]:
    found: list[str] = []
    for item in items or []:
        command = str((item.get("command") if isinstance(item, dict) else item) or "").strip()
        if command and command not in found:
            found.append(command)
    return found


def dl_toggle_commands(
    toggles: Iterable[Any], *, current_toggles: Iterable[Any] | None = None
) -> tuple[list[ToggleCommand], list[ToggleCommand]]:
    """``(shown, turn_off)`` for a `$dl` preset.

    ``shown`` is every toggle the preset has — always listed, so each can be
    copied whatever the server's state — marked ``send`` when it must flip on.
    ``turn_off`` is the toggles on now that the preset does not have; they are
    not shown, but a send flips them off. ``$eall`` leaves toggles alone, so
    this is what makes the toggles match the preset.

    ``current_toggles`` is the toggle set from the last fetch of the server, or
    ``None`` when that is unknown.
    """
    wanted = _toggle_set(toggles)
    if current_toggles is None:
        shown = [
            ToggleCommand(c, "flips the toggle — send only if it is off on this server now", True)
            for c in wanted
        ]
        return shown, []
    have = _toggle_set(current_toggles)
    shown = [
        ToggleCommand(c, "already on in the last fetch — sending it turns it off", False)
        if c in have
        else ToggleCommand(c, "turns it on (off in the last fetch)", True)
        for c in wanted
    ]
    turn_off = [
        ToggleCommand(c, "on in the last fetch, not on this preset — turns it off", True)
        for c in have
        if c not in wanted
    ]
    return shown, turn_off


# --- $wl --------------------------------------------------------------------

WishType = tuple[bool, bool, bool]  # (starwish, kakera_wish, locked)


def _wish_type(entry: Any) -> WishType:
    if not isinstance(entry, dict):
        return (False, False, False)
    return (bool(entry.get("starwish")), bool(entry.get("kakera_wish")), bool(entry.get("locked")))


def wish_command(kind: WishType, *, insert: bool = False) -> str:
    starwish, kakera, locked = kind
    return (
        ("$sw" if starwish else "$wish")
        + ("k" if kakera else "")
        + ("l" if locked else "")
        + ("i" if insert else "")
    )


def _type_note(kind: WishType) -> str:
    starwish, kakera, locked = kind
    words = ["starwishes" if starwish else "wishes"]
    if locked:
        words.insert(0, "locked")
    if kakera:
        words.insert(0, "kakera")
    return " ".join(words)


def _plan_order(
    names: list[str], kinds: list[WishType], order: tuple[WishType, ...], limit: int
) -> list[ListCommand]:
    """Commands for one order of wish types, by simulating the list as it grows."""
    present: list[int] = []  # final indices currently on the list, in list order
    out: list[ListCommand] = []
    for step, kind in enumerate(order):
        items = [i for i, k in enumerate(kinds) if k == kind]
        if step == 0:
            for _o, chunk in _pack(lambda _o: wish_command(kind) + " ", [names[i] for i in items], limit):
                out.append(ListCommand(wish_command(kind) + " " + "$".join(chunk), _type_note(kind)))
            present.extend(items)
            continue
        # Group the items by the gap they fall into: the next item already
        # on the list after them (None = the end).
        groups: list[tuple[int | None, list[int]]] = []
        for index in items:
            after = next((p for p in present if p > index), None)
            if groups and groups[-1][0] == after:
                groups[-1][1].append(index)
            else:
                groups.append((after, [index]))
        for after, group in groups:
            group_names = [names[i] for i in group]
            if after is None:
                for _o, chunk in _pack(lambda _o: wish_command(kind) + " ", group_names, limit):
                    out.append(
                        ListCommand(wish_command(kind) + " " + "$".join(chunk), _type_note(kind) + " · at the end")
                    )
                present.extend(group)
                continue
            position = present.index(after) + 1  # 1-based slot the group starts at
            command = wish_command(kind, insert=True)
            for offset, chunk in _pack(lambda o: f"{command} {position + o}$", group_names, limit):
                out.append(
                    ListCommand(
                        f"{command} {position + offset}$" + "$".join(chunk),
                        f"{_type_note(kind)} · into place at #{position + offset}",
                    )
                )
            at = present.index(after)
            present[at:at] = group
    return out


def wl_commands(entries: Iterable[Any], limit: int = DISCORD_LIMIT) -> list[ListCommand]:
    rows = [e for e in entries or [] if _names([e])]
    names = _names(rows)
    kinds = [_wish_type(e) for e in rows]
    if not names:
        return []
    # Types by size, largest first, so ties keep the biggest batch as the base.
    counts: dict[WishType, int] = {}
    for kind in kinds:
        counts[kind] = counts.get(kind, 0) + 1
    types = sorted(counts, key=lambda k: (-counts[k], kinds.index(k)))
    if len(types) <= _MAX_PERMUTED_TYPES:
        candidates: Iterable[tuple[WishType, ...]] = permutations(types)
    else:
        candidates = [tuple(types)]
    best: list[ListCommand] | None = None
    for order in candidates:
        plan = _plan_order(names, kinds, order, limit)
        if best is None or len(plan) < len(best):
            best = plan
    return best or []


# --- one call for the page -----------------------------------------------------


def plan_list_commands(
    kind: str,
    data: dict[str, Any],
    *,
    current_toggles: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Everything the copy popup (and later the macro) needs for one list.

    The order to send is ``clear``, then ``regular`` (or ``nitro``) in order,
    then the ``toggles`` whose ``send`` is true and every ``toggles_off``
    (shown nowhere — the popup lists only the preset's own toggles). ``split`` is true when the
    plain-Discord plan needed more messages than the Nitro one; the page shows
    one column otherwise.
    """
    entries = data.get("entries") or []

    def plan(limit: int) -> list[ListCommand]:
        if kind == "adl":
            return adl_commands(entries, limit)
        if kind == "dl":
            return dl_commands(entries, limit)
        return wl_commands(entries, limit)

    clear = ListCommand(CLEAR_COMMANDS[kind], _CLEAR_NOTES[kind]) if kind in CLEAR_COMMANDS else None
    toggles, toggles_off = (
        dl_toggle_commands(data.get("toggles") or [], current_toggles=current_toggles)
        if kind == "dl"
        else ([], [])
    )
    try:
        regular, nitro = plan(DISCORD_LIMIT), plan(NITRO_LIMIT)
    except CommandTooLong as exc:
        return {
            "error": f"“{exc}” is too long to fit in one Discord message.",
            "clear": clear.to_dict() if clear else None,
            "regular": [],
            "nitro": [],
            "toggles": [t.to_dict() for t in toggles],
            "toggles_off": [t.to_dict() for t in toggles_off],
        }
    notes = []
    if kind == "wl":
        notes.append("Send in this order: later commands insert by position into what the earlier ones built.")
    return {
        "clear": clear.to_dict() if clear else None,
        "regular": [c.to_dict() for c in regular],
        "nitro": [c.to_dict() for c in nitro],
        "toggles": [t.to_dict() for t in toggles],
        "toggles_off": [t.to_dict() for t in toggles_off],
        "split": [c.text for c in regular] != [c.text for c in nitro],
        "total_chars": sum(len(c.text) for c in regular),
        "notes": notes,
    }
