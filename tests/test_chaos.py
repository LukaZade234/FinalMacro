"""Chaos-kakera parser and macro follow-up (rolls, discount, omega, free, wish)."""

from __future__ import annotations

import asyncio
from collections import deque
from unittest.mock import patch

import pytest

from macro.chaos_followup import (
    apply_chaos_hourly_rolls,
    chaos_extra_rolls,
    discounted_reaction_cost,
    merge_tu_hourly_rolls,
    original_hourly_rolls,
)
from macro.config import CharacterClaimRules, KakeraReactionRules, MacroConfig
from macro.kakera_reactor import KakeraReactor
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState
from mudae.key_log import record_chaos_omega, reset_for_tests
from mudae.parsers.chaos import parse_chaos_rewards
from mudae.parsers.kakera import parse_kakera_claim
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult


def _snap(
    message_id: int,
    *,
    content: str = "",
    buttons: list | None = None,
    embeds: list | None = None,
) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id,
        channel_id=1,
        channel_name="mudae",
        guild_id=1,
        guild_name="srv",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content=content,
        embeds=embeds or [],
        buttons=buttons or [],
        created_at="12:00:00",
    )


# --- parser ---


def test_parse_rolls_this_hour_from_log():
    content = (
        "<:kakeraC:1441097472587075758>**lukazade234 +13,252** ($k)\n"
        "<:kakeraC:1441097472587075758>**+86** <:sp:1437140700604137554>\n"
        "<:kakeraC:1441097472587075758>**+5 rolls** this hour."
    )
    result = parse_kakera_claim(content)
    assert result.fields["amount"] == 13252
    assert result.fields["chaos_rolls_this_hour"] == 5
    assert "+5 rolls" in result.summary


def test_parse_rolls_this_hour_without_kakera_on_same_line():
    content = (
        "<:kakeraC:1>**user +100** ($k)\n"
        "**+5 rolls** this hour."
    )
    assert parse_chaos_rewards(content).rolls_this_hour == 5


def test_parse_ten_and_fifteen_rolls_same_line():
    for n in (10, 15):
        content = (
            "<:kakeraC:1>**user +100** ($k)\n"
            f"<:kakeraC:1>**+{n} rolls** this hour."
        )
        assert parse_chaos_rewards(content).rolls_this_hour == n


def test_parse_stored_minigames_not_shop5():
    content = (
        "<:kakeraC:1>**lukazade234 +8,460** ($k)\n"
        "<:kakeraC:1>**+1 $oc stored!**\n"
        "<:kakeraC:1>**+1 $oh stored!**\n"
        "<:kakeraC:1>**+1 $oq stored!**\n"
        "<:kakeraC:1>**+1 $ot stored!**"
    )
    rewards = parse_chaos_rewards(content)
    assert rewards.minigames == {"oc": 1, "oh": 1, "oq": 1, "ot": 1}
    assert rewards.shop_perk5_ot == 0
    fields = parse_kakera_claim(content).fields
    assert fields["chaos_minigames"] == rewards.minigames
    assert "shop_perk5_ot" not in fields


def test_shop5_ot_is_not_chaos_minigame():
    content = (
        "<:kakeraC:1>**lukazade234 +18,232** ($k)\n"
        "<:kakeraC:1>**+86** <:sp:1>\n"
        "(Shop 5) **+1 $ot stored!**"
    )
    result = parse_kakera_claim(content)
    assert result.fields["shop_perk5_ot"] == 1
    assert "chaos_minigames" not in result.fields


def test_shop5_ot_on_non_chaos_kakera():
    content = (
        "<:kakeraO:1>**lukazade234 +3,618** ($k) "
        "**+46** <:sp:1>\n"
        "(Shop 5) **+1 $ot stored!**"
    )
    result = parse_kakera_claim(content)
    assert result.fields["kakera_type"] == "kakeraO"
    assert result.fields["shop_perk5_ot"] == 1
    assert "chaos_rolls_this_hour" not in result.fields


