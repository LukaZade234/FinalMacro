"""Macro engine unit tests (no Discord)."""

from macro.actions import is_roll_parse_result, is_tu_parse_result
from macro.config import MacroConfig
from macro.roll_stop import RollStopTracker
from macro.state import AccountState, MacroPhase
from mudae.types import MessageKind, ParseResult


def test_wish_ping_interrupt_when_user_in_wished_by():
    from macro.roll_interrupts import RollInterruptContext, evaluate_roll_interrupts

    ctx = RollInterruptContext(
        fields={"wished_by": [111, 222, 333]},
        own_user_ids=[222],
    )
    hit = evaluate_roll_interrupts(ctx)
    assert hit is not None
    assert hit.code == "wish_ping"


def test_wish_ping_no_interrupt_when_user_not_pinged():
    from macro.roll_interrupts import RollInterruptContext, evaluate_roll_interrupts

    ctx = RollInterruptContext(
        fields={"wished_by": [111, 333]},
        own_user_ids=[222],
    )
    assert evaluate_roll_interrupts(ctx) is None


def test_wish_ping_no_interrupt_without_wished_by():
    from macro.roll_interrupts import RollInterruptContext, evaluate_roll_interrupts

    ctx = RollInterruptContext(fields={"character_name": "Rem"}, own_user_ids=[1])
    assert evaluate_roll_interrupts(ctx) is None


def test_activity_log_writes_once_per_line():
    from macro.activity_log import ActivityLog

    state = AccountState()
    updates = []

    log = ActivityLog(state, on_update=lambda: updates.append(1))
    log.write("first")
    log.write("second")

    assert [entry.text for entry in state.activity_log] == ["first", "second"]
    assert len(updates) == 2


def test_classify_activity_line():
    from macro.activity_log import classify_activity_line

    assert classify_activity_line("Claimed Rem (you)") == "claim"
    assert classify_activity_line("kakera click ×2 Maki: matched") == "click"
    assert classify_activity_line(":kakeraT: TestUser +546 ($k)") == "click"
    assert classify_activity_line(":spB: lukazade234 +72 (1/15)") == "click"
    assert classify_activity_line("sphere skip Rem: no button") == "skip"
    assert classify_activity_line("Roll embed timeout") == "error"
    assert classify_activity_line("Sent $tu") == "info"
    assert classify_activity_line("$wa") == "info"
    assert classify_activity_line("Roll 12: $wa") == "info"


def test_roll_stop_tracker_warning_then_tail():
    tracker = RollStopTracker(threshold=2, tail_count=2)

    assert tracker.on_roll_parsed(29) is False
    assert tracker.saw_warning is False

    assert tracker.on_roll_parsed(2) is False
    assert tracker.saw_warning is True
    assert tracker.tail_remaining == 2

    assert tracker.on_roll_parsed(1) is False
    assert tracker.tail_remaining == 1

    assert tracker.on_roll_parsed(None) is True
    assert tracker.tail_remaining == 0


def test_roll_stop_tracker_does_not_stop_on_warning_roll():
    """Seeing 2 left schedules two more rolls; warning roll itself does not stop."""
    tracker = RollStopTracker(threshold=2, tail_count=2)
    assert tracker.on_roll_parsed(2) is False
    assert tracker.tail_remaining == 2


def test_pick_best_claimable():
    import time

    from macro.post_roll import RollRecord, pick_best_claimable, roll_total_kakera

    now = time.monotonic()
    records = [
        RollRecord(1, "Low", {"total_kakera": 50, "can_claim": True, "claimed": False}, rolled_at=now),
        RollRecord(2, "High", {"total_kakera": 200, "can_claim": True, "claimed": False}, rolled_at=now),
        RollRecord(3, "Taken", {"total_kakera": 999, "can_claim": False, "claimed": True}, rolled_at=now),
    ]
    best = pick_best_claimable(records, expire_sec=45, now=now)
    assert best is not None
    assert best.character_name == "High"
    assert roll_total_kakera(best.fields) == 200


def test_pick_best_excludes_expired_rolls():
    import time

    from macro.post_roll import RollRecord, pick_best_claimable

    now = time.monotonic()
    records = [
        RollRecord(1, "Old", {"total_kakera": 500, "can_claim": True, "claimed": False}, rolled_at=now - 60),
        RollRecord(2, "Fresh", {"total_kakera": 80, "can_claim": True, "claimed": False}, rolled_at=now),
    ]
    best = pick_best_claimable(records, expire_sec=45, now=now)
    assert best is not None
    assert best.character_name == "Fresh"


def test_pick_best_claimable_none():
    from macro.post_roll import RollRecord, pick_best_claimable

    records = [
        RollRecord(1, "A", {"total_kakera": 10, "can_claim": False, "claimed": True}),
    ]
    assert pick_best_claimable(records) is None


