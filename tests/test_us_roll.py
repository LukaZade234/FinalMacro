"""Tests for the $us mass-roll mode loop in RollCycleEngine."""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

from macro.config import CharacterClaimRules, KakeraReactionRules, MacroConfig, UsRollKakeraRules
from macro.roll_cycle import RollCycleEngine
from macro.state import AccountState
from macro.us_stop import UsModeStopOptions
from mudae.types import MessageKind, ParseResult


def _tu(rolls_left: int, reset_minutes: int, us_bonus: int | None = None) -> ParseResult:
    fields = {
        "rolls_left": rolls_left,
        "rolls_reset_minutes": reset_minutes,
        "claim_available": False,
    }
    if us_bonus is not None:
        fields["rolls_us_bonus"] = us_bonus
    return ParseResult(kind=MessageKind.TU, summary="$tu", fields=fields)


def _us_stack(stacked: float):
    """A bare $us response snapshot reporting the stacked pool size."""
    content = (
        f"<:rollstack:1> You have **{stacked:,}** rolls stacked.\n"
        "Syntax: **$us <number of stacked rolls to use>**"
    )
    return SimpleNamespace(message_id=900, content=content), ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary="$us",
        fields={"us_stacked": stacked},
    )


def _roll(message_id: int, rolls_left: int | None = None) -> tuple[SimpleNamespace, ParseResult]:
    snapshot = SimpleNamespace(message_id=message_id)
    fields: dict = {"character_name": f"Char{message_id}", "wished_by": None}
    if rolls_left is not None:
        fields["rolls_left"] = rolls_left
    parsed = ParseResult(
        kind=MessageKind.ROLL,
        summary="$roll",
        fields=fields,
    )
    return snapshot, parsed


class _FakeActions:
    def __init__(self, tu_script: list, roll_script: list, stack_script: list | None = None) -> None:
        self._tu = deque(tu_script)
        self._rolls = deque(roll_script)
        self._stack = deque(stack_script or [])
        self.sent: list[tuple[str, str | None]] = []
        self._message_id = 1000
        self.tick_ack = True

    def drain_queue(self) -> None:
        pass

    async def send_command(self, command: str, *, prefix: str | None = None) -> int | None:
        self.sent.append((command, prefix))
        self._message_id += 1
        return self._message_id

    async def wait_for_mudae_tick(self, message_id: int, *, timeout: float = 5.0) -> bool:
        return self.tick_ack

    async def wait_for_tu(self, *, timeout: float = 12.0):
        return self._tu.popleft() if self._tu else None

    async def wait_for_roll(self, *, roll_command: str, timeout: float = 20.0):
        return self._rolls.popleft() if self._rolls else None

    async def wait_for_perk6_spawn(self, *, parent_character: str, timeout: float = 5.0):
        return None

    async def wait_for(self, predicate, *, timeout: float = 15.0):
        while self._stack:
            snapshot, parsed = self._stack.popleft()
            if predicate(snapshot, parsed):
                return snapshot, parsed
        return None

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        return True

    def us_reads(self) -> list[str]:
        return [c for c, _ in self.sent if c == "us"]

    def us_adds(self) -> list[str]:
        return [c for c, _ in self.sent if c.startswith("us ")]

    def roll_commands(self) -> list[str]:
        return [c for c, _ in self.sent if c == "wa"]


def _make_engine(actions: _FakeActions, **config_kw) -> tuple[RollCycleEngine, AccountState]:
    # Disable claiming/reactions so the loop is isolated from action side effects.
    config = MacroConfig(
        roll_command="wa",
        roll_delay_sec=0.6,
        us_reset_margin_minutes=2,
        character_claim=CharacterClaimRules(enabled=False, claim_on_wish_ping=False),
        **config_kw,
    )
    state = AccountState()
    monitor = SimpleNamespace(macro_active=False)
    engine = RollCycleEngine(actions, config, state, monitor)
    return engine, state


async def _fast_sleep(*_a, **_k) -> None:
    return None


