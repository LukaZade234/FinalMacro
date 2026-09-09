"""Parsing for the force-divorce farm: the harem listing and ``$forcedivorce``.

Both fixtures are real messages, captured through ParseLab on 2026-09-07 and
copied here verbatim (``data/`` is not in git). Both were **misparsed** before
these parsers existed, and in the same way the ``$wl`` listing once was: an
unrecognised command falls through to ``detect_command_from_snapshot``, which
answers ``"roll"`` for anything with a character-shaped embed.
"""

from __future__ import annotations

from macro.actions import is_roll_parse_result
from mudae.parsers.force_divorce import (
    is_force_divorce_prompt,
    is_force_divorce_result,
    parse_force_divorce,
)
from mudae.parsers.harem import is_harem_message, parse_harem, parse_harem_page
from mudae.parsers.pipeline import parse_mudae_message
from mudae.types import MessageKind, MudaeMessageSnapshot

# --- real captures -----------------------------------------------------------

HAREM_EMBED = {
    "title": "",
    "author": "lukazade234's harem",
    "description": (
        "​\nTotal value: **4,865,155**<:kakera:469835869059153940>\n\n"
        "Lucy **271,065** ka\n"
        "Reze **125,670** ka\n"
        "Hatsune Miku **112,661** ka\n"
        "2B **87,922** ka\n"
        "Kasane Teto **76,132** ka"
    ),
    "footer": "Page 1 / 155",
    "image_url": "",
}
# The page arrows. Their custom ids are shaped exactly like a claim button's,
# which is half of why the page used to read as a claimable roll.
HAREM_BUTTONS = [
    {"label": "", "emoji": "wleft", "custom_id": "1p2p847502744176820256",
     "kind": "claim", "disabled": False, "style": "secondary"},
    {"label": "", "emoji": "wright", "custom_id": "1p2p847502746025459792",
     "kind": "claim", "disabled": False, "style": "secondary"},
]

FORCE_DIVORCE_PROMPT = (
    "<@554009750375890945>, **Lucy** belongs to <@554009750375890945>, "
    "do you want to force the divorce? (y/n/yes/no)\n\n"
    "⚠️ Spheres are still invested in the divorced characters until the "
    "former character owners use $or <character> (10% spheres lost) or retrieve "
    "the character (no spheres lost).\n"
    "Use **$sphererefund** + **$sphereremove** (or **$cleansphere**) to refund "
    "and remove the spheres invested."
)


def _snapshot(content="", embeds=None, buttons=None):
    return MudaeMessageSnapshot(
        1, 2, "mudae-w", 3, "Key Server 0", 4, "Mudae", True,
        content, embeds or [], buttons or [], "2026-09-07T23:13:09+00:00",
    )


# --- the harem listing -------------------------------------------------------


def test_harem_page_reads_owner_total_page_and_rows():
    fields = parse_harem_page(
        HAREM_EMBED["description"] + "\n" + HAREM_EMBED["footer"]
        + "\n" + HAREM_EMBED["author"]
    )
    assert fields["owner"] == "lukazade234"
    assert fields["total_value"] == 4_865_155
    assert (fields["page"], fields["pages"]) == (1, 155)
    assert len(fields["entries"]) == 5
    assert fields["entries"][0] == {"name": "Lucy", "kakera": 271_065}
    # $mmk= sorts by value, so row 0 is the farm's target.
    assert fields["top_name"] == "Lucy"
    assert fields["top_kakera"] == 271_065


def test_harem_page_keeps_names_with_spaces_and_digits():
    fields = parse_harem_page(HAREM_EMBED["description"])
    names = [entry["name"] for entry in fields["entries"]]
    assert "Hatsune Miku" in names
    assert "2B" in names


def test_harem_listing_is_not_a_claimable_roll():
    """The bug this parser exists for.

    Before the ``mmk`` alias, this page parsed as a roll of a character called
    "lukazade234's harem" worth 4,865,155 kakera, with ``can_claim: true`` and
    the page arrows offered as claim buttons.
    """
    snapshot = _snapshot(embeds=[HAREM_EMBED], buttons=HAREM_BUTTONS)
    parsed = parse_mudae_message(snapshot, reply_to_command="mmk")

    assert parsed.kind is not MessageKind.ROLL
    # This is the predicate ``wait_for_roll`` uses, so a True here means the
    # page could be picked up and processed as a rolled card.
    assert not is_roll_parse_result(parsed, roll_command="wa")
    assert parsed.fields.get("can_claim") is not True
    assert parsed.fields.get("top_name") == "Lucy"


