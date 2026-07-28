"""Helpers for classifying recoverable Discord transport failures."""

from __future__ import annotations

import asyncio

_TRANSIENT_MARKERS = (
    "503",
    "502",
    "504",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "upstream connect error",
    "connection reset",
    "connection termination",
    "connection closed",
    "cannot connect to host",
    "server disconnected",
    "websocket closed",
    "client is not connected",
    "not connected",
    "network is unreachable",
    "temporary failure",
    "errno 104",  # Connection reset by peer
    "errno 32",  # Broken pipe
)


def is_fatal_runtime_error(exc: BaseException) -> bool:
    """True for shutdown / closed-loop errors that must not be retried."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return "event loop is closed" in text or "loop is closed" in text


def is_transient_discord_error(exc: BaseException) -> bool:
    """True when a Discord HTTP/gateway blip is worth retrying / reconnecting."""
    if is_fatal_runtime_error(exc):
        return False
    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
        return False
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)
