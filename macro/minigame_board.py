"""Shared 5×5 board helpers for minigame session logs."""

from __future__ import annotations

from typing import Any

from mudae.constants import SPHERE_WIN_EMOJIS, canonical_sphere_emoji, sphere_base_sp

GRID_CELLS = 25
HIDDEN_EMOJIS = frozenset({"", "spU"})

_OC_LETTER_TO_EMOJI = {
    "R": "spR",
    "O": "spO",
    "Y": "spY",
    "G": "spG",
    "T": "spT",
    "B": "spB",
}
_OQ_STATE_TO_EMOJI = {
    "t": "spP",
    "r": "spR",
    "0": "spB",
    "1": "spT",
    "2": "spG",
    "3": "spY",
    "4": "spO",
}


def sphere_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        button
        for button in buttons
        if (button.get("kind") == "sphere")
        or str(button.get("emoji") or "").strip().startswith("sp")
    ]


def cell_index(buttons: list[dict[str, Any]], custom_id: str) -> int | None:
    for index, button in enumerate(sphere_buttons(buttons)):
        if button.get("custom_id") == custom_id:
            return index
    return None


def board_emojis(buttons: list[dict[str, Any]]) -> list[str]:
    """25-cell board of emoji names; hidden / missing cells are ``spU``."""
    spheres = sphere_buttons(buttons)[:GRID_CELLS]
    board: list[str] = []
    for index in range(GRID_CELLS):
        if index >= len(spheres):
            board.append("spU")
            continue
        board.append(normalize_sphere_emoji(spheres[index].get("emoji")))
    return board


def board_is_complete(board: list[str]) -> bool:
    return len(board) >= GRID_CELLS and all(
        str(cell or "").strip() not in HIDDEN_EMOJIS for cell in board[:GRID_CELLS]
    )


# Post-game $oh reveal fills every non-$oc cell. A mid-game snapshot only
# has the clicked cells coloured, so leftover ``spU`` there are still unknown.
_OH_FINAL_REVEAL_COLOURED_MIN = 20


def oh_hidden_cells_are_oc(
    board: list[str],
    clicks: list[dict[str, Any]] | None = None,
) -> bool:
    """True when leftover ``spU`` on a finished ``$oh`` board are ``$oc`` uses.

    After Mudae’s final reveal, every remaining hidden emoji is an ``$oc``
    token (clicked or not). Face-down cells during play stay ``spU`` too, so
    only treat them as ``$oc`` once the board is clearly fully revealed.
    """
    cells = [normalize_sphere_emoji(cell) for cell in board[:GRID_CELLS]]
    if len(cells) < GRID_CELLS:
        return False
    hidden = sum(1 for cell in cells if cell in HIDDEN_EMOJIS)
    coloured = GRID_CELLS - hidden
    if coloured >= _OH_FINAL_REVEAL_COLOURED_MIN:
        return True
    n_clicks = len(clicks or [])
    return n_clicks > 0 and coloured > n_clicks


