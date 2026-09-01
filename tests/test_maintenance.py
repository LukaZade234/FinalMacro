"""Backing off while Mudae is down for maintenance.

Mudae reboots occasionally and, for the duration, answers every command with
the same text instead of the reply that was asked for::

    Command under maintenance!
    (For 3 minutes, reboot)

Two things go wrong without this. First the reply is *misread*: the parse
pipeline pairs a Mudae message with the command the macro just typed, so a
maintenance reply to ``$tu`` was handed to ``parse_tu`` and came back as a
valid-looking sheet saying "0 rolls" — which sent the hourly loop straight
back around to ``$tu``, once every three seconds, for the whole outage.
Second, even parsed correctly there was nothing to wait on: a ``$tu`` that
never answers stops the macro outright.

So the macro now recognises the reply and waits it out on a ladder — 5, 10,
then 30 minutes — and stops only once that is spent, on the grounds that an
outage lasting three quarters of an hour is not a reboot.
"""

from __future__ import annotations

from types import SimpleNamespace

from macro.maintenance import MAINTENANCE_BACKOFF_MINUTES, MaintenanceWatch
from mudae.parsers.maintenance import (
    is_maintenance_message,
    parse_maintenance,
    parse_maintenance_window,
)
from mudae.parsers.pipeline import parse_mudae_message
from mudae.types import MessageKind, MudaeMessageSnapshot

from tests.test_roll_cycle import _FakeActions, _make_engine, _run_normal, _tu
from tests.test_us_roll import (
    _FakeActions as _UsFakeActions,
    _make_engine as _us_make_engine,
    _run_us,
)

MAINTENANCE_TEXT = "Command under maintenance!\n(For 3 minutes, reboot)"


def _snapshot(content: str = MAINTENANCE_TEXT, *, message_id: int = 1) -> MudaeMessageSnapshot:
    return MudaeMessageSnapshot(
        message_id=message_id,
        channel_id=5,
        channel_name="commands",
        guild_id=1,
        guild_name="srv",
        author_id=432610292342587392,
        author_name="Mudae",
        is_mudae=True,
        content=content,
        embeds=[],
        buttons=[],
        created_at="14:47:00",
    )


# --- recognising the reply --------------------------------------------------


def test_maintenance_text_is_recognised():
    assert is_maintenance_message(MAINTENANCE_TEXT)
    assert not is_maintenance_message("You can't claim right now.")
    assert not is_maintenance_message("")


def test_the_stated_window_is_parsed_for_the_log():
    assert parse_maintenance_window(MAINTENANCE_TEXT) == (3, "reboot")
    assert parse_maintenance_window("Command under maintenance!\n(For 1 hour, update)") == (
        60,
        "update",
    )
    assert parse_maintenance_window("Command under maintenance!") == (None, "")


def test_parse_maintenance_fields():
    result = parse_maintenance(MAINTENANCE_TEXT)
    assert result.kind == MessageKind.MAINTENANCE
    assert result.fields["maintenance"] is True
    assert result.fields["maintenance_minutes"] == 3
    assert result.fields["maintenance_reason"] == "reboot"


def test_a_maintenance_reply_to_tu_is_not_read_as_a_tu_sheet():
    """The regression: the pipeline pairs replies with the command that was sent."""
    parsed = parse_mudae_message(_snapshot(), reply_to_command="tu")
    assert parsed.kind == MessageKind.MAINTENANCE
    assert "rolls_left" not in parsed.fields

    from macro.actions import is_tu_parse_result

    assert not is_tu_parse_result(parsed)


def test_a_maintenance_reply_to_a_roll_is_not_read_as_a_roll():
    parsed = parse_mudae_message(_snapshot(), reply_to_command="wa")
    assert parsed.kind == MessageKind.MAINTENANCE


# --- the watch and its ladder ----------------------------------------------


def test_watch_notices_a_maintenance_reply():
    watch = MaintenanceWatch()
    assert not watch.pending
    assert watch.observe(_snapshot(), parse_maintenance(MAINTENANCE_TEXT))
    assert watch.pending
    assert watch.minutes == 3
    assert watch.reason == "reboot"


def test_watch_ignores_ordinary_replies():
    watch = MaintenanceWatch()
    assert not watch.observe(_snapshot("You have 5 rolls left."), _tu(5, 30))
    assert not watch.pending


def test_watch_falls_back_to_the_raw_content():
    """A caller that never ran the parse pipeline still gets the detection."""
    watch = MaintenanceWatch()
    assert watch.observe(_snapshot(), SimpleNamespace(kind=None, fields={}))
    assert watch.pending


def test_the_same_reply_seen_twice_is_one_outage():
    """`wait_for` re-queues messages its predicate skipped."""
    watch = MaintenanceWatch()
    snapshot = _snapshot()
    parsed = parse_maintenance(MAINTENANCE_TEXT)
    watch.observe(snapshot, parsed)
    watch.clear()
    watch.observe(snapshot, parsed)
    assert not watch.pending, "a re-queued copy must not re-arm the pause"