def _run_us(engine: RollCycleEngine) -> None:
    engine._stop.clear()
    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(engine._run_us_cycle())


def test_us_mode_adds_from_stack_until_exhausted():
    # Reads the stack once (35), then tracks it locally: add 20 -> roll 20 ->
    # add 15 -> roll 15 -> local stack hits 0 -> stop. Second add skips $tu.
    actions = _FakeActions(
        tu_script=[
            _tu(0, 30),
            _tu(0, 30, us_bonus=20),
        ],
        roll_script=[_roll(i) for i in range(1, 36)],
        stack_script=[_us_stack(35)],
    )
    engine, state = _make_engine(actions)

    _run_us(engine)

    assert actions.us_adds() == ["us 20", "us 15"]
    assert actions.us_reads() == ["us"]
    assert len(actions.roll_commands()) == 35
    assert sum(1 for entry in state.activity_log if entry.text.startswith("Sent $tu")) == 2
    assert any("acknowledged — rolling" in entry.text for entry in state.activity_log)


def test_us_mode_counts_us_bonus_as_usable():
    # The $tu (+20 $us) bonus must be rolled, not treated as "0 rolls".
    actions = _FakeActions(
        tu_script=[_tu(0, 30, us_bonus=20), _tu(0, 30)],
        roll_script=[_roll(i) for i in range(1, 21)],
        stack_script=[_us_stack(0)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert len(actions.roll_commands()) == 20  # rolled the +20 $us bonus
    assert actions.us_adds() == []  # already had usable rolls; no add needed


def test_us_mode_requests_floored_to_stack_when_below_20():
    # Only 7 stacked -> request "$us 7" (capped at 20, floored to the stack).
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30, us_bonus=7)],
        roll_script=[_roll(i) for i in range(1, 8)],
        stack_script=[_us_stack(7)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert actions.us_adds() == ["us 7"]
    assert len(actions.roll_commands()) == 7


def test_us_mode_fast_add_skips_tu_when_tick_received():
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30, us_bonus=20)],
        roll_script=[_roll(i) for i in range(1, 36)],
        stack_script=[_us_stack(35)],
    )
    engine, state = _make_engine(actions)

    _run_us(engine)

    tu_sends = sum(1 for entry in state.activity_log if entry.text == "Sent $tu")
    assert tu_sends == 2
    assert actions.us_adds() == ["us 20", "us 15"]
    assert any("acknowledged — rolling" in entry.text for entry in state.activity_log)


def test_us_mode_falls_back_to_tu_when_tick_missing():
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30, us_bonus=20), _tu(0, 30, us_bonus=15)],
        roll_script=[_roll(i) for i in range(1, 36)],
        stack_script=[_us_stack(35)],
    )
    actions.tick_ack = False
    engine, state = _make_engine(actions)

    _run_us(engine)

    assert any("no Mudae tick" in entry.text for entry in state.activity_log)
    assert len(actions.roll_commands()) == 35


def test_us_mode_stops_when_adds_not_registering():
    # Mudae ignores every "$us 20" (usable stays 0) -> stop after the cap instead
    # of looping forever re-adding against the same stack.
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30), _tu(0, 30), _tu(0, 30)],
        roll_script=[],
        stack_script=[_us_stack(50), _us_stack(50), _us_stack(50), _us_stack(50)],
    )
    actions.tick_ack = False
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert actions.us_adds() == ["us 20", "us 20", "us 20"]  # stopped at the cap (3)
    assert len(actions.roll_commands()) == 0


class _TimeoutOnceActions(_FakeActions):
    """Returns None for every embed-wait stage on one roll, then serves the rest."""

    def __init__(
        self,
        tu_script: list,
        rolls_before_timeout: list,
        rolls_after_timeout: list,
        stack_script: list | None = None,
    ) -> None:
        super().__init__(tu_script, [], stack_script)
        wait_script: list = []
        for item in rolls_before_timeout:
            if item is None:
                wait_script.extend([None, None, None])
            else:
                wait_script.append(item)
        wait_script.extend(rolls_after_timeout)
        self._roll_waits = deque(wait_script)

    async def wait_for_roll(self, *, roll_command: str, timeout: float = 20.0):
        return self._roll_waits.popleft() if self._roll_waits else None


