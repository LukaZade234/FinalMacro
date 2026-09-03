"""The report's detail panels: colours, hours, click tapes and soulmates.

Two of these encode a rule that is easy to get wrong and expensive to get wrong
quietly. A kakera *colour* only exists on a click — ``$bku`` payouts and ``$dk``
carry none — so a colour share taken over the day's whole take would silently
attribute nearly half of it to nothing. And a purple click never consumes a
perk-8 slot, because purple cannot spawn on a perk-8 character.
"""

from __future__ import annotations

from gui.accounts import AccountProfile
from mudae import event_log, stats_index


MAIN = AccountProfile(id="a1", name="Main", type="Main")


def _store():
    return type("S", (), {"accounts": [MAIN], "active_account_id": "a1"})()


def _reset():
    for kind in ("kakera", "sphere", "key", "soulmate"):
        event_log.replace(kind, [])
    stats_index.rebuild()


def _kakera(day, amount, *, method="kakera_click", ktype="", time="12:00:00"):
    event_log.append("kakera", {
        "amount": amount, "earn_method": method, "kakera_type": ktype,
        "date_key": day, "time": time, "account_id": "a1",
        "account_name": "Main", "guild_name": "G",
    })


def _sphere(day, amount, *, source="sphere_click", stype="spG", time="12:00:00"):
    event_log.append("sphere", {
        "amount": amount, "source": source, "sphere_type": stype,
        "date_key": day, "time": time, "account_id": "a1",
        "account_name": "Main", "guild_name": "G",
    })


DAY = "2026-09-01"


def _scoped():
    """The report narrowed to the one account on the one server these fixtures log.

    The perk-8 and perk-9 tapes only exist in that shape: each (account, server)
    pairing has its own daily allowance, so an unscoped report draws no tape.
    """
    return stats_index.daily_report(_store(), date_key=DAY, account="a1", server="G")


# --- colour split -------------------------------------------------------------


def test_colour_share_counts_clicks_only_not_the_whole_day():
    _reset()
    _kakera(DAY, 1000, method="kakera_click", ktype="kakeraP")
    _kakera(DAY, 9000, method="bku_reset")          # no colour at all
    out = stats_index.daily_report(_store(), date_key=DAY)
    colours = out["breakdowns"]["kakera"]["by_type"]
    assert [(row["label"], row["amount"], row["count"]) for row in colours] == [
        ("Purple", 1000, 1)
    ]
    assert out["kinds"]["kakera"]["total"] == 10000   # the day is still the day


def test_colour_rows_carry_a_readable_label_not_the_emoji_id():
    _reset()
    _kakera(DAY, 5, ktype="kakeraL")
    out = stats_index.daily_report(_store(), date_key=DAY)
    assert out["breakdowns"]["kakera"]["by_type"][0]["label"] == "Light"


def test_methods_carry_event_counts_as_well_as_amounts():
    _reset()
    _kakera(DAY, 10, method="bku_reset")
    _kakera(DAY, 10, method="bku_reset")
    out = stats_index.daily_report(_store(), date_key=DAY)
    row = next(r for r in out["breakdowns"]["kakera"]["by_method"] if r["id"] == "bku_reset")
    assert (row["amount"], row["count"]) == (20, 2)


# --- all-time comparison ------------------------------------------------------


def test_all_time_average_excludes_the_day_being_judged():
    _reset()
    _kakera("2026-08-30", 100)
    _kakera("2026-08-31", 300)
    _kakera(DAY, 1000)
    out = stats_index.daily_report(_store(), date_key=DAY)
    assert out["kinds"]["kakera"]["all_time"]["average"] == 200.0
    assert out["kinds"]["kakera"]["all_time"]["active_days"] == 3


def test_all_time_average_is_over_active_days_not_calendar_days():
    """A month the macro was off is not a run of zero-earning days."""
    _reset()
    _kakera("2026-01-01", 500)
    _kakera(DAY, 500)
    out = stats_index.daily_report(_store(), date_key=DAY)
    assert out["kinds"]["kakera"]["all_time"]["average"] == 500.0
    assert out["kinds"]["kakera"]["all_time"]["delta_pct"] == 0.0


