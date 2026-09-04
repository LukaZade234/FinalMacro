"""Tests for the app-only wishlist matcher (macro/wishlist.py)."""

from __future__ import annotations

from macro.wishlist import match_wishlist, normalize_wishlist_name


def test_normalize_folds_case_and_whitespace():
    assert normalize_wishlist_name("  Rem   Roswaal ") == "rem roswaal"
    assert normalize_wishlist_name("REM") == normalize_wishlist_name("rem")


def test_match_wishlist_character_hit():
    fields = {"character_name": "Rem", "series": "Re:Zero"}
    assert match_wishlist(fields, ["Rem"], []) == "Rem (wishlist)"


def test_match_wishlist_series_hit():
    fields = {"character_name": "Someone Else", "series": "Re:Zero"}
    assert match_wishlist(fields, [], ["re:zero"]) == "Re:Zero (series wishlist)"


def test_match_wishlist_is_exact_not_substring():
    fields = {"character_name": "Marin", "series": ""}
    assert match_wishlist(fields, ["Mari"], []) is None


def test_match_wishlist_no_lists_no_match():
    fields = {"character_name": "Rem", "series": "Re:Zero"}
    assert match_wishlist(fields, [], []) is None


def test_match_wishlist_no_match_when_name_absent_from_both_lists():
    fields = {"character_name": "Rem", "series": "Re:Zero"}
    assert match_wishlist(fields, ["Emilia"], ["Overlord"]) is None


def test_match_wishlist_handles_missing_fields():
    assert match_wishlist({}, ["Rem"], ["Re:Zero"]) is None


def test_parse_input_splits_on_dollar_signs():
    from macro.wishlist import parse_wishlist_input

    assert parse_wishlist_input("Rem$Alice$Audrey") == ["Rem", "Alice", "Audrey"]
    assert parse_wishlist_input("Rem $Alice $Audrey") == ["Rem", "Alice", "Audrey"]


def test_parse_input_splits_on_commas_and_newlines():
    from macro.wishlist import parse_wishlist_input

    assert parse_wishlist_input("Rem, Alice,Audrey") == ["Rem", "Alice", "Audrey"]
    assert parse_wishlist_input("Rem\nAlice\r\nAudrey") == ["Rem", "Alice", "Audrey"]


def test_parse_input_single_name_and_blanks():
    from macro.wishlist import parse_wishlist_input

    assert parse_wishlist_input("Marin Kitagawa") == ["Marin Kitagawa"]
    assert parse_wishlist_input("") == []
    assert parse_wishlist_input("  $ , $ ") == []


def test_parse_input_collapses_whitespace_and_dedupes():
    from macro.wishlist import parse_wishlist_input

    assert parse_wishlist_input("Rem$rem$  Marin   Kitagawa ") == [
        "Rem",
        "Marin Kitagawa",
    ]


def test_parse_input_round_trips_the_list_formatter_output():
    """The formatter joins with ``$``; its output must paste straight in."""
    from mudae.list_formatter import format_mudae_character_list
    from macro.wishlist import parse_wishlist_input

    formatted = format_mudae_character_list("#1 - Rem · $wa\n#2 - Emilia · $wa")
    assert formatted == "Rem$Emilia"
    assert parse_wishlist_input(formatted) == ["Rem", "Emilia"]
