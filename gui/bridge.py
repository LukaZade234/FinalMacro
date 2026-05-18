"""Qt bridge between QML UI and Discord channel monitor."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from PySide6.QtCore import QObject, Property, Q_ARG, QMetaObject, Qt, Signal, Slot

from gui.settings import load_settings, save_settings
from mudae.discord_reader import ChannelMonitor


class AppBridge(QObject):
    entryReceived = Signal(dict)
    statusChanged = Signal(str)
    connectedChanged = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        saved = load_settings()
        self._token = saved.get("token", "")
        self._channel_id = saved.get("channel_id", "")
        self._status = "Idle"
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._monitor: ChannelMonitor | None = None
        self._stop_event: asyncio.Event | None = None

    @Property(str, constant=False, notify=statusChanged)
    def statusText(self) -> str:
        return self._status

    @Property(bool, constant=False, notify=connectedChanged)
    def connected(self) -> bool:
        return self._connected

    def _set_status(self, text: str) -> None:
        self._status = text
        self.statusChanged.emit(text)

    def _set_connected(self, value: bool) -> None:
        if self._connected != value:
            self._connected = value
            self.connectedChanged.emit(value)

    @Slot(str)
    def setToken(self, value: str) -> None:
        self._token = value

    @Slot(str)
    def setChannelId(self, value: str) -> None:
        self._channel_id = value.strip()

    @Slot(result=str)
    def getToken(self) -> str:
        return self._token

    @Slot(result=str)
    def getChannelId(self) -> str:
        return self._channel_id

    def _persist(self) -> None:
        save_settings(
            {
                "token": self._token,
                "channel_id": self._channel_id,
            }
        )

    def _parse_int(self, value: str, label: str) -> int:
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid {label}: must be a numeric Discord ID") from exc

    @Slot(str)
    def _deliver_entry_json(self, payload_json: str) -> None:
        self.entryReceived.emit(json.loads(payload_json))

    @Slot(str)
    def _deliver_status(self, text: str) -> None:
        self._set_status(text)

    @Slot(bool)
    def _deliver_connected(self, value: bool) -> None:
        self._set_connected(value)

    def _on_entry(self, payload: dict[str, Any]) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_entry_json",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, json.dumps(payload)),
        )

    def _on_status(self, text: str) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_status",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, text),
        )

    def _on_connected(self, value: bool) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_connected",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(bool, value),
        )

    def _reader_thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._stop_event = asyncio.Event()

        channel_id = self._parse_int(self._channel_id, "channel ID")

        self._monitor = ChannelMonitor(
            token=self._token,
            channel_id=channel_id,
            on_entry=self._on_entry,
            on_status=self._on_status,
        )

        async def runner() -> None:
            connect_task = asyncio.create_task(self._monitor.connect())
            ready = await self._monitor.wait_ready(timeout=30.0)
            if connect_task.done():
                exc = connect_task.exception()
                if exc is not None:
                    raise exc
            if ready:
                self._on_connected(True)
            else:
                self._on_status("Connection timed out")
            await self._stop_event.wait()
            await self._monitor.disconnect()
            connect_task.cancel()
            try:
                await connect_task
            except asyncio.CancelledError:
                pass
            self._on_connected(False)

        try:
            loop.run_until_complete(runner())
        except Exception as exc:
            self._on_status(f"Error: {exc}")
            self._on_connected(False)
        finally:
            loop.close()
            self._loop = None

    @Slot()
    def connect(self) -> None:
        if self._thread and self._thread.is_alive():
            self._set_status("Already connected or connecting")
            return
        if not self._token.strip():
            self._set_status("Token required")
            return
        if not self._channel_id.strip():
            self._set_status("Channel ID required")
            return

        self._persist()
        self._thread = threading.Thread(
            target=self._reader_thread_main,
            name="channel-monitor",
            daemon=True,
        )
        self._thread.start()

    @Slot()
    def disconnect(self) -> None:
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self._set_status("Disconnecting…")

    @Slot()
    def shutdown(self) -> None:
        self._persist()
        self.disconnect()
