"""Minigame yield, and the window a rate is allowed to be formed over.

The bug these exist to prevent: sphere events reach back to the first day the
macro ran, while board counts only start when ``minigame_log.json`` did. Divide
one by the other and every average inflates — on live data that overstated
``$oh`` by 4.7x. The benchmark must therefore be computed over the days board
counts exist for, and must say so.
"""

from __future__ import annotations

import pytest

from mudae import event_log, minigame_stats


@pytest.fixture
def logs(monkeypatch):
    """Board counts for two days; sphere payouts for four."""
    boards = [
        {"game": "oh", "date_key": "2026-03-03", "won": False, "uses": 1,
         "account_id": "a", "guild_name": "S"},
        {"game": "oh", "date_key": "2026-03-04", "won": False, "uses": 1,
         "account_id": "a", "guild_name": "S"},
        {"game": "oc", "date_key": "2026-03-04", "won": True, "uses": 1,
         "account_id": "a", "guild_name": "S"},
        {"game": "oc", "date_key": "2026-03-04", "won": False, "uses": 1,
         "account_id": "a", "guild_name": "S"},
    ]
    monkeypatch.setattr(minigame_stats, "get_minigame_events", lambda: boards)
    event_log.replace("sphere", [
        # Two days that predate any board count — the trap.
        {"source": "minigame_oh", "amount": 9000, "date_key": "2026-03-01",
         "account_id": "a", "guild_name": "S"},
        {"source": "minigame_oh", "amount": 9000, "date_key": "2026-03-02",
         "account_id": "a", "guild_name": "S"},
        # Days that do have board counts.
        {"source": "minigame_oh", "amount": 100, "date_key": "2026-03-03",
         "account_id": "a", "guild_name": "S"},
        {"source": "minigame_oh", "amount": 300, "date_key": "2026-03-04",
         "account_id": "a", "guild_name": "S"},
        {"source": "minigame_oc", "amount": 200, "date_key": "2026-03-04",
         "account_id": "a", "guild_name": "S"},
        {"source": "minigame_oc", "amount": 200, "date_key": "2026-03-04",
         "account_id": "a", "guild_name": "S"},
        {"source": "sphere_click", "amount": 500, "date_key": "2026-03-04",
         "account_id": "a", "guild_name": "S"},
    ])
    return boards


# --- the window ---------------------------------------------------------------


def test_benchmark_ignores_sphere_days_that_have_no_board_count(logs):
    """18,000 SP from before the board log must not enter the rate."""
    out = minigame_stats.daily_yield("2026-03-04", account="a", server="S")
    oh = next(g for g in out["games"] if g["game"] == "oh")
    # 400 SP over 2 counted uses, not 18,400 over 2.
    assert oh["benchmark_sp_per_use"] == 200
    assert oh["benchmark_uses"] == 2


def test_benchmark_reports_the_window_it_actually_covers(logs):
    out = minigame_stats.daily_yield("2026-03-04", account="a", server="S")
    assert out["benchmark"]["from"] == "2026-03-03"
    assert out["benchmark"]["to"] == "2026-03-04"
    assert out["benchmark"]["days"] == 2
    assert "not all history" in out["benchmark"]["note"]


def test_window_is_empty_rather_than_guessed_when_no_boards_are_logged(monkeypatch):
    monkeypatch.setattr(minigame_stats, "get_minigame_events", lambda: [])
    event_log.replace("sphere", [
        {"source": "minigame_oh", "amount": 9000, "date_key": "2026-03-01"},
    ])
    out = minigame_stats.daily_yield("2026-03-01")
    oh = next(g for g in out["games"] if g["game"] == "oh")
    assert oh["benchmark_sp_per_use"] is None
    assert oh["sp_per_use"] is None            # no boards, so no rate either
    assert "recorded how many uses" in out["benchmark"]["note"]


# --- the day ------------------------------------------------------------------


def test_day_rate_uses_awarded_spheres_not_board_base_values(logs):
    """base_sp is not comparable across games, so it is never the numerator."""
    out = minigame_stats.daily_yield("2026-03-04", account="a", server="S")
    oh = next(g for g in out["games"] if g["game"] == "oh")
    assert oh["sp"] == 300 and oh["boards"] == 1
    assert oh["sp_per_use"] == 300


def test_delta_is_none_when_there_is_nothing_to_compare_against(monkeypatch):
    monkeypatch.setattr(minigame_stats, "get_minigame_events",
                        lambda: [{"game": "oq", "date_key": "2026-03-04"}])
    event_log.replace("sphere", [])
    out = minigame_stats.daily_yield("2026-03-04")
    oq = next(g for g in out["games"] if g["game"] == "oq")
    assert oq["delta_pct"] is None


def test_non_minigame_sphere_sources_are_excluded(logs):
    out = minigame_stats.daily_yield("2026-03-04", account="a", server="S")
    assert out["sp"] == 300 + 400          # the 500 sphere_click is not a minigame


# --- win state ----------------------------------------------------------------


