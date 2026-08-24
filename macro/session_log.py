"""Persist full macro activity logs per run for later debugging."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from macro.activity_log import ActivityLogEntry

_SESSION_DIR = Path(__file__).resolve().parent.parent / "data" / "session_logs"
_FILENAME_BAD = re.compile(r"[^\w.\-]+", re.ASCII)


def session_log_dir() -> Path:
    return _SESSION_DIR


def _safe_slug(value: str, *, fallback: str = "unknown", max_len: int = 48) -> str:
    text = _FILENAME_BAD.sub("_", (value or "").strip())
    text = text.strip("._") or fallback
    return text[:max_len]


def _session_path(meta: dict[str, Any]) -> Path:
    started = meta.get("started_at") or dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    try:
        stamp = dt.datetime.fromisoformat(str(started).replace("Z", "+00:00"))
    except ValueError:
        stamp = dt.datetime.now(dt.UTC)
    stamp_local = stamp.astimezone()
    prefix = stamp_local.strftime("%Y-%m-%d_%H%M%S")
    mode = _safe_slug(str(meta.get("mode") or "session"), fallback="session")
    account = _safe_slug(str(meta.get("account") or "account"), fallback="account")
    return _SESSION_DIR / f"{prefix}_{mode}_{account}.json"


@dataclass
class SessionLogRecorder:
    """Collects timestamped activity lines and writes one JSON file per session."""

    _meta: dict[str, Any] = field(default_factory=dict)
    _lines: list[dict[str, Any]] = field(default_factory=list)
    _active: bool = False
    _path: Path | None = None
    _minigames: list[dict[str, Any]] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self._active

    @property
    def path(self) -> Path | None:
        return self._path

    def start(self, *, mode: str, **meta: Any) -> None:
        self._meta = {
            "mode": mode,
            **meta,
            "started_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }
        self._lines = []
        self._minigames = []
        self._active = True
        self._path = None

    def attach_minigame(self, session: dict[str, Any]) -> None:
        """Store a finished $oh / $oc / $oq board on this session file."""
        if not self._active:
            return
        self._minigames.append(dict(session))

    def write(self, entry: ActivityLogEntry, *, ts: str) -> None:
        if not self._active:
            return
        self._lines.append(
            {
                "ts": ts,
                "severity": entry.severity,
                "text": entry.text,
            }
        )

    def finish(self, reason: str) -> Path | None:
        if not self._active:
            return self._path
        self._active = False
        self._meta["ended_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        self._meta["reason"] = reason
        self._meta["line_count"] = len(self._lines)
        path = _session_path(self._meta)
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "meta": self._meta,
            "lines": self._lines,
        }
        if self._minigames:
            payload["minigames"] = self._minigames
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        text_path = path.with_suffix(".log")
        text_path.write_text(format_session_text(payload), encoding="utf-8")
        self._path = path
        return path


def format_session_text(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    lines: list[str] = [
        f"# mode={meta.get('mode')} account={meta.get('account')} "
        f"preset={meta.get('preset')} channel={meta.get('channel')}",
        f"# started={meta.get('started_at')} ended={meta.get('ended_at')} "
        f"reason={meta.get('reason')} lines={meta.get('line_count')}",
        "",
    ]
    for row in payload.get("lines") or []:
        if not isinstance(row, dict):
            continue
        ts = str(row.get("ts") or "")
        hhmmss = ts[11:19] if len(ts) >= 19 else ts
        text = str(row.get("text") or "")
        severity = str(row.get("severity") or "info")
        if severity == "debug":
            lines.append(f"[{hhmmss}] [debug] {text}")
        else:
            lines.append(f"[{hhmmss}] {text}")
    games = payload.get("minigames") or []
    if games:
        lines.append("")
        lines.append(f"# minigames={len(games)} (board + clicks also in the .json)")
        for index, game in enumerate(games, start=1):
            if not isinstance(game, dict):
                continue
            name = str(game.get("game") or "?")
            paid = game.get("clicks_paid")
            budget = game.get("clicks_budget")
            value = game.get("base_value")
            lines.append(
                f"#   {index}. ${name} · {paid}/{budget} paid · {value} base SP"
            )
    return "\n".join(lines).rstrip() + "\n"