def test_parse_kakeraloot_one():
    content = (
        "<:kakeraC:1>**lukazade234 +8,080** ($k)\n"
        "<:kakeraC:1>A **kakeraloot** spawned!\n"
        "\n"
        "<:rollstack:1><:mudapin:1><:quant2x:1>\n"
        "\n"
        "<:rollstack:1> **+2** rolls stacked (Stock: 22,946.4)\n"
    )
    rewards = parse_chaos_rewards(content)
    assert rewards.kakeraloots == 1
    assert rewards.kakeraloot_stacked == 2.0
    assert rewards.loot_rows


def test_parse_kakeraloot_ten_example():
    content = (
        "<:kakeraC:1>lukazade234 +16,578 ($k)\n"
        "<:kakeraC:1>+86 <:sp:1>\n"
        "<:kakeraC:1>10 kakeraloots spawned!\n"
        "\n"
        ":1tierUS::mudapin::quant2x:\n"
        ":1tierUS::quant2x:\n"
        ":rollstack::morekakera::quant2x::qualityup:\n"
        "+9.2 rolls stacked\n"
        ":morekakera: +617 kakera\n"
        "+2 LVL of wish protection\n"
    )
    rewards = parse_chaos_rewards(content)
    assert rewards.kakeraloots == 10
    assert rewards.kakeraloot_stacked == 9.2
    assert rewards.kakeraloot_kakera == 617
    assert rewards.wish_protect_levels == 2
    assert rewards.minigames == {}


def test_chaos_kakera_with_stacked_rolls_is_not_us():
    from mudae.parsers.pipeline import parse_mudae_message

    content = (
        "<:kakeraC:1>**user +100** ($k)\n"
        "<:kakeraC:1>A **kakeraloot** spawned!\n"
        "<:rollstack:1> **+2** rolls stacked (Stock: 22,946.4)\n"
    )
    result = parse_mudae_message(_snap(1, content=content))
    assert result.kind == MessageKind.KAKERA_CLAIM
    assert result.fields["chaos_kakeraloots"] == 1
    assert result.fields.get("chaos_kakeraloot_stacked") == 2.0
    assert "us_stacked" not in result.fields


def test_parse_power_discount_percentages():
    for pct in (50, 20, 35):
        content = (
            "<:kakeraC:1>**user +100** ($k)\n"
            f"<:kakeraC:1>**{pct}% kakera power discount** "
            "when you clicked on this chaos kakera."
        )
        assert parse_chaos_rewards(content).power_discount_pct == float(pct)


def test_parse_omega_keys():
    content = (
        "<:kakeraC:1>**lukazade234 +8,080** ($k)\n"
        "<:kakeraC:1>**+5** <:omegakey:1473308158263951582> ($ok)"
    )
    result = parse_kakera_claim(content)
    assert result.fields["chaos_omega_keys"] == 5
    assert "+5 omega" in result.summary


def test_parse_free_kakera_and_wish():
    owned = (
        "<:kakeraC:1>**user +100** ($k)\n"
        "<:kakeraC:1>A character you own spawned with **2 free kakera buttons**, "
        "only you can click!"
    )
    assert parse_chaos_rewards(owned).free_kakera == 2
    wish = (
        "<:kakeraC:1>**user +100** ($k)\n"
        "<:kakeraC:1>A **wish** from your wishlist spawned!"
    )
    assert parse_chaos_rewards(wish).wish_spawn is True


def test_non_chaos_claim_does_not_grow_fields():
    content = (
        "<:kakeraO:605112954391887888>**lukazade234 +3,618** ($k) "
        "**+46** <:sp:1437140700604137554>"
    )
    result = parse_kakera_claim(content)
    assert result.fields == {
        "earn_method": "kakera_click",
        "kakera_type": "kakeraO",
        "amount": 3618,
        "spheres": 46,
        "claimed_by": "lukazade234",
    }