def test_only_oc_and_oq_carry_a_win_rate(logs):
    """$ot and $oh have no win condition — a rate for them would be invented."""
    out = minigame_stats.daily_yield("2026-03-04", account="a", server="S")
    by = {g["game"]: g for g in out["games"]}
    assert by["oc"]["has_win_state"] is True
    assert by["oc"]["win_rate"] == 50.0     # one of two boards
    assert by["oh"]["has_win_state"] is False
    assert by["oh"]["win_rate"] is None
    assert by["oh"]["won"] is None


def test_win_rate_is_none_for_a_winnable_game_that_was_not_played(logs):
    out = minigame_stats.daily_yield("2026-03-03", account="a", server="S")
    by = {g["game"]: g for g in out["games"]}
    assert by["oc"]["boards"] == 0
    assert by["oc"]["win_rate"] is None


# --- scoping ------------------------------------------------------------------


def test_account_filter_narrows_both_halves_of_the_rate(logs):
    out = minigame_stats.daily_yield("2026-03-04", account="someone-else", server="S")
    assert out["boards"] == 0
    assert out["benchmark"]["days"] == 0


def test_games_are_ordered_by_what_they_paid(logs):
    out = minigame_stats.daily_yield("2026-03-04", account="a", server="S")
    assert [g["game"] for g in out["games"]] == ["oc", "oh"]


# --- uses vs boards -----------------------------------------------------------


def test_uses_counts_the_allowance_a_command_spent(monkeypatch):
    """`$ot 5` is one board and five uses, so the two are counted apart."""
    monkeypatch.setattr(minigame_stats, "get_minigame_events", lambda: [
        {"game": "ot", "date_key": "2026-03-04", "uses": 5},
        {"game": "ot", "date_key": "2026-03-04", "uses": 2},
    ])
    event_log.replace("sphere", [])
    out = minigame_stats.daily_yield("2026-03-04")
    ot = next(g for g in out["games"] if g["game"] == "ot")
    assert ot["boards"] == 2
    assert ot["uses"] == 7
    assert out["uses"] == 7


def test_uses_is_unknown_for_rows_recorded_before_the_field_existed(monkeypatch):
    """Reporting them as one use each would read as fact and be wrong."""
    monkeypatch.setattr(minigame_stats, "get_minigame_events", lambda: [
        {"game": "oh", "date_key": "2026-03-04"},
    ])
    event_log.replace("sphere", [])
    out = minigame_stats.daily_yield("2026-03-04")
    oh = next(g for g in out["games"] if g["game"] == "oh")
    assert oh["boards"] == 1
    assert oh["uses"] is None
    assert out["uses"] is None


def test_one_undated_row_makes_the_whole_game_unknown(monkeypatch):
    """A partial sum would understate the day without saying so."""
    monkeypatch.setattr(minigame_stats, "get_minigame_events", lambda: [
        {"game": "oq", "date_key": "2026-03-04", "uses": 3},
        {"game": "oq", "date_key": "2026-03-04"},
    ])
    event_log.replace("sphere", [])
    out = minigame_stats.daily_yield("2026-03-04")
    assert next(g for g in out["games"] if g["game"] == "oq")["uses"] is None


def test_a_batched_board_does_not_inflate_the_rate(monkeypatch):
    """`$ot 6` pays ~6x what one use pays, so per-board is 6x too high.

    This is the live case: one `$ot` board took 6 uses and paid 12,600 SP.
    Rated per board that reads as 12,600 a game against a ~900 baseline; per
    use it is 2,100, which is the number that can actually be compared.
    """
    monkeypatch.setattr(minigame_stats, "get_minigame_events", lambda: [
        {"game": "ot", "date_key": "2026-03-04", "uses": 6},
    ])
    event_log.replace("sphere", [
        {"source": "minigame_ot", "amount": 12600, "date_key": "2026-03-04"},
    ])
    out = minigame_stats.daily_yield("2026-03-04")
    ot = next(g for g in out["games"] if g["game"] == "ot")
    assert ot["boards"] == 1 and ot["uses"] == 6
    assert ot["sp_per_use"] == 2100
    assert ot["benchmark_sp_per_use"] == 2100


def test_a_day_with_an_unrecorded_use_count_is_left_out_of_the_rate(monkeypatch):
    """Both halves must cover the same days, so an unknown day drops from both.

    Counting the unknown board as one use would put its whole payout against a
    single use and pull the benchmark up exactly the way per-board did.
    """
    monkeypatch.setattr(minigame_stats, "get_minigame_events", lambda: [
        {"game": "ot", "date_key": "2026-03-03"},               # no `uses`
        {"game": "ot", "date_key": "2026-03-04", "uses": 4},
    ])
    event_log.replace("sphere", [
        {"source": "minigame_ot", "amount": 9000, "date_key": "2026-03-03"},
        {"source": "minigame_ot", "amount": 800, "date_key": "2026-03-04"},
    ])
    out = minigame_stats.daily_yield("2026-03-04")
    ot = next(g for g in out["games"] if g["game"] == "ot")
    assert ot["benchmark_sp_per_use"] == 200        # 800/4, the 9,000 excluded
    assert out["benchmark"]["days"] == 1
    assert out["benchmark"]["from"] == "2026-03-04"
