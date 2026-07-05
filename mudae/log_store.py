"""Write-behind persistence for the append-mostly JSON event logs.

``kakera_log`` and ``sphere_log`` record an event per kakera/sphere click, and
each record used to rewrite the whole JSON file synchronously — I/O that grows
with the log and runs in the middle of mass rolling. This writer batches those
rewrites: bursts of events collapse into one file write shortly after the burst,
and a final flush runs at interpreter exit (plus on disconnect via the bridge).
"""

from __future__ import annotations

import atexit
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_DEFAULT_FLUSH_DELAY_SEC = 5.0


class DebouncedJsonLog:
    """Batches rewrites of one JSON list file.

    ``mark_dirty()`` snapshots the target path and schedules a write after
    ``delay_sec``; repeated calls within that window coalesce into one write.
    The path is captured at mark time so a stale timer can never write to a
    path configured later (relevant for tests that redirect the log path).
    """

    def __init__(
        self,
        get_path: Callable[[], Path],
        get_events: Callable[[], list[dict[str, Any]]],
        *,
        delay_sec: float = _DEFAULT_FLUSH_DELAY_SEC,
    ) -> None:
        self._get_path = get_path
        self._get_events = get_events
        self._delay = delay_sec
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._pending_path: Path | None = None
        atexit.register(self.flush)

    def mark_dirty(self) -> None:
        with self._lock:
            self._pending_path = self._get_path()
            if self._timer is None:
                self._timer = threading.Timer(self._delay, self.flush)
                self._timer.daemon = True
                self._timer.start()

    def flush(self) -> None:
        """Write pending events now (no-op when nothing is dirty)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            path = self._pending_path
            self._pending_path = None
            if path is None:
                return
            events = list(self._get_events())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(events, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            # Target may be gone (e.g. temp dir from a finished test run);
            # the next mark_dirty will retry with the current path.
            pass