def test_all_time_abstains_when_the_day_is_the_only_one():
    _reset()
    _kakera(DAY, 500)
    all_time = stats_index.daily_report(_store(), date_key=DAY)["kinds"]["kakera"]["all_time"]
    assert all_time["average"] is None and all_time["delta_pct"] is None


# --- hours --------------------------------------------------------------------


def test_hourly_kakera_splits_by_method_across_24_buckets():
    _reset()
    _kakera(DAY, 100, method="kakera_click", ktype="kakeraP", time="03:15:00")
    _kakera(DAY, 700, method="bku_reset", time="03:45:00")
    _kakera(DAY, 50, method="kakera_click", ktype="kakeraP", time="21:00:00")
    hourly = stats_index.daily_report(_store(), date_key=DAY)["hourly"]["kakera_by_method"]
    by_id = {row["id"]: row["values"] for row in hourly}
    assert len(by_id["kakera_click"]) == 24
    assert by_id["kakera_click"][3] == 100
    assert by_id["kakera_click"][21] == 50
    assert by_id["bku_reset"][3] == 700


def test_hourly_sphere_and_key_stay_on_their_own_scales():
    _reset()
    _sphere(DAY, 40, time="05:00:00")
    out = stats_index.daily_report(_store(), date_key=DAY)["hourly"]
    assert out["sphere"][5] == 40
    assert sum(out["key"]) == 0


# --- perk 8 tape --------------------------------------------------------------


def test_perk8_tape_skips_purple_because_it_never_takes_a_slot():
    _reset()
    _kakera(DAY, 10, ktype="kakeraP", time="01:00:00")
    _kakera(DAY, 20, ktype="kakeraO", time="02:00:00")
    tape = _scoped()["tapes"]["perk8"]
    assert [slot["label"] for slot in tape["slots"]] == ["Orange"]
    assert "purple" in tape["note"].lower()


def test_perk8_tape_stops_at_the_daily_budget():
    _reset()
    for i in range(50):
        _kakera(DAY, 1, ktype="kakeraO", time="%02d:00:00" % (i % 24))
    tape = _scoped()["tapes"]["perk8"]
    assert len(tape["slots"]) == stats_index.PERK8_DAILY_CLICKS == 40
    assert tape["candidates"] == 50


def test_perk8_tape_says_it_is_an_approximation():
    """The log does not mark which click spent a slot, and the page must not pretend."""
    _reset()
    _kakera(DAY, 1, ktype="kakeraO")
    assert _scoped()["tapes"]["perk8"]["exact"] is False


def test_perk8_tape_ignores_income_that_was_never_a_click():
    _reset()
    _kakera(DAY, 9000, method="bku_reset")
    assert _scoped()["tapes"]["perk8"]["slots"] == []


# --- perk 9 tape --------------------------------------------------------------


def test_perk9_tape_keeps_the_order_the_buttons_were_clicked():
    _reset()
    _sphere(DAY, 10, stype="spG", time="04:00:00")
    _sphere(DAY, 10, stype="spB", time="01:00:00")
    _sphere(DAY, 10, stype="spY", time="09:00:00")
    tape = _scoped()["tapes"]["perk9"]
    assert [slot["label"] for slot in tape["slots"]] == ["Blue", "Green", "Yellow"]
    assert tape["exact"] is True


def test_perk9_tape_flags_transforms_which_pay_out_as_another_colour():
    _reset()
    _sphere(DAY, 10, stype="spL", time="01:00:00")
    _sphere(DAY, 10, stype="spG", time="02:00:00")
    slots = _scoped()["tapes"]["perk9"]["slots"]
    assert [slot["transform"] for slot in slots] == [True, False]


def test_perk9_tape_excludes_spheres_that_were_not_button_clicks():
    _reset()
    _sphere(DAY, 30, source="kakera_bonus", stype="kakeraO")
    _sphere(DAY, 90, source="minigame_oh", stype="spO")
    assert _scoped()["tapes"]["perk9"]["slots"] == []


# --- soulmates ----------------------------------------------------------------


