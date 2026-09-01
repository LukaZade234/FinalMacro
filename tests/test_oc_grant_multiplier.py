"""A multiplied ``$oh`` grants several ``$oc`` uses on one reward line.

Clicking a face-down cell in ``$oh`` can grant a bonus ``$oc`` game. When the
``$oh`` was played with a multiplier (``$oh 4``), Mudae multiplies the grant
too and writes the whole amount on a single hidden-sphere line:

    <:spU:…> **+4 $oc**

The macro used to *count the lines*, so a ``$oh 4`` that earned four ``$oc``
uses added exactly one to the play-all budget and the other three were never
played. The number on the line is the grant count, so it has to be read rather
than counted — the same amount slot a coloured line uses for spheres, which is
why hidden lines must still be kept out of the sphere total.
"""

from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace

from macro.minigame_board import build_session, classify_oh_click, make_click
from macro.sphere_game import (
    OhSphereGame,
    new_oc_grants,
    oc_grants_from_content,
    parse_reward_clicks,
    total_reward_from_content,
)

from tests.test_sphere_game import (  # reuse the $oh engine's fakes
    _FakeActions,
    _btn,
    _grid_snapshot,
    _reward_snapshot,
)

_X4 = "<:spU:1> **+4 $oc**"


# --- reading the grant count off the tracker -------------------------------


def test_grant_count_comes_from_the_number_on_the_line():
    assert oc_grants_from_content(_X4) == 4


def test_a_single_grant_still_reads_as_one():
    assert oc_grants_from_content("<:spU:1> **+1 $oc**") == 1
    # Older captures wrote the bare amount with no `$oc` tag.
    assert oc_grants_from_content("<:spU:1> **+1**") == 1


def test_content_without_a_hidden_line_grants_nothing():
    assert oc_grants_from_content("<:spY:1> **+59**\n<:spB:2> **+14**") == 0
    assert oc_grants_from_content("") == 0


def test_several_hidden_lines_add_up():
    assert oc_grants_from_content(f"{_X4}\n<:spY:2> **+59**\n{_X4}") == 8


def test_grants_are_not_counted_as_spheres():
    """The amount slot is shared, so `+4 $oc` must not become 4 SP."""
    content = f"{_X4}\n<:spY:2> **+59**"
    assert total_reward_from_content(content) == 59


def test_new_grants_diffs_the_append_only_tracker():
    before = "<:spY:2> **+59**"
    after = f"{before}\n{_X4}"
    assert new_oc_grants(before, after) == 4
    assert new_oc_grants(after, after) == 0
    # A tracker that somehow shrank must not report a negative grant.
    assert new_oc_grants(after, before) == 0


def test_parse_reward_clicks_reads_the_multiplied_grant():
    clicks = parse_reward_clicks(_X4)
    assert [row["emoji"] for row in clicks] == ["spU"]
    assert clicks[0]["oc_bonus"] == 4


# --- classifying the click --------------------------------------------------


def test_classify_uses_the_grant_count_over_the_line_count():
    classified = classify_oh_click(
        clicked_emoji="spU",
        reward_types=["spU"],
        oc_grants=4,
    )
    assert classified["emoji"] == "spU"
    assert classified["oc_bonus"] == 4


def test_classify_falls_back_to_counting_lines_without_a_count():
    """Callers holding only emoji names cannot know the multiplier."""
    assert (
        classify_oh_click(clicked_emoji="spU", reward_types=["spU"])["oc_bonus"] == 1
    )


def test_a_multiplied_grant_is_still_worth_no_spheres():
    classified = classify_oh_click(
        clicked_emoji="spU", reward_types=["spU"], oc_grants=4
    )
    click = make_click(12, classified["emoji"], paid=True, oc_bonus=classified["oc_bonus"])
    session = build_session(
        "oh", [click], ["spU"] * 25, clicks_paid=1, clicks_budget=5, reason="done"
    )
    assert session["oc_bonus"] == 4
    assert session["base_value"] == 0


# --- end to end through the $oh player --------------------------------------


def test_oh_game_at_x4_banks_four_oc_uses():
    """The whole point: play-all spends `oc_bonus`, so it must say 4, not 1."""
    grid0 = _grid_snapshot(
        [_btn(i, "spU", disabled=(i != 8)) for i in range(25)],
        content="You can click **1** times on the buttons below.",
    )
    grid1 = _grid_snapshot(
        [_btn(i, "spU", disabled=True) for i in range(25)],
        content="You can click **1** times on the buttons below.",
    )
    actions = _FakeActions([grid0, _reward_snapshot(_X4), grid1])
    logs: list[str] = []
    game = OhSphereGame(
        actions,
        SimpleNamespace(macro_active=False),
        log=logs.append,
        rng=random.Random(0),
        click_delay=0.0,
    )

    result = asyncio.run(game.play(prefix="$", uses=4))

    assert actions.sent == [("oh 4", "$")]
    assert int(result["oc_bonus"]) == 4
    assert result["session"]["clicks"][0]["oc_bonus"] == 4
    assert result["session"]["clicks"][0]["base_sp"] == 0
    assert any("granted +4 $oc" in line for line in logs)