def test_harem_listing_classifies_without_a_typed_command():
    """A page someone else's command produced still must not read as a roll."""
    parsed = parse_mudae_message(
        _snapshot(embeds=[HAREM_EMBED], buttons=HAREM_BUTTONS)
    )
    assert parsed.kind is MessageKind.HAREM
    assert parsed.fields["top_name"] == "Lucy"


def test_is_harem_message_needs_the_listing_header_not_just_a_row():
    # A bare "Name 12,345 ka" line is a shape other output could wander into.
    assert not is_harem_message("Lucy **271,065** ka")
    assert is_harem_message("Total value: **4,865,155**")
    assert is_harem_message("lukazade234's harem")


# --- $forcedivorce -----------------------------------------------------------


def test_prompt_reads_the_character_and_the_owner():
    parsed = parse_force_divorce(FORCE_DIVORCE_PROMPT)
    assert parsed.kind is MessageKind.FORCE_DIVORCE_PROMPT
    assert parsed.fields["outcome"] == "prompt"
    assert parsed.fields["character"] == "Lucy"
    # Both halves are checked before "y" is ever sent: the command works on
    # other people's characters too.
    assert parsed.fields["owner_id"] == "554009750375890945"
    assert parsed.fields["asked_id"] == "554009750375890945"
    assert not parsed.warnings


def test_prompt_is_not_a_claim():
    """The other bug: two bold runs was all it took to be called a claim.

    It parsed as ``winner="Lucy", character="$sphererefund"`` — and because
    ``DiscordActions.wait_for_claim`` accepts ``CLAIM``, a prompt could be
    mistaken for the confirmation of a real claim.
    """
    parsed = parse_mudae_message(
        _snapshot(FORCE_DIVORCE_PROMPT), reply_to_command="forcedivorce"
    )
    assert parsed.kind is MessageKind.FORCE_DIVORCE_PROMPT
    assert parsed.kind not in {
        MessageKind.CLAIM,
        MessageKind.MARRIAGE,
        MessageKind.CLAIM_INTERVAL,
    }
    assert parsed.fields.get("winner") is None


def test_prompt_still_recognised_when_no_command_was_typed():
    parsed = parse_mudae_message(_snapshot(FORCE_DIVORCE_PROMPT))
    assert parsed.kind is MessageKind.FORCE_DIVORCE_PROMPT


def test_result_outcomes():
    # Mudae's live reply, confirmed 2026-09-08. It is the entire message —
    # no character, no owner — so the wording is all there is to match on.
    assert parse_force_divorce("Successful divorce...").fields["outcome"] == "success"
    assert parse_force_divorce("**Lucy** has been divorced!").fields["outcome"] == "success"
    assert parse_force_divorce("Divorce cancelled.").fields["outcome"] == "cancelled"
    assert (
        parse_force_divorce("You are not allowed to use this command.").fields["outcome"]
        == "refused"
    )


def test_a_real_marriage_is_left_alone():
    content = (
        "\U0001f496 lukazade234 and Lucy are now married! \U0001f496\n"
        "**+316**<:kakera:469835869059153940> (Emerald IV bonus)"
    )
    assert not is_force_divorce_prompt(content)
    assert not is_force_divorce_result(content)
    assert parse_mudae_message(_snapshot(content)).kind is MessageKind.MARRIAGE


# --- the farm's engine flow ---------------------------------------------------
#
# What is worth testing here is not the earning, it is the two ways this mode can
# lose a very valuable character: divorcing it with no way to claim it back, and
# answering "y" to a prompt about the wrong character.

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from macro import force_divorce as fd
from macro.config import CharacterClaimRules, MacroConfig
from macro.force_divorce import ForceDivorceSession, target_from_harem
from macro.perk8_daily import mudae_daily_date
from macro.post_roll import PostRollHandler, RollRecord
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState


def _today() -> str:
    """The Mudae day the engine will compute, not a fixed date.

    A hardcoded day silently changes what these tests exercise once the
    calendar passes it: the target reads as stale, so the farm re-reads $mmk=
    before doing anything and the assertions about what it sent stop matching.
    """
    from mudae.clock import utc_now

    return str(mudae_daily_date(utc_now()))


class _FarmActions:
    """Scripted replies for the ``$forcedivorce`` exchange, recording what is sent."""

    def __init__(self, *, harem=None, prompt=None, result=None, harem_after=None):
        self.sent: list[str] = []
        self.texts: list[str] = []
        self._harem = [h for h in (harem, harem_after) if h is not None]
        self._prompt = prompt
        self._result = result

    def drain_queue(self) -> None:
        pass

    async def send_command(self, command, *, prefix=None):
        self.sent.append(f"{prefix or '$'}{command}")
        return len(self.sent)

    async def send_text(self, text):
        self.texts.append(text)
        return 1

    async def wait_for_harem(self, *, timeout=12.0):
        return self._harem.pop(0) if self._harem else None

    async def wait_for_force_divorce_prompt(self, *, timeout=12.0):
        return self._prompt

    async def wait_for_force_divorce_result(self, *, timeout=12.0):
        return self._result


