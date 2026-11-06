"""Alts claim the main's rolls the main can't, then give them to the main."""

from __future__ import annotations

import asyncio

from macro.account_pool import AccountPool, AltSpec
from macro.actions import DiscordActions
from macro.alt_claims import AltClaims, rank_for_alts
from macro.alt_rules import rules_for_tier
from macro.config import CharacterClaimRules, MacroConfig
from macro.post_roll import RollRecord
from macro.state import AccountState
from macro.transfers import TransferResult
from macro.turns import ChannelCoordinator
from mudae.parsers.pipeline import parse_message
from mudae.types import MudaeMessageSnapshot


def _snap(content: str, message_id: int = 99) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id, channel_id=1, channel_name="c", guild_id=1, guild_name="s",
        author_id=432610292342587392, author_name="Mudae", is_mudae=True,
        content=content, embeds=[], buttons=[], created_at="",
    )


def married(user: str, character: str) -> str:
    return f"\U0001f496 {user} and {character} are now married! \U0001f496"


class Mon:
    def __init__(self, name, reply):
        self.name, self.reply = name, reply
        self.clicks: list[tuple[int, str]] = []
        self.on_parsed = None

    async def start_background(self):
        return True

    async def stop_background(self):
        pass

    def get_own_user_id(self):
        return abs(hash(self.name)) % 10_000

    def get_own_usernames(self):
        return [self.name]

    async def send_command(self, command, prefix=None):
        return 1

    async def click_button(self, message_id, custom_id):
        self.clicks.append((message_id, custom_id))
        text = self.reply(self.name, message_id)
        if text:
            snap = _snap(text)
            asyncio.get_running_loop().call_soon(self.on_parsed, snap, parse_message(snap))
        return True


def _record(mid: int, name: str, kakera: int, **extra) -> RollRecord:
    fields = {
        "character_name": name,
        "total_kakera": kakera,
        "can_claim": True,
        "claimed": False,
        "claim_method": "button",
        "buttons": [{"kind": "claim", "custom_id": f"claim-{mid}"}],
    }
    fields.update(extra)
    return RollRecord(message_id=mid, character_name=name, fields=fields)


NAMES = {1: "Reze", 2: "Makima", 3: "Power", 4: "Kobeni"}


def _won(name, mid):
    return married(name, NAMES[mid])


async def _pool(reply, *, can_claim=(True, True)):
    coord = ChannelCoordinator("main", [], reply_hold=0)
    mons = {}

    def make_monitor(token, channel_id, on_parsed):
        mon = Mon(token, reply)
        mon.on_parsed = on_parsed
        mons[token] = mon
        return mon

    pool = AccountPool(coord, make_monitor=make_monitor, make_actions=DiscordActions)
    specs = [AltSpec(a, a, a, rules_for_tier("support"), MacroConfig()) for a in ("alt1", "alt2")]
    await pool.start(specs, 1)
    for session, ok in zip(pool.sessions.values(), can_claim):
        session.ready = True
        session.state.claim_available = ok
    return pool, mons


def test_ranking_uses_the_mains_rules_as_if_it_had_a_claim():
    rules = CharacterClaimRules(enabled=True, only_final_hour=False)
    main = AccountState(claim_available=False)
    records = [
        _record(1, "Reze", 600),
        _record(2, "Makima", 900),
        _record(3, "Power", 700, claimed=True),
        _record(4, "Kobeni", 800, free_claim=True),
    ]
    ranked = rank_for_alts(records, rules, main, final_hour=True, expire_sec=45)
    assert [r.character_name for r in ranked] == ["Makima", "Reze"]
    assert main.claim_available is False  # the main's state is untouched


def test_batch_end_gives_the_2nd_and_3rd_best_to_the_alts_in_order():
    async def go():
        pool, mons = await _pool(_won)
        helper = AltClaims(pool, reply_timeout=0.5)
        # The main already took the best one; these are what is left, best first.
        claimed = await helper.batch_end([_record(2, "Makima", 900), _record(1, "Reze", 600)])
        return pool, mons, helper, claimed

    pool, mons, helper, claimed = asyncio.run(go())
    assert claimed == 2
    assert mons["alt1"].clicks == [(2, "claim-2")]
    assert mons["alt2"].clicks == [(1, "claim-1")]
    assert helper.pending == {"alt1": ["Makima"], "alt2": ["Reze"]}
    assert all(s.state.claim_available is False for s in pool.sessions.values())


