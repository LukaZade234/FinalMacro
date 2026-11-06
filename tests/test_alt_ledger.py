"""The alts' ledger on disk, and automatic passing to the main."""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

from macro.alt_ledger import AltLedger
from macro.alt_passing import AltPassing
from macro.alt_rules import rules_for_tier
from macro.state import AccountState
from macro.transfers import TransferResult

DAY = dt.datetime(2026, 11, 5, 23, 35, tzinfo=dt.timezone.utc)


async def _nosleep(_s):
    return None


def _ledger(tmp_path, when=DAY):
    clock = {"now": when}
    led = AltLedger(tmp_path / "alts_ledger.json", clock=lambda: clock["now"])
    return led, clock


def test_counters_transfers_and_pending_survive_a_restart(tmp_path):
    led, _ = _ledger(tmp_path)
    led.add("a1", "claims")
    led.add("a1", "kakera_earned", 700)
    led.record_transfer("a1", "lukijade", TransferResult(True, "character", character="Flareon"), why="claimed for the main")
    led.record_transfer("a1", "lukijade", TransferResult(True, "kakera", amount=12_400), why="end of session")
    led.record_transfer("a1", "lukijade", TransferResult(False, "spheres", amount=10, reason="no prompt"))
    led.set_pending("a2", ["Kyuusaku Yumeno"])
    led.mark_passed("a1", "spheres")

    again, _ = _ledger(tmp_path)
    assert again.day() == {"a1": {"claims": 1, "kakera_earned": 700, "characters_given": 1, "kakera_passed": 12_400}}
    assert [t["why"] for t in again.transfers] == ["claimed for the main", "end of session", ""]
    assert again.transfers[-1]["ok"] is False
    assert again.pending == {"a2": ["Kyuusaku Yumeno"]}
    assert again.passed_today("a1", "spheres") and not again.passed_today("a1", "kakera")


def test_days_are_utc_and_the_week_adds_them_up(tmp_path):
    led, clock = _ledger(tmp_path)
    led.add("a1", "claims", 2)
    clock["now"] = DAY + dt.timedelta(hours=1)  # 00:35 UTC next day
    led.add("a1", "claims", 1)
    assert led.today() == "2026-11-06"
    assert led.day() == {"a1": {"claims": 1}}
    assert led.last_days(7) == {"a1": {"claims": 3}}
    clock["now"] = DAY + dt.timedelta(days=8)
    assert led.last_days(7) == {}
    assert not led.passed_today("a1", "kakera")


class _Pool:
    """Just what AltPassing uses."""

    def __init__(self, ledger, sessions, stocks, fail=()):
        self.ledger = ledger
        self._sessions = sessions
        self._stocks = stocks
        self._fail = set(fail)
        self.passed: list[tuple] = []

    def connected_sessions(self):
        return self._sessions

    async def read_stocks(self, acc):
        ka, sp = self._stocks[acc]
        s = next(s for s in self._sessions if s.spec.account_id == acc)
        s.state.kakera_stock, s.state.sphere_stock = ka, sp
        return ka is not None and sp is not None

    amount_to_pass = staticmethod(lambda stock, keep: max(0, int(stock) - int(keep)) if stock is not None else 0)

    async def pass_to_main(self, acc, *, kakera_keep=None, spheres_keep=None, why=""):
        kind = "kakera" if kakera_keep is not None else "spheres"
        self.passed.append((acc, kind, kakera_keep if kakera_keep is not None else spheres_keep, why))
        return [TransferResult(kind not in self._fail, kind)]


def _session(acc, *, kakera_mode, kakera_keep=0, sphere_mode="never", sphere_keep=0):
    rules = rules_for_tier("support")
    rules.kakera.pass_mode, rules.kakera.keep = kakera_mode, kakera_keep
    rules.spheres.pass_mode, rules.spheres.keep = sphere_mode, sphere_keep
    return SimpleNamespace(spec=SimpleNamespace(account_id=acc, name=acc, rules=rules), state=AccountState())