def _harem_reply(top="Lucy", kakera=271_065, owner="Main", entries=None):
    if entries is None:
        entries = [{"name": top, "kakera": kakera}, {"name": "Reze", "kakera": 125_670}]
    from mudae.types import ParseResult

    return ParseResult(
        kind=MessageKind.HAREM,
        summary="harem",
        fields={
            "owner": owner, "top_name": top, "top_kakera": kakera,
            "entries": entries, "page": 1, "pages": 155,
        },
    )


def _prompt_reply(character="Lucy", owner_id="777"):
    from mudae.types import ParseResult

    return ParseResult(
        kind=MessageKind.FORCE_DIVORCE_PROMPT,
        summary="prompt",
        fields={"outcome": "prompt", "character": character,
                "owner_id": owner_id, "asked_id": owner_id},
    )


def _result_reply(outcome="success"):
    from mudae.types import ParseResult

    return ParseResult(
        kind=MessageKind.FORCE_DIVORCE_RESULT,
        summary="result",
        fields={"outcome": outcome},
    )


def _farm_engine(actions, *, claim_available=True, rt_available=False):
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0,
        character_claim=CharacterClaimRules(enabled=True, auto_use_rt=True),
    )
    state = AccountState(claim_available=claim_available, rt_available=rt_available)
    state.own_usernames = ["Main"]
    state.own_user_ids = [777]
    engine = RollCycleEngine(actions, config, state, SimpleNamespace(macro_active=False))
    engine._force_divorce = ForceDivorceSession()
    return engine, state


# --- invariant 1: never divorce without a claim slot in hand ------------------


def test_a_divorce_needs_a_claim_slot_already_in_hand():
    """The character is exposed the moment it is divorced.

    A slot that is not already held may not arrive for an hour, and the most
    valuable character on the server sitting unowned is the one outcome the
    whole design is built to avoid.
    """
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())

    ok, why = session.can_divorce(AccountState(claim_available=False, rt_available=False))
    assert ok is False
    assert "exposed" in why

    # An unspent $rt *is* a slot, which is what makes the re-cycle work.
    ok, _ = session.can_divorce(AccountState(claim_available=False, rt_available=True))
    assert ok is True
    ok, _ = session.can_divorce(AccountState(claim_available=True))
    assert ok is True


def test_no_divorce_is_sent_while_the_target_is_already_out_there():
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    session.note_divorced()
    ok, why = session.can_divorce(AccountState(claim_available=True))
    assert ok is False
    assert "already divorced" in why


def test_the_step_sends_nothing_without_a_slot():
    actions = _FarmActions(harem=_harem_reply())
    engine, _ = _farm_engine(actions, claim_available=False, rt_available=False)
    asyncio.run(engine._run_force_divorce_step())
    # The target is read, but nothing is divorced.
    assert actions.sent == ["$mmk="]
    assert actions.texts == []
    assert engine._force_divorce.phase == fd.IDLE


# --- invariant 2: never answer "y" to the wrong prompt ------------------------


def test_a_prompt_about_another_character_is_never_confirmed():
    actions = _FarmActions(
        harem=_harem_reply(), prompt=_prompt_reply(character="Rem"),
        result=_result_reply(),
    )
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())

    assert actions.texts == []          # no "y" — nothing was divorced
    assert engine._force_divorce.phase == fd.STOPPED
    assert "Rem" in engine._force_divorce.stop_reason


def test_a_prompt_about_another_owners_character_is_never_confirmed():
    """$forcedivorce works on other people's characters, so the owner is checked."""
    actions = _FarmActions(
        harem=_harem_reply(), prompt=_prompt_reply(owner_id="999"),
        result=_result_reply(),
    )
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())

    assert actions.texts == []
    assert engine._force_divorce.phase == fd.STOPPED


def test_a_missing_prompt_leaves_nothing_divorced():
    actions = _FarmActions(harem=_harem_reply(), prompt=None)
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())

    assert actions.texts == []
    # Back to idle, not stopped: nothing was spent and nothing is exposed.
    assert engine._force_divorce.phase == fd.IDLE


def test_a_good_prompt_is_confirmed_and_the_hunt_begins():
    actions = _FarmActions(
        harem=_harem_reply(), prompt=_prompt_reply(), result=_result_reply("success")
    )
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())

    assert actions.sent == ["$mmk=", "$forcedivorce Lucy"]
    assert actions.texts == ["y"]
    assert engine._force_divorce.phase == fd.HUNTING


