"""Sheets ($bonus, $shop, $ov …) go to whoever typed the command."""

from macro.sheet_attribution import SheetAskers, attribute_sheet

MAIN, ALT, STRANGER = 554009750375890945, 1410311771092422777, 42


def _who(kind, asker, *, alts=True, scope=""):
    return attribute_sheet(
        kind, asker=asker, scope_account=scope, run_account="main-acc",
        main_user_id=MAIN, alt_user_ids={ALT: "alt-acc"} if alts else {},
    )


def test_each_asker_gets_its_own_sheet():
    assert _who("bonus", MAIN) == "main-acc"
    assert _who("bonus", ALT) == "alt-acc"
    assert _who("bonus", STRANGER) is None          # another player's upgrades
    assert _who("settings", STRANGER) == "main-acc"  # server-wide: fine


def test_unknown_asker():
    assert _who("bonus", None, alts=False) == "main-acc"  # solo: as before
    assert _who("bonus", None) is None                     # alts present: don't guess
    assert _who("settings", None) == "main-acc"


def test_scope_fetch_wins():
    assert _who("bonus", STRANGER, scope="hop-acc") == "hop-acc"


def test_askers_expire_and_track_per_command():
    now = [0.0]
    askers = SheetAskers(window=20, clock=lambda: now[0])
    askers.observe("bonus", ALT)
    askers.observe("ov", MAIN)
    askers.observe("wa", STRANGER)  # not a sheet command
    assert askers.asker("bonus") == ALT and askers.asker("ov") == MAIN
    now[0] = 25
    assert askers.asker("bonus") is None


def test_alt_needs_its_bonus_and_flags_ov_differences():
    from macro.alt_readiness import alt_readiness

    assert alt_readiness(bonus={}, shop={}, ov={}, main_ov={})["ready"] is False
    bonus = {"power_cost_per_kakera_button": 30, "kakera_max_power": 145}
    main_ov = {"setfooter": True, "displaykeys": False, "toggleletters": False}
    alt_ov = {"setfooter": True, "displaykeys": True, "toggleletters": False}
    report = alt_readiness(bonus=bonus, shop={}, ov=alt_ov, main_ov=main_ov)
    assert report["ready"] is True
    assert [d["key"] for d in report["ov_diffs"]] == ["displaykeys"]
    # Nothing to compare when the main's $ov is missing.
    assert alt_readiness(bonus=bonus, shop={}, ov=alt_ov, main_ov={})["ov_diffs"] == []
