"""The commands that rebuild a list (`macro/list_commands.py`).

These will be sent by the macro, so the wishlist plans are replayed through a
small model of how Mudae applies them — append without ``i``, insert at a
1-based position with ``i`` — and must come out as exactly the preset, in
order, with every wish's type.
"""

from __future__ import annotations

import random
import re

import pytest

from macro.list_commands import (
    DISCORD_LIMIT,
    NITRO_LIMIT,
    CommandTooLong,
    adl_commands,
    dl_commands,
    dl_toggle_commands,
    plan_list_commands,
    wish_command,
    wl_commands,
)

_CMD_RE = re.compile(r"^\$(?P<base>sw|wish)(?P<opts>[kli]*) (?P<body>.+)$")


def _apply(commands) -> list[tuple[str, bool, bool, bool]]:
    """Mudae, as these commands assume it behaves. Starts from an empty list."""
    wl: list[tuple[str, bool, bool, bool]] = []
    for command in commands:
        match = _CMD_RE.match(command.text)
        assert match, command.text
        opts = match.group("opts")
        # Option letters appear at most once each.
        assert len(set(opts)) == len(opts), command.text
        parts = match.group("body").split("$")
        position = None
        if "i" in opts:
            position = int(parts.pop(0))
            assert 1 <= position <= len(wl), f"{command.text}: position past the list"
        rows = [
            (name, match.group("base") == "sw", "k" in opts, "l" in opts) for name in parts
        ]
        assert all(rows), command.text
        if position is None:
            wl.extend(rows)
        else:
            wl[position - 1:position - 1] = rows
    return wl


def _want(entries):
    return [(e["name"], e["starwish"], e["kakera_wish"], e["locked"]) for e in entries]


def _row(name, starwish=False, locked=False, kakera=False):
    return {"name": name, "starwish": starwish, "locked": locked, "kakera_wish": kakera}


def test_wish_command_letters():
    assert wish_command((True, False, True)) == "$swl"
    assert wish_command((False, True, True)) == "$wishkl"
    assert wish_command((False, False, True), insert=True) == "$wishli"
    assert wish_command((False, False, False)) == "$wish"


def test_users_example_shape():
    """Locked starwishes with locked wishes among them, kakera wishes at the end."""
    entries = [
        _row("Han Sooyoung", starwish=True, locked=True),
        _row("Marin Kitagawa", locked=True),
        _row("Lucy", starwish=True, locked=True),
        _row("2B", starwish=True, locked=True),
        _row("Power", locked=True),
        _row("Makima", locked=True),
        _row("Asa", locked=True, kakera=True),
        _row("Reze", starwish=True, locked=True),
    ]
    commands = wl_commands(entries)
    assert _apply(commands) == _want(entries)
    texts = [c.text for c in commands]
    assert texts[0] == "$swl Han Sooyoung$Lucy$2B$Reze"
    assert "$wishli 2$Marin Kitagawa" in texts
    assert "$wishli 5$Power$Makima" in texts
    assert "$wishkli 7$Asa" in texts
    assert len(commands) == 4


def test_one_type_is_one_command():
    entries = [_row(f"C{i}", locked=True) for i in range(30)]
    commands = wl_commands(entries)
    assert [c.text.split(" ")[0] for c in commands] == ["$wishl"]
    assert _apply(commands) == _want(entries)


def test_random_wishlists_rebuild_exactly():
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(1, 40)
        entries = [
            _row(
                f"Char {i}",
                starwish=rng.random() < 0.3,
                locked=rng.random() < 0.6,
                kakera=rng.random() < 0.2,
            )
            for i in range(n)
        ]
        for limit in (DISCORD_LIMIT, NITRO_LIMIT, 60):
            commands = wl_commands(entries, limit)
            assert _apply(commands) == _want(entries)
            assert all(len(c.text) <= limit for c in commands)