def test_a_refusal_stops_the_farm():
    # The method needs admin; a refusal will not fix itself next hour.
    actions = _FarmActions(
        harem=_harem_reply(), prompt=_prompt_reply(), result=_result_reply("refused")
    )
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())
    assert engine._force_divorce.phase == fd.STOPPED


def test_an_unreadable_reply_is_resolved_by_re_reading_the_harem():
    """The confirmation was sent, so the divorce may well have landed.

    Guessing "it failed" would leave the character exposed with the farm idle.
    """
    actions = _FarmActions(
        harem=_harem_reply(),
        prompt=_prompt_reply(),
        result=None,
        # Lucy is gone from the harem, so it landed.
        harem_after=_harem_reply(top="Reze", kakera=125_670,
                                 entries=[{"name": "Reze", "kakera": 125_670}]),
    )
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())

    assert actions.sent == ["$mmk=", "$forcedivorce Lucy", "$mmk="]
    assert engine._force_divorce.phase == fd.HUNTING


def test_an_unreadable_reply_with_the_character_still_owned_is_a_failure():
    actions = _FarmActions(
        harem=_harem_reply(), prompt=_prompt_reply(), result=None,
        harem_after=_harem_reply(),   # Lucy still there
    )
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())
    assert engine._force_divorce.phase == fd.IDLE


def test_someone_elses_harem_is_never_farmed_from():
    actions = _FarmActions(harem=_harem_reply(owner="SomeoneElse"))
    engine, _ = _farm_engine(actions)
    asyncio.run(engine._run_force_divorce_step())
    assert actions.sent == ["$mmk="]
    assert engine._force_divorce.target is None


# --- invariant 3: the slot is spent on nothing else ---------------------------


def _gate_handler(session):
    return PostRollHandler(
        SimpleNamespace(), MacroConfig(character_claim=CharacterClaimRules(enabled=True)),
        AccountState(claim_available=True), log=lambda _m: None,
        claim_gate=session.allows_claim,
    )


def test_the_gate_refuses_every_character_but_the_target():
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    # Whatever the reason a claim was triggered — a wish ping, an app-wishlist
    # match, the end-of-batch best pick — the slot belongs to the target.
    assert session.allows_claim("Lucy")
    assert session.allows_claim("lucy")     # matching is normalised
    assert not session.allows_claim("Rem")
    assert not session.allows_claim("")


def test_claim_record_refuses_a_non_target():
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    handler = _gate_handler(session)
    record = RollRecord(message_id=1, character_name="Rem",
                        fields={"can_claim": True, "claimed": False})
    assert asyncio.run(handler.claim_record(record, reason="wish ping")) is False


def test_once_stopped_the_ordinary_claim_rules_come_back():
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    session.stop("target lost")
    assert session.allows_claim("Rem") is True


def test_target_from_harem_takes_the_top_row():
    assert target_from_harem({"top_name": "Lucy", "top_kakera": 271_065}) == ("Lucy", 271_065)
    assert target_from_harem({}) is None


# --- wiring -------------------------------------------------------------------


