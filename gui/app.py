"""PySide6 + QML entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from gui.bridge import AppBridge


def main() -> None:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Mudae Reader")

    bridge = AppBridge()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("App", bridge)

    qml_path = Path(__file__).resolve().parent / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        sys.exit(1)

    app.aboutToQuit.connect(bridge.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
