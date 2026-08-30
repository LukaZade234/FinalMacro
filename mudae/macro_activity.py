"""Nesting-safe ownership of ``ChannelMonitor.macro_active``.

``macro_active`` tells :mod:`mudae.discord_reader` that every Mudae message
arriving in the channel is a reply to something *we* sent, so it must not be
attributed to a command the user typed by hand. It has more than one owner —
the roll cycle for the length of a session, and each minigame for the length
of a board — and those owners overlap: the GUI deliberately allows a manual
``$oh`` while the hourly loop sits in its refill wait.

The old save-and-restore idiom (``was = monitor.macro_active`` … ``monitor
.macro_active = was``) cannot express that. Two failures were observed
overnight:

* the roll cycle's ``finally`` cleared the flag while a manual minigame was
  still clicking, so the minigame's own replies were attributed to whatever
  the user last typed;
* the minigame restored a stale ``True`` after the cycle had already stopped,
  leaving the flag set with nothing running, which silences
  ``CommandContextTracker.observe`` for the rest of the connection.

A depth count fixes both: the flag is true while *any* owner holds it and
false only when the last one lets go. The count lives on the monitor object
via ``setattr``, so duck-typed fakes (``SimpleNamespace(macro_active=False)``,
used throughout the tests) work without implementing an interface.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_DEPTH_ATTR = "_macro_activity_depth"


def macro_activity_depth(monitor: Any) -> int:
    """How many owners currently hold ``macro_active``."""
    return int(getattr(monitor, _DEPTH_ATTR, 0))


def enter_macro_activity(monitor: Any) -> None:
    """Claim ``macro_active`` for one more owner."""
    depth = macro_activity_depth(monitor) + 1
    setattr(monitor, _DEPTH_ATTR, depth)
    monitor.macro_active = True


def exit_macro_activity(monitor: Any) -> None:
    """Release one owner's claim; the flag clears only when the last one goes."""
    depth = max(0, macro_activity_depth(monitor) - 1)
    setattr(monitor, _DEPTH_ATTR, depth)
    monitor.macro_active = depth > 0


@contextmanager
def macro_activity(monitor: Any) -> Iterator[None]:
    """Hold ``macro_active`` for the duration of a block."""
    enter_macro_activity(monitor)
    try:
        yield
    finally:
        exit_macro_activity(monitor)
