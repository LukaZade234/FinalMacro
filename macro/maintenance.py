"""Wait out a Mudae maintenance window instead of hammering a dead bot.

Mudae goes down for a reboot occasionally and answers every command with
``Command under maintenance!`` for the duration
(:mod:`mudae.parsers.maintenance`). There is nothing the macro can do but wait,
and retrying on the ordinary command cadence just fills the channel — during
one real outage the hourly loop sent ``$tu`` every three seconds for the whole
reboot.

The policy is a fixed ladder rather than Mudae's own stated window: it says
"(For 3 minutes, reboot)" and keeps saying it long after three minutes have
passed, so the estimate is logged and otherwise ignored. Each retry waits
longer, and once the ladder runs out the macro stops rather than sitting
connected against an outage that is clearly not a reboot.
"""

from __future__ import annotations

from typing import Any

from mudae.parsers.maintenance import is_maintenance_message
from mudae.types import MessageKind

# Minutes to wait before each retry. Exhausting the ladder stops the macro.
MAINTENANCE_BACKOFF_MINUTES: tuple[int, ...] = (5, 10, 30)


class MaintenanceWatch:
    """Notices maintenance replies and paces the retries after one.

    One instance per :class:`~macro.actions.DiscordActions`, so every command
    on that account shares both the observation and the ladder: it does not
    matter whether the outage is noticed on ``$tu``, a roll, or ``$ohu``.
    """

    def __init__(
        self,
        backoff_minutes: tuple[int, ...] = MAINTENANCE_BACKOFF_MINUTES,
    ) -> None:
        self._backoff = tuple(backoff_minutes)
        self._pending = False
        self._minutes: int | None = None
        self._reason = ""
        self._attempts = 0
        self._last_message_id: int | None = None

    # --- observation --------------------------------------------------------

    def observe(self, snapshot: Any, parsed: Any) -> bool:
        """Record a maintenance reply. True when this message was one.

        Takes the parsed result when it has one and falls back to the raw
        content, so a caller that never ran the parse pipeline still works.
        """
        if not self._is_maintenance(snapshot, parsed):
            return False
        message_id = getattr(snapshot, "message_id", None)
        if message_id is not None and message_id == self._last_message_id:
            # ``wait_for`` re-queues messages its predicate skipped, so the
            # same reply comes past repeatedly; it is still one outage.
            return True
        self._last_message_id = message_id
        self._pending = True
        fields = getattr(parsed, "fields", None) or {}
        minutes = fields.get("maintenance_minutes")
        self._minutes = int(minutes) if isinstance(minutes, int) else None
        self._reason = str(fields.get("maintenance_reason") or "")
        return True

    @staticmethod
    def _is_maintenance(snapshot: Any, parsed: Any) -> bool:
        if getattr(parsed, "kind", None) == MessageKind.MAINTENANCE:
            return True
        return is_maintenance_message(getattr(snapshot, "content", "") or "")

    # --- state --------------------------------------------------------------

    @property
    def pending(self) -> bool:
        """True when a maintenance reply has been seen and not yet acted on."""
        return self._pending

    @property
    def minutes(self) -> int | None:
        """Mudae's own estimate for the window, in minutes. Advisory only."""
        return self._minutes

    @property
    def reason(self) -> str:
        """Mudae's stated reason, e.g. ``reboot``."""
        return self._reason

    @property
    def attempts(self) -> int:
        """How many backoff waits this outage has taken so far."""
        return self._attempts

    @property
    def backoff_minutes(self) -> tuple[int, ...]:
        return self._backoff

    # --- the ladder ---------------------------------------------------------

    def clear(self) -> None:
        """Acknowledge the reply, keeping the ladder — the outage may continue.

        The message id is kept too: ``wait_for`` re-queues what it skipped, so
        the very same reply comes past again and must not re-arm the pause.
        Only a *new* maintenance reply does that.
        """
        self._pending = False

    def reset(self) -> None:
        """Mudae answered a command: forget the outage and the ladder with it."""
        self._pending = False
        self._minutes = None
        self._reason = ""
        self._attempts = 0
        self._last_message_id = None

    def next_wait_seconds(self) -> float | None:
        """Seconds to wait before the next retry, or ``None`` when out of rungs."""
        if self._attempts >= len(self._backoff):
            return None
        wait = self._backoff[self._attempts] * 60.0
        self._attempts += 1
        return wait


def format_maintenance_wait(seconds: float) -> str:
    """``5m`` / ``30m`` for the activity log."""
    return f"{int(round(seconds / 60.0))}m"
