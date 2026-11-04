"""Sending a list plan (`macro/list_send.py`) against a scripted Mudae.

The scripts follow what Mudae was captured doing on 2026-11-04: a clear asks
for ``confirm`` and then ticks the clear command; adds are ticked; a ``$sw``
past the starwish limit asks to sacrifice wishlist slots (y/n).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from macro.list_commands import plan_list_commands
from macro.list_send import ListSender, _yield_once, compare_list, starwish_trade_rule

CLEAR_PROMPT = "Type confirm to confirm the clean of your $disablelist."
TOGGLED_ON = (
    "Western animanga series are now DISABLED for YOUR rolls! ($ima western)\n"
    "Use $disable western INSTEAD OF $togglewestern if you want to be able to roll "
    "your wished/antidisabled western characters."
)
TOGGLED_OFF = "Real Life People series are now ENABLED for YOUR rolls!"
WRALL_PROMPT = "Type confirm to confirm the clean of all YOUR wishes (characters and series)."
SW_PROMPT = (
    "You reached your limit of 9 $starwish!\n"
    "Would you like to sacrifice 8 wishlist slots to upgrade this limit by +1? (y/n/yes/no)"
)


class FakeMudae:
    """``behaviour(command)`` → ``tick`` / ``cross`` / ``clear`` / ``sw`` / ``silent``,
    or ``toggled_on`` / ``toggled_off`` (a toggle: no tick, only a reply)."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.sent: list[str] = []
        self.texts: list[str] = []
        self.state: dict[int, str] = {}
        self.answered: set[int] = set()
        self.tick_waits: list[str] = []

    def drain_queue(self):
        pass

    async def send_command(self, command):
        self.sent.append(command)
        mid = len(self.sent)
        self.state[mid] = self.behaviour(command)
        return mid

    async def send_text(self, text):
        self.texts.append(text)
        last = len(self.sent)
        if self.state[last] == "clear" and text == "confirm":
            self.answered.add(last)
        if self.state[last] == "sw" and text == "y":
            self.answered.add(last)

    async def wait_for_mudae_tick(self, message_id, *, timeout=0.0):
        self.tick_waits.append(self.sent[message_id - 1])
        state = self.state[message_id]
        if state == "tick":
            return True
        # A clear / starwish question is ticked once answered: wait a little,
        # like the reader does, rather than looking once.
        for _ in range(50):
            if state in ("clear", "sw") and message_id in self.answered:
                return True
            await _yield_once()
        return False

    async def wait_for_mudae_cross(self, message_id, *, timeout=0.0):
        await asyncio.sleep(0)
        return self.state[message_id] == "cross"

    async def wait_for(self, predicate, *, timeout=0.0):
        await asyncio.sleep(0)
        last = len(self.sent)
        text = {
            "clear": CLEAR_PROMPT,
            "sw": SW_PROMPT,
            "toggled_on": TOGGLED_ON,
            "toggled_off": TOGGLED_OFF,
        }.get(self.state.get(last, ""))
        if text and last not in self.answered:
            snap = SimpleNamespace(is_mudae=True, content=text, embeds=[], components=[])
            if predicate(snap, None):
                return snap, None
        return None


async def _nosleep(_s):
    return None


def _send(mudae, plan, **kw):
    return asyncio.run(ListSender(mudae, sleep=_nosleep).run(plan, **kw))


def test_clear_is_confirmed_before_anything_is_added():
    plan = plan_list_commands("dl", {"entries": ["A", "B"]})
    mudae = FakeMudae(lambda c: "clear" if c == "$eall" else "tick")
    outcome = _send(mudae, plan, toggles=["$toggleirl"])
    assert outcome.ok, outcome.reason
    assert mudae.sent == ["$eall", "$d A$B", "$toggleirl"]
    assert mudae.texts == ["confirm"]


