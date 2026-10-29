"""``$kl`` kakera loots: parsing, classification, and the Run-page batch loop."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from macro.config import KakeraLootRules, MacroConfig
from macro.kakera_loot import KakeraLootRunner, kl_cooldown_sec, kl_gap_sec
from mudae.command_ack import is_mudae_command_deny_emoji
from mudae.parsers.classify import classify_message
from mudae.parsers.kakeraloot import parse_kakeraloot
from mudae.parsers.pipeline import parse_mudae_message
from mudae.parsers.reaction_power import parse_ku
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_KU = (
    "You can't react to kakera for **1h 21** min.\n"
    "Power: **3%**\n"
    "Each kakera button consumes **30%** of your reaction power.\n"
    "Your characters with 10+ keys consume half the power (15%)\n"
    "Stock: **190,748,290**<:kakera:469835869059153940>"
)

_RESULT = (
    "<:rollstack:1> +9,628.8 rolls stacked (Stock: 3,469,817.8)\n"
    "<:morekakera:2> +1,195,387 kakera\n"
    "<:disablemore:3> $limroul limits pushed away by 66 $wa, 66 $ha, 44 $wg, 44 $hg\n"
    "<:wishprotect:4> +5,742 LVL of wish protection!\n"
    "<:bku:5> +32% bku reset on starwishes"
)

_PROMPT = "Do you want to spend 6,000,000<:kakera:469835869059153940>? (y/n/yes/no)"


def _snap(content: str, message_id: int = 10) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id,
        channel_id=1,
        channel_name="test",
        guild_id=None,
        guild_name=None,
        author_id=432610292342587392,
        author_name="Mudae",
        content=content,
        embeds=[],
        buttons=[],
        is_mudae=True,
        created_at="",
    )


# ---- parsing ---------------------------------------------------------------


def test_ku_reads_kakera_stock_and_button_cost():
    fields = parse_ku(_KU).fields
    assert fields["kakera_stock"] == 190_748_290
    assert fields["power_consumption_percent"] == 30


def test_ku_stock_ignores_sphere_and_roll_stock():
    assert "kakera_stock" not in parse_ku("Stock: **3,924** <:sp:1>").fields
    assert "kakera_stock" not in parse_ku("+2 rolls stacked (Stock: 22,946.4)").fields


def test_result_reads_refund():
    parsed = parse_kakeraloot(_RESULT)
    assert parsed.kind == MessageKind.KAKERALOOT_RESULT
    assert parsed.fields["kl_kakera_gained"] == 1_195_387


def test_result_without_kakera_line_refunds_nothing():
    parsed = parse_kakeraloot("<:rollstack:1> **+2** rolls stacked (Stock: 10.0)")
    assert parsed.fields["kl_outcome"] == "result"
    assert parsed.fields["kl_kakera_gained"] == 0


def test_prompt_reads_amount():
    parsed = parse_kakeraloot(_PROMPT)
    assert parsed.kind == MessageKind.KAKERALOOT_PROMPT
    assert parsed.fields["kl_spend"] == 6_000_000


def test_unpaired_result_is_not_bonus_or_us():
    assert classify_message(_snap(_RESULT)) == MessageKind.KAKERALOOT_RESULT
    parsed = parse_mudae_message(_snap(_RESULT))
    assert parsed.fields["kl_outcome"] == "result"
    assert "us_stacked" not in parsed.fields


def test_paired_result_and_prompt():
    result = parse_mudae_message(_snap(_RESULT), reply_to_command="kl 12000")
    assert result.fields["kl_kakera_gained"] == 1_195_387
    prompt = parse_mudae_message(_snap(_PROMPT), reply_to_command="kl 12000")
    assert prompt.fields["kl_outcome"] == "prompt"


def test_bare_us_and_bonus_still_classify_as_before():
    us = parse_mudae_message(_snap("<:rollstack:1> You have **7,872.8** rolls stacked."))
    assert us.fields.get("us_stacked") == 7872.8
    bonus = "<:morekakera:1> · Kakera max power: **175%** ($kt)"
    assert classify_message(_snap(bonus)) == MessageKind.BONUS


def test_chaos_claim_with_loot_stays_a_kakera_claim():
    content = (
        "<:kakeraC:1>**user +100** ($k)\n"
        "<:kakeraC:1>A **kakeraloot** spawned!\n"
        "<:rollstack:1> **+2** rolls stacked (Stock: 22,946.4)\n"
    )
    assert parse_mudae_message(_snap(content)).kind == MessageKind.KAKERA_CLAIM


def test_deny_emoji():
    assert is_mudae_command_deny_emoji("❌")
    assert not is_mudae_command_deny_emoji("✅")


def test_rules_defaults_and_clamp():
    assert KakeraLootRules().batch_cost() == 6_000_000
    rules = KakeraLootRules.from_dict({"loot_value": 600, "batch": 50_000})
    assert rules.batch == 12_000
    cfg = MacroConfig.from_dict({"kakera_loot": {"batch": 1000}})
    assert cfg.kakera_loot.batch == 1000
    assert MacroConfig.from_dict(cfg.to_dict()).kakera_loot == cfg.kakera_loot


def test_cooldown_tiers():
    assert kl_cooldown_sec(12000) == 20.0
    assert kl_cooldown_sec(999) == 5.0
    assert kl_cooldown_sec(99) == 0.0
    assert kl_gap_sec(1000) == 21.0


# ---- the batch loop --------------------------------------------------------


class _FakeActions:
    """Answers each command from a script of Mudae replies."""

    def __init__(self, *, ku: list[int], kl: list[Any]) -> None:
        self.ku = list(ku)
        self.kl = list(kl)
        self.sent: list[str] = []
        self.texts: list[str] = []
        self._queue: list[ParseResult] = []
        self._crossed: set[int] = set()
        self._after_y: list[ParseResult] = []
        self._next_id = 100

    def drain_queue(self) -> None:
        self._queue.clear()

    async def send_command(self, command: str, *, prefix: str | None = None) -> int:
        self.sent.append(command)
        self._next_id += 1
        if command == "ku":
            stock = self.ku.pop(0)
            self._queue.append(parse_ku(f"Stock: **{stock:,}**<:kakera:1>"))
        else:
            step = self.kl.pop(0)
            if step == "cross":
                self._crossed.add(self._next_id)
            elif step == "silent":
                pass
            elif isinstance(step, tuple):  # ("prompt", amount, refund)
                _, amount, refund = step
                self._queue.append(
                    parse_kakeraloot(f"Do you want to spend {amount:,}<:kakera:1>? (y/n/yes/no)")
                )
                self._after_y.append(
                    parse_kakeraloot(f"<:morekakera:2> +{refund:,} kakera")
                )
            else:
                self._queue.append(parse_kakeraloot(f"<:morekakera:2> +{step:,} kakera"))
        return self._next_id

    async def send_text(self, text: str) -> int:
        self.texts.append(text)
        if text == "y" and self._after_y:
            self._queue.append(self._after_y.pop(0))
        return 0

    async def wait_for(self, predicate, *, timeout: float = 15.0):
        for _ in range(3):
            for parsed in list(self._queue):
                if predicate(None, parsed):
                    self._queue.remove(parsed)
                    return None, parsed
            await asyncio.sleep(0)
        return None

    async def wait_for_mudae_cross(self, message_id: int, *, timeout: float = 5.0) -> bool:
        await asyncio.sleep(0)
        return message_id in self._crossed


def _run(actions: _FakeActions, rules: KakeraLootRules | None = None) -> tuple[dict, list[str]]:
    lines: list[str] = []
    sleeps: list[float] = []

    async def _sleep(sec: float) -> None:
        sleeps.append(sec)

    runner = KakeraLootRunner(
        actions,
        SimpleNamespace(macro_active=False),
        rules=rules or KakeraLootRules(),
        log=lines.append,
        sleep=_sleep,
        clock=lambda: 0.0,
    )
    result = asyncio.run(runner.run())
    return result, lines


def test_stops_when_next_batch_is_unaffordable():
    actions = _FakeActions(ku=[14_000_000], kl=[1_195_387, 1_285_268])
    result, _ = _run(actions)
    assert actions.sent == ["ku", "kl 12000", "kl 12000"]
    assert result["batches"] == 2
    assert result["balance"] == 14_000_000 - 12_000_000 + 1_195_387 + 1_285_268
    assert result["reason"] == "insufficient"


def test_refund_keeps_the_run_going():
    # 11M covers one batch and leaves 5M; the 1.2M refund lifts that to 6.2M.
    actions = _FakeActions(ku=[11_000_000], kl=[1_200_000, 0])
    result, _ = _run(actions)
    assert result["batches"] == 2


def test_not_enough_for_one_batch_sends_nothing():
    actions = _FakeActions(ku=[5_500_000], kl=[])
    result, lines = _run(actions)
    assert actions.sent == ["ku"]
    assert result["batches"] == 0
    assert any("not enough" in line for line in lines)


def test_confirm_prompt_is_answered_y():
    actions = _FakeActions(ku=[6_000_000], kl=[("prompt", 6_000_000, 900_000)])
    result, _ = _run(actions)
    assert actions.texts == ["y"]
    assert result["batches"] == 1
    assert result["balance"] == 900_000


def test_prompt_for_the_wrong_amount_is_refused():
    actions = _FakeActions(ku=[20_000_000], kl=[("prompt", 7_200_000, 0)])
    result, _ = _run(actions)
    assert actions.texts == ["n"]
    assert result["reason"] == "wrong cost"
    assert result["batches"] == 0


def test_cross_resyncs_then_retries():
    actions = _FakeActions(ku=[6_000_000, 6_000_000], kl=["cross", 500_000])
    result, _ = _run(actions)
    assert actions.sent == ["ku", "kl 12000", "ku", "kl 12000"]
    assert result["batches"] == 1


def test_two_failures_in_a_row_stop():
    actions = _FakeActions(ku=[30_000_000, 30_000_000, 30_000_000], kl=["cross", "silent"])
    result, _ = _run(actions)
    assert result["reason"] == "failed"
    assert actions.sent.count("kl 12000") == 2


def test_cooldown_is_waited_between_batches():
    actions = _FakeActions(ku=[12_000_000], kl=[0, 0])
    lines: list[str] = []
    sleeps: list[float] = []

    async def _sleep(sec: float) -> None:
        sleeps.append(sec)

    runner = KakeraLootRunner(
        actions,
        SimpleNamespace(macro_active=False),
        rules=KakeraLootRules(),
        log=lines.append,
        sleep=_sleep,
        clock=lambda: 0.0,
    )
    asyncio.run(runner.run())
    # 1 s after $ku before the first $kl, then the 20 s cooldown + margin.
    assert sleeps == [1.0, 21.0]