def test_an_alt_without_a_claim_is_skipped():
    async def go():
        pool, mons = await _pool(_won, can_claim=(False, True))
        helper = AltClaims(pool, reply_timeout=0.5)
        await helper.batch_end([_record(2, "Makima", 900), _record(1, "Reze", 600)])
        return mons, helper

    mons, helper = asyncio.run(go())
    assert mons["alt1"].clicks == []
    assert helper.pending == {"alt2": ["Makima"]}


def test_someone_elses_claim_is_not_counted_and_not_passed_on():
    async def go():
        pool, mons = await _pool(lambda _n, mid: married("stranger", NAMES[mid]))
        helper = AltClaims(pool, reply_timeout=0.5)
        rec = _record(2, "Makima", 900)
        await helper.batch_end([rec])
        return mons, helper, rec

    mons, helper, rec = asyncio.run(go())
    assert helper.pending == {}
    assert rec.fields["claimed"] is True
    assert len(mons["alt1"].clicks) == 1 and mons["alt2"].clicks == []


def test_silence_passes_the_roll_to_the_next_alt():
    async def go():
        pool, mons = await _pool(lambda n, mid: None if n == "alt1" else _won(n, mid))
        helper = AltClaims(pool, reply_timeout=0.2)
        await helper.batch_end([_record(2, "Makima", 900)])
        return mons, helper

    mons, helper = asyncio.run(go())
    assert len(mons["alt1"].clicks) == 1 and len(mons["alt2"].clicks) == 1
    assert helper.pending == {"alt2": ["Makima"]}


def test_pending_claims_are_given_to_the_main_and_a_failure_is_kept():
    async def go():
        pool, _ = await _pool(_won)
        helper = AltClaims(pool, reply_timeout=0.5)
        helper.pending = {"alt1": ["Makima", "Reze"], "alt2": ["Power"]}
        gives = []

        async def give_to_main(acc, *, character=None, **_kw):
            gives.append((acc, character))
            ok = character != "Reze"
            return TransferResult(ok, "character", character=character, reason="" if ok else "no y")

        pool.give_to_main = give_to_main
        n = await helper.give_pending()
        return pool, helper, gives, n

    pool, helper, gives, n = asyncio.run(go())
    assert gives == [("alt1", "Makima"), ("alt1", "Reze"), ("alt2", "Power")]
    assert n == 2
    assert helper.pending == {"alt1": ["Reze"], "alt2": []}
    assert pool.sessions["alt1"].claimed_for_main == ["Reze"]


def _engine_stub(state, rules, offered):
    from types import SimpleNamespace

    return SimpleNamespace(
        alt_spare_claim=lambda rec, reason: offered.append((rec.character_name, reason)),
        _state=state,
        _config=SimpleNamespace(character_claim=rules),
        _final_roll_session=False,
        _log=lambda _t: None,
    )


def test_engine_offers_a_roll_the_main_would_claim_but_cannot():
    from macro.roll_cycle import RollCycleEngine
    from macro.roll_interrupts import RollInterruptContext

    rules = CharacterClaimRules(enabled=True, min_kakera=500)
    offered: list = []
    rec = _record(1, "Reze", 900)
    ctx = RollInterruptContext(fields=rec.fields, own_user_ids=[], wishlist_characters=[], wishlist_series=[])

    blocked = _engine_stub(AccountState(claim_available=False), rules, offered)
    RollCycleEngine._offer_spare_claim(blocked, rec, ctx)
    assert offered and offered[0][0] == "Reze"

    offered.clear()  # the main has its claim: it claims, not an alt
    RollCycleEngine._offer_spare_claim(_engine_stub(AccountState(claim_available=True), rules, offered), rec, ctx)
    cheap = _record(2, "Makima", 100)  # below the main's threshold
    cheap_ctx = RollInterruptContext(fields=cheap.fields, own_user_ids=[], wishlist_characters=[], wishlist_series=[])
    RollCycleEngine._offer_spare_claim(blocked, cheap, cheap_ctx)
    assert offered == []


