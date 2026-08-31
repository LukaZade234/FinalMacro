"""Tests for Discord transport error classification and recovery."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mudae.discord_errors import is_fatal_runtime_error, is_transient_discord_error
from macro.roll_cycle import RollCycleEngine
from macro.config import CharacterClaimRules, MacroConfig
from macro.state import AccountState


class _FakeClient:
    """Stands in for ``discord.Client`` where only liveness and identity matter.

    ``is_closed`` matters because `ChannelMonitor.is_connected` consults it: the
    flag alone was only ever cleared by an explicit disconnect, so it reported
    True through a dead gateway.
    """

    def __init__(self, closed: bool = False, user=None):
        self._closed = closed
        self.user = user

    def is_closed(self) -> bool:
        return self._closed


def test_transient_discord_error_detects_503():
    exc = Exception(
        "503 Service Unavailable (error code: 0): upstream connect error or "
        "disconnect/reset before headers. reset reason: remote connection failure"
    )
    assert is_transient_discord_error(exc) is True
    assert is_fatal_runtime_error(exc) is False


def test_event_loop_closed_is_fatal_not_transient():
    exc = RuntimeError("Event loop is closed")
    assert is_fatal_runtime_error(exc) is True
    assert is_transient_discord_error(exc) is False


def test_rate_limits_and_timeouts_are_retryable():
    """A 429 is the *most* retryable thing there is, and used to be missed.

    `$ot` under Extra Chance presses 12-25 buttons a board where the old rule
    pressed 12-20, so it is the game that finds Discord's ceiling — and the
    classifier that decides whether to retry never mentioned rate limits.
    """
    for text in (
        "429 Too Many Requests (error code: 0)",
        "You are being rate limited.",
        "500 Internal Server Error",
        "TimeoutError: ",
        "Connection timed out (errno 110)",
    ):
        assert is_transient_discord_error(Exception(text)) is True, text


def test_a_missing_button_is_not_a_transport_problem():
    assert is_transient_discord_error(Exception("no button cmd s7")) is False


def test_send_command_retries_transient_errors():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    channel = SimpleNamespace(send=AsyncMock())
    calls = {"n": 0}

    async def flaky_send(_payload: str):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("503 Service Unavailable: upstream connect error")
        return SimpleNamespace(id=12345)

    channel.send = flaky_send
    monitor._get_text_channel = AsyncMock(return_value=channel)  # type: ignore[method-assign]
    monitor._connected = True
    monitor._client = _FakeClient()

    message_id = asyncio.run(monitor.send_command("wa", prefix="$"))
    assert calls["n"] == 3
    assert message_id == 12345


def test_send_command_reconnects_when_the_gateway_dropped():
    """Minigames send straight through here, with no engine wrapper to help.

    `RollCycleEngine._send_command_with_reconnect` covers rolls; `$oh` / `$oc` /
    `$oq` / `$ot` call `actions.send_command`, so without this a dropped gateway
    burned all three attempts and failed the command.
    """
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor._connected = False
    monitor._client = _FakeClient()
    calls = {"n": 0}

    async def flaky_send(_payload: str):
        calls["n"] += 1
        if calls["n"] < 2:
            raise Exception("Client is not connected")
        return SimpleNamespace(id=777)

    channel = SimpleNamespace(send=flaky_send)
    monitor._get_text_channel = AsyncMock(return_value=channel)  # type: ignore[method-assign]
    monitor.force_reconnect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.send_command("ot", prefix="$") == 777

    asyncio.run(run())
    monitor.force_reconnect.assert_awaited_once()


def test_send_command_does_not_reconnect_while_still_connected():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor._connected = True
    monitor._client = _FakeClient()
    calls = {"n": 0}

    async def flaky_send(_payload: str):
        calls["n"] += 1
        if calls["n"] < 2:
            raise Exception("429 Too Many Requests")
        return SimpleNamespace(id=778)

    monitor._get_text_channel = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(send=flaky_send)
    )
    monitor.force_reconnect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.send_command("ot", prefix="$") == 778

    asyncio.run(run())
    monitor.force_reconnect.assert_not_called()


def test_is_connected_reports_a_closed_client_as_disconnected():
    """The flag alone lied: set by `on_ready`, cleared only by `disconnect()`.

    A gateway that died on its own therefore left `is_connected` True forever,
    which made every `if not self.is_connected: reconnect` guard unreachable —
    and let an `$ot` board spend five minutes fetching every acknowledgement
    over HTTP because nothing noticed the socket was dead.
    """
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    assert monitor.is_connected is False  # no client yet

    monitor._connected = True
    monitor._client = _FakeClient(closed=False)
    assert monitor.is_connected is True

    monitor._client = _FakeClient(closed=True)
    assert monitor.is_connected is False


def test_ensure_connected_waits_for_discord_pys_own_resume():
    """A dropped socket is usually resumed by the library within moments.

    Forcing a full reconnect there would be far more disruptive than waiting,
    so escalation only happens if the client has not come back by itself.
    """
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor._connected = False
    monitor._client = _FakeClient()
    monitor.force_reconnect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def resume_after_one_poll(_delay: float) -> None:
        monitor._connected = True

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=resume_after_one_poll):
            assert await monitor.ensure_connected() is True

    asyncio.run(run())
    monitor.force_reconnect.assert_not_called()


def test_ensure_connected_escalates_when_the_resume_never_lands():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor._connected = False
    monitor._client = _FakeClient()
    monitor.force_reconnect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.ensure_connected() is True

    asyncio.run(run())
    monitor.force_reconnect.assert_awaited_once()


def test_seconds_since_last_event_tracks_gateway_silence():
    """A zombie socket looks exactly like a quiet channel from outside."""
    import time as _time

    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    assert monitor.seconds_since_last_event() == 0.0  # nothing heard yet
    monitor._last_event_at = _time.monotonic() - 42.0
    assert monitor.seconds_since_last_event() >= 42.0


def test_recover_transient_connection_reconnects():
    actions = SimpleNamespace(drain_queue=lambda: None)
    monitor = SimpleNamespace(
        force_reconnect=AsyncMock(return_value=True),
        is_connected=True,
        macro_active=False,
    )
    engine = RollCycleEngine(
        actions,  # type: ignore[arg-type]
        MacroConfig(character_claim=CharacterClaimRules(enabled=False)),
        AccountState(),
        monitor,
    )

    async def run() -> None:
        recovered = await engine._recover_transient_connection(
            Exception("503 Service Unavailable"),
            label="$us mode",
            recoveries=0,
        )
        assert recovered == 1
        monitor.force_reconnect.assert_awaited_once()

    asyncio.run(run())


def test_recover_transient_gives_up_after_max():
    actions = SimpleNamespace(drain_queue=lambda: None)
    monitor = SimpleNamespace(force_reconnect=AsyncMock(return_value=True))
    engine = RollCycleEngine(
        actions,  # type: ignore[arg-type]
        MacroConfig(character_claim=CharacterClaimRules(enabled=False)),
        AccountState(),
        monitor,
    )

    async def run() -> None:
        recovered = await engine._recover_transient_connection(
            Exception("503 Service Unavailable"),
            label="$us mode",
            recoveries=3,
        )
        assert recovered is None
        monitor.force_reconnect.assert_not_called()

    asyncio.run(run())


def test_send_command_with_reconnect_retries_after_transient_error():
    calls: list[str] = []

    class _FlakyActions:
        def drain_queue(self) -> None:
            pass

        async def send_command(self, command: str, *, prefix: str | None = None) -> int:
            calls.append(command)
            if len(calls) == 1:
                raise Exception("503 Service Unavailable")
            return 42

    monitor = SimpleNamespace(
        force_reconnect=AsyncMock(return_value=True),
        is_connected=True,
        macro_active=False,
    )
    engine = RollCycleEngine(
        _FlakyActions(),  # type: ignore[arg-type]
        MacroConfig(character_claim=CharacterClaimRules(enabled=False)),
        AccountState(),
        monitor,
    )

    async def run() -> None:
        with patch("macro.roll_cycle.asyncio.sleep", new=AsyncMock()):
            message_id = await engine._send_command_with_reconnect(
                "wa",
                label="Roll 1",
            )
        assert message_id == 42
        assert calls == ["wa", "wa"]
        monitor.force_reconnect.assert_awaited_once()

    asyncio.run(run())


class _FakeButton:
    """A component button whose ``click`` can be made to fail."""

    def __init__(self, custom_id: str, failures: int = 0, error: str = "429 Too Many Requests"):
        self.custom_id = custom_id
        self.message = None
        self.clicks = 0
        self._failures = failures
        self._error = error

    async def click(self) -> None:
        self.clicks += 1
        if self.clicks <= self._failures:
            raise Exception(self._error)


def _monitor_with_button(button, *, connected: bool = True):
    """A ChannelMonitor whose cached message carries ``button``."""
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor._connected = connected
    monitor._client = _FakeClient()
    monitor._message_for_click = AsyncMock(return_value=object())  # type: ignore[method-assign]
    monitor._find_button = lambda _message, _custom_id: button  # type: ignore[assignment]
    return monitor


def test_click_button_retries_a_rate_limit_instead_of_giving_up():
    """The 2026-08-30 failure: one refused click ended a live board.

    Six certain ships — 220 free SP — were still on the grid, and the log said
    only "click failed — stopping" because the exception was swallowed.
    """
    button = _FakeButton("cmd s7", failures=2)
    monitor = _monitor_with_button(button)
    statuses: list[str] = []
    monitor.on_status = statuses.append

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.click_button(999, "cmd s7") is True

    asyncio.run(run())
    assert button.clicks == 3
    assert any("retry 1/2" in line for line in statuses)


def test_click_button_reconnects_when_the_gateway_dropped():
    button = _FakeButton("cmd s7", failures=1, error="Client is not connected")
    monitor = _monitor_with_button(button, connected=False)
    monitor.force_reconnect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.click_button(999, "cmd s7") is True

    asyncio.run(run())
    monitor.force_reconnect.assert_awaited_once()


def test_click_button_gives_up_loudly_rather_than_silently():
    button = _FakeButton("cmd s7", failures=99)
    monitor = _monitor_with_button(button)
    statuses: list[str] = []
    monitor.on_status = statuses.append

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.click_button(999, "cmd s7") is False

    asyncio.run(run())
    assert button.clicks == 3
    # The whole point: the reason reaches the log instead of being swallowed.
    assert any("429" in line for line in statuses), statuses


def test_click_button_does_not_retry_a_permanent_error():
    button = _FakeButton("cmd s7", failures=99, error="Unknown interaction")
    monitor = _monitor_with_button(button)

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.click_button(999, "cmd s7") is False

    asyncio.run(run())
    assert button.clicks == 1, "a non-transient error must not be retried"


def test_click_button_refetches_when_the_button_is_not_on_the_cached_copy():
    """A stale cached message is the likeliest reason a button 'vanishes'."""
    from mudae.discord_reader import ChannelMonitor

    button = _FakeButton("cmd s7")
    monitor = ChannelMonitor("token", 123)
    monitor._connected = True
    monitor._client = _FakeClient()
    seen: list[bool] = []

    async def _message(_id: int, *, refresh: bool):
        seen.append(refresh)
        return object()

    monitor._message_for_click = _message  # type: ignore[method-assign]
    # Missing on the cached copy, present once refetched.
    monitor._find_button = lambda _m, _c: (button if len(seen) > 1 else None)  # type: ignore[assignment]

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.click_button(999, "cmd s7") is True

    asyncio.run(run())
    assert seen == [False, True], "second attempt must refetch the message"


class _FakeReactMessage:
    """A message whose ``add_reaction`` can be made to fail."""

    def __init__(self, failures: int = 0, error: str = "429 Too Many Requests"):
        self.reactions: list[str] = []
        self.attempts = 0
        self._failures = failures
        self._error = error

    async def add_reaction(self, emoji: str) -> None:
        self.attempts += 1
        if self.attempts <= self._failures:
            raise Exception(self._error)
        self.reactions.append(emoji)


def _monitor_with_message(message, *, connected: bool = True):
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor._connected = connected
    monitor._client = _FakeClient()
    monitor._message_for_click = AsyncMock(return_value=message)  # type: ignore[method-assign]
    return monitor


def test_add_reaction_retries_a_rate_limit_like_a_click():
    """A claim react is a claim: losing one to a 429 loses the character."""
    message = _FakeReactMessage(failures=2)
    monitor = _monitor_with_message(message)
    statuses: list[str] = []
    monitor.on_status = statuses.append

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.add_reaction(999, "\u2705") is True

    asyncio.run(run())
    assert message.attempts == 3
    assert message.reactions == ["\u2705"]
    assert any("retry 1/2" in line for line in statuses)


def test_add_reaction_does_not_retry_a_permanent_error():
    message = _FakeReactMessage(failures=99, error="Unknown emoji")
    monitor = _monitor_with_message(message)

    async def run() -> None:
        with patch("mudae.discord_reader.asyncio.sleep", new=AsyncMock()):
            assert await monitor.add_reaction(999, "\u2705") is False

    asyncio.run(run())
    assert message.attempts == 1


def test_add_reaction_reports_a_message_that_is_gone():
    monitor = _monitor_with_message(None)
    statuses: list[str] = []
    monitor.on_status = statuses.append

    async def run() -> None:
        assert await monitor.add_reaction(999, "\u2705") is False

    asyncio.run(run())
    assert any("is gone" in line for line in statuses), statuses


def test_discord_reader_imports_transient_error_helper():
    from mudae import discord_reader

    assert discord_reader.is_transient_discord_error is not None


def test_force_reconnect_restores_macro_active():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor.macro_active = True
    monitor.stop_background = AsyncMock()  # type: ignore[method-assign]
    monitor.start_background = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def run() -> None:
        ready = await monitor.force_reconnect()
        assert ready is True
        assert monitor.macro_active is True
        assert monitor._pending_macro_command is None

    asyncio.run(run())


def test_force_reconnect_leaves_macro_inactive_when_it_was():
    from mudae.discord_reader import ChannelMonitor

    monitor = ChannelMonitor("token", 123)
    monitor.macro_active = False
    monitor.stop_background = AsyncMock()  # type: ignore[method-assign]
    monitor.start_background = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def run() -> None:
        await monitor.force_reconnect()
        assert monitor.macro_active is False

    asyncio.run(run())
