"""$give / $givek / $givesp — parsing the captured replies, and the gated exchange."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from macro.actions import DiscordActions
from macro.transfers import TransferParty, Transfers
from macro.turns import ChannelCoordinator
from mudae.parsers.classify import classify_message
from mudae.parsers.pipeline import parse_message
from mudae.types import MessageKind, MudaeMessageSnapshot

MAIN_ID = 554009750375890945
ALT_ID = 1410311771092422777

# Verbatim from data/alts_log.json (2026-11-05).
GIVE_PROMPT = (
    "<@554009750375890945>, **lukijade** wants to give you **Anna (PC)**. Do you confirm? (y/n/yes/no)\n"
    "(Enhanced multitrade: this gift is free)"
)
GIVE_RESULT = "**Anna (PC)** given to <@554009750375890945>"
GIVEK_PROMPT = "**lukijade**, do you really want to give **1,000<:kakera:469835869059153940>**? (y/n/yes/no)"
GIVEK_RESULT = (
    "<@1410311771092422777> just gifted **1,000**<:kakera:469835869059153940>to <@554009750375890945>"
)
GIVESP_PROMPT = "**lukijade**, do you really want to give **100 <:sp:1437140700604137554> **? (y/n/yes/no)"
GIVESP_RESULT = (
    "<@1410311771092422777> just gifted **100** <:sp:1437140700604137554> to <@554009750375890945>"
)


def _snap(content: str, message_id: int = 1) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id, channel_id=1, channel_name="mudae-w", guild_id=1, guild_name="s",
        author_id=432610292342587392, author_name="Mudae", is_mudae=True, content=content,
        embeds=[], buttons=[], created_at="12:19:23",
    )


# ---- parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    "content, kind, fields",
    [
        (GIVE_PROMPT, MessageKind.TRANSFER_PROMPT,
         {"transfer": "character", "recipient_id": str(MAIN_ID), "giver_name": "lukijade",
          "character": "Anna (PC)", "free": True}),
        (GIVE_RESULT, MessageKind.TRANSFER_RESULT,
         {"transfer": "character", "character": "Anna (PC)", "recipient_id": str(MAIN_ID)}),
        (GIVEK_PROMPT, MessageKind.TRANSFER_PROMPT,
         {"transfer": "kakera", "giver_name": "lukijade", "amount": 1000}),
        (GIVEK_RESULT, MessageKind.TRANSFER_RESULT,
         {"transfer": "kakera", "giver_id": str(ALT_ID), "recipient_id": str(MAIN_ID), "amount": 1000}),
        (GIVESP_PROMPT, MessageKind.TRANSFER_PROMPT,
         {"transfer": "spheres", "giver_name": "lukijade", "amount": 100}),
        (GIVESP_RESULT, MessageKind.TRANSFER_RESULT,
         {"transfer": "spheres", "giver_id": str(ALT_ID), "recipient_id": str(MAIN_ID), "amount": 100}),
    ],
)
def test_captured_transfers_parse(content, kind, fields):
    assert classify_message(_snap(content)) == kind
    for reply_to in (None, "give", "givek", "givesp"):
        result = parse_message(_snap(content), reply_to_command=reply_to)
        assert result.kind == kind
        assert result.fields == fields


def test_give_prompt_is_not_a_claim():
    # Two bold runs used to make it a CLAIM by "lukijade" of "Anna (PC)",
    # which the main's wait_for_claim would accept as its own confirmation.
    async def run():
        actions = DiscordActions(object())
        snap = _snap(GIVE_PROMPT)
        actions.feed(snap, parse_message(snap))
        return await actions.wait_for_claim(timeout=0.3)

    assert asyncio.run(run()) is None


def test_saved_capture_still_parses():
    path = Path(__file__).resolve().parent.parent / "data" / "alts_log.json"
    if not path.exists():
        pytest.skip("capture not on this machine")
    entries = [e for e in json.loads(path.read_text())["entries"] if e["author"] == "Mudae"]
    kinds = [parse_message(_snap(e["rawContent"])).kind for e in entries]
    assert kinds == [MessageKind.TRANSFER_PROMPT, MessageKind.TRANSFER_RESULT] * 3


# ---- the exchange -------------------------------------------------------


class Channel:
    """Two accounts in one channel; Mudae answers from a script."""

    def __init__(self, script):
        self.script = script  # (account, text) -> list of Mudae replies
        self.sent: list[tuple[str, str]] = []
        self.watchers: list[DiscordActions] = []

    def monitor(self, who: str):
        channel = self

        class Mon:
            async def send_command(self, command, prefix=None):
                return channel.post(who, f"{prefix or '$'}{command}")

            async def send_text(self, text):
                return channel.post(who, text)

        return Mon()

    def post(self, who: str, text: str) -> int:
        # Every message gets the next id, as Discord's snowflakes grow with
        # time: a reply is always newer than the command it answers.
        self.sent.append((who, text))
        self.last_id = getattr(self, "last_id", 0) + 1
        command_id = self.last_id
        replies = self.script(who, text)

        def deliver():
            for reply in replies:
                self.last_id += 1
                snap = _snap(reply, self.last_id)
                parsed = parse_message(snap)
                for actions in self.watchers:
                    actions.feed(snap, parsed)

        asyncio.get_running_loop().call_soon(deliver)
        return command_id


def _accounts(script, *, alt_names=("lukijade",)):
    channel = Channel(script)
    coord = ChannelCoordinator("main", ["alt"], command_gap=0, reply_hold=0)
    alt = DiscordActions(channel.monitor("alt"))
    main = DiscordActions(channel.monitor("main"))
    alt.set_lane(coord, "alt")
    main.set_lane(coord, "main")
    channel.watchers = [alt, main]
    giver = TransferParty(alt, ALT_ID, list(alt_names))
    receiver = TransferParty(main, MAIN_ID, ["LukaZade"])
    transfers = Transfers(sleep=_no_sleep, prompt_timeout=1.0, result_timeout=1.0)
    return channel, transfers, giver, receiver


async def _no_sleep(_s):
    return None


def _mudae(prompt, result):
    def script(who, text):
        if text.startswith("$"):
            return [prompt]
        if text == "y":
            return [result]
        return []

    return script


def test_give_character_the_main_confirms():
    channel, transfers, giver, receiver = _accounts(_mudae(GIVE_PROMPT, GIVE_RESULT))
    result = asyncio.run(transfers.give_character(giver, receiver, "Anna (PC)"))
    assert result.ok, result.reason
    assert channel.sent == [("alt", f"$give <@{MAIN_ID}> Anna (PC)"), ("main", "y")]


@pytest.mark.parametrize(
    "kind, amount, prompt, result, command",
    [
        ("kakera", 1000, GIVEK_PROMPT, GIVEK_RESULT, "givek"),
        ("spheres", 100, GIVESP_PROMPT, GIVESP_RESULT, "givesp"),
    ],
)
def test_give_amount_the_alt_confirms(kind, amount, prompt, result, command):
    channel, transfers, giver, receiver = _accounts(_mudae(prompt, result))
    outcome = asyncio.run(transfers.give_amount(giver, receiver, kind, amount))
    assert outcome.ok, outcome.reason
    assert channel.sent == [("alt", f"${command} <@{MAIN_ID}> {amount}"), ("alt", "y")]


def test_wrong_character_is_answered_n():
    channel, transfers, giver, receiver = _accounts(_mudae(GIVE_PROMPT, GIVE_RESULT))
    result = asyncio.run(transfers.give_character(giver, receiver, "Lucy"))
    assert not result.ok and result.reason == "prompt mismatch"
    assert channel.sent[-1] == ("main", "n")


def test_wrong_amount_is_answered_n():
    channel, transfers, giver, receiver = _accounts(_mudae(GIVEK_PROMPT, GIVEK_RESULT))
    result = asyncio.run(transfers.give_amount(giver, receiver, "kakera", 500))
    assert not result.ok and result.reason == "prompt mismatch"
    assert channel.sent[-1] == ("alt", "n")
    assert ("alt", "y") not in channel.sent


def test_another_accounts_prompt_is_not_answered():
    # A $givek question for someone else ("**otherguy**, do you really…")
    # must not get this alt's "y".
    other = GIVEK_PROMPT.replace("lukijade", "otherguy")
    channel, transfers, giver, receiver = _accounts(_mudae(other, GIVEK_RESULT))
    result = asyncio.run(transfers.give_amount(giver, receiver, "kakera", 1000))
    assert not result.ok and result.reason == "no confirmation prompt"
    assert [t for _w, t in channel.sent] == [f"$givek <@{MAIN_ID}> 1000"]


def test_transfer_waits_while_the_main_has_a_question_open():
    channel, transfers, giver, receiver = _accounts(_mudae(GIVE_PROMPT, GIVE_RESULT))

    async def run():
        order: list[str] = []
        async with receiver.actions.open_prompt():
            task = asyncio.create_task(transfers.give_character(giver, receiver, "Anna (PC)"))
            for _ in range(10):
                await asyncio.sleep(0)
            order.append(f"main's own question done, sent so far: {len(channel.sent)}")
        result = await task
        order.append("transfer done")
        return order, result

    order, result = asyncio.run(run())
    assert order[0].endswith("sent so far: 0")
    assert result.ok
