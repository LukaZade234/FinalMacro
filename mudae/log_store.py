"""Write-behind persistence for the append-mostly JSON event logs.

``kakera_log`` and ``sphere_log`` record an event per kakera/sphere click.
JSONL rows are appended in place (Syncthing-friendly). The pretty-JSON
minigame / chaos files still rewrite the whole array after a short debounce.
A final flush runs at interpreter exit (plus on disconnect via the bridge).
"""

from __future__ import annotations

import atexit
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_DEFAULT_FLUSH_DELAY_SEC = 5.0

FileSignature = tuple[int, int]


def file_signature(path: Path) -> FileSignature | None:
    """``(mtime_ns, size)`` for change detection, or ``None`` if unreadable."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


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
        on_written: Callable[[], None] | None = None,
    ) -> None:
        self._get_path = get_path
        self._get_events = get_events
        self._delay = delay_sec
        self._on_written = on_written
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._pending_path: Path | None = None
        atexit.register(self.flush)

    def is_dirty(self) -> bool:
        with self._lock:
            return self._pending_path is not None

    def mark_dirty(self) -> None:
        with self._lock:
            self._pending_path = self._get_path()
            if self._timer is None:
                self._timer = threading.Timer(self._delay, self.flush)
                self._timer.daemon = True
                self._timer.start()

    def cancel_pending(self) -> None:
        """Drop a scheduled write without touching disk."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_path = None

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
            return
        if self._on_written is not None:
            self._on_written()


class DebouncedJsonlLog:
    """Batches writes of one JSONL event file.

    New rows are **appended** in place so Syncthing (and anyone else watching
    the file) sees a small change instead of an 18MB rewrite every few seconds.
    Full rewrite is only used for import / replace / tests.
    """

    def __init__(
        self,
        get_path: Callable[[], Path],
        get_events: Callable[[], list[dict[str, Any]]],
        *,
        delay_sec: float = _DEFAULT_FLUSH_DELAY_SEC,
        on_written: Callable[[], None] | None = None,
    ) -> None:
        self._get_path = get_path
        self._get_events = get_events
        self._delay = delay_sec
        self._on_written = on_written
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._pending_path: Path | None = None
        self._synced_count = 0
        self._needs_rewrite = False
        atexit.register(self.flush)

    def is_dirty(self) -> bool:
        with self._lock:
            return self._pending_path is not None or self._needs_rewrite

    def synced_count(self) -> int:
        with self._lock:
            return self._synced_count

    def mark_dirty(self, *, rewrite: bool = False) -> None:
        with self._lock:
            if rewrite:
                self._needs_rewrite = True
            self._pending_path = self._get_path()
            if self._timer is None:
                self._timer = threading.Timer(self._delay, self.flush)
                self._timer.daemon = True
                self._timer.start()

    def cancel_pending(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_path = None
            self._needs_rewrite = False

    def reset_sync(self) -> None:
        self.cancel_pending()
        with self._lock:
            self._synced_count = 0
            self._needs_rewrite = False

    def set_synced_count(self, count: int) -> None:
        with self._lock:
            self._synced_count = max(0, int(count))
            self._needs_rewrite = False

    def flush(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            path = self._pending_path
            self._pending_path = None
            rewrite = self._needs_rewrite
            self._needs_rewrite = False
            start = self._synced_count
            if path is None:
                return
            events = list(self._get_events())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if rewrite or start > len(events) or not path.is_file():
                _write_jsonl(path, events)
            elif start < len(events):
                _append_jsonl(path, events[start:])
            with self._lock:
                self._synced_count = len(events)
        except OSError:
            return
        if self._on_written is not None:
            self._on_written()


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for entry in events:
            handle.write(json.dumps(entry, separators=(",", ":"), default=str))
            handle.write("\n")
    tmp.replace(path)


def _append_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for entry in events:
            handle.write(json.dumps(entry, separators=(",", ":"), default=str))
            handle.write("\n")
        handle.flush()