def test_the_ladder_is_five_then_ten_then_thirty_then_out():
    watch = MaintenanceWatch()
    assert MAINTENANCE_BACKOFF_MINUTES == (5, 10, 30)
    assert [watch.next_wait_seconds() for _ in range(3)] == [300.0, 600.0, 1800.0]
    assert watch.next_wait_seconds() is None
    assert watch.attempts == 3


def test_clear_keeps_the_ladder_but_reset_drops_it():
    watch = MaintenanceWatch()
    watch.observe(_snapshot(), parse_maintenance(MAINTENANCE_TEXT))
    watch.next_wait_seconds()
    watch.clear()
    assert watch.attempts == 1, "the outage may still be going"
    watch.reset()
    assert watch.attempts == 0
    assert not watch.pending


def test_discord_actions_watches_every_message_it_is_fed():
    """One watch per account, whichever command hits the outage."""
    from macro.actions import DiscordActions

    actions = DiscordActions(SimpleNamespace())
    actions.feed(_snapshot(), parse_maintenance(MAINTENANCE_TEXT))
    assert actions.maintenance.pending


# --- the hourly loop --------------------------------------------------------


class _MaintenanceActions(_FakeActions):
    """Mudae is down: `$tu` never answers, and the reply says why.

    ``tu_script`` supplies the replies that arrive *once Mudae is back*, so a
    test can say how long the outage lasts.
    """

    def __init__(self, *, outages: int, tu_script: list | None = None) -> None:
        super().__init__(tu_script=tu_script or [], roll_script=[])
        self.maintenance = MaintenanceWatch()
        self._outages = outages
        self.tu_attempts = 0

    async def wait_for_tu(self, *, timeout: float = 12.0):
        self.tu_attempts += 1
        if self.tu_attempts <= self._outages:
            self.maintenance.observe(
                _snapshot(message_id=self.tu_attempts),
                parse_maintenance(MAINTENANCE_TEXT),
            )
            return None
        return await super().wait_for_tu(timeout=timeout)


def _log_text(state) -> list[str]:
    return [entry.text for entry in state.activity_log]


def test_the_loop_waits_out_a_short_outage_and_carries_on():
    actions = _MaintenanceActions(outages=1, tu_script=[_tu(0, 30)])
    engine, state = _make_engine(actions)

    _run_normal(engine)

    lines = _log_text(state)
    assert any("Mudae is under maintenance" in line for line in lines)
    assert any("waiting 5m before retry 1" in line for line in lines)
    # The retry went through and its $tu was applied, so the loop carried on
    # from where it was rather than stopping on the outage.
    assert state.rolls_reset_minutes == 30
    assert not any("still under maintenance" in line for line in lines)


def test_the_stated_window_is_reported_not_obeyed():
    actions = _MaintenanceActions(outages=1, tu_script=[_tu(0, 30)])
    engine, state = _make_engine(actions)

    _run_normal(engine)

    line = next(l for l in _log_text(state) if "under maintenance" in l)
    assert "Mudae says ~3 min, reboot" in line
    assert "waiting 5m" in line, "the ladder decides the wait, not Mudae's guess"


def test_the_loop_backs_off_further_each_time_then_stops():
    actions = _MaintenanceActions(outages=99)
    engine, state = _make_engine(actions)

    _run_normal(engine)

    lines = _log_text(state)
    assert any("waiting 5m before retry 1" in line for line in lines)
    assert any("waiting 10m before retry 2" in line for line in lines)
    assert any("waiting 30m before retry 3" in line for line in lines)
    assert any(
        "still under maintenance after 3 retries — stopping" in line for line in lines
    )
    # Four $tu in total: the one that found the outage, plus one per rung.
    assert actions.tu_attempts == 4


def test_a_recovered_mudae_resets_the_ladder():
    """A second outage next hour starts at five minutes again, not at ten."""
    actions = _MaintenanceActions(outages=1, tu_script=[_tu(0, 30)])
    engine, _state = _make_engine(actions)

    _run_normal(engine)

    assert actions.maintenance.attempts == 0
    assert not actions.maintenance.pending


# --- $us mode ---------------------------------------------------------------


class _UsMaintenanceActions(_UsFakeActions):
    """The same outage, seen by the ``$us`` loop's own ``$tu``."""

    def __init__(self, *, outages: int) -> None:
        super().__init__(tu_script=[], roll_script=[], stack_script=[])
        self.maintenance = MaintenanceWatch()
        self._outages = outages
        self.tu_attempts = 0

    async def wait_for_tu(self, *, timeout: float = 12.0):
        self.tu_attempts += 1
        if self.tu_attempts <= self._outages:
            self.maintenance.observe(
                _snapshot(message_id=self.tu_attempts),
                parse_maintenance(MAINTENANCE_TEXT),
            )
            return None
        return await super().wait_for_tu(timeout=timeout)


def test_us_mode_backs_off_on_the_same_ladder():
    actions = _UsMaintenanceActions(outages=99)
    engine, state = _us_make_engine(actions)

    _run_us(engine)

    lines = _log_text(state)
    assert any("$us mode: Mudae is under maintenance" in line for line in lines)
    assert any("waiting 5m before retry 1" in line for line in lines)
    assert any("waiting 30m before retry 3" in line for line in lines)
    assert any(
        "still under maintenance after 3 retries — stopping" in line for line in lines
    )
    assert actions.tu_attempts == 4