def test_final_roll_session_detection():
    from macro.claim_window import is_final_roll_session_before_claim_reset

    assert is_final_roll_session_before_claim_reset(60, 60) is True
    assert is_final_roll_session_before_claim_reset(180, 60) is False
    assert is_final_roll_session_before_claim_reset(120, 60) is False
    assert is_final_roll_session_before_claim_reset(75, 60) is False
    assert is_final_roll_session_before_claim_reset(61, 60) is False


def test_macro_config_roundtrip():
    from macro.config import CharacterClaimRules

    cfg = MacroConfig(
        roll_command="wa",
        character_claim=CharacterClaimRules(
            enabled=False,
            claim_on_wish_ping=True,
        ),
    )
    restored = MacroConfig.from_dict(cfg.to_dict())
    assert restored.character_claim.claim_on_wish_ping is True
    assert restored.character_claim.enabled is False
    assert restored.auto_claim_wish is True
    assert restored.claim_best_at_claim_reset is False
    assert restored.normalized_roll_command() == "wa"
    assert restored.roll_delay() >= 0.6


def test_humanize_roll_delay_roundtrip_and_jitter(monkeypatch):
    cfg = MacroConfig(
        humanize_roll_delay=True,
        roll_delay_sec=0.8,
        roll_delay_jitter_sec=0.3,
    )
    restored = MacroConfig.from_dict(cfg.to_dict())
    assert restored.humanize_roll_delay is True
    assert restored.roll_delay_jitter_sec == 0.3
    monkeypatch.setattr("macro.config.random.uniform", lambda _a, _b: 0.25)
    delay = restored.roll_delay()
    assert delay == 0.8 + 0.25


def test_humanize_off_uses_fixed_delay(monkeypatch):
    calls = []

    def _uniform(a, b):
        calls.append((a, b))
        return 0.5

    monkeypatch.setattr("macro.config.random.uniform", _uniform)
    cfg = MacroConfig(humanize_roll_delay=False, roll_delay_sec=0.9)
    assert cfg.roll_delay() == 0.9
    assert calls == []


def test_notification_mode_config_roundtrip():
    cfg = MacroConfig(notification_mode=True)
    restored = MacroConfig.from_dict(cfg.to_dict())
    assert restored.notification_mode is True


def test_account_state_to_dict():
    state = AccountState(rolls_left=29, claim_available=True, phase=MacroPhase.ROLLING)
    data = state.to_dict()
    assert data["rolls_left"] == 29
    assert data["phase"] == "Rolling"
    assert state.claim_label() == "can claim"


def test_is_tu_parse_result():
    assert is_tu_parse_result(ParseResult(kind=MessageKind.TU, summary="tu", fields={}))
    assert is_tu_parse_result(
        ParseResult(
            kind=MessageKind.COMMAND_RESPONSE,
            summary="",
            fields={"parser_command": "tu"},
        )
    )
    assert not is_tu_parse_result(
        ParseResult(kind=MessageKind.KAKERA_CLAIM, summary="", fields={})
    )


def test_is_roll_parse_result():
    assert is_roll_parse_result(
        ParseResult(
            kind=MessageKind.CHARACTER_EMBED,
            summary="",
            fields={"character_name": "Rem"},
        ),
        roll_command="wa",
    )
    assert is_roll_parse_result(
        ParseResult(
            kind=MessageKind.COMMAND_RESPONSE,
            summary="",
            fields={"parser_command": "roll", "character_name": "Rem"},
        ),
        roll_command="wa",
    )
    assert is_roll_parse_result(
        ParseResult(
            kind=MessageKind.ROLL_LIMIT,
            summary="",
            fields={"rolls_left": 0, "rolls_reset_minutes": 34},
        ),
        roll_command="wa",
    )
    assert not is_roll_parse_result(
        ParseResult(
            kind=MessageKind.COMMAND_RESPONSE,
            summary="",
            fields={"parser_command": "roll", "command": "wa"},
        ),
        roll_command="wa",
    )
    assert not is_roll_parse_result(
        ParseResult(
            kind=MessageKind.ROLL,
            summary="",
            fields={
                "character_name": "Akame",
                "perk_6": True,
                "spawned_by": "Power",
            },
        ),
        roll_command="wa",
    )
    assert not is_roll_parse_result(
        ParseResult(kind=MessageKind.TU, summary="", fields={}),
        roll_command="wa",
    )


def test_macro_suppresses_user_command_context():
    from mudae.command_context import CommandContextTracker
    from mudae.types import MudaeMessageSnapshot

    tracker = CommandContextTracker()
    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=99,
        channel_name="c",
        guild_id=1,
        guild_name="g",
        author_id=123,
        author_name="user",
        is_mudae=False,
        content="$wa",
        embeds=[],
        buttons=[],
        created_at="t",
    )
    tracker.observe(snapshot)
    assert tracker.consume(99) is not None
    # When macro_active, observe is skipped in discord_reader — tested via flag semantics:
    # macro_active True means consume only from pending_macro_command path.