def test_long_wishlist_splits_and_inserts_continue_at_the_right_position():
    entries = [_row(f"A rather long character name number {i:03d}", starwish=True, locked=True) for i in range(80)]
    # One plain wish near the front makes the starwish batch the base and
    # forces an insert; a block of plain wishes in the middle forces a split insert.
    entries.insert(1, _row("Front", locked=True))
    for i in range(70):
        entries.insert(40 + i, _row(f"Middle wish with a fairly long name {i:03d}", locked=True))
    regular = wl_commands(entries, DISCORD_LIMIT)
    nitro = wl_commands(entries, NITRO_LIMIT)
    assert _apply(regular) == _want(entries)
    assert _apply(nitro) == _want(entries)
    assert all(len(c.text) <= DISCORD_LIMIT for c in regular)
    assert all(len(c.text) <= NITRO_LIMIT for c in nitro)
    assert len(regular) > len(nitro)


def test_dl_toggles_shown_are_the_presets_own_always():
    entries = ["Kadokawa Corporation", "Shueisha"]
    toggles = [{"name": "IRL series", "command": "$toggleirl"}]
    assert [c.text for c in dl_commands(entries)] == ["$d Kadokawa Corporation$Shueisha"]

    shown, off = dl_toggle_commands(toggles)
    assert [(t.text, t.send) for t in shown] == [("$toggleirl", True)]
    assert "only if it is off" in shown[0].note and off == []
    # Western on now, IRL wanted: show IRL (to send), turn western off unseen.
    shown, off = dl_toggle_commands(toggles, current_toggles=[{"command": "$togglewestern"}])
    assert [(t.text, t.send) for t in shown] == [("$toggleirl", True)]
    assert [t.text for t in off] == ["$togglewestern"]
    # Already on: still shown, not to be sent.
    shown, off = dl_toggle_commands(toggles, current_toggles=[{"command": "$toggleirl"}])
    assert [(t.text, t.send) for t in shown] == [("$toggleirl", False)] and off == []
    # No toggles on the preset: none shown.
    assert dl_toggle_commands([], current_toggles=[]) == ([], [])


def test_every_plan_clears_first_with_the_short_command():
    for kind, clear in (("dl", "$eall"), ("adl", "$aeall"), ("wl", "$wrall")):
        plan = plan_list_commands(kind, {"entries": ["A"]})
        assert plan["clear"]["text"] == clear
    dl = plan_list_commands("dl", {"entries": ["A"], "toggles": [{"command": "$togglewestern"}]})
    assert [c["text"] for c in dl["regular"]] == ["$d A"]
    assert [(t["text"], t["send"]) for t in dl["toggles"]] == [("$togglewestern", True)]


def test_dl_and_adl_split_at_the_limit_without_losing_names():
    names = [f"Series name number {i:04d}" for i in range(400)]
    for build, prefix in ((dl_commands, "$d "), (adl_commands, "$ad ")):
        for limit in (DISCORD_LIMIT, NITRO_LIMIT):
            commands = build(names, limit)
            assert all(len(c.text) <= limit and c.text.startswith(prefix) for c in commands)
            joined = []
            for c in commands:
                joined.extend(c.text[len(prefix):].split("$"))
            assert joined == names


def test_plan_reports_split_only_when_plain_discord_needs_more_messages():
    small = plan_list_commands("adl", {"entries": ["A", "B"]})
    assert small["split"] is False and [c["text"] for c in small["regular"]] == ["$ad A$B"]
    big = plan_list_commands("adl", {"entries": [f"Series {i:05d}" for i in range(400)]})
    assert big["split"] is True
    assert len(big["regular"]) > len(big["nitro"])


def test_a_name_too_long_for_any_message_is_reported():
    with pytest.raises(CommandTooLong):
        adl_commands(["x" * 5000])
    plan = plan_list_commands("adl", {"entries": ["x" * 5000]})
    assert "too long" in plan["error"]
