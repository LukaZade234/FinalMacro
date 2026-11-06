"""Alt connections, the lane's reply hold, and per-account $tu."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from macro.account_pool import AccountPool, AltSpec
from macro.actions import DiscordActions
from macro.alt_rules import rules_for_tier
from macro.config import MacroConfig
from macro.turns import ChannelCoordinator
from mudae.parsers.tu import parse_tu
from mudae.types import MessageKind, ParseResult


def _tu(user: str, *, claim: bool = True) -> str:
    claim_line = "you __can__ claim right now!" if claim else "you can't claim for another **1h 05** min."
    return (
        f"**{user}**, {claim_line} The next claim reset is in **41** min.\n"
        "You have **11** rolls left. Next rolls reset in **41** min.\n"
        "Power: **62%**\n"
    )


def test_tu_names_its_user():
    assert parse_tu(_tu("noa_alt")).fields["tu_user"] == "noa_alt"
    assert "tu_user" not in parse_tu("You have **3** rolls left.").fields


class FakeMonitor:
    def __init__(self, token, channel_id, on_parsed, *, user=None, fail=False):
        self.token, self.channel_id, self.on_parsed = token, channel_id, on_parsed
        self.user = user or token
        self.fail = fail
        self.sent: list[str] = []
        self.is_connected = False
        self.after_send = None

    async def start_background(self):
        self.is_connected = not self.fail
        return not self.fail

    async def stop_background(self):
        self.is_connected = False

    def get_own_user_id(self):
        return abs(hash(self.user)) % 10_000

    def get_own_usernames(self):
        return [self.user]

    async def send_command(self, command, prefix=None):
        self.sent.append(command)
        if self.after_send is not None:
            asyncio.get_running_loop().call_soon(self.after_send)
        return 1


def _spec(acc, token=None):
    return AltSpec(account_id=acc, name=acc, token=token if token is not None else acc, rules=rules_for_tier("support"), config=MacroConfig())


def _pool(fail=()):
    coord = ChannelCoordinator("main", [], reply_hold=0)
    monitors: dict[str, FakeMonitor] = {}

    def make_monitor(token, channel_id, on_parsed):
        mon = FakeMonitor(token, channel_id, on_parsed, fail=token in fail)
        monitors[token] = mon
        return mon

    pool = AccountPool(coord, make_monitor=make_monitor, make_actions=DiscordActions)
    return pool, coord, monitors


def test_failed_or_tokenless_alts_are_left_out_of_the_turn_order():
    pool, coord, _ = _pool(fail={"a2"})
    up = asyncio.run(pool.start([_spec("a1"), _spec("a2"), _spec("a3", token=""), _spec("a4")], 1))
    assert up == 2
    assert coord.roster == ["main", "a1", "a4"]
    rows = pool.snapshot()
    assert [(r["name"], r["turn"]) for r in rows][:2] == [("a1", 1), ("a4", 2)]
    assert {r["status"] for r in rows if r["turn"] == 0} == {"offline", "no token"}


def test_notification_standby_takes_alts_out_of_turns_and_back():
    pool, coord, _ = _pool()

    async def run():
        await pool.start([_spec("a1"), _spec("a2")], 1)
        await pool.release_for_notifications()
        assert coord.alts == []
        await pool.restore_for_notifications()
        assert coord.alts == ["a1", "a2"]

    asyncio.run(run())


def test_alt_reads_only_its_own_tu():
    pool, _, monitors = _pool()

    async def run():
        await pool.start([_spec("a1")], 1)
        session = pool.sessions["a1"]
        mon = monitors["a1"]

        def replies():
            # The main's $tu arrives first on the alt's connection too — ignored.
            for user, claim in (("lukazade234", False), ("a1", True)):
                text = _tu(user, claim=claim)
                parsed = ParseResult(kind=MessageKind.TU, summary="", fields=parse_tu(text).fields, warnings=[])
                mon.on_parsed(SimpleNamespace(is_mudae=True, content=text, message_id=5), parsed)

        mon.after_send = replies
        task = asyncio.create_task(pool.refresh_status(session))
        assert await task is True
        assert session.state.claim_available is True
        assert mon.sent == ["tu"]
        # Mudae's name for the alt, which its transfer prompts use.
        assert session.mudae_name == "a1"
        assert session.names()[0] == "a1"

    asyncio.run(run())


def test_lane_hold_keeps_others_out_until_the_reply_is_read():
    async def run():
        coord = ChannelCoordinator("main", ["a1"], command_gap=0, reply_hold=5.0)
        events: list[str] = []

        async with coord.command_lane("main"):
            events.append("main sends $tu")

        async def alt_send():
            async with coord.command_lane("a1"):
                events.append("a1 sends")

        task = asyncio.create_task(alt_send())
        for _ in range(5):
            await asyncio.sleep(0)
        events.append("main reads reply")
        coord.reply_seen("main")
        await task
        return events

    assert asyncio.run(run()) == ["main sends $tu", "main reads reply", "a1 sends"]


def test_actions_without_a_lane_behave_as_before():
    mon = FakeMonitor("t", 1, None)
    actions = DiscordActions(mon)
    assert actions.lane_account == ""
    asyncio.run(actions.send_command("tu"))
    assert mon.sent == ["tu"]


def test_transfers_are_refused_without_the_main():
    pool, _, _ = _pool()

    async def run():
        await pool.start([_spec("a1")], 1)
        return await pool.give_to_main("a1", kind="kakera", amount=100)

    result = asyncio.run(run())
    assert not result.ok and result.reason == "main not connected"


# The alts' full $tu (2026-11-05). The main trims its own with $tuarrange.
ALT_FULL_TU = (
    "**lukijade**, you can't claim for another **27** min.\n"
    "You have **34** rolls (+**3** $mk) left. Next rolls reset in **27** min.\n"
    "$daily is available!\n\n"
    "You __can__ react to kakera right now!\n"
    "Power: **145%**\n"
    "Each kakera button consumes 30% of your reaction power.\n"
    "Your characters with 10+ keys consume half the power (15%)\n"
    "Stock: **6,337,375**<:kakera:469835869059153940>\n\n"
    "$rt is available!\n"
    "$dk is ready!\n"
    "You may vote right now!\n\n"
    "**4** $oh left for today, **1** $oc, **0** $oq and **0** $ot.\n"
    "**11h 27** min before the refill.\n"
    "Stock: **128** <:sp:1437140700604137554>\n"
    "=> $tuarrange"
)


def test_full_tu_gives_balances_minigames_and_dk():
    f = parse_tu(ALT_FULL_TU).fields
    assert f["tu_user"] == "lukijade"
    assert f["dk_stock"] == 1  # "$dk is ready!": a single-use account
    assert f["rt_available"] is True
    assert (f["kakera_stock"], f["sphere_stock"]) == (6_337_375, 128)
    assert (f["oh_total"], f["oc_total"], f["oq_total"], f["ot_total"]) == (4, 1, 0, 0)
    assert f["daily_available"] is True and f["vote_available"] is True


def test_stock_lines_without_emojis_go_by_position():
    # Copied text loses custom emojis (the user's paste of kleinam0n's $tu).
    text = ALT_FULL_TU.replace("<:kakera:469835869059153940>", "").replace(
        " <:sp:1437140700604137554>", " "
    )
    f = parse_tu(text).fields
    assert (f["kakera_stock"], f["sphere_stock"]) == (6_337_375, 128)


def test_multi_dk_wording_and_trimmed_tu():
    f = parse_tu("**lukazade234**, you __can__ claim right now!\n**2** $dk available!").fields
    assert f["dk_stock"] == 2
    # A trimmed $tu has no balances: nothing to overwrite the last values with.
    assert "kakera_stock" not in f and "oh_total" not in f
    assert "kakera_stock" not in parse_tu("+2 rolls stacked (Stock: 22,946.4)").fields


def test_full_tu_lands_on_the_alt_row():
    from macro.state import AccountState
    from macro.tu_apply import apply_tu_fields

    state = AccountState()
    apply_tu_fields(state, parse_tu(ALT_FULL_TU).fields)
    from macro.account_pool import AltSession

    session = AltSession(spec=_spec("a1"), state=state)
    pool_row = session.snapshot(1)
    assert pool_row["dk_stock"] == 1
    assert pool_row["kakera_stock"] == 6_337_375 and pool_row["sphere_stock"] == 128
    assert pool_row["minigames_left"] == {"oh": 4, "oc": 1, "oq": 0, "ot": 0}
    # A later trimmed $tu keeps the balances.
    apply_tu_fields(state, parse_tu("**a1**, you __can__ claim right now!").fields)
    assert state.kakera_stock == 6_337_375


def test_stock_lines_with_short_emoji_names():
    # Mudae's balance lines carry :kakera: and :sp: — that alone says which is which.
    text = (
        "Power: **145%**\nStock: **589** :kakera:\n\n"
        "**4** $oh left for today, **1** $oc, **0** $oq and **0** $ot.\nStock: **128** :sp:"
    )
    f = parse_tu(text).fields
    assert (f["kakera_stock"], f["sphere_stock"]) == (589, 128)
    # Order does not matter when the emoji is there.
    swapped = "Stock: **128** :sp:\nPower: **145%**\nStock: **589** :kakera:"
    f = parse_tu(swapped).fields
    assert (f["kakera_stock"], f["sphere_stock"]) == (589, 128)


def test_pass_to_main_keeps_the_reserve_and_stops_on_failure():
    from macro.transfers import TransferResult

    pool, _, _ = _pool()
    calls: list[tuple] = []

    async def run(fail_on=None):
        await pool.start([_spec("a1")], 1)
        session = pool.sessions["a1"]
        session.state.kakera_stock, session.state.sphere_stock = 6_337_375, 128
        session.harem = [{"name": "Anna (PC)", "kakera": 400}, {"name": "Lucy", "kakera": 300}]

        async def give(acc, *, character=None, kind=None, amount=None, why=""):
            calls.append((character or kind, amount))
            ok = (character or kind) != fail_on
            return TransferResult(ok, character or kind, amount=amount, character=character)

        pool.give_to_main = give
        results = await pool.pass_to_main(
            "a1", kakera_keep=337_375, spheres_keep=500, characters=["Anna (PC)", "Lucy"]
        )
        return session, results

    session, results = asyncio.run(run())
    # Spheres are below the reserve: nothing sent for them.
    assert calls == [("kakera", 6_000_000), ("Anna (PC)", None), ("Lucy", None)]
    assert session.state.kakera_stock == 337_375 and session.harem == []

    calls.clear()
    pool2, _, _ = _pool()
    pool = pool2
    session, results = asyncio.run(run(fail_on="Anna (PC)"))
    assert [c[0] for c in calls] == ["kakera", "Anna (PC)"]  # Lucy never tried
    assert not results[-1].ok


def test_silent_mmk_means_an_empty_harem(monkeypatch):
    import macro.account_pool as ap

    monkeypatch.setattr(ap, "HAREM_SILENCE_SEC", 0.2)
    pool, _, monitors = _pool()

    async def run():
        await pool.start([_spec("a1")], 1)
        session = pool.sessions["a1"]
        session.harem = [{"name": "stale", "kakera": 1}]
        source = await pool._fetch_harem(session)
        return session, source, monitors["a1"].sent

    session, source, sent = asyncio.run(run())
    assert sent == ["mmk="]
    assert session.harem == [] and session.harem_pages == 0
    assert "empty" in source


def test_mmk_reply_to_the_alts_own_command_is_read():
    """2026-11-06: kleinam0n's '$mmk=' came back as a command response, which
    the alt's harem wait did not accept — so a harem holding Lucy read as empty."""
    from mudae.parsers.pipeline import parse_message
    from mudae.types import MudaeMessageSnapshot

    pool, _, monitors = _pool()

    async def run():
        await pool.start([_spec("a1")], 1)
        session = pool.sessions["a1"]
        mon = monitors["a1"]
        content = "a1's harem\n\nTotal value: 2,931,854\n\nLucy 2,931,854 ka"
        snap = MudaeMessageSnapshot(
            message_id=5, channel_id=1, channel_name="c", guild_id=1, guild_name="s",
            author_id=432610292342587392, author_name="Mudae", is_mudae=True,
            content=content, embeds=[], buttons=[], created_at="",
        )
        mon.after_send = lambda: mon.on_parsed(snap, parse_message(snap, reply_to_command="mmk="))
        source = await pool._fetch_harem(session)
        held = await pool.holds_character("a1", "Lucy")
        return session, source, held

    session, source, held = asyncio.run(run())
    assert source == "$mmk="
    assert session.harem == [{"name": "Lucy", "kakera": 2_931_854}]
    assert held is True


def test_an_alts_commands_are_spaced_from_its_own_last_one(monkeypatch):
    """Fetch sent $tu then $mmk= at once and Mudae sometimes missed the second."""
    import macro.account_pool as ap

    slept: list[float] = []

    async def fake_sleep(sec):
        slept.append(sec)

    monkeypatch.setattr(ap.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ap, "HAREM_SILENCE_SEC", 0)
    pool, _, monitors = _pool()

    async def run():
        await pool.start([_spec("a1")], 1)
        session = pool.sessions["a1"]
        session.last_command_at = 0.0
        await pool._fetch_harem(session)  # first command: no wait
        first = list(slept)
        await pool._fetch_harem(session)  # straight after: waits out the gap
        return first

    first = asyncio.run(run())
    assert first == []
    assert slept and slept[-1] > ap.OWN_COMMAND_GAP_SEC - 0.5
