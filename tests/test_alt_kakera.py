"""Alts take the kakera the main leaves for lack of power — one alt per button."""

from __future__ import annotations

import asyncio

from macro.account_pool import AccountPool, AltSpec
from macro.actions import DiscordActions
from macro.alt_kakera import AltKakera, alt_click_cost
from macro.alt_rules import rules_for_tier
from macro.config import MacroConfig
from macro.turns import ChannelCoordinator
from mudae.parsers.pipeline import parse_message
from mudae.types import MudaeMessageSnapshot


def _snap(content: str) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=1000, channel_id=1, channel_name="c", guild_id=1, guild_name="s",
        author_id=432610292342587392, author_name="Mudae", is_mudae=True,
        content=content, embeds=[], buttons=[], created_at="",
    )


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
        text = self.reply(self.name, custom_id)
        if text:
            snap = _snap(text)
            asyncio.get_running_loop().call_soon(self.on_parsed, snap, parse_message(snap))
        return True


def _setup(reply, *, powers=(100, 100), ready=(True, True)):
    coord = ChannelCoordinator("main", [], reply_hold=0)
    mons = {}

    def make_monitor(token, channel_id, on_parsed):
        mon = Mon(token, reply)
        mon.on_parsed = on_parsed
        mons[token] = mon
        return mon

    pool = AccountPool(coord, make_monitor=make_monitor, make_actions=DiscordActions)
    specs = [AltSpec(a, a, a, rules_for_tier("support"), MacroConfig()) for a in ("alt1", "alt2")]
    return pool, specs, mons, powers, ready


def _run(reply, buttons, *, powers=(100, 100), ready=(True, True), perk_8=False):
    async def go():
        pool, specs, mons, _, _ = _setup(reply)
        await pool.start(specs, 1)
        for (acc, s), power, ok in zip(pool.sessions.items(), powers, ready):
            s.state.power_percent = power
            s.ready = ok
        helper = AltKakera(pool, outcome_timeout=0.5)
        fields = {"buttons": buttons, "perk_8": perk_8}
        if perk_8:
            helper.main_power_short(99, fields)
            await asyncio.sleep(0)
            return pool, mons, 0
        clicked = await helper.handle(99, buttons)
        return pool, mons, clicked

    return asyncio.run(go())


ORANGE = {"is_kakera": True, "custom_id": "o1", "emoji": "kakeraO"}
BLUE = {"is_kakera": True, "custom_id": "b1", "emoji": "kakera"}


def claim(name, custom_id):
    return f"<:kakeraO:1> {name} +700 ($k)"


def test_first_alt_in_order_takes_it_at_full_price():
    pool, mons, clicked = _run(claim, [ORANGE])
    assert clicked == 1
    assert mons["alt1"].clicks == [(99, "o1")] and mons["alt2"].clicks == []
    s = pool.sessions["alt1"]
    assert s.state.power_percent == 100 - alt_click_cost(s.state, "kakeraO") == 70
    assert s.kakera_from_main_rolls == 700


def test_colours_outside_the_alt_list_are_left():
    # Support's default list starts at orange: blue is not worth an alt's power.
    _, mons, clicked = _run(claim, [BLUE])
    assert clicked == 0 and not mons["alt1"].clicks and not mons["alt2"].clicks


def test_skips_alts_without_power_or_without_bonus():
    _, mons, clicked = _run(claim, [ORANGE], powers=(10, 100))
    assert clicked == 1 and not mons["alt1"].clicks and mons["alt2"].clicks
    _, mons, clicked = _run(claim, [ORANGE], ready=(False, True))
    assert clicked == 1 and not mons["alt1"].clicks and mons["alt2"].clicks
    _, mons, clicked = _run(claim, [ORANGE], ready=(False, False))
    assert clicked == 0


def test_a_refused_click_passes_to_the_next_alt_once():
    def reply(name, custom_id):
        if name == "alt1":
            return f"**{name}**, you can't react to kakera for **45** min."
        return claim(name, custom_id)

    pool, mons, clicked = _run(reply, [ORANGE])
    assert clicked == 1
    assert len(mons["alt1"].clicks) == 1 and len(mons["alt2"].clicks) == 1


def test_another_accounts_claim_is_not_taken_as_ours():
    # alt1 hears only the main's claim on that button: no answer of its own.
    def reply(name, custom_id):
        return claim("lukazade234", custom_id) if name == "alt1" else claim(name, custom_id)

    _, mons, clicked = _run(reply, [ORANGE])
    assert clicked == 1 and mons["alt2"].clicks  # passed on after alt1 heard nothing


def test_never_on_a_perk_8_roll():
    _, mons, _ = _run(claim, [ORANGE], perk_8=True)
    assert not mons["alt1"].clicks and not mons["alt2"].clicks


DK_REPLY = "**+3,100**<:kakera:469835869059153940> added to your kakera collection (**5,000** total)"


def test_alt_short_of_power_uses_its_own_dk_then_clicks():
    async def go():
        pool, specs, mons, _, _ = _setup(claim)
        await pool.start(specs, 1)
        sent: list[str] = []
        for s in pool.sessions.values():
            s.ready = True
            s.state.power_percent = 10
        alt1 = pool.sessions["alt1"]
        alt1.state.dk_stock = 1
        mon = mons["alt1"]

        async def send_command(command, prefix=None):
            sent.append(command)
            snap = _snap(DK_REPLY)
            asyncio.get_running_loop().call_soon(mon.on_parsed, snap, parse_message(snap))
            return 1

        mon.send_command = send_command
        helper = AltKakera(pool, outcome_timeout=0.5, dk_timeout=0.5, dk_settle=0)
        clicked = await helper.handle(99, [ORANGE])
        return pool, mons, sent, clicked

    pool, mons, sent, clicked = asyncio.run(go())
    assert clicked == 1 and sent == ["dk"]
    assert mons["alt1"].clicks == [(99, "o1")] and mons["alt2"].clicks == []
    st = pool.sessions["alt1"].state
    assert st.dk_stock == 0
    assert st.power_percent == st.power_max_percent - alt_click_cost(st, "kakeraO")


def test_dk_switch_off_leaves_the_button_to_the_next_alt():
    async def go():
        pool, specs, mons, _, _ = _setup(claim)
        await pool.start(specs, 1)
        for s, power in zip(pool.sessions.values(), (10, 100)):
            s.ready = True
            s.state.power_percent = power
        alt1 = pool.sessions["alt1"]
        alt1.state.dk_stock = 1
        alt1.spec.rules.kakera.use_dk = False
        helper = AltKakera(pool, outcome_timeout=0.5, dk_timeout=0.5, dk_settle=0)
        return mons, await helper.handle(99, [ORANGE])

    mons, clicked = asyncio.run(go())
    assert clicked == 1 and not mons["alt1"].clicks and mons["alt2"].clicks