def test_the_button_reaches_a_real_bridge_slot_in_every_shell():
    """Every Run page must call a slot that exists.

    Two Quiet buttons shipped calling ``App.checkTu()`` / ``App.checkUs()``,
    which the bridge has never had — they did nothing, silently, and a typo
    here fails exactly the same way.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    bridge = (root / "gui" / "bridge.py").read_text()
    slots = set(re.findall(r"def (\w+)\(self", bridge))

    pages = [
        "gui/shells/HaulRunPage.qml",
        "gui/shells/BoxedRunPage.qml",
        "gui/shells/ConsoleRunPage.qml",
        "gui/shells/QuietRunPage.qml",
        "gui/views/RunView.qml",
    ]
    for rel in pages:
        text = (root / rel).read_text()
        assert "startForceDivorce" in text, f"{rel} has no $forcedivorce button"
        for call in set(re.findall(r"App\.(\w+)\(", text)):
            assert call in slots, f"{rel} calls App.{call}(), which the bridge lacks"


def test_the_farm_setting_survives_a_preset_round_trip():
    from macro.config import MacroConfig

    config = MacroConfig.from_dict({"force_divorce": {"target_override": "Lucy"}})
    assert config.force_divorce.target_override == "Lucy"
    # Both directions matter: a block missing from ``to_dict`` is dropped on save.
    assert MacroConfig.from_dict(config.to_dict()).force_divorce.target_override == "Lucy"
    assert MacroConfig().force_divorce.target_override == ""


def test_the_run_summary_carries_the_farm_without_a_separate_kakera_line():
    from gui.run_summary import build_run_summary

    summary = build_run_summary(
        AccountState(),
        None,
        force_divorce={"enabled": True, "target": "Lucy", "phase": "hunting",
                       "cycles": 3, "kakera": 900, "spheres": 270, "stop_reason": ""},
    )
    assert summary["force_divorce"]["target"] == "Lucy"
    assert summary["force_divorce"]["cycles"] == 3
    # The farm's kakera is logged as ordinary kakera events, so the session
    # figure is the single total the user asked for.
    assert "kakera" in summary["session"]


# --- what the farm banks, and when it cycles ----------------------------------


def test_a_claim_pays_more_than_one_bonus_line():
    """The live claim carried two kakera lines and two sphere lines.

    Kakera was summed; spheres read only the first line, reporting 92 against a
    real 164.
    """
    from mudae.parsers.claim import parse_claim

    content = (
        "\U0001f496 lukazade234 and Lucy are now married! \U0001f496\n"
        "**+638,858**<:kakera:469835869059153940>(Emerald IV bonus) **+92** <:sp:1>\n"
        "**+2,876**<:kakera:469835869059153940>(Bronze IV bonus) **+72** <:sp:1>"
    )
    fields = parse_claim(content).fields
    assert fields["kakera"] == 641_734
    assert fields["spheres"] == 164
    assert [b["label"] for b in fields["kakera_bonuses"]] == [
        "Emerald IV bonus", "Bronze IV bonus",
    ]


def test_the_farm_banks_what_the_claim_actually_paid():
    """``kakera banked`` read 0 on a live run.

    The session was told a claim happened but never what it paid — the figure
    only exists on the claim message, which the handler sees and the caller
    does not.
    """
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    actions = _FarmActions()
    engine, _ = _farm_engine(actions)
    engine._force_divorce = session

    engine._note_claim_payout("Lucy", {"kakera": 641_734, "spheres": 164})

    assert session.kakera_banked == 641_734
    assert session.spheres_banked == 164
    assert session.cycles == 1
    # Someone else's claim is not the farm's income.
    engine._note_claim_payout("Rem", {"kakera": 5_000})
    assert session.kakera_banked == 641_734


def test_rt_is_spent_when_there_is_time_to_hunt_with_it():
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    session.note_divorced()
    session.note_claimed(kakera=641_734)
    session.ready_for_next_cycle()

    # Claim spent, $rt in hand, most of the hour still to roll: go again now.
    ok, _ = session.can_divorce(
        AccountState(claim_available=False, rt_available=True,
                     next_claim_reset_minutes=50)
    )
    assert ok is True


def test_rt_is_held_when_the_reset_is_about_to_hand_one_over():
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    ok, why = session.can_divorce(
        AccountState(claim_available=False, rt_available=True,
                     next_claim_reset_minutes=12)
    )
    assert ok is False
    assert "saving it for the next cycle" in why
    # The boundary itself counts as enough time.
    ok, _ = session.can_divorce(
        AccountState(claim_available=False, rt_available=True,
                     next_claim_reset_minutes=fd.RT_MIN_MINUTES_BEFORE_RESET)
    )
    assert ok is True


def test_a_free_claim_slot_is_never_held_back_by_the_rt_rule():
    session = ForceDivorceSession()
    session.set_target("Lucy", 271_065, day=_today())
    ok, _ = session.can_divorce(
        AccountState(claim_available=True, next_claim_reset_minutes=2)
    )
    assert ok is True


def test_claiming_the_target_banks_it_and_starts_the_next_cycle_at_once():
    """The whole point of the $rt rule, end to end.

    On the live run the target was claimed with ~50 minutes and an unspent $rt
    still in hand, and the farm sat idle until the next hour — by which time
    the rolls that could have hunted the character again were gone.
    """
    actions = _FarmActions(
        harem=_harem_reply(), prompt=_prompt_reply(), result=_result_reply("success"),
    )
    engine, state = _farm_engine(actions, claim_available=True)
    state.next_claim_reset_minutes = 50
    state.rt_available = True
    session = engine._force_divorce
    session.set_target("Lucy", 271_065, day=_today())
    session.note_divorced()

    class _StubHandler:
        """Claims, and reports the payout the way the real handler does."""

        def __init__(self, on_claim):
            self._on_claim = on_claim

        async def claim_record(self, record, *, reason="", allow_rt=False):
            state.claim_available = False      # the slot is spent
            self._on_claim("Lucy", {"kakera": 641_734, "spheres": 164})
            return True

    engine._make_post_roll_handler = lambda: _StubHandler(engine._note_claim_payout)

    # The engine passes the parsed roll fields, which carry the name.
    fields = {"character_name": "Lucy", "can_claim": True, "claimed": False}
    record = RollRecord(message_id=1, character_name="Lucy", fields=fields)
    outcome = asyncio.run(engine._force_divorce_roll_check(record, fields, 40))

    assert outcome is not None and outcome.claimed is True
    # Banked from the claim message, not guessed.
    assert session.kakera_banked == 641_734
    assert session.spheres_banked == 164
    # And straight back out: divorced again on the $rt, in the same hour.
    assert actions.sent == ["$forcedivorce Lucy"]
    assert actions.texts == ["y"]
    assert session.phase == fd.HUNTING
    # The batch is not stopped — the rolls left are what the new cycle hunts with.
    assert outcome.stop is False


# --- surviving a restart with a character still out there ---------------------


def test_a_divorced_character_is_remembered_across_a_restart():
    """The hazard: a restart between the divorce and the claim.

    The divorced character is not in the harem — that is what divorced means —
    so ``$mmk=`` tops out at somebody else. Taking that name would divorce a
    second character and leave two of the account's most valuable sitting
    unowned at once.
    """
    from macro.force_divorce import (
        ForceDivorceRecord,
        harem_holds,
        load_force_divorce_record,
        save_force_divorce_record,
    )

    daily = save_force_divorce_record({}, ForceDivorceRecord("Lucy", owned=False))
    record = load_force_divorce_record(daily)
    assert record.outstanding is True

    # Lucy is gone from page 1, so she is the one to claim back — not Reze.
    page = {"entries": [{"name": "Reze", "kakera": 125_670}]}
    assert harem_holds(page, "Lucy") is False

    # Once claimed back, the record stops being outstanding.
    daily = save_force_divorce_record(daily, ForceDivorceRecord("Lucy", owned=True))
    assert load_force_divorce_record(daily).outstanding is False


def test_the_farm_resumes_the_outstanding_character_instead_of_divorcing_another():
    stored: dict = {}
    actions = _FarmActions(
        # Lucy is missing from the harem: she is still divorced.
        harem=_harem_reply(top="Reze", kakera=125_670,
                           entries=[{"name": "Reze", "kakera": 125_670}]),
        prompt=_prompt_reply(), result=_result_reply("success"),
    )
    engine, _ = _farm_engine(actions)
    engine._get_daily_resets = lambda: dict(stored)
    engine._save_daily_resets = lambda d: stored.update(d)
    engine._save_force_divorce_record("Lucy", owned=False)

    asyncio.run(engine._run_force_divorce_step())

    session = engine._force_divorce
    assert session.target.name == "Lucy"        # not Reze
    assert session.phase == fd.HUNTING          # already out there, so hunt it
    assert actions.texts == []                  # and divorce nothing new
    assert "$forcedivorce Reze" not in actions.sent


def test_a_target_still_in_the_harem_is_farmed_normally():
    stored: dict = {}
    actions = _FarmActions(
        harem=_harem_reply(), prompt=_prompt_reply(), result=_result_reply("success"),
    )
    engine, _ = _farm_engine(actions)
    engine._get_daily_resets = lambda: dict(stored)
    engine._save_daily_resets = lambda d: stored.update(d)
    # Claimed back last run, so there is nothing outstanding.
    engine._save_force_divorce_record("Lucy", owned=True)

    asyncio.run(engine._run_force_divorce_step())

    assert engine._force_divorce.phase == fd.HUNTING
    assert actions.texts == ["y"]
    # And the divorce is recorded as leaving the character out there.
    assert stored["force_divorce"]["owned"] is False
    assert stored["force_divorce"]["target"] == "Lucy"


def test_the_us_hunt_is_not_gated_on_the_final_hour():
    """The bug the live run exposed.

    At ``claim reset 60m · rolls reset 55m`` the hour is not the final one, so
    the hunt was skipped — and the divorced character sat unowned for the 53
    minutes until the next refill. The trigger is the exposure, not the hour.
    """
    import inspect

    from macro.roll_cycle import RollCycleEngine

    source = inspect.getsource(RollCycleEngine._force_divorce_us_hunt)
    body = source.split('"""', 2)[-1]
    assert "_final_roll_session" not in body