def test_waiting_characters_come_back_from_the_ledger_after_a_restart(tmp_path):
    from macro.alt_ledger import AltLedger

    async def go():
        pool, _ = await _pool(_won)
        pool.ledger = AltLedger(tmp_path / "l.json")
        first = AltClaims(pool, reply_timeout=0.5)
        await first.batch_end([_record(2, "Makima", 900)])
        pool.ledger = AltLedger(tmp_path / "l.json")  # app restarted
        second = AltClaims(pool)
        return pool, second

    pool, second = asyncio.run(go())
    assert second.pending == {"alt1": ["Makima"]}
    assert pool.sessions["alt1"].claimed_for_main == ["Makima"]
    assert pool.ledger.day()["alt1"]["claims"] == 1


def test_farm_claims_are_returned_not_queued_and_farm_alts_skip_ordinary_claims():
    async def go():
        pool, mons = await _pool(_won)
        farm = {"on": True}
        helper = AltClaims(pool, reply_timeout=0.5, farm_active=lambda: farm["on"])
        # Support tier has Force divorce on: while the farm runs, no batch claims.
        assert await helper.batch_end([_record(2, "Makima", 900)]) == 0
        assert helper.farm_ready() is True
        got = await helper.claim_for_farm(_record(1, "Reze", 600))
        return pool, mons, helper, got

    pool, mons, helper, got = asyncio.run(go())
    assert got["account_id"] == "alt1" and got["name"] == "alt1"
    assert mons["alt1"].clicks == [(1, "claim-1")] and mons["alt2"].clicks == []
    assert helper.pending == {}  # the engine gives it back itself
    assert pool.sessions["alt1"].state.claim_available is False


def test_an_earlier_claim_of_the_same_character_is_not_read_as_this_one():
    """2026-11-06: lukijade's claim of Lucy from the first farm cycle was still
    queued when kleinam0n claimed Lucy on the second, and kleinam0n's own
    claim was read as "Lucy went to lukijade"."""

    async def go():
        pool, mons = await _pool(lambda n, _mid: married(n, "Makima"), can_claim=(False, True))
        stale = _snap(married("alt1", "Makima"), message_id=10)
        pool.sessions["alt2"].actions.feed(stale, parse_message(stale))
        helper = AltClaims(pool, reply_timeout=0.5)
        rec = _record(2, "Makima", 900)
        rec.message_id = 50  # the second cycle's roll, newer than the stale claim
        got = await helper.claim_for_farm(rec)
        return pool, got

    pool, got = asyncio.run(go())
    assert got is not None and got["account_id"] == "alt2"
    assert pool.sessions["alt2"].state.claim_available is False


def _with_rt(pool, mons, account_id, *, tick=True):
    sent: list[str] = []
    mon = mons[account_id]

    async def send_command(command, prefix=None):
        sent.append(command)
        return 1

    async def wait_for_mudae_tick(message_id, timeout=5.0):
        return tick

    mon.send_command = send_command
    mon.wait_for_mudae_tick = wait_for_mudae_tick
    state = pool.sessions[account_id].state
    state.rt_available = True
    state.set_claim_reset(90)
    return sent


def test_farm_alt_with_rt_and_no_claim_spends_rt_then_claims():
    async def go():
        pool, mons = await _pool(_won, can_claim=(False, False))
        sent = _with_rt(pool, mons, "alt1")
        helper = AltClaims(pool, reply_timeout=0.5, rt_settle=0)
        assert helper.farm_ready() is True
        got = await helper.claim_for_farm(_record(1, "Reze", 600))
        return pool, mons, sent, got

    pool, mons, sent, got = asyncio.run(go())
    assert sent == ["rt"]
    assert got is not None and got["account_id"] == "alt1"
    assert mons["alt1"].clicks == [(1, "claim-1")]
    state = pool.sessions["alt1"].state
    assert state.rt_available is False and state.claim_available is False


def test_alt_rt_waits_for_the_mains_own_claim_and_for_time_before_the_reset():
    async def go():
        pool, mons = await _pool(_won, can_claim=(False, False))
        _with_rt(pool, mons, "alt1")
        main = {"claim": True}
        helper = AltClaims(pool, reply_timeout=0.5, main_has_claim=lambda: main["claim"])
        first = helper.farm_ready()  # the main's own slot comes first
        main["claim"] = False
        second = helper.farm_ready()
        pool.sessions["alt1"].state.set_claim_reset(12)  # under 30m: saved
        third = helper.farm_ready()
        pool.sessions["alt1"].spec.rules.claims.spend_rt = False
        pool.sessions["alt1"].state.set_claim_reset(90)
        fourth = helper.farm_ready()
        return first, second, third, fourth

    assert asyncio.run(go()) == (False, True, False, False)