def test_soulmates_are_listed_by_name_for_the_day():
    _reset()
    event_log.append("soulmate", {
        "character_name": "Klee", "series": "Genshin Impact", "time": "15:04:31",
        "date_key": DAY, "account_id": "a1", "account_name": "Main", "guild_name": "G",
    })
    rows = stats_index.daily_report(_store(), date_key=DAY)["soulmates"]
    assert rows == [{"character": "Klee", "series": "Genshin Impact", "time": "15:04",
                     "server": "G", "starwish": False}]


def test_soulmates_are_empty_rather_than_absent_on_a_day_with_none():
    _reset()
    _kakera(DAY, 10)
    assert stats_index.daily_report(_store(), date_key=DAY)["soulmates"] == []


# --- transforms ---------------------------------------------------------------


def test_perk9_tape_names_what_a_transform_turned_into():
    """The tape shows the sphere pressed; the payout belongs on hover."""
    _reset()
    event_log.append("sphere", {
        "amount": 552, "source": "sphere_click", "sphere_type": "spL",
        "sphere_resolved": ["spB", "spB", "spO"],
        "date_key": DAY, "time": "10:00:00", "account_id": "a1",
        "account_name": "Main", "guild_name": "G",
    })
    slot = _scoped()["tapes"]["perk9"]["slots"][0]
    assert slot["label"] == "Light"
    assert slot["transform"] is True
    # Ids, not names: the tooltip draws the sphere art rather than listing words.
    assert slot["resolved"] == ["spB", "spB", "spO"]


def test_a_plain_sphere_click_resolves_to_nothing():
    _reset()
    _sphere(DAY, 35, stype="spG")
    slot = _scoped()["tapes"]["perk9"]["slots"][0]
    assert slot["transform"] is False
    assert slot["resolved"] == []


# --- the tapes refuse to generalise -------------------------------------------


def test_tapes_are_empty_when_the_report_covers_more_than_one_pairing():
    """Two accounts each get 40 perk-8 clicks; laid on one tape that reads as 80."""
    _reset()
    _kakera(DAY, 10, ktype="kakeraO")
    _sphere(DAY, 35, stype="spG")
    out = stats_index.daily_report(_store(), date_key=DAY)
    assert out["scope"]["scoped"] is False
    for key in ("perk8", "perk9"):
        assert out["tapes"][key]["slots"] == []
        assert out["tapes"][key]["scoped"] is False
        assert out["tapes"][key]["note"] == stats_index.TAPE_SCOPE_NOTE
    # The rest of the day still adds up across everything — that is the point of
    # the general view.
    assert out["kinds"]["kakera"]["total"] == 10
    assert out["kinds"]["sphere"]["total"] == 35


def test_one_half_of_a_scope_is_not_a_scope():
    """A server hosts several accounts and an account plays several servers."""
    _reset()
    _kakera(DAY, 10, ktype="kakeraO")
    account_only = stats_index.daily_report(_store(), date_key=DAY, account="a1")
    server_only = stats_index.daily_report(_store(), date_key=DAY, server="G")
    assert account_only["tapes"]["perk8"]["scoped"] is False
    assert server_only["tapes"]["perk8"]["scoped"] is False


def test_a_scoped_report_says_so_and_draws_its_tape():
    _reset()
    _kakera(DAY, 10, ktype="kakeraO")
    out = _scoped()
    assert out["scope"] == {"account": "a1", "server": "G", "scoped": True}
    assert out["tapes"]["perk8"]["scoped"] is True
    assert [slot["label"] for slot in out["tapes"]["perk8"]["slots"]] == ["Orange"]


def test_a_scope_that_matches_nothing_still_draws_an_empty_tape_not_a_note():
    """"Nobody clicked" and "we cannot tell whose clicks these are" differ."""
    _reset()
    _kakera(DAY, 10, ktype="kakeraO")
    out = stats_index.daily_report(_store(), date_key=DAY, account="a1", server="Other")
    assert out["tapes"]["perk8"]["scoped"] is True
    assert out["tapes"]["perk8"]["slots"] == []