def test_a_clear_that_never_answers_stops_before_adding():
    plan = plan_list_commands("adl", {"entries": ["A"]})
    mudae = FakeMudae(lambda c: "silent" if c == "$aeall" else "tick")
    outcome = _send(mudae, plan)
    assert not outcome.ok
    assert mudae.sent == ["$aeall"]
    assert "did not answer" in outcome.reason


def test_a_refused_add_stops_the_send():
    plan = plan_list_commands("adl", {"entries": ["A"]})
    mudae = FakeMudae(lambda c: "clear" if c == "$aeall" else "cross")
    outcome = _send(mudae, plan)
    assert not outcome.ok and "❌" in outcome.reason


REAL_SW_PROMPT = (
    "You reached your limit of 29 $starwish!\n"
    "Would you like to sacrifice 1,122 wishlist slots to upgrade this limit by +33? (y/n/yes/no)"
)


def test_starwish_trade_rule_from_the_real_offer():
    from mudae.parsers.list_prompts import parse_list_prompt

    fields = parse_list_prompt(REAL_SW_PROMPT).fields
    assert (fields["starwish_limit"], fields["sacrifice_slots"], fields["gain"]) == (29, 1122, 33)
    # 1,324 − 1,122 = 202 slots, room for 168 wishes: accept.
    ok, why = starwish_trade_rule(1324, 168)(fields)
    assert ok and "1,324 → 202" in why
    # Too few slots left for the preset: refuse.
    ok, why = starwish_trade_rule(1324, 250)(fields)
    assert not ok and "fewer than the preset's 250" in why
    # Size unknown: refuse and say how to fix it.
    ok, why = starwish_trade_rule(None, 10)(fields)
    assert not ok and "Fetch $wl" in why


def test_a_second_offer_counts_the_slots_already_traded():
    decide = starwish_trade_rule(1324, 168)
    fields = {"starwish_limit": 29, "sacrifice_slots": 1000, "gain": 20}
    assert decide(fields)[0] is True  # 1,324 → 324
    assert decide(fields)[0] is False  # 324 → −676


def test_starwish_trade_is_answered_by_the_rule():
    entries = [{"name": "Rebecca", "starwish": True, "locked": False, "kakera_wish": False}]
    plan = plan_list_commands("wl", {"entries": entries})
    behaviour = lambda c: "clear" if c == "$wrall" else ("sw" if c.startswith("$sw") else "tick")

    refused = FakeMudae(behaviour)
    outcome = asyncio.run(
        ListSender(refused, sleep=_nosleep, starwish_trade=lambda f: (False, "no room")).run(plan)
    )
    assert not outcome.ok and outcome.reason == "no room"
    assert refused.texts == ["confirm", "n"]

    accepted = FakeMudae(behaviour)
    outcome = asyncio.run(
        ListSender(accepted, sleep=_nosleep, starwish_trade=lambda f: (True, "traded")).run(plan)
    )
    assert outcome.ok and outcome.trades == ["traded"]
    assert accepted.texts == ["confirm", "y"]

    # No rule at all: refuse.
    default = FakeMudae(behaviour)
    outcome = _send(default, plan)
    assert not outcome.ok and default.texts == ["confirm", "n"]


def test_a_tick_the_gateway_never_delivers_is_found_by_rechecking():
    """The remaining $wrall pause: the tick event never arrives.

    The reader's wait re-fetches the message when it times out; with short
    re-checks the tick is found on the second check, not after 12 s.
    """
    calls: list[float] = []

    class LateTick(FakeMudae):
        async def wait_for_mudae_tick(self, message_id, *, timeout=0.0):
            if self.state[message_id] != "clear":
                return await super().wait_for_mudae_tick(message_id, timeout=timeout)
            if message_id not in self.answered:
                return False  # no event, and nothing to find yet
            calls.append(timeout)
            return len(calls) >= 2  # found by the re-fetch at the end of check 2

    plan = plan_list_commands("wl", {"entries": [{"name": "Lucy"}]})
    mudae = LateTick(lambda c: "clear" if c == "$wrall" else "tick")
    outcome = _send(mudae, plan)
    assert outcome.ok
    assert calls == [2.0, 2.0]