def test_us_mode_retries_after_roll_timeout():
    # Two rolls succeed, third times out on all resend stages; after wait, $tu shows 3 left.
    actions = _TimeoutOnceActions(
        tu_script=[_tu(0, 30, us_bonus=5), _tu(0, 30, us_bonus=3), _tu(0, 30)],
        rolls_before_timeout=[_roll(1), _roll(2), None],
        rolls_after_timeout=[_roll(3), _roll(4), _roll(5)],
        stack_script=[_us_stack(0)],
    )
    engine, state = _make_engine(actions)

    _run_us(engine)

    # Eight $wa sends: roll 3 uses initial + 2 resends before timing out (3 sends).
    assert len(actions.roll_commands()) == 8
    assert any("resending $wa" in entry.text for entry in state.activity_log)
    assert any("resuming" in entry.text for entry in state.activity_log)
    assert any("finished (5 roll(s))" in entry.text for entry in state.activity_log)


def test_us_mode_consumes_normal_rolls_first():
    # Start with 5 normal rolls -> roll them (stop-at-2 tail); then stack empty -> stop.
    actions = _FakeActions(
        tu_script=[_tu(5, 30), _tu(2, 30)],
        roll_script=[
            _roll(1, 4),
            _roll(2, 3),
            _roll(3, 2),
            _roll(4, 1),
            _roll(5, 0),
        ],
        stack_script=[_us_stack(0.2)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert len(actions.roll_commands()) == 5
    assert actions.us_adds() == []  # normal rolls used before any $us add


def test_us_mode_spends_leftover_bonus_rolls():
    """One-off bonus rolls (chaos kakera and friends) must not be stranded.

    A pool that starts at or below the stop-at-2 threshold never triggers Mudae's
    "N rolls left" footer, so the standard pass would roll nothing and these two
    would sit unused forever while $us rolls cycled and refilled around them.
    """
    actions = _FakeActions(
        tu_script=[_tu(2, 30), _tu(0, 30)],
        roll_script=[_roll(1), _roll(2)],
        stack_script=[_us_stack(0.2)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert len(actions.roll_commands()) == 2
    assert actions.us_adds() == []


def test_us_mode_spends_a_single_leftover_roll():
    actions = _FakeActions(
        tu_script=[_tu(1, 30), _tu(0, 30)],
        roll_script=[_roll(1)],
        stack_script=[_us_stack(0.2)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert len(actions.roll_commands()) == 1


def test_us_mode_spends_leftovers_before_stacking_more():
    """The reported scenario: 2 leftover rolls alongside a live $us stack."""
    actions = _FakeActions(
        # Leftovers, then an empty pool, then $tu confirming the added $us rolls.
        tu_script=[_tu(2, 30), _tu(0, 30), _tu(0, 30, us_bonus=5)],
        roll_script=[_roll(i) for i in range(1, 8)],
        stack_script=[_us_stack(5)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    first_add = next(
        i for i, (cmd, _) in enumerate(actions.sent) if cmd.startswith("us ")
    )
    rolled_before_add = [c for c, _ in actions.sent[:first_add] if c == "wa"]
    assert len(rolled_before_add) == 2
    assert actions.us_adds() == ["us 5"]
    assert len(actions.roll_commands()) == 7


def test_us_mode_spends_chaos_extras_as_ordinary_hourly():
    """$tu already includes +N chaos rolls; they are ordinary stop-at-2 rolls."""
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
        stack_script=[_us_stack(0.2)],
    )
    engine, state = _make_engine(actions)
    state.chaos_rolls_left = 5

    _run_us(engine)

    assert len(actions.roll_commands()) == 7
    assert actions.us_adds() == []
    assert any("Parsed 2 rolls left" in entry.text for entry in state.activity_log)
    assert not any("extra hourly roll" in entry.text for entry in state.activity_log)


def test_roll_counts_tick_down_between_tu_polls():
    """Mudae prints a footer count only near the end of a pool.

    Without a local decrement the status bar would sit on the last $tu figure for
    the whole batch, so the user never sees rolls being spent.
    """
    actions = _FakeActions(
        tu_script=[_tu(0, 30, us_bonus=3), _tu(0, 30)],
        roll_script=[_roll(1), _roll(2), _roll(3)],
        stack_script=[_us_stack(0.2)],
    )
    engine, state = _make_engine(actions)
    seen: list[tuple[int | None, int | None]] = []
    engine._on_state = lambda: seen.append((state.rolls_left, state.rolls_us_bonus))

    _run_us(engine)

    assert (0, 2) in seen
    assert (0, 1) in seen
    assert (0, 0) in seen


def test_footer_count_wins_over_the_local_decrement():
    """$tu and the embed footer stay authoritative; the decrement only fills gaps."""
    actions = _FakeActions(
        tu_script=[_tu(4, 30), _tu(0, 30)],
        roll_script=[_roll(1, 3), _roll(2, 2), _roll(3, 1), _roll(4, 0)],
        stack_script=[_us_stack(0.2)],
    )
    engine, state = _make_engine(actions)
    seen: list[int | None] = []
    engine._on_state = lambda: seen.append(state.rolls_left)

    _run_us(engine)

    # Collapse repeats from notifications that were not roll counts changing.
    counts = [n for n in seen if n is not None]
    steps = [n for i, n in enumerate(counts) if i == 0 or n != counts[i - 1]]
    # Straight down by the footer values, never skipping one to a double decrement.
    assert steps == [4, 3, 2, 1, 0]


def test_consume_roll_takes_us_rolls_from_the_bonus_pool_first():
    engine, state = _make_engine(_FakeActions(tu_script=[], roll_script=[]))
    state.rolls_left = 2
    state.rolls_us_bonus = 3

    engine._consume_roll(us_roll=True)
    assert (state.rolls_left, state.rolls_us_bonus) == (2, 2)

    engine._consume_roll(us_roll=False)
    assert (state.rolls_left, state.rolls_us_bonus) == (1, 2)


def test_consume_roll_falls_back_to_normal_rolls_when_bonus_is_gone():
    engine, state = _make_engine(_FakeActions(tu_script=[], roll_script=[]))
    state.rolls_left = 2
    state.rolls_us_bonus = 0

    engine._consume_roll(us_roll=True)

    assert state.rolls_left == 1


def test_consume_roll_never_goes_negative():
    engine, state = _make_engine(_FakeActions(tu_script=[], roll_script=[]))
    state.rolls_left = 0
    state.rolls_us_bonus = 0

    engine._consume_roll(us_roll=True)
    engine._consume_roll(us_roll=False)

    assert (state.rolls_left, state.rolls_us_bonus) == (0, 0)


def test_us_mode_does_not_add_when_reset_imminent():
    # Rolls reset in 2 min (== margin): roll out the 3 remaining, wait, resume.
    actions = _FakeActions(
        tu_script=[_tu(3, 2), _tu(0, 58), _tu(0, 58)],
        roll_script=[_roll(i) for i in range(1, 4)],
        stack_script=[_us_stack(0)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert actions.us_adds() == []  # no $us adds while reset was imminent
    assert len(actions.roll_commands()) == 3


def test_us_mode_waits_and_resumes_after_reset():
    # Near reset with 0 usable -> wait -> normal rolls refresh -> roll them out.
    actions = _FakeActions(
        tu_script=[_tu(0, 1), _tu(5, 55), _tu(5, 55), _tu(2, 55), _tu(0, 55)],
        roll_script=[
            _roll(1, 4),
            _roll(2, 3),
            _roll(3, 2),
            _roll(4, 1),
            _roll(5, 0),
        ],
        stack_script=[_us_stack(0)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert len(actions.roll_commands()) == 5  # rolled after reset, not stopped early
    assert actions.us_adds() == []


def test_us_mode_stops_immediately_when_reset_imminent_and_no_rolls():
    # Near reset, nothing to roll, wait until reset passes, then stack is empty.
    actions = _FakeActions(
        tu_script=[_tu(0, 1), _tu(0, 58), _tu(0, 58)],
        roll_script=[],
        stack_script=[_us_stack(0)],
    )
    engine, _ = _make_engine(actions)

    _run_us(engine)

    assert actions.us_adds() == []
    assert len(actions.roll_commands()) == 0


def test_us_kakera_rules_for_us_rolls():
    cfg = MacroConfig(
        kakera_reaction=KakeraReactionRules(enabled=True, types_allowed=["kakeraR"]),
        us_roll_kakera=UsRollKakeraRules(override=True, skip_kakera=True),
    )
    assert cfg.kakera_rules_for_roll(us_roll=False).enabled is True
    assert cfg.kakera_rules_for_roll(us_roll=True).enabled is False

    cfg2 = MacroConfig(
        kakera_reaction=KakeraReactionRules(enabled=True, types_allowed=["kakeraR"]),
        us_roll_kakera=UsRollKakeraRules(override=True, types_allowed=["kakeraP"]),
    )
    selected = cfg2.kakera_rules_for_roll(us_roll=True)
    assert selected.enabled is True
    assert selected.types_allowed == ["kakeraP"]
    assert cfg2.kakera_rules_for_roll(us_roll=False).types_allowed == ["kakeraR"]

    cfg3 = MacroConfig(
        us_roll_kakera=UsRollKakeraRules.from_dict(
            {"mode": "selected", "types_allowed": ["kakeraG"]}
        ),
    )
    migrated = cfg3.us_roll_kakera
    assert migrated.override is True
    assert migrated.types_allowed == ["kakeraG"]


def _roll_limit(reset_minutes: int = 30) -> tuple[SimpleNamespace, ParseResult]:
    from mudae.parsers.roll_limit import parse_roll_limit

    content = (
        "user, the roulette is limited to 30 uses per hour. "
        f"{reset_minutes} min left."
    )
    return SimpleNamespace(message_id=999), parse_roll_limit(content)


def test_us_mode_continues_when_bonus_normal_rolls_hit_hourly_limit():
    """Bonus normals from $tu are spent when real; roll limit clears phantoms."""
    actions = _FakeActions(
        tu_script=[
            _tu(0, 30, us_bonus=2),
            _tu(2, 30),
            _tu(0, 30, us_bonus=2),
            _tu(0, 30),
        ],
        roll_script=[
            _roll(1),
            _roll(2),
            _roll_limit(30),
            _roll(3),
            _roll(4),
        ],
        stack_script=[_us_stack(0.2)],
    )
    engine, state = _make_engine(actions)

    _run_us(engine)

    # Rolls 1–2 ($us), roll 3 (bonus attempt → limit), rolls 3–4 ($us resume).
    assert len(actions.roll_commands()) == 5
    assert any(
        "continuing $us rolls" in entry.text for entry in state.activity_log
    )
    assert not any(
        "normal roll failed — stopping" in entry.text for entry in state.activity_log
    )


def test_us_roll_footer_updates_us_bonus_not_normal_rolls():
    """Low-roll footers during $us track the $us pool, not bonus normal rolls."""
    actions = _FakeActions(tu_script=[], roll_script=[])
    engine, state = _make_engine(actions)
    state.rolls_left = 0
    state.rolls_us_bonus = 5

    snapshot, parsed = _roll(1, rolls_left=4)

    async def _run() -> None:
        await engine._process_roll_embed(
            snapshot,
            parsed,
            roll_index=1,
            session_records=[],
            us_roll=True,
            stop_on_interrupt=False,
        )

    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(_run())

    assert state.rolls_left == 0
    assert state.rolls_us_bonus == 4


def test_us_roll_footer_ignored_when_us_pool_empty():
    """With no $us pool left, footers must not invent bonus normal rolls."""
    actions = _FakeActions(tu_script=[], roll_script=[])
    engine, state = _make_engine(actions)
    state.rolls_left = 0
    state.rolls_us_bonus = 0

    snapshot, parsed = _roll(1, rolls_left=2)

    async def _run() -> None:
        await engine._process_roll_embed(
            snapshot,
            parsed,
            roll_index=1,
            session_records=[],
            us_roll=True,
            stop_on_interrupt=False,
        )

    with patch("macro.roll_cycle.asyncio.sleep", new=_fast_sleep):
        asyncio.run(_run())

    assert state.rolls_left == 0
    assert state.rolls_us_bonus == 0


def test_us_kakera_override_ignores_base_low_power_colors():
    from macro.config import LowPowerOverride
    from macro.rule_eval import passes_kakera_reaction
    from macro.state import AccountState

    cfg = MacroConfig(
        kakera_reaction=KakeraReactionRules(
            enabled=True,
            types_allowed=["kakeraR", "kakeraC"],
            low_power=LowPowerOverride(below_percent=50, types_allowed=["kakeraC"]),
        ),
        us_roll_kakera=UsRollKakeraRules(
            override=True,
            types_allowed=["kakeraP", "kakeraR"],
        ),
    )
    rules = cfg.kakera_rules_for_roll(us_roll=True)
    assert rules.low_power is None
    assert rules.perk_8_types_allowed == []

    fields = {
        "buttons": [
            {
                "is_kakera": True,
                "emoji": "kakeraC",
                "disabled": False,
                "custom_id": "k1",
            }
        ],
    }
    decision = passes_kakera_reaction(
        fields,
        rules,
        AccountState(power_percent=10.0),
    )
    assert not decision.should_click
    assert "kakeraC" not in (decision.reason or "")


def test_us_kakera_perk_8_character_uses_base_perk_8_colors():
    from macro.config import LowPowerOverride
    from macro.rule_eval import passes_kakera_reaction
    from macro.state import AccountState

    cfg = MacroConfig(
        kakera_reaction=KakeraReactionRules(
            enabled=True,
            types_allowed=["kakeraR"],
            perk_8_budget_mode=True,
            perk_8_types_allowed=["kakeraT", "kakeraR"],
        ),
        us_roll_kakera=UsRollKakeraRules(
            override=True,
            types_allowed=["kakeraP"],
        ),
    )
    rules = cfg.kakera_rules_for_roll(us_roll=True)
    assert rules.types_allowed == ["kakeraP"]
    assert rules.perk_8_types_allowed == ["kakeraT", "kakeraR"]
    assert rules.perk_8_priority is True

    fields = {
        "perk_8": True,
        "buttons": [
            {
                "is_kakera": True,
                "emoji": "kakeraT",
                "disabled": False,
                "custom_id": "k1",
            },
            {
                "is_kakera": True,
                "emoji": "kakeraP",
                "disabled": False,
                "custom_id": "k2",
            },
        ],
    }
    state = AccountState(perk8_priority_mode="active", perk8_click_max=40, power_percent=100.0)
    decision = passes_kakera_reaction(fields, rules, state)
    assert len(decision.buttons) == 1
    assert decision.buttons[0].emoji == "kakeraT"


def test_us_kakera_rules_copy_perk8_priority_off():
    cfg = MacroConfig(
        kakera_reaction=KakeraReactionRules(
            enabled=True,
            perk_8_budget_mode=True,
            perk_8_priority=False,
        ),
        us_roll_kakera=UsRollKakeraRules(override=True, types_allowed=["kakeraP"]),
    )
    rules = cfg.kakera_rules_for_roll(us_roll=True)
    assert rules.perk_8_priority is False
    assert rules.perk8_priority_on() is False


def test_us_mode_does_not_add_when_power_exhausted():
    actions = _FakeActions(
        tu_script=[_tu(0, 30)],
        roll_script=[],
        stack_script=[_us_stack(20)],
    )
    engine, state = _make_engine(
        actions,
        kakera_reaction=KakeraReactionRules(enabled=True, auto_use_dk=True),
    )
    state.power_percent = 0.0
    state.dk_stock = 0
    engine._us_stop = UsModeStopOptions(stop_on_power_exhausted=True)

    _run_us(engine)

    assert actions.us_adds() == []
    assert len(actions.roll_commands()) == 0
    assert any("stopping" in entry.text for entry in state.activity_log)


def test_us_mode_keep_draining_resumes_after_power():
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30), _tu(0, 30, us_bonus=5)],
        roll_script=[_roll(i) for i in range(1, 6)],
        stack_script=[_us_stack(5)],
    )
    engine, state = _make_engine(
        actions,
        kakera_reaction=KakeraReactionRules(enabled=True, auto_use_dk=True),
    )
    state.power_percent = 0.0
    state.dk_stock = 0
    engine._us_stop = UsModeStopOptions(
        keep_draining=True,
        stop_on_power_exhausted=True,
    )

    async def _recover() -> bool:
        state.power_percent = 80.0
        return True

    engine._wait_for_us_power = _recover  # type: ignore[method-assign]
    _run_us(engine)

    assert actions.us_adds() == ["us 5"]
    assert len(actions.roll_commands()) == 5
    assert any("pausing" in entry.text for entry in state.activity_log)


def test_us_mode_keep_draining_roll_cap_still_stops():
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30, us_bonus=20)],
        roll_script=[_roll(i) for i in range(1, 21)],
        stack_script=[_us_stack(20)],
    )
    engine, state = _make_engine(actions)
    engine._us_stop = UsModeStopOptions(
        keep_draining=True,
        stop_after_rolls_enabled=True,
        stop_after_rolls=2,
    )

    _run_us(engine)

    assert actions.us_adds() == ["us 20"]
    assert len(actions.roll_commands()) == 2
    assert any("roll limit" in entry.text for entry in state.activity_log)


def test_us_mode_schedule_stops_after_window_without_adding():
    actions = _FakeActions(
        tu_script=[_tu(0, 30)],
        roll_script=[],
        stack_script=[_us_stack(20)],
    )
    engine, state = _make_engine(actions)
    engine._us_stop = UsModeStopOptions(
        schedule_enabled=True,
        schedule_start="04:00",
        schedule_end="06:00",
    )
    engine._us_schedule_entered = True
    engine._us_in_schedule_window = lambda: False  # type: ignore[method-assign]

    _run_us(engine)

    assert actions.us_adds() == []
    assert any("schedule window ended" in entry.text for entry in state.activity_log)


def test_us_mode_schedule_waits_then_adds():
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30), _tu(0, 30, us_bonus=5)],
        roll_script=[_roll(i) for i in range(1, 6)],
        stack_script=[_us_stack(5)],
    )
    engine, state = _make_engine(actions)
    engine._us_stop = UsModeStopOptions(
        schedule_enabled=True,
        schedule_start="04:00",
        schedule_end="06:00",
    )
    inside = {"on": False}
    engine._us_in_schedule_window = lambda: inside["on"]  # type: ignore[method-assign]

    async def _open_window() -> bool:
        inside["on"] = True
        engine._us_schedule_entered = True
        return True

    engine._wait_for_us_schedule_window = _open_window  # type: ignore[method-assign]
    _run_us(engine)

    assert actions.us_adds() == ["us 5"]
    assert len(actions.roll_commands()) == 5


def test_us_mode_manual_ignores_closed_schedule_window():
    actions = _FakeActions(
        tu_script=[_tu(0, 30), _tu(0, 30, us_bonus=5)],
        roll_script=[_roll(i) for i in range(1, 6)],
        stack_script=[_us_stack(5)],
    )
    engine, state = _make_engine(actions)
    engine._us_stop = UsModeStopOptions(
        schedule_enabled=False,
        schedule_start="04:00",
        schedule_end="06:00",
    )
    engine._us_in_schedule_window = lambda: False  # type: ignore[method-assign]

    _run_us(engine)

    assert actions.us_adds() == ["us 5"]
    assert len(actions.roll_commands()) == 5
    assert not any("schedule window" in entry.text for entry in state.activity_log)
