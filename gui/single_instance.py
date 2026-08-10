"""Ensure only one GUI instance runs; raise the existing window on relaunch."""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket

_RAISE_MESSAGE = b"raise"
_CONNECT_MS = 500
_WRITE_MS = 1000


def instance_server_name(app_id: str = "FinalMacro") -> str:
    """Per-user socket name so different OS users do not block each other."""
    try:
        scope = str(os.getuid())
    except AttributeError:
        scope = os.environ.get("USERNAME") or os.environ.get("USER") or "default"
    return f"{app_id}-single-instance-{scope}"


def try_notify_running_instance(app_id: str = "FinalMacro") -> bool:
    """If another instance is listening, ask it to raise its window."""
    socket = QLocalSocket()
    socket.connectToServer(instance_server_name(app_id))
    if not socket.waitForConnected(_CONNECT_MS):
        return False
    socket.write(_RAISE_MESSAGE)
    socket.flush()
    socket.waitForBytesWritten(_WRITE_MS)
    socket.disconnectFromServer()
    return True


class SingleInstanceServer:
    """Listen for relaunch requests from secondary process starts."""

    def __init__(self, app_id: str = "FinalMacro") -> None:
        self._name = instance_server_name(app_id)
        self._server = QLocalServer()
        self._on_raise: Callable[[], None] | None = None

    def listen(self, on_raise: Callable[[], None]) -> bool:
        self._on_raise = on_raise
        QLocalServer.removeServer(self._name)
        if not self._server.listen(self._name):
            return False
        self._server.newConnection.connect(self._on_new_connection)
        return True

    def _on_new_connection(self) -> None:
        while (socket := self._server.nextPendingConnection()) is not None:
            socket.readyRead.connect(lambda s=socket: self._handle_socket(s))

    def _handle_socket(self, socket: QLocalSocket) -> None:
        if socket.bytesAvailable() <= 0:
            return
        payload = bytes(socket.readAll())
        if _RAISE_MESSAGE in payload and self._on_raise is not None:
            self._on_raise()
        socket.disconnectFromServer()


def raise_window(window: object) -> None:
    """Show, un-minimize, and focus the main application window."""
    if window is None:
        return
    show = getattr(window, "show", None)
    if callable(show):
        show()
    set_state = getattr(window, "setWindowState", None)
    window_state = getattr(window, "windowState", None)
    if callable(set_state) and callable(window_state):
        from PySide6.QtCore import Qt

        state = window_state()
        if state & Qt.WindowState.WindowMinimized:
            set_state(state & ~Qt.WindowState.WindowMinimized)
    raise_fn = getattr(window, "raise_", None)
    if callable(raise_fn):
        raise_fn()
    activate = getattr(window, "requestActivate", None)
    if callable(activate):
        activate()