def test_an_add_without_a_tick_is_recorded_not_fatal():
    plan = plan_list_commands("adl", {"entries": ["A"]})
    mudae = FakeMudae(lambda c: "clear" if c == "$aeall" else "silent")
    outcome = _send(mudae, plan)
    assert outcome.ok
    assert outcome.unconfirmed == ["$ad A"]


def test_nitro_plan_is_used_when_asked():
    names = [f"Series name number {i:04d}" for i in range(150)]
    plan = plan_list_commands("adl", {"entries": names})
    assert plan["split"]
    mudae = FakeMudae(lambda c: "clear" if c == "$aeall" else "tick")
    _send(mudae, plan, nitro=True)
    assert len(mudae.sent) == 1 + len(plan["nitro"])


def test_compare_list():
    wanted = {"entries": [
        {"name": "Reze", "starwish": True, "locked": True, "kakera_wish": False},
        {"name": "Lucy", "starwish": False, "locked": True, "kakera_wish": False},
    ]}
    same = {"entries": [
        {"name": "reze", "starwish": True, "locked": True, "kakera_wish": False, "owned": True},
        {"name": "Lucy", "starwish": False, "locked": True, "kakera_wish": False},
    ]}
    assert compare_list("wl", wanted, same) == []
    swapped = {"entries": list(reversed(same["entries"]))}
    assert "order differs" in compare_list("wl", wanted, swapped)[0]
    unlocked = {"entries": [same["entries"][0], {**same["entries"][1], "locked": False}]}
    assert "wrong wish type" in compare_list("wl", wanted, unlocked)[0]
    assert compare_list("dl", {"entries": ["A"], "toggles": []}, {"entries": ["A", "B"], "toggles": [{"command": "$toggleirl"}]}) == [
        "unexpected 1: B",
        "toggles differ: wanted none, found $toggleirl",
    ]


def test_toggles_wait_for_the_reply_not_a_tick():
    plan = plan_list_commands("dl", {"entries": ["A"]})
    states = {"$eall": "clear", "$togglewestern": "toggled_on", "$toggleirl": "toggled_off"}
    mudae = FakeMudae(lambda c: states.get(c, "tick"))
    outcome = _send(mudae, plan, toggles=[{"text": "$togglewestern", "on": True}, {"text": "$toggleirl", "on": False}])
    assert outcome.ok and outcome.unconfirmed == [] and outcome.warnings == []
    assert mudae.sent == ["$eall", "$d A", "$togglewestern", "$toggleirl"]
    assert not any(c.startswith("$toggle") for c in mudae.tick_waits)


def test_a_toggle_that_went_the_wrong_way_is_reported():
    plan = plan_list_commands("dl", {"entries": ["A"]})
    mudae = FakeMudae(lambda c: {"$eall": "clear", "$toggleirl": "toggled_off"}.get(c, "tick"))
    outcome = _send(mudae, plan, toggles=[{"text": "$toggleirl", "on": True}])
    assert outcome.ok
    assert outcome.warnings == ["$toggleirl turned it off, the preset wants it on"]


def test_wrall_prompt_wording_is_recognised_and_confirmed():
    from mudae.parsers.list_prompts import is_list_clear_prompt, parse_list_prompt, toggle_result

    assert is_list_clear_prompt(WRALL_PROMPT)
    assert parse_list_prompt(WRALL_PROMPT).fields["prompt"] == "clear"
    assert toggle_result(TOGGLED_ON) is True and toggle_result(TOGGLED_OFF) is False
    assert toggle_result(WRALL_PROMPT) is None

    class WrallMudae(FakeMudae):
        async def wait_for(self, predicate, *, timeout=0.0):
            await asyncio.sleep(0)
            last = len(self.sent)
            if self.state.get(last) == "clear" and last not in self.answered:
                snap = SimpleNamespace(is_mudae=True, content=WRALL_PROMPT, embeds=[], components=[])
                if predicate(snap, None):
                    return snap, None
            return None

    plan = plan_list_commands("wl", {"entries": [{"name": "Lucy"}]})
    mudae = WrallMudae(lambda c: "clear" if c == "$wrall" else "tick")
    outcome = _send(mudae, plan)
    assert outcome.ok and mudae.texts == ["confirm"]