# --- arithmetic ---


def test_discounted_reaction_cost():
    assert discounted_reaction_cost(30.0, 50) == 15.0
    assert discounted_reaction_cost(30.0, 20) == 24.0
    assert discounted_reaction_cost(15.0, None) == 15.0
    assert discounted_reaction_cost(0.0, 50) == 0.0


def test_apply_chaos_hourly_rolls_tracks_extras():
    state = AccountState(rolls_left=2)
    assert apply_chaos_hourly_rolls(state, 5) == 7
    assert state.chaos_rolls_left == 5
    assert state.rolls_left == 7
    merge_tu_hourly_rolls(state, 7)
    assert state.rolls_left == 7
    assert chaos_extra_rolls(state) == 0
    assert original_hourly_rolls(state) == 7
    state.chaos_rolls_left = 5
    state.rolls_left = 5
    merge_tu_hourly_rolls(state, 0)
    assert state.rolls_left == 5
    assert state.chaos_rolls_left == 5


def test_record_chaos_omega_source():
    reset_for_tests()
    snap = _snap(99)
    created = record_chaos_omega(snap, amount=5, character_name="Shinobu")
    assert len(created) == 1
    assert created[0]["key_type"] == "omega"
    assert created[0]["amount"] == 5
    assert created[0]["source"] == "chaos"
    assert record_chaos_omega(snap, amount=5) == []


# --- reactor ---