def test_end_of_session_passes_above_the_reserve_every_batch(tmp_path):
    led, _ = _ledger(tmp_path)
    pool = _Pool(led, [_session("a1", kakera_mode="session", kakera_keep=1000)], {"a1": (5000, 3)})
    assert asyncio.run(AltPassing(pool, sleep=_nosleep).batch_end()) == 1
    assert asyncio.run(AltPassing(pool, sleep=_nosleep).batch_end()) == 1
    assert pool.passed == [("a1", "kakera", 1000, "end of session")] * 2


def test_once_a_day_is_a_start_of_day_step_not_a_batch_end_one(tmp_path):
    led, clock = _ledger(tmp_path)
    alt = _session("a1", kakera_mode="never", sphere_mode="daily", sphere_keep=10)
    pool = _Pool(led, [alt], {"a1": (0, 50)})
    helper = AltPassing(pool, sleep=_nosleep)
    asyncio.run(helper.batch_end())
    assert pool.passed == []  # never after a roll batch
    asyncio.run(helper.start_of_day(alt))
    asyncio.run(helper.start_of_day(alt))
    assert pool.passed == [("a1", "spheres", 10, "once a day")]
    clock["now"] = DAY + dt.timedelta(hours=1)
    asyncio.run(helper.start_of_day(alt))
    assert len(pool.passed) == 2


def test_nothing_above_the_reserve_or_unreadable_stock_sends_nothing(tmp_path):
    led, _ = _ledger(tmp_path)
    pool = _Pool(
        led,
        [_session("a1", kakera_mode="session", kakera_keep=10_000), _session("a2", kakera_mode="session")],
        {"a1": (9_000, 0), "a2": (None, None)},
    )
    assert asyncio.run(AltPassing(pool, sleep=_nosleep).batch_end()) == 0
    assert pool.passed == []


def test_a_failed_daily_pass_is_retried_at_the_next_session_start(tmp_path):
    led, _ = _ledger(tmp_path)
    alt = _session("a1", kakera_mode="daily")
    pool = _Pool(led, [alt], {"a1": (500, 0)}, fail={"kakera"})
    helper = AltPassing(pool, sleep=_nosleep)
    asyncio.run(helper.start_of_day(alt))
    asyncio.run(helper.start_of_day(alt))
    assert len(pool.passed) == 2 and not led.passed_today("a1", "kakera")


# ---- the alt's start-of-day: minigames once a day, saved ---------------------


def _daily_pool(led, sessions):
    pool = _Pool(led, sessions, {s.spec.account_id: (0, 0) for s in sessions})
    pool.notify = lambda: None
    return pool


def test_minigames_run_once_a_day_and_are_not_checked_again(tmp_path):
    from macro.alt_daily import AltDaily

    led, clock = _ledger(tmp_path)
    alt = _session("a1", kakera_mode="never")
    alt.status = "watching"
    pool = _daily_pool(led, [alt])
    plays: list[str] = []

    async def play(session):
        plays.append(session.spec.account_id)
        return {"played": {"oh": {}, "oc": {}}, "reason": None}

    daily = AltDaily(pool, play_minigames=play, passing=AltPassing(pool, sleep=_nosleep))
    asyncio.run(daily.run_due())
    asyncio.run(daily.run_due())
    assert plays == ["a1"]
    # Saved: a restart the same day does not ask again.
    again = AltDaily(_daily_pool(AltLedger(tmp_path / "alts_ledger.json", clock=lambda: clock["now"]), [alt]),
                     play_minigames=play, passing=AltPassing(pool, sleep=_nosleep))
    asyncio.run(again.run_due())
    assert plays == ["a1"]
    clock["now"] = DAY + dt.timedelta(hours=1)  # next UTC day
    asyncio.run(daily.run_due())
    assert plays == ["a1", "a1"]