def test_the_us_hunt_still_needs_a_target_that_is_actually_out_there():
    actions = _FarmActions()
    engine, _ = _farm_engine(actions)
    session = engine._force_divorce
    session.set_target("Lucy", 271_065, day=_today())

    # Nothing divorced yet: no hunt, and no $us spent.
    assert asyncio.run(engine._force_divorce_us_hunt([], 0)) is False
    assert actions.sent == []


# --- the hunt survives a $us that Mudae acknowledges late ---------------------


class _HuntActions(_FarmActions):
    """A hunt harness: a stack to spend, ticks that can be withheld, and rolls.

    ``ticks`` is consumed one entry per ``$us N``; ``tu_us_bonus`` is what a
    follow-up ``$tu`` reports, which is how a missed tick is distinguished from
    a missed add.
    """

    def __init__(self, *, stacked=40.0, ticks=(), tu_us_bonus=()):
        super().__init__()
        self.stacked = stacked
        self._ticks = list(ticks)
        self._tu_us_bonus = list(tu_us_bonus)
        self.tu_calls = 0
        self.rolls_served = 0
        self.stack_reads = 0
        self.stack_silent_for = 0  # how many bare $us reads answer nothing
        self.rolls_before_stack_read = None

    def queue_size(self) -> int:
        return 0

    async def wait_for(self, predicate, *, timeout=15.0):
        if self.rolls_before_stack_read is None:
            self.rolls_before_stack_read = self.rolls_served
        self.stack_reads += 1
        if self.stack_reads <= self.stack_silent_for:
            return None
        content = (
            f"<:rollstack:1> You have **{self.stacked:,}** rolls stacked.\n"
            "Syntax: **$us <number of stacked rolls to use>**"
        )
        return SimpleNamespace(message_id=900, content=content), None

    async def wait_for_mudae_tick(self, message_id, *, timeout=5.0):
        return self._ticks.pop(0) if self._ticks else False

    async def wait_for_tu(self, *, timeout=12.0):
        from mudae.types import ParseResult

        self.tu_calls += 1
        bonus = self._tu_us_bonus.pop(0) if self._tu_us_bonus else 0
        return ParseResult(
            kind=MessageKind.TU,
            summary="$tu",
            fields={
                "rolls_left": 0,
                "rolls_us_bonus": bonus,
                "claim_available": True,
                "rolls_reset_minutes": 40,
            },
        )

    async def wait_for_roll(self, *, roll_command, timeout=20.0):
        from mudae.types import ParseResult

        self.rolls_served += 1
        return (
            SimpleNamespace(message_id=3000 + self.rolls_served),
            ParseResult(
                kind=MessageKind.ROLL,
                summary="$roll",
                fields={"character_name": f"Other{self.rolls_served}", "wished_by": None},
            ),
        )

    async def wait_for_perk6_spawn(self, *, parent_character, timeout=5.0):
        return None


