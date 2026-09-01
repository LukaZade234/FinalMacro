"""Parse Mudae's "command under maintenance" reply.

While Mudae reboots it answers **every** command with the same short text
instead of the reply the command asked for — ``$tu``, ``$wa``, ``$oh``,
anything::

    Command under maintenance!
    (For 3 minutes, reboot)

This has to be recognised *before* the reply is matched to the command that was
sent, because the macro pairs a Mudae message with the command it just typed
(``mudae.commands.resolve_command``) rather than with the message's own shape.
Without this parser a maintenance reply to ``$tu`` is handed to ``parse_tu``,
comes back as an empty but otherwise valid ``$tu`` sheet, and the hourly loop
reads "0 rolls, reset passed" and immediately sends ``$tu`` again — which is
what a real outage produced: one ``$tu`` every three seconds for the length of
the reboot.

The parenthesised window is Mudae's own estimate and is parsed for the log, but
the macro does not schedule off it: it uses its own backoff ladder in
:mod:`macro.maintenance`, because the stated minutes are a guess Mudae keeps
repeating after they have elapsed.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.types import MessageKind, ParseResult

_MAINTENANCE_RE = re.compile(
    r"command\s+under\s+maintenance",
    re.IGNORECASE,
)
# ``(For 3 minutes, reboot)`` — the estimate, then the reason.
_WINDOW_RE = re.compile(
    r"\(\s*for\s+(?P<amount>\d+)\s*(?P<unit>second|minute|hour)s?"
    r"(?:\s*,\s*(?P<reason>[^)]*))?\)",
    re.IGNORECASE,
)
_UNIT_MINUTES = {"second": 0, "minute": 1, "hour": 60}


def is_maintenance_message(content: str) -> bool:
    """True when Mudae refused a command because it is under maintenance."""
    return _MAINTENANCE_RE.search(content or "") is not None


def parse_maintenance_window(content: str) -> tuple[int | None, str]:
    """``(minutes, reason)`` from ``(For 3 minutes, reboot)``.

    Minutes is ``None`` when Mudae gave no window. Sub-minute windows round to
    zero rather than to one — the number is only ever logged.
    """
    match = _WINDOW_RE.search(content or "")
    if match is None:
        return None, ""
    unit = (match.group("unit") or "").lower()
    minutes = int(match.group("amount")) * _UNIT_MINUTES.get(unit, 1)
    return minutes, (match.group("reason") or "").strip()


def format_maintenance_activity(fields: dict[str, Any]) -> str:
    """Activity-log line for a maintenance reply."""
    minutes = fields.get("maintenance_minutes")
    reason = str(fields.get("maintenance_reason") or "")
    note = ""
    if minutes is not None and reason:
        note = f" · Mudae says ~{minutes} min ({reason})"
    elif minutes is not None:
        note = f" · Mudae says ~{minutes} min"
    elif reason:
        note = f" · {reason}"
    return f"Mudae is under maintenance{note}"


def parse_maintenance(content: str) -> ParseResult:
    minutes, reason = parse_maintenance_window(content or "")
    fields: dict[str, Any] = {
        "maintenance": True,
        "maintenance_minutes": minutes,
        "maintenance_reason": reason,
    }
    return ParseResult(
        kind=MessageKind.MAINTENANCE,
        summary=format_maintenance_activity(fields),
        fields=fields,
        warnings=[],
    )