class _QueueActions:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, str]] = []
        self.sent: list[tuple[str, str | None]] = []
        self._queue: list[tuple[MudaeMessageSnapshot, ParseResult]] = []
        self._outcomes: deque[tuple[MudaeMessageSnapshot, ParseResult]] = deque()
        self.claim_parsed: ParseResult | None = None

    def feed(self, snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> None:
        self._queue.append((snapshot, parsed))

    def feed_outcome(self, snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> None:
        self._outcomes.append((snapshot, parsed))

    def collect_queued(self, predicate):
        matches = [item for item in self._queue if predicate(*item)]
        self._queue = [item for item in self._queue if item not in matches]
        return matches

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        self.clicks.append((message_id, custom_id))
        return True

    async def wait_for(self, predicate, *, timeout: float = 8.0):
        del timeout
        if self._outcomes:
            item = self._outcomes[0]
            if predicate(*item):
                self._outcomes.popleft()
                return item
        for index, item in enumerate(self._queue):
            if predicate(*item):
                return self._queue.pop(index)
        return None

    async def send_command(self, command: str, *, prefix: str | None = None) -> int:
        self.sent.append((command, prefix))
        return 1

    async def wait_for_mudae_tick(self, message_id: int, *, timeout: float = 5.0) -> bool:
        del message_id, timeout
        return True

    async def wait_for_rt_use(self, *, timeout: float = 12.0) -> ParseResult:
        del timeout
        return ParseResult(
            kind=MessageKind.COMMAND_RESPONSE,
            summary="$rt",
            fields={"rt_used": True, "claim_available": True},
        )

    async def wait_for_claim(self, *, timeout: float = 8.0) -> ParseResult:
        del timeout
        if self.claim_parsed is not None:
            return self.claim_parsed
        return ParseResult(
            kind=MessageKind.MARRIAGE,
            summary="claimed",
            fields={"winner": "me", "character": "WishChar"},
        )

    async def fetch_message_snapshot(self, message_id: int):
        del message_id
        return None


def _chaos_fields(emoji: str = "kakeraC") -> dict:
    return {
        "character_name": "Fors Wall",
        "keys": [{"type": "chaos", "level": 1}],
        "buttons": [
            {
                "kind": "kakera",
                "is_kakera": True,
                "custom_id": "chaos1",
                "emoji": emoji,
            }
        ],
    }


async def _fast_sleep(_delay: float) -> None:
    return None


def test_reactor_spends_discounted_power_and_adds_rolls():
    async def _case() -> None:
        content = (
            "<:kakeraC:1>**me +100** ($k)\n"
            "<:kakeraC:1>**+5 rolls** this hour.\n"
            "<:kakeraC:1>**50% kakera power discount** when you clicked "
            "on this chaos kakera."
        )
        parsed = parse_kakera_claim(content)
        state = AccountState(power_percent=100.0, power_max_percent=155.0, rolls_left=2)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True, types_allowed=["kakeraC"]
            ),
        )
        actions = _QueueActions()
        actions.feed_outcome(_snap(50, content=content), parsed)
        logs: list[str] = []
        reactor = KakeraReactor(
            actions=actions, config=config, state=state, log=logs.append
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            clicks = await reactor.react(message_id=1, fields=_chaos_fields())
        assert clicks == 1
        assert state.rolls_left == 7
        assert state.chaos_rolls_left == 5
        # Chaos key halves 30% → 15%, then 50% off → 7.5%.
        assert state.power_percent == pytest.approx(92.5, abs=0.01)
        assert any("50% power discount" in line for line in logs)
        assert any("+5 rolls this hour" in line for line in logs)

    asyncio.run(_case())


def test_reactor_clicks_free_kakera_at_zero_cost():
    async def _case() -> None:
        content = (
            "<:kakeraC:1>**me +100** ($k)\n"
            "<:kakeraC:1>A character you own spawned with **2 free kakera buttons**, "
            "only you can click!"
        )
        claim = parse_kakera_claim(content)
        spawn_buttons = [
            {
                "kind": "kakera",
                "emoji": "kakeraY",
                "custom_id": "free0",
                "disabled": False,
            },
            {
                "kind": "kakera",
                "emoji": "kakeraY",
                "custom_id": "free1",
                "disabled": False,
            },
        ]
        spawn = ParseResult(
            kind=MessageKind.KAKERA_BUTTONS,
            summary="Pearl",
            fields={
                "character_name": "Pearl (SU)",
                "claimed": True,
                "can_claim": False,
                "buttons": spawn_buttons,
            },
        )
        yellow_claim = parse_kakera_claim(
            "<:kakeraY:1>**me +10** ($k)"
        )
        state = AccountState(power_percent=40.0, power_max_percent=155.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True, types_allowed=["kakeraC"]
            ),
        )
        actions = _QueueActions()
        actions.feed_outcome(_snap(50, content=content), claim)
        actions.feed(_snap(80, buttons=spawn_buttons), spawn)
        actions.feed_outcome(_snap(81), yellow_claim)
        actions.feed_outcome(_snap(82), yellow_claim)
        logs: list[str] = []
        reactor = KakeraReactor(
            actions=actions, config=config, state=state, log=logs.append
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            await reactor.react(message_id=1, fields=_chaos_fields())
        assert any(cid == "free0" for _mid, cid in actions.clicks)
        assert any(cid == "free1" for _mid, cid in actions.clicks)
        assert state.power_percent == pytest.approx(25.0, abs=0.01)
        assert any("free kakera" in line for line in logs)

    asyncio.run(_case())


def test_reactor_claims_wish_and_uses_rt():
    async def _case() -> None:
        content = (
            "<:kakeraC:1>**me +100** ($k)\n"
            "<:kakeraC:1>A **wish** from your wishlist spawned!"
        )
        claim = parse_kakera_claim(content)
        wish_buttons = [
            {
                "kind": "claim",
                "emoji": "❤️",
                "custom_id": "9p8p7",
                "disabled": False,
            }
        ]
        wish = ParseResult(
            kind=MessageKind.CLAIM_BUTTONS,
            summary="WishChar",
            fields={
                "character_name": "WishChar",
                "can_claim": True,
                "claimed": False,
                "buttons": wish_buttons,
            },
        )
        state = AccountState(
            power_percent=100.0,
            claim_available=False,
            rt_available=True,
            own_user_ids=[123],
        )
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True, types_allowed=["kakeraC"]
            ),
            character_claim=CharacterClaimRules(
                enabled=True,
                claim_on_wish_ping=True,
                auto_use_rt=True,
            ),
        )
        actions = _QueueActions()
        actions.feed_outcome(_snap(50, content=content), claim)
        actions.feed(_snap(90, buttons=wish_buttons), wish)
        logs: list[str] = []
        reactor = KakeraReactor(
            actions=actions, config=config, state=state, log=logs.append
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            with patch("macro.post_roll.asyncio.sleep", new=_fast_sleep):
                await reactor.react(message_id=1, fields=_chaos_fields())
        assert any(cmd == "rt" for cmd, _p in actions.sent)
        assert any(cid == "9p8p7" for _mid, cid in actions.clicks)
        assert any("chaos wish spawn" in line or "Claiming WishChar" in line for line in logs)

    asyncio.run(_case())


def test_reactor_logs_omega_keys():
    async def _case() -> None:
        reset_for_tests()
        content = (
            "<:kakeraC:1>**me +100** ($k)\n"
            "<:kakeraC:1>**+5** <:omegakey:1> ($ok)"
        )
        parsed = parse_kakera_claim(content)
        state = AccountState(power_percent=100.0)
        config = MacroConfig(
            prefix="$",
            kakera_reaction=KakeraReactionRules(
                enabled=True, types_allowed=["kakeraC"]
            ),
        )
        actions = _QueueActions()
        actions.feed_outcome(_snap(50, content=content), parsed)
        keys_notified = []
        reactor = KakeraReactor(
            actions=actions,
            config=config,
            state=state,
            log=lambda _m: None,
            on_keys=lambda: keys_notified.append(1),
        )
        with patch("macro.kakera_reactor.asyncio.sleep", new=_fast_sleep):
            await reactor.react(message_id=1, fields=_chaos_fields())
        assert keys_notified == [1]

    asyncio.run(_case())


# --- hourly extras are spent ---


def test_hourly_loop_spends_chaos_extra_rolls_before_refill():
    from tests.test_roll_cycle import _FakeActions, _make_engine, _roll, _run_normal, _tu

    added = {"n": 0}

    async def _add_extras(self, **_kwargs):
        if added["n"] == 0:
            apply_chaos_hourly_rolls(self.state, 2)
            added["n"] = 1
        return 0

    actions = _FakeActions(
        tu_script=[_tu(1, 30), _tu(0, 30)],
        roll_script=[_roll(1, 0), _roll(2, 1), _roll(3, 0)],
    )
    engine, state = _make_engine(actions)
    with patch("macro.kakera_reactor.KakeraReactor.react", new=_add_extras):
        _run_normal(engine)

    assert len(actions.roll_commands()) == 3
    assert any("waiting 30m until hourly refill" in entry.text for entry in state.activity_log)


def test_hourly_loop_rolls_chaos_extras_with_stop_at_two():
    """+N chaos rolls join the ordinary pool so the 2-left footer can fire."""
    from tests.test_roll_cycle import _FakeActions, _make_engine, _roll, _run_normal, _tu

    actions = _FakeActions(
        tu_script=[_tu(7, 30), _tu(0, 30)],
        roll_script=[
            _roll(1, 6),
            _roll(2, 5),
            _roll(3, 4),
            _roll(4, 3),
            _roll(5, 2),
            _roll(6, 1),
            _roll(7, 0),
        ],
    )
    engine, state = _make_engine(actions)
    state.chaos_rolls_left = 5

    _run_normal(engine)

    assert len(actions.roll_commands()) == 7
    assert any("Parsed 2 rolls left" in entry.text for entry in state.activity_log)
    assert any("Finished rolls after warning" in entry.text for entry in state.activity_log)
    assert not any("extra hourly roll" in entry.text for entry in state.activity_log)