def _hunting_engine(actions):
    engine, state = _farm_engine(actions)
    session = engine._force_divorce
    session.set_target("Lucy", 271_065, day=_today())
    session.note_divorced()
    state.rolls_reset_minutes = 40
    return engine, state


def test_a_missed_us_tick_is_confirmed_with_tu_rather_than_ending_the_hunt():
    """The live failure: one unacknowledged ``$us 20`` abandoned the hunt.

    Mudae applies ``$us`` and reacts late often enough that the tick alone is
    not evidence. The stack was 20,534 rolls deep and the divorced character was
    left unowned, which is the one outcome the hunt exists to prevent.
    """
    actions = _HuntActions(stacked=20.0, ticks=[False], tu_us_bonus=[20])
    engine, _state = _hunting_engine(actions)
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        claimed = asyncio.run(engine._force_divorce_us_hunt([], 0))
    assert claimed is False
    # $tu was asked, and the rolls were spent instead of abandoned.
    assert actions.tu_calls == 1
    assert actions.rolls_served == 20


def test_the_hunt_retries_a_us_that_really_did_not_register():
    """Three tries before giving up, as $us mode does — the stack is not scarce."""
    actions = _HuntActions(stacked=40.0, ticks=[False, False, False], tu_us_bonus=[0, 0, 0])
    engine, _state = _hunting_engine(actions)
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        claimed = asyncio.run(engine._force_divorce_us_hunt([], 0))
    assert claimed is False
    assert len([c for c in actions.sent if c.startswith("$us ")]) == 3
    assert actions.rolls_served == 0


async def _fast_sleep(*_a, **_k) -> None:
    return None


def test_zero_hourly_rolls_still_hunts_before_waiting_out_the_hour():
    """The restart case: nothing to roll with, but the target is still exposed.

    A run resumed at ``$tu OK · 0 rolls`` correctly saw Lucy was still divorced
    from the previous run, then took the "no rolls" branch straight to a 19
    minute refill wait — with 20k rolls stacked and a claim slot in hand. The
    $us stack is the only thing that can close the exposure before the refill,
    so it is tried before the wait.
    """
    actions = _FarmActions()
    engine, state = _farm_engine(actions)
    session = engine._force_divorce
    session.set_target("Lucy", 271_065, day=_today())
    session.note_divorced()
    state.rolls_left = 0
    order: list[str] = []

    async def _ok(*_a, **_k):
        return True

    async def _none(*_a, **_k):
        return None

    async def _tu():
        order.append("tu")
        return True

    async def _step():
        return False

    async def _hunt(_records, _index):
        order.append("hunt")
        return False

    async def _refill():
        order.append("refill")
        engine._stop.set()
        return False

    engine._restore_connection_for_notifications = _ok
    engine._refresh_perk8_status = _none
    engine._run_priority_pause = _none
    engine._maybe_refresh_perk8_status = _none
    engine._maybe_play_daily_minigames = _none
    engine.run_tu = _tu
    engine._run_force_divorce_step = _step
    engine._force_divorce_us_hunt = _hunt
    engine._wait_for_hourly_refill = _refill

    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._run_cycle())

    assert "hunt" in order, "the exposed target was never hunted"
    assert order.index("hunt") < order.index("refill")


