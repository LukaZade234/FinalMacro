"""Capture wheel events at the native window for Remmina/VNC remote sessions."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QWheelEvent


class WindowWheelFilter(QObject):
    """Forward QWheelEvent to QML before controls consume them."""

    def __init__(self, bridge) -> None:
        super().__init__()
        self._bridge = bridge

    def eventFilter(self, watched, event) -> bool:  # noqa: ARG002
        if event.type() != QEvent.Type.Wheel:
            return False
        if not isinstance(event, QWheelEvent):
            return False
        pos = event.globalPosition()
        self._bridge.wheelScrollRequested.emit(
            pos.x(),
            pos.y(),
            float(event.angleDelta().y()),
            float(event.pixelDelta().y()),
        )
        event.accept()
        return True