def test_an_undecided_minigame_run_is_retried_and_off_means_done(tmp_path):
    from macro.alt_daily import AltDaily

    led, _ = _ledger(tmp_path)
    alt = _session("a1", kakera_mode="never")
    alt.status = ""
    off = _session("a2", kakera_mode="never")
    off.status = ""
    off.spec.rules.spheres.minigames = False
    pool = _daily_pool(led, [alt, off])
    answers = [None, {"played": {}, "reason": None}]
    plays: list[str] = []

    async def play(session):
        plays.append(session.spec.account_id)
        return answers.pop(0)

    daily = AltDaily(pool, play_minigames=play, passing=AltPassing(pool, sleep=_nosleep))
    asyncio.run(daily.run_due())
    assert not led.done_today("a1", "minigames") and led.done_today("a2", "minigames")
    asyncio.run(daily.run_due())
    assert plays == ["a1", "a1"] and led.done_today("a1", "minigames")


def test_the_daily_pass_comes_after_the_minigames(tmp_path):
    from macro.alt_daily import AltDaily

    led, _ = _ledger(tmp_path)
    alt = _session("a1", kakera_mode="never", sphere_mode="daily")
    alt.status = ""
    pool = _daily_pool(led, [alt])
    pool._stocks["a1"] = (0, 40)
    order: list[str] = []

    async def play(session):
        order.append("games")
        return {"played": {"oh": {}}, "reason": None}

    real = pool.pass_to_main

    async def pass_to_main(*a, **k):
        order.append("pass")
        return await real(*a, **k)

    pool.pass_to_main = pass_to_main
    asyncio.run(AltDaily(pool, play_minigames=play, passing=AltPassing(pool, sleep=_nosleep)).run_due())
    assert order == ["games", "pass"]


def test_known_stocks_are_used_without_a_tu_and_a_failure_does_not_block_the_other(tmp_path):
    led, _ = _ledger(tmp_path)
    alt = _session("a1", kakera_mode="daily", sphere_mode="daily")
    alt.state.kakera_stock, alt.state.sphere_stock = 3_615_388, 2_980
    pool = _Pool(led, [alt], {"a1": (1, 1)}, fail={"kakera"})
    reads: list[str] = []
    real = pool.read_stocks

    async def read_stocks(acc):
        reads.append(acc)
        return await real(acc)

    pool.read_stocks = read_stocks
    asyncio.run(AltPassing(pool, sleep=_nosleep).start_of_day(alt))
    assert reads == []  # no $tu just before passing
    kinds = [p[1] for p in pool.passed]
    assert "spheres" in kinds  # kakera failing did not stop the sphere pass
    assert led.passed_today("a1", "spheres") and not led.passed_today("a1", "kakera")


def test_no_prompt_is_retried_once_after_a_pause_and_a_sent_y_is_not(tmp_path):
    led, _ = _ledger(tmp_path)
    alt = _session("a1", kakera_mode="daily")
    alt.state.kakera_stock, alt.state.sphere_stock = 500, 0
    pool = _Pool(led, [alt], {"a1": (500, 0)})
    answers = [
        TransferResult(False, "kakera", reason="no confirmation prompt"),
        TransferResult(True, "kakera", amount=500),
    ]
    sleeps: list[float] = []

    async def pass_to_main(acc, **_k):
        pool.passed.append(acc)
        return [answers.pop(0)]

    async def sleep(sec):
        sleeps.append(sec)

    pool.pass_to_main = pass_to_main
    assert asyncio.run(AltPassing(pool, sleep=sleep).start_of_day(alt)) == 1
    assert len(pool.passed) == 2 and sleeps[0] >= 1.0 and len(sleeps) == 2

    led2, _ = _ledger(tmp_path / "b") if (tmp_path / "b").mkdir() is None else (None, None)
    pool2 = _Pool(led2, [alt], {"a1": (500, 0)})
    sent_y = [TransferResult(False, "kakera", reason="no result", confirmed=True)]

    async def pass_once(acc, **_k):
        pool2.passed.append(acc)
        return [sent_y[0]]

    pool2.pass_to_main = pass_once
    asyncio.run(AltPassing(pool2, sleep=_nosleep).start_of_day(alt))
    assert len(pool2.passed) == 1
