"""One UTC day rolled up across every kind (Statistics › Report).

The other Statistics sub-pages slice the event cube by *kind*. The report
slices the same cells by *day*, so it needs no new storage — but it does need
to be honest about comparison: a day with no history behind it must say
"no baseline", not "0% change".
"""

from __future__ import annotations

from gui.accounts import AccountProfile
from mudae import event_log, stats_index


def _store(*accounts: AccountProfile):
    return type(
        "S",
        (),
        {
            "accounts": list(accounts),
            "active_account_id": accounts[0].id if accounts else "",
        },
    )()


MAIN = AccountProfile(id="a1", name="Main", type="Main")
ALT = AccountProfile(id="a2", name="Alt", type="Alt")


def _kakera(day: str, amount: int, *, method="kakera_click", account="a1", guild="Guild"):
    event_log.append(
        "kakera",
        {
            "amount": amount,
            "earn_method": method,
            "date_key": day,
            "account_id": account,
            "account_name": "Main" if account == "a1" else "Alt",
            "guild_name": guild,
        },
    )


def test_report_rolls_up_one_day_across_kinds():
    _kakera("2026-09-01", 100)
    _kakera("2026-09-01", 250, method="bku_reset")
    event_log.append(
        "sphere",
        {
            "amount": 900,
            "source": "perk9",
            "sphere_type": "spY",
            "date_key": "2026-09-01",
            "account_id": "a1",
            "guild_name": "Guild",
        },
    )

    report = stats_index.daily_report(_store(MAIN), date_key="2026-09-01")

    assert report["date"] == "2026-09-01"
    assert report["kinds"]["kakera"]["total"] == 350
    assert report["kinds"]["kakera"]["count"] == 2
    assert report["kinds"]["sphere"]["total"] == 900
    methods = {row["id"]: row["amount"] for row in report["kinds"]["kakera"]["by_method"]}
    assert methods == {"kakera_click": 100, "bku_reset": 250}


def test_a_day_with_no_history_reports_no_baseline_rather_than_zero():
    """"Nothing to compare with" is not "no change" — the UI must be able to tell."""
    _kakera("2026-09-01", 100)

    entry = stats_index.daily_report(_store(MAIN), date_key="2026-09-01")["kinds"]["kakera"]

    assert entry["delta_pct"] is None
    assert entry["average"] is None
    assert entry["baseline_days"] == 0


def test_delta_is_against_the_seven_days_before_not_all_history():
    # An old, much bigger day must not drag the recent baseline.
    _kakera("2026-01-01", 10_000)
    for day in ("2026-08-26", "2026-08-27", "2026-08-28"):
        _kakera(day, 100)
    _kakera("2026-09-01", 150)

    entry = stats_index.daily_report(_store(MAIN), date_key="2026-09-01")["kinds"]["kakera"]

    assert entry["baseline_days"] == 3
    assert entry["average"] == 100.0
    assert entry["delta_pct"] == 50.0


def test_baseline_only_counts_days_that_have_data():
    """Averaging over 7 slots when 2 had events would understate the baseline."""
    _kakera("2026-08-30", 200)
    _kakera("2026-08-31", 100)
    _kakera("2026-09-01", 150)

    entry = stats_index.daily_report(_store(MAIN), date_key="2026-09-01")["kinds"]["kakera"]

    assert entry["baseline_days"] == 2
    assert entry["average"] == 150.0
    assert entry["delta_pct"] == 0.0


def test_report_filters_by_account():
    _kakera("2026-09-01", 100, account="a1")
    _kakera("2026-09-01", 900, account="a2")

    both = stats_index.daily_report(_store(MAIN, ALT), date_key="2026-09-01")
    just_main = stats_index.daily_report(
        _store(MAIN, ALT), date_key="2026-09-01", account="a1"
    )

    assert both["kinds"]["kakera"]["total"] == 1000
    assert just_main["kinds"]["kakera"]["total"] == 100


def test_report_filters_by_server():
    _kakera("2026-09-01", 100, guild="Guild")
    _kakera("2026-09-01", 400, guild="Other")

    only = stats_index.daily_report(
        _store(MAIN), date_key="2026-09-01", server="Other"
    )
    assert only["kinds"]["kakera"]["total"] == 400


def test_soulmates_are_counted_not_summed():
    """A soulmate row has no amount — the event itself is the unit."""
    for name in ("2B", "Akame"):
        event_log.append(
            "soulmate",
            {
                "character_name": name,
                "date_key": "2026-09-01",
                "account_id": "a1",
                "guild_name": "Guild",
            },
        )

    entry = stats_index.daily_report(_store(MAIN), date_key="2026-09-01")["kinds"]["soulmate"]
    assert entry["total"] == 2


def test_trend_is_fourteen_days_ending_on_the_target():
    _kakera("2026-09-01", 100)

    trend = stats_index.daily_report(_store(MAIN), date_key="2026-09-01")["trend"]

    assert len(trend) == stats_index.REPORT_TREND_DAYS
    assert trend[-1]["date"] == "2026-09-01"
    assert trend[-1]["kakera"] == 100
    assert trend[0]["date"] == "2026-08-19"
    assert trend[0]["kakera"] == 0


def test_available_days_lists_only_days_with_data():
    _kakera("2026-08-30", 100)
    _kakera("2026-09-01", 100)

    report = stats_index.daily_report(_store(MAIN), date_key="2026-09-01")
    assert report["available_days"] == ["2026-08-30", "2026-09-01"]


def test_no_date_defaults_to_the_most_recent_day_with_data():
    _kakera("2026-08-30", 100)
    _kakera("2026-09-01", 250)

    report = stats_index.daily_report(_store(MAIN))
    assert report["date"] == "2026-09-01"
    assert report["kinds"]["kakera"]["total"] == 250


def test_an_empty_log_still_returns_a_usable_shape():
    report = stats_index.daily_report(_store(MAIN))

    assert report["available_days"] == []
    assert report["kinds"]["kakera"]["total"] == 0
    assert report["kinds"]["kakera"]["delta_pct"] is None
    assert len(report["trend"]) == stats_index.REPORT_TREND_DAYS