def test_a_silent_us_is_retried_rather_than_read_as_an_empty_stack():
    """The live failure: $us sent on the heels of $mmk= got no reply at all.

    Mudae ignores a bare $us that lands on top of another command — no reply,
    no error — and the hunt read that silence as "nothing stacked" and gave up,
    twice in a row, with the divorced character still out there.
    """
    actions = _HuntActions(stacked=20.0, ticks=[True])
    actions.stack_silent_for = 2  # first two $us reads answer nothing
    engine, _state = _hunting_engine(actions)
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._force_divorce_us_hunt([], 0))

    assert actions.stack_reads == 3, "the stack read was not retried"
    # The third answer was believed, so the hunt actually spent the stack.
    assert actions.rolls_served == 20


def test_the_hunt_gives_up_after_the_retries_without_claiming_the_stack_is_empty():
    actions = _HuntActions(stacked=20.0)
    actions.stack_silent_for = 99
    engine, _state = _hunting_engine(actions)
    logs: list[str] = []
    engine._log = logs.append
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._force_divorce_us_hunt([], 0))

    assert actions.stack_reads == 3
    assert actions.rolls_served == 0
    # "nothing stacked" would be a lie — the stack was never read.
    assert not any("nothing on the $us stack" in line for line in logs)
    assert any("no answer to $us" in line for line in logs)


def test_the_hunt_lets_the_previous_command_settle_before_asking_for_the_stack():
    """One second between the $mmk= that chose the target and the bare $us."""
    from macro.roll_cycle import _FORCE_DIVORCE_STEP_PAUSE_SEC

    actions = _HuntActions(stacked=20.0, ticks=[True])
    engine, _state = _hunting_engine(actions)
    waits: list[float] = []
    sends_at_first_wait: list[int] = []

    async def _record_sleep(seconds, *_a, **_k):
        waits.append(seconds)
        sends_at_first_wait.append(actions.stack_reads)

    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_record_sleep):
        asyncio.run(engine._force_divorce_us_hunt([], 0))

    assert waits, "the hunt asked for the stack with no settle at all"
    assert waits[0] == _FORCE_DIVORCE_STEP_PAUSE_SEC
    # And it waited *before* sending, not after the answer came back.
    assert sends_at_first_wait[0] == 0


def test_usable_us_rolls_are_spent_before_the_stack_is_topped_up():
    """A live $tu read ``0 (+9 $us) rolls`` and the hunt ignored the 9.

    Mudae spends the $us bonus before anything else, and the bonus is wiped at
    the rolls reset whether or not it is used, so adding more on top of it both
    strands rolls that are already paid for and delays the hunt.
    """
    actions = _HuntActions(stacked=40.0, ticks=[True, True])
    engine, state = _hunting_engine(actions)
    state.rolls_us_bonus = 9
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._force_divorce_us_hunt([], 0))

    # The 9 usable rolls went out before the stack was even asked about, and
    # the 40 stacked then followed in two batches.
    assert actions.rolls_before_stack_read == 9
    assert actions.rolls_served == 9 + 40
    assert [c for c in actions.sent if c.startswith("$us")] == [
        "$us", "$us 20", "$us 20",
    ]


def test_the_usable_bonus_alone_can_close_the_hunt():
    """Claiming off the already-usable rolls never touches the stack at all."""
    actions = _HuntActions(stacked=40.0)
    engine, state = _hunting_engine(actions)
    state.rolls_us_bonus = 5
    claimed_after = 3

    async def _roll_batch(cmd, count, records, index, *, us_roll=True, respect_us_stop=True):
        actions.rolls_served += count
        return claimed_after, True, None

    engine._roll_us_batch = _roll_batch
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        claimed = asyncio.run(engine._force_divorce_us_hunt([], 0))

    assert claimed is True
    assert actions.stack_reads == 0, "the stack was read despite the claim landing"
    assert [c for c in actions.sent if c.startswith("$us")] == []
