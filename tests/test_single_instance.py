"""Tests for single-instance launcher behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from gui.single_instance import (
    SingleInstanceServer,
    instance_server_name,
    raise_window,
    try_notify_running_instance,
)


def test_instance_server_name_includes_uid():
    with patch("gui.single_instance.os.getuid", return_value=1001):
        assert instance_server_name() == "FinalMacro-single-instance-1001"


def test_try_notify_running_instance_returns_false_when_not_running():
    socket = MagicMock()
    socket.waitForConnected.return_value = False
    with patch("gui.single_instance.QLocalSocket", return_value=socket):
        assert try_notify_running_instance() is False


def test_try_notify_running_instance_sends_raise_when_connected():
    socket = MagicMock()
    socket.waitForConnected.return_value = True
    with patch("gui.single_instance.QLocalSocket", return_value=socket):
        assert try_notify_running_instance() is True
    socket.write.assert_called_once_with(b"raise")
    socket.flush.assert_called_once()
    socket.waitForBytesWritten.assert_called_once()
    socket.disconnectFromServer.assert_called_once()


def test_single_instance_server_invokes_callback_on_raise_message():
    from PySide6.QtCore import QByteArray

    server = SingleInstanceServer()
    calls: list[str] = []
    server._on_raise = lambda: calls.append("raised")

    socket = MagicMock()
    socket.bytesAvailable.return_value = 5
    socket.readAll.return_value = QByteArray(b"raise")

    server._handle_socket(socket)

    assert calls == ["raised"]
    socket.disconnectFromServer.assert_called_once()


def test_raise_window_unminimizes_and_focuses():
    calls: list[str] = []
    from PySide6.QtCore import Qt

    window = SimpleNamespace(
        show=lambda: calls.append("show"),
        windowState=lambda: Qt.WindowState.WindowMinimized,
        setWindowState=lambda state: calls.append(f"state:{state}"),
        raise_=lambda: calls.append("raise"),
        requestActivate=lambda: calls.append("activate"),
    )
    raise_window(window)
    assert calls[0] == "show"
    assert calls[1].startswith("state:")
    assert calls[2:] == ["raise", "activate"]