class _Clock:
    """A clock that only moves when the sender sleeps."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += max(0.0, seconds)


def test_every_message_is_at_least_a_second_after_the_last():
    clock = _Clock()
    sends: list[float] = []

    class Timed(FakeMudae):
        async def send_command(self, command):
            sends.append(clock.now)
            return await super().send_command(command)

        async def send_text(self, text):
            sends.append(clock.now)
            return await super().send_text(text)

    entries = [{"name": f"C{i}", "starwish": i % 3 == 0, "locked": True, "kakera_wish": False} for i in range(9)]
    plan = plan_list_commands("wl", {"entries": entries})
    mudae = Timed(lambda c: "clear" if c == "$wrall" else "tick")
    outcome = asyncio.run(ListSender(mudae, sleep=clock.sleep, clock=clock).run(plan))
    assert outcome.ok
    assert len(sends) == 2 + len(plan["regular"])  # $wrall, confirm, adds
    gaps = [b - a for a, b in zip(sends, sends[1:])]
    assert all(g >= 1.0 for g in gaps), gaps


def test_confirm_tick_is_caught_even_when_it_lands_during_the_send():
    """The $wrall pause: Mudae ticks the clear while `confirm` is still going out.

    This fake behaves like the reader: a tick only reaches waits that are
    already listening when it arrives, and a later wait would time out.
    """

    class FastTick(FakeMudae):
        def __init__(self, behaviour):
            super().__init__(behaviour)
            self.listening: set[int] = set()
            self.caught: set[int] = set()

        async def wait_for_mudae_tick(self, message_id, *, timeout=0.0):
            if self.state[message_id] != "clear":
                return await super().wait_for_mudae_tick(message_id, timeout=timeout)
            self.listening.add(message_id)
            try:
                for _ in range(50):
                    if message_id in self.caught:
                        return True
                    await _yield_once()
                return False
            finally:
                self.listening.discard(message_id)

        async def send_text(self, text):
            await super().send_text(text)
            last = len(self.sent)
            if text == "confirm" and last in self.listening:
                self.caught.add(last)

    plan = plan_list_commands("wl", {"entries": [{"name": "Lucy"}]})
    mudae = FastTick(lambda c: "clear" if c == "$wrall" else "tick")
    outcome = _send(mudae, plan)
    assert outcome.ok, outcome.reason


def test_reader_remembers_a_tick_that_landed_before_the_wait():
    from mudae.constants import MUDAE_BOT_IDS
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor(token="x", channel_id=5)
    mudae_id = next(iter(MUDAE_BOT_IDS))
    message = SimpleNamespace(id=42, channel=SimpleNamespace(id=5))
    tick = SimpleNamespace(message=message, emoji="\u2705")
    asyncio.run(monitor._handle_reaction_add(tick, SimpleNamespace(id=mudae_id)))
    assert asyncio.run(monitor.wait_for_mudae_tick(42, timeout=0.01)) is True
    cross = SimpleNamespace(message=SimpleNamespace(id=43, channel=SimpleNamespace(id=5)), emoji="\u274c")
    asyncio.run(monitor._handle_reaction_add(cross, SimpleNamespace(id=mudae_id)))
    assert asyncio.run(monitor.wait_for_mudae_cross(43, timeout=0.01)) is True


def test_skip_clear_goes_straight_to_the_adds():
    plan = plan_list_commands("sdl", {"entries": ["Abra", "Absol"]})
    assert plan["clear"]["text"] == "$serverenableall"
    mudae = FakeMudae(lambda c: "tick")
    outcome = _send(mudae, plan, skip_clear=True)
    assert outcome.ok
    assert mudae.sent == ["$sdc Abra$Absol"] and mudae.texts == []