def spawn_cell_emojis(
    board: list[str],
    *,
    game: str,
    clicks: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Emoji ids that count toward minigame spawn rates.

    Unrevealed ``spU`` is skipped. On a fully revealed ``$oh`` board, leftover
    ``spU`` are ``$oc`` tokens and are included.
    """
    cells = [normalize_sphere_emoji(cell) for cell in board[:GRID_CELLS]]
    count_hidden = str(game or "").strip().lower() == "oh" and oh_hidden_cells_are_oc(
        cells, clicks
    )
    out: list[str] = []
    for emoji in cells:
        if emoji in HIDDEN_EMOJIS:
            if count_hidden and emoji == "spU":
                out.append("spU")
            continue
        out.append("spR" if emoji == "sp" else emoji)
    return out


def normalize_sphere_emoji(emoji: str | None) -> str:
    key = canonical_sphere_emoji(emoji)
    if key in _OC_LETTER_TO_EMOJI:
        return _OC_LETTER_TO_EMOJI[key]
    if key in _OQ_STATE_TO_EMOJI:
        return _OQ_STATE_TO_EMOJI[key]
    if key == "sp":
        return "spR"
    return key or "spU"


def revealed_click_emoji(
    *,
    reward_types: list[str],
    buttons: list[dict[str, Any]],
    clicked_index: int | None,
    fallback: str = "",
) -> str:
    """Prefer the reward-line colour (dark→purple), then the grid cell."""
    for raw in reward_types:
        emoji = normalize_sphere_emoji(raw)
        if emoji not in HIDDEN_EMOJIS:
            return emoji
    if clicked_index is not None:
        board = board_emojis(buttons)
        if 0 <= clicked_index < len(board):
            emoji = normalize_sphere_emoji(board[clicked_index])
            if emoji not in HIDDEN_EMOJIS:
                return emoji
    return normalize_sphere_emoji(fallback) or "spU"


TRANSFORM_EMOJIS = frozenset({"spL", "spD"})


def click_is_win(click: dict[str, Any]) -> bool:
    if str(click.get("emoji") or "") in SPHERE_WIN_EMOJIS:
        return True
    return any(
        str(item or "") in SPHERE_WIN_EMOJIS for item in (click.get("resolved") or [])
    )


def classify_oh_click(
    *,
    clicked_emoji: str,
    reward_types: list[str],
    grid_emoji: str = "",
    oc_grants: int | None = None,
) -> dict[str, Any]:
    """Identity of an $oh click vs what it paid out.

    Light/dark stay ``spL``/``spD`` for spawn stats; ``resolved`` is the
    fragment / transform used for base SP. A hidden click whose reward line
    is ``spU`` is a bonus ``$oc`` use, not a colour.

    ``oc_grants`` is how many ``$oc`` uses those hidden lines actually granted,
    read off the reward tracker by
    :func:`macro.sphere_game.new_oc_grants`. It matters because one line can
    grant several: an ``$oh`` played with a multiplier writes ``+4 $oc`` on a
    single ``spU`` line. Callers that only have the emoji names (and so cannot
    know the number) leave it ``None`` and fall back to counting the lines,
    which is right whenever the multiplier is 1.
    """
    clicked = normalize_sphere_emoji(clicked_emoji)
    rewards = [normalize_sphere_emoji(item) for item in reward_types if item]
    grid = normalize_sphere_emoji(grid_emoji) if grid_emoji else ""

    if clicked in HIDDEN_EMOJIS and any(item == "spU" for item in rewards):
        return {
            "emoji": "spU",
            "resolved": [],
            "oc_bonus": int(oc_grants) if oc_grants else sum(
                1 for item in rewards if item == "spU"
            ),
        }

    if clicked == "spL":
        fragments = [item for item in rewards if item not in {"spL", "spU"}]
        return {"emoji": "spL", "resolved": fragments, "oc_bonus": 0}

    if clicked == "spD":
        outcome = next((item for item in rewards if item not in {"spD", "spU"}), "")
        if not outcome and grid not in HIDDEN_EMOJIS | {"spD"}:
            outcome = grid
        return {
            "emoji": "spD",
            "resolved": [outcome] if outcome else [],
            "oc_bonus": 0,
        }

    reveal = next((item for item in rewards if item not in HIDDEN_EMOJIS), "")
    if not reveal and grid not in HIDDEN_EMOJIS:
        reveal = grid
    if not reveal and clicked not in HIDDEN_EMOJIS:
        reveal = clicked
    return {
        "emoji": reveal or "spU",
        "resolved": [reveal] if reveal else [],
        "oc_bonus": 0,
    }


def make_click(
    cell: int | None,
    emoji: str,
    *,
    paid: bool,
    resolved: list[str] | None = None,
    oc_bonus: int = 0,
) -> dict[str, Any]:
    kind = normalize_sphere_emoji(emoji)
    resolved_list = [
        normalize_sphere_emoji(item) for item in (resolved or []) if item
    ]
    if oc_bonus:
        value = 0
    elif kind in TRANSFORM_EMOJIS:
        value = sum(sphere_base_sp(item) for item in resolved_list)
    else:
        value = sphere_base_sp(kind)
    entry: dict[str, Any] = {
        "cell": cell,
        "emoji": kind,
        "paid": bool(paid),
        "base_sp": value,
    }
    if resolved_list and resolved_list != [kind]:
        entry["resolved"] = resolved_list
    if oc_bonus:
        entry["oc_bonus"] = int(oc_bonus)
    return entry


def build_session(
    game: str,
    clicks: list[dict[str, Any]],
    board: list[str],
    *,
    clicks_paid: int,
    clicks_budget: int,
    reason: str,
    oc_bonus: int | None = None,
    oq_bonus: int = 0,
    ot_bonus: int = 0,
    spheres_bonus: int = 0,
    uses: int = 1,
) -> dict[str, Any]:
    normalized_board = [normalize_sphere_emoji(cell) for cell in board]
    while len(normalized_board) < GRID_CELLS:
        normalized_board.append("spU")
    grants = int(oc_bonus) if oc_bonus is not None else sum(
        int(click.get("oc_bonus") or 0) for click in clicks
    )
    # Light/dark stay themselves on the logged board even if Mudae replaced
    # the cell with a fragment / transform colour.
    for click in clicks:
        cell = click.get("cell")
        emoji = str(click.get("emoji") or "").strip()
        if cell is None or emoji not in TRANSFORM_EMOJIS:
            continue
        index = int(cell)
        if 0 <= index < GRID_CELLS:
            normalized_board[index] = emoji
    game_key = str(game).strip().lower()
    oc_spawn = 0
    if game_key == "oh" and oh_hidden_cells_are_oc(normalized_board, clicks):
        oc_spawn = sum(
            1 for cell in normalized_board[:GRID_CELLS] if cell == "spU"
        )
    return {
        "game": game_key,
        # One command can consume several daily uses ($ot 5 is one board and
        # five uses), so the two have to be counted separately.
        "uses": max(1, int(uses)),
        "clicks": list(clicks),
        "board": normalized_board[:GRID_CELLS],
        "won": any(click_is_win(click) for click in clicks),
        "base_value": sum(int(click.get("base_sp") or 0) for click in clicks),
        "clicks_paid": int(clicks_paid),
        "clicks_budget": int(clicks_budget),
        "oc_bonus": grants,
        "oc_spawn": oc_spawn,
        "oq_bonus": int(oq_bonus),
        "ot_bonus": int(ot_bonus),
        "spheres_bonus": int(spheres_bonus),
        "reason": str(reason or ""),
    }
