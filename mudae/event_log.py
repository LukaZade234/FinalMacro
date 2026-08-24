"""Unified append-only event store for Statistics (kakera / spheres / keys / soulmates).

On first launch after this lands, existing pretty-JSON logs are **imported**
into ``data/events.jsonl``. Those JSON files are left on disk as a backup and
are never deleted or overwritten. If ``events.jsonl`` already exists, it is
the source of truth (re-import would duplicate rows).

Minigame boards and chaos capture stay in their own files.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from mudae.log_store import DebouncedJsonlLog

KINDS = ("kakera", "sphere", "key", "soulmate")

LEGACY_FILENAMES: dict[str, str] = {
    "kakera": "kakera_log.json",
    "sphere": "sphere_log.json",
    "key": "key_log.json",
    "soulmate": "soulmate_log.json",
}

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_JSONL_NAME = "events.jsonl"

_lock = threading.Lock()
_path = _DATA_DIR / _JSONL_NAME
_data_dir = _DATA_DIR
_all: list[dict[str, Any]] = []
_by_kind: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
_loaded = False
_imported_legacy = False

_writer = DebouncedJsonlLog(lambda: _path, lambda: list(_all))


def jsonl_path() -> Path:
    return _path


def data_dir() -> Path:
    return _data_dir


def events(kind: str) -> list[dict[str, Any]]:
    """Live list for one kind (same object the facade modules hold)."""
    ensure_loaded()
    return _by_kind[kind]


def all_events() -> list[dict[str, Any]]:
    ensure_loaded()
    return list(_all)


def imported_legacy() -> bool:
    """True when this process imported JSON arrays into JSONL on first load."""
    return _imported_legacy


def _notify_index_add(kind: str, entry: dict[str, Any]) -> None:
    from mudae import stats_index

    stats_index.add(kind, entry)


def _notify_index_rebuild() -> None:
    from mudae import stats_index

    stats_index.rebuild()


def _notify_index_rebuild_kind(kind: str) -> None:
    from mudae import stats_index

    stats_index.rebuild_kind(kind)


def ensure_loaded() -> None:
    global _loaded, _imported_legacy
    should_rebuild = False
    with _lock:
        if _loaded:
            return
        _loaded = True
        if "pytest" in sys.modules:
            # Collection/import must not touch the user's data/ folder.
            return
        if _path.is_file() and _path.stat().st_size > 0:
            _load_jsonl(_path)
            _imported_legacy = False
            should_rebuild = True
        else:
            imported = _import_legacy_files(_data_dir)
            _imported_legacy = imported > 0
            if imported:
                _writer.reset_sync()
                _writer.mark_dirty(rewrite=True)
                _writer.flush()
            should_rebuild = True
    if should_rebuild:
        _notify_index_rebuild()


def append(kind: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Stamp ``kind`` and append. ``entry`` is stored (mutated) and returned."""
    if kind not in _by_kind:
        raise ValueError(f"unknown event kind {kind!r}")
    ensure_loaded()
    entry["kind"] = kind
    with _lock:
        _by_kind[kind].append(entry)
        _all.append(entry)
    _writer.mark_dirty()
    _notify_index_add(kind, entry)
    return entry


def replace(kind: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace all rows of one kind (dedupe / test setup). Returns the live list."""
    if kind not in _by_kind:
        raise ValueError(f"unknown event kind {kind!r}")
    ensure_loaded()
    with _lock:
        _all[:] = [row for row in _all if row.get("kind") != kind]
        live = _by_kind[kind]
        live.clear()
        for item in entries:
            row = dict(item)
            row["kind"] = kind
            live.append(row)
            _all.append(row)
    _writer.mark_dirty(rewrite=True)
    _notify_index_rebuild_kind(kind)
    return live


def mark_dirty(rewrite: bool = False) -> None:
    ensure_loaded()
    _writer.mark_dirty(rewrite=rewrite)


def flush() -> None:
    _writer.flush()


def cancel_pending() -> None:
    _writer.cancel_pending()


def reset_for_tests(path: Path | None = None) -> None:
    """Empty the store and optionally point it at a temp JSONL (tests only)."""
    global _loaded, _imported_legacy, _path, _data_dir
    _writer.cancel_pending()
    with _lock:
        _all.clear()
        for kind in KINDS:
            _by_kind[kind].clear()
        _loaded = True
        _imported_legacy = False
        if path is not None:
            _path = Path(path)
            _data_dir = _path.parent
        _writer.reset_sync()
    _notify_index_rebuild()


def load_from_data_dir(directory: Path) -> None:
    """Load JSONL or import legacy JSON arrays from ``directory`` (tests)."""
    global _loaded, _imported_legacy, _path, _data_dir
    _writer.cancel_pending()
    directory = Path(directory)
    with _lock:
        _data_dir = directory
        _path = directory / _JSONL_NAME
        _all.clear()
        for kind in KINDS:
            _by_kind[kind].clear()
        _loaded = True
        jsonl = _path
        if jsonl.is_file() and jsonl.stat().st_size > 0:
            _load_jsonl(jsonl)
            _imported_legacy = False
        else:
            imported = _import_legacy_files(directory)
            _imported_legacy = imported > 0
            if imported:
                _writer.reset_sync()
                _writer.mark_dirty(rewrite=True)
                _writer.flush()
    _notify_index_rebuild()


def _load_jsonl(path: Path) -> None:
    _all.clear()
    for kind in KINDS:
        _by_kind[kind].clear()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "")
        if kind not in _by_kind:
            continue
        _by_kind[kind].append(row)
        _all.append(row)
    _writer.reset_sync()
    _writer.set_synced_count(len(_all))


def _import_legacy_files(directory: Path) -> int:
    """Copy JSON array logs into memory. Does not delete or rewrite those files."""
    imported = 0
    _all.clear()
    for kind in KINDS:
        live = _by_kind[kind]
        live.clear()
        path = directory / LEGACY_FILENAMES[kind]
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["kind"] = kind
            live.append(row)
            _all.append(row)
            imported += 1
    return imported
