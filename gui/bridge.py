"""Qt bridge between QML UI and Discord channel monitor."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject,
    Property,
    Q_ARG,
    QFileSystemWatcher,
    QMetaObject,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont, QGuiApplication

from gui.accounts import AccountStore
from gui.mudae_settings_presets import MudaeSettingsPresetStore
from gui.presets import PresetStore
from gui.run_summary import build_run_summary
from gui.run_target import resolve_run_target
from gui.server_profiles import ServerProfileStore
from gui.settings import SETTINGS_PATH, load_settings, save_app_settings
from gui.targets import ResolvedRunTarget, TargetStore
from gui.update_check import MAX_COMMIT_SUMMARY, UpdateStatus, check_for_updates, pull_update
from macro.actions import DiscordActions
from macro.activity_log import ActivityLog, ActivitySeverity, activity_log_text
from macro.config import MacroConfig
from macro.roll_cycle import RollCycleEngine
from macro.settings_apply import SettingsApplyRunner
from macro.us_stop import (
    UsModeStopOptions,
    overlay_legacy_us_options,
    us_stop_from_config,
)
from macro.sphere_game import OhSphereGame
from macro.oc_game import OcSphereGame
from macro.oq_game import OqSphereGame
from macro.ot_game import OtSphereGame
from macro.minigames import PlayAllMinigames
from macro.state import AccountState, MacroPhase
from mudae.discord_reader import ChannelMonitor
from mudae.parsers.bonus_catalog import fields_to_bonus_display_dict
from mudae.parsers.settings import SETTINGS_FIELD_KEYS
from mudae.parsers.shop_catalog import fields_to_shop_display_dict
from mudae.parsers.settings_normalize import normalize_settings_fields
from mudae.settings_commands import (
    ESSENTIAL_APPLY_FIELDS,
    FIELD_GROUPS,
    compliance_status,
    diff_settings,
)
from mudae.settings_catalog import (
    CATALOG_BY_FIELD,
    catalog_to_client_dict,
    coerce_editor_value,
    fields_to_display_dict,
    merge_preset_fields,
)
from mudae.list_formatter import extract_character_names, format_mudae_character_list
from mudae.live_feed import format_live_feed
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000
_UPDATE_STARTUP_DELAY_MS = 4000
_SETTINGS_RELOAD_DEBOUNCE_MS = 400
_STATS_RELOAD_DEBOUNCE_MS = 800
_RUN_SUMMARY_THROTTLE_MS = 1000

_DEFAULT_UI_LAYOUT = "classic"
_DEFAULT_UI_PALETTE = "tokyonight"
_UI_LAYOUTS = frozenset({"classic", "haul", "console", "boxed"})
_UI_PALETTES = frozenset({
    "kakera", "tokyonight", "ember", "phosphor", "ice", "bone", "mono",
})
# Each design was drawn against one palette; picking a design swaps the colours
# to match unless the user has already chosen a palette of their own.
_LAYOUT_PALETTE = {
    "classic": "tokyonight",
    "haul": "kakera",
    "console": "kakera",
    "boxed": "kakera",
}

_PROFILE_META_KEYS = frozenset({
    "command",
    "response_label",
    "part",
    "parts",
    "parser_command",
    "detected_command",
    "command_alias",
    "line_count",
    "cached_settings",
})


def profile_kind_from_parse(parsed: ParseResult) -> str | None:
    """Map parse results to server-profile updates (includes fetch command replies)."""
    if parsed.kind == MessageKind.SETTINGS:
        return "settings"
    if parsed.kind == MessageKind.BONUS:
        return "bonus"
    if parsed.kind == MessageKind.SHOP:
        return "shop"
    if parsed.kind != MessageKind.COMMAND_RESPONSE:
        return None
    parser_cmd = str(parsed.fields.get("parser_command") or "").lower().lstrip("$")
    if parser_cmd in {"settings", "bonus", "shop"}:
        return parser_cmd
    label = str(parsed.fields.get("response_label") or "").lower()
    if "settings" in label:
        return "settings"
    if "bonus" in label:
        return "bonus"
    if "shop" in label:
        return "shop"
    if parsed.fields.get("setrolls") is not None and parsed.fields.get("gamemode") is not None:
        return "settings"
    return None


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``patch`` into a copy of ``base``.

    Lists and scalars from ``patch`` replace those in ``base``. ``None`` in
    ``patch`` clears the key.
    """
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def profile_fields_from_parse(parsed: ParseResult, kind: str) -> dict[str, Any]:
    if kind == "settings":
        allowed = set(SETTINGS_FIELD_KEYS)
        return {key: value for key, value in parsed.fields.items() if key in allowed}
    return {
        key: value
        for key, value in parsed.fields.items()
        if key not in _PROFILE_META_KEYS
    }


class AppBridge(QObject):
    entryReceived = Signal(dict)
    statusChanged = Signal(str)
    connectedChanged = Signal(bool)
    connectingChanged = Signal()
    disconnectingChanged = Signal()
    notificationStandbyChanged = Signal()
    sessionActiveChanged = Signal()
    runActionPendingChanged = Signal()
    usModeOptionsChanged = Signal()
    minimizeToTrayChanged = Signal()
    appearanceChanged = Signal()
    runSummaryChanged = Signal()
    updateStatusChanged = Signal()
    updateCheckingChanged = Signal()
    updatePullingChanged = Signal()
    autoUpdateCheckChanged = Signal()
    macroPhaseChanged = Signal(str)
    macroStateChanged = Signal()
    macroLogChanged = Signal()
    serversChanged = Signal()
    configChanged = Signal()
    soulmatesChanged = Signal()
    kakeraChanged = Signal()
    spheresChanged = Signal()
    minigamesChanged = Signal()
    keysChanged = Signal()
    mudaeSettingsPresetsChanged = Signal()
    settingsApplyChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        app = QGuiApplication.instance()
        self._system_font = QFont(app.font()) if app is not None else QFont()
        self._ui_system_fonts = False
        saved = load_settings()
        self._profiles = ServerProfileStore()
        self._accounts = AccountStore()
        self._presets = PresetStore()
        self._mudae_settings_presets = MudaeSettingsPresetStore()
        self._targets = TargetStore()
        self._apply_saved_settings(saved, initial=True)
        self._macro_state = AccountState()
        self._status = "Disconnected"
        self._connected = False
        self._connecting = False
        self._disconnecting = False
        self._run_action_pending = ""
        self._tu_pending_active = False
        self._action_timer = QTimer(self)
        self._action_timer.setSingleShot(True)
        self._action_timer.timeout.connect(self._on_run_action_timeout)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._monitor: ChannelMonitor | None = None
        self._actions: DiscordActions | None = None
        self._engine: RollCycleEngine | None = None
        self._stop_event: asyncio.Event | None = None
        self._parse_lab_entries: list[dict[str, Any]] = []
        self._oh_running = False
        self._oc_running = False
        self._oq_running = False
        self._ot_running = False
        self._minigames_running = False
        self._minigame_availability: dict[str, int] = {}
        self._settings_apply_running = False
        self._settings_apply_log: list[str] = []
        self._settings_apply_groups: frozenset[str] | None = None
        self._notification_standby = False
        self._servers_emit_pending = False
        self._config_emit_pending = False
        self._run_guild_id: int | None = None
        self._run_guild_name: str | None = None
        self._run_channel_name: str | None = None
        self._run_account_name: str = ""
        self._run_preset_id: str = ""
        self._run_account_id: str = ""
        self._run_channel_profile_id: str = ""
        self._run_token: str = ""
        self._account_daily_lock: asyncio.Lock | None = None
        self._account_daily_runtime: Any = None
        self._us_schedule_session_active = False
        self._us_schedule_skip_hourly_resume = False
        self._session_started_at: datetime | None = None
        # Rebuilding the run summary walks the whole earning log, and the macro
        # notifies on every activity line, so the change signal is coalesced.
        self._run_summary_timer = QTimer(self)
        self._run_summary_timer.setSingleShot(True)
        self._run_summary_timer.setInterval(_RUN_SUMMARY_THROTTLE_MS)
        self._run_summary_timer.timeout.connect(self.runSummaryChanged.emit)
        self._settings_file_mtime: float | None = None
        self._record_settings_file_mtime()
        self._settings_reload_timer = QTimer(self)
        self._settings_reload_timer.setSingleShot(True)
        self._settings_reload_timer.setInterval(_SETTINGS_RELOAD_DEBOUNCE_MS)
        self._settings_reload_timer.timeout.connect(self._reload_settings_from_disk)
        self._settings_watcher = QFileSystemWatcher(self)
        self._settings_watcher.fileChanged.connect(self._on_settings_file_changed)
        self._settings_watcher.directoryChanged.connect(self._on_settings_directory_changed)
        self._ensure_settings_watch()
        self._stats_reload_timer = QTimer(self)
        self._stats_reload_timer.setSingleShot(True)
        self._stats_reload_timer.setInterval(_STATS_RELOAD_DEBOUNCE_MS)
        self._stats_reload_timer.timeout.connect(self._reload_stats_from_disk)
        self._stats_watcher = QFileSystemWatcher(self)
        self._stats_watcher.fileChanged.connect(self._on_stats_file_changed)
        self._stats_watcher.directoryChanged.connect(self._on_stats_directory_changed)
        self._ensure_stats_watch()
        self._tray_available = False
        self._tray: Any = None

        self._update_status: UpdateStatus | None = None
        self._update_checking = False
        self._update_pulling = False
        self._update_pull_message = ""
        self._update_pull_ok = False
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self.checkForUpdates)
        if self._update_auto_check:
            self._update_timer.start(_UPDATE_CHECK_INTERVAL_MS)
            QTimer.singleShot(_UPDATE_STARTUP_DELAY_MS, self.checkForUpdates)

    @Property(str, constant=False, notify=statusChanged)
    def statusText(self) -> str:
        return self._status

    @Property(bool, constant=False, notify=connectedChanged)
    def connected(self) -> bool:
        return self._connected

    @Property(bool, constant=False, notify=connectingChanged)
    def connecting(self) -> bool:
        return self._connecting

    @Property(bool, constant=False, notify=disconnectingChanged)
    def disconnecting(self) -> bool:
        return self._disconnecting

    @Property(bool, constant=False, notify=notificationStandbyChanged)
    def notificationStandby(self) -> bool:
        return self._notification_standby

    @Property(bool, constant=False, notify=sessionActiveChanged)
    def sessionActive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @Property(bool, constant=False, notify=macroStateChanged)
    def macroEngineRunning(self) -> bool:
        return bool(self._engine and self._engine.is_running)

    @Property(str, constant=False, notify=runActionPendingChanged)
    def runActionPending(self) -> str:
        return self._run_action_pending

    @Property(str, constant=False, notify=macroPhaseChanged)
    def macroPhase(self) -> str:
        return self._macro_state.phase.value

    @Property(str, constant=False, notify=macroStateChanged)
    def macroStateJson(self) -> str:
        return json.dumps(self._macro_state.to_dict())

    @Property(str, constant=False, notify=macroLogChanged)
    def macroActivityLog(self) -> str:
        return activity_log_text(self._macro_state.activity_log)

    @Property(str, constant=False, notify=macroLogChanged)
    def macroActivityLogJson(self) -> str:
        return json.dumps([entry.to_dict() for entry in self._macro_state.activity_log])

    @Property(int, constant=False, notify=macroStateChanged)
    def macroRollsLeft(self) -> int:
        return self._macro_state.rolls_left if self._macro_state.rolls_left is not None else -1

    @Property(int, constant=False, notify=macroStateChanged)
    def macroRollsMax(self) -> int:
        """Hourly roll pool from ``$bonus`` net, else ``$setrolls``, or -1.

        ``$tu`` remaining is often far above ``$setrolls`` (the server base)
        because ``$bonus`` adds extra rolls. The gauge scale has to match that.
        """
        from macro.sheet_caps import rolls_max_from_sheets

        channel = None
        if self._run_channel_profile_id:
            found = self._profiles.find_channel_by_profile_id(
                self._run_channel_profile_id
            )
            if found:
                channel = found[1]
        if channel is None:
            channel = self._profiles.active_channel()
        value = rolls_max_from_sheets(
            getattr(channel, "bonus", None) if channel else None,
            getattr(channel, "settings", None) if channel else None,
        )
        return int(value) if value else -1

    @Property(str, constant=False, notify=macroStateChanged)
    def macroClaimStatus(self) -> str:
        return self._macro_state.claim_label()

    @Property(int, constant=False, notify=macroStateChanged)
    def macroPowerPercent(self) -> int:
        from macro.live_clock import live_power_percent
        from macro.reaction_power import display_reaction_power

        return display_reaction_power(live_power_percent(self._macro_state))

    @Property(int, constant=False, notify=macroStateChanged)
    def macroDkStock(self) -> int:
        stock = self._macro_state.dk_stock
        return int(stock) if stock is not None else -1

    @Property(bool, constant=False, notify=usModeOptionsChanged)
    def usKeepDraining(self) -> bool:
        return bool(self._macro_config.us_keep_draining)

    @Property(bool, constant=False, notify=usModeOptionsChanged)
    def usStopOnPowerExhausted(self) -> bool:
        return bool(self._macro_config.us_stop_on_power_exhausted)

    @Property(bool, constant=False, notify=usModeOptionsChanged)
    def usStopAfterRollsEnabled(self) -> bool:
        return bool(self._macro_config.us_stop_after_rolls_enabled)

    @Property(int, constant=False, notify=usModeOptionsChanged)
    def usStopAfterRolls(self) -> int:
        return max(1, int(self._macro_config.us_stop_after_rolls))

    @Property(bool, constant=False, notify=minimizeToTrayChanged)
    def minimizeToTray(self) -> bool:
        return self._minimize_to_tray

    @Property(bool, constant=False, notify=minimizeToTrayChanged)
    def trayAvailable(self) -> bool:
        return self._tray_available

    @Property(bool, constant=False, notify=updateCheckingChanged)
    def updateChecking(self) -> bool:
        return self._update_checking

    @Property(bool, constant=False, notify=updatePullingChanged)
    def updatePulling(self) -> bool:
        return self._update_pulling

    @Property(bool, constant=False, notify=autoUpdateCheckChanged)
    def autoUpdateCheckEnabled(self) -> bool:
        return self._update_auto_check

    @Property(bool, constant=False, notify=updateStatusChanged)
    def updatePending(self) -> bool:
        """True when the remote is ahead, regardless of banner dismiss state."""
        status = self._update_status
        return bool(status and status.available)

    @Property(bool, constant=False, notify=updateStatusChanged)
    def updateAvailable(self) -> bool:
        """True when an update exists and the compact notice has not been dismissed."""
        status = self._update_status
        if not status or not status.available:
            return False
        return status.remote_sha != self._update_dismissed_sha

    @Property(bool, constant=False, notify=updateStatusChanged)
    def updateCanPull(self) -> bool:
        return bool(self._update_status and self._update_status.can_pull)

    @Property(int, constant=False, notify=updateStatusChanged)
    def updateBehindCount(self) -> int:
        return self._update_status.behind if self._update_status else 0

    @Property(str, constant=False, notify=updateStatusChanged)
    def updateCommitsJson(self) -> str:
        commits = self._update_status.commits if self._update_status else []
        return json.dumps(commits[:MAX_COMMIT_SUMMARY])

    @Property(str, constant=False, notify=updateStatusChanged)
    def updateBranch(self) -> str:
        return (self._update_status.branch or "") if self._update_status else ""

    @Property(str, constant=False, notify=updateStatusChanged)
    def updateError(self) -> str:
        return (self._update_status.error or "") if self._update_status else ""

    @Property(float, constant=False, notify=updateStatusChanged)
    def updateLastCheckedEpoch(self) -> float:
        return self._update_status.checked_at if self._update_status else 0.0

    @Property(str, constant=False, notify=updateStatusChanged)
    def updatePullMessage(self) -> str:
        return self._update_pull_message

    @Property(bool, constant=False, notify=updateStatusChanged)
    def updatePullOk(self) -> bool:
        return self._update_pull_ok

    @Property(str, constant=False, notify=serversChanged)
    def serversJson(self) -> str:
        return json.dumps(self._profiles.to_client_dict())

    @Property(str, constant=False, notify=serversChanged)
    def activeChannelLabel(self) -> str:
        return self._profiles.active_label()

    @Property(str, constant=False, notify=configChanged)
    def accountsJson(self) -> str:
        return json.dumps(self._accounts.to_client_dict())

    @Property(str, constant=False, notify=configChanged)
    def presetsJson(self) -> str:
        return json.dumps(self._presets.to_client_dict())

    @Property(str, constant=False, notify=mudaeSettingsPresetsChanged)
    def mudaeSettingsPresetsJson(self) -> str:
        return json.dumps(self._mudae_settings_presets.to_client_dict())

    @Property(str, constant=False, notify=settingsApplyChanged)
    def settingsApplyLogText(self) -> str:
        return "\n".join(self._settings_apply_log)

    @Property(bool, constant=False, notify=settingsApplyChanged)
    def settingsApplyRunning(self) -> bool:
        return self._settings_apply_running

    @Property(str, constant=True)
    def mudaeSettingsCatalogJson(self) -> str:
        return json.dumps(catalog_to_client_dict())

    @Property(str, constant=False, notify=settingsApplyChanged)
    def mudaeSettingsFieldGroupsJson(self) -> str:
        groups: dict[str, list[str]] = {}
        for field, group in FIELD_GROUPS.items():
            if field in ESSENTIAL_APPLY_FIELDS:
                groups.setdefault(group, []).append(field)
        return json.dumps(groups)

    @Property(str, constant=False, notify=configChanged)
    def runTargetLabel(self) -> str:
        resolved = resolve_run_target(
            self._accounts, self._profiles, self._presets, self._targets
        )
        return resolved.label if resolved else ""

    @Property(str, constant=False, notify=soulmatesChanged)
    def soulmatesJson(self) -> str:
        from mudae.soulmate_log import client_payload

        return json.dumps(client_payload(self._accounts))

    @Property(str, constant=False, notify=kakeraChanged)
    def kakeraJson(self) -> str:
        from mudae.kakera_log import client_payload

        return json.dumps(client_payload(self._accounts))

    @Property(str, constant=False, notify=spheresChanged)
    def spheresJson(self) -> str:
        from mudae.sphere_log import client_payload

        return json.dumps(client_payload(self._accounts))

    @Property(str, constant=False, notify=minigamesChanged)
    def minigamesJson(self) -> str:
        from mudae.minigame_log import client_payload

        return json.dumps(client_payload(self._accounts))

    @Property(str, constant=True)
    def minigameLogPath(self) -> str:
        from mudae.minigame_log import log_path

        return str(log_path())

    @Property(str, constant=False, notify=keysChanged)
    def keysJson(self) -> str:
        from mudae.key_log import client_payload

        return json.dumps(client_payload(self._accounts))

    @Slot(str, str, str, str, str, int, int, result=str)
    def statsQuery(
        self,
        kind: str,
        account: str,
        server: str,
        method: str,
        extra: str,
        offset: int,
        limit: int,
    ) -> str:
        """Filtered Statistics summary + one page of events (newest first)."""
        from mudae.stats_index import PAGE_SIZE, payload

        return json.dumps(
            payload(
                str(kind or ""),
                self._accounts,
                account=account,
                server=server,
                method=method,
                type_id=extra,
                offset=int(offset or 0),
                limit=int(limit or PAGE_SIZE),
            )
        )

    def _sync_initial_target(self) -> None:
        account = self._accounts.active_account()
        channel = self._profiles.active_channel()
        if account and channel and not self._targets.find_target(account.id, channel.id):
            self._targets.ensure_target(
                account.id,
                channel.id,
                self._presets.active_preset_id,
            )

    def _apply_saved_settings(self, saved: dict[str, Any], *, initial: bool = False) -> None:
        """Load persisted stores and UI prefs from a settings dict."""
        self._profiles.load_from_settings(saved)
        self._accounts.load_from_settings(saved)
        self._presets.load_from_settings(saved)
        self._mudae_settings_presets.load_from_settings(saved)
        self._targets.load_from_settings(saved)
        self._sync_initial_target()
        self._macro_config = self._presets.active_preset()

        us_opts_raw = saved.get("us_mode_options")
        legacy_us = UsModeStopOptions.from_dict(
            us_opts_raw if isinstance(us_opts_raw, dict) else None
        )
        raw_presets = saved.get("presets")
        if not isinstance(raw_presets, dict):
            raw_presets = {}
        legacy_macro = saved.get("macro")
        if not isinstance(legacy_macro, dict):
            legacy_macro = {}
        for preset_id, cfg in list(self._presets.presets.items()):
            stored = raw_presets.get(preset_id)
            if not isinstance(stored, dict):
                stored = legacy_macro if preset_id == "default" else {}
            merged = overlay_legacy_us_options(stored, legacy_us)
            if merged is not stored:
                data = cfg.to_dict()
                data["us_keep_draining"] = bool(merged.get("us_keep_draining", False))
                data["us_stop_on_power_exhausted"] = bool(
                    merged.get("us_stop_on_power_exhausted", False)
                )
                data["us_stop_after_rolls_enabled"] = bool(
                    merged.get("us_stop_after_rolls_enabled", False)
                )
                data["us_stop_after_rolls"] = max(
                    1, int(merged.get("us_stop_after_rolls", 100) or 100)
                )
                self._presets.presets[preset_id] = MacroConfig.from_dict(data)
        self._macro_config = self._presets.active_preset()
        # NOTE: save_app_settings() flattens every fragment into the top-level
        # dict (the kwarg name is just a label), so these are read from ``saved``
        # directly rather than a nested "run_ui" key.
        self._minimize_to_tray = bool(saved.get("minimize_to_tray", False))

        layout = str(saved.get("ui_layout") or _DEFAULT_UI_LAYOUT)
        palette = str(saved.get("ui_palette") or _DEFAULT_UI_PALETTE)
        self._ui_layout = layout if layout in _UI_LAYOUTS else _DEFAULT_UI_LAYOUT
        self._ui_palette = palette if palette in _UI_PALETTES else _DEFAULT_UI_PALETTE
        # Set once the user picks a palette explicitly; until then switching
        # design is free to move the palette with it.
        self._ui_palette_pinned = bool(saved.get("ui_palette_pinned", False))
        self._ui_system_fonts = bool(saved.get("ui_system_fonts", False))
        if not initial:
            self.appearanceChanged.emit()

        self._update_dismissed_sha = str(saved.get("update_dismissed_sha") or "")
        self._update_notified_sha = str(saved.get("update_notified_sha") or "")
        auto_check = bool(saved.get("update_auto_check_enabled", True))
        if initial:
            self._update_auto_check = auto_check
        elif auto_check != self._update_auto_check:
            self._update_auto_check = auto_check
            self.autoUpdateCheckChanged.emit()
            if auto_check:
                self._update_timer.start(_UPDATE_CHECK_INTERVAL_MS)
            else:
                self._update_timer.stop()

        if not initial:
            self._sync_engine_config()
            self.configChanged.emit()
            self.serversChanged.emit()
            self.mudaeSettingsPresetsChanged.emit()
            self.usModeOptionsChanged.emit()
            self.minimizeToTrayChanged.emit()
            self.updateStatusChanged.emit()

    def _record_settings_file_mtime(self) -> None:
        try:
            self._settings_file_mtime = SETTINGS_PATH.stat().st_mtime
        except OSError:
            self._settings_file_mtime = None

    def _ensure_settings_watch(self) -> None:
        settings_path = str(SETTINGS_PATH)
        if SETTINGS_PATH.is_file():
            if settings_path not in self._settings_watcher.files():
                self._settings_watcher.addPath(settings_path)
            return
        directory = str(SETTINGS_PATH.parent)
        if SETTINGS_PATH.parent.is_dir() and directory not in self._settings_watcher.directories():
            self._settings_watcher.addPath(directory)

    def _schedule_settings_reload(self) -> None:
        self._ensure_settings_watch()
        self._settings_reload_timer.start()

    def _on_settings_file_changed(self, _path: str) -> None:
        # Some platforms drop the watch after a change; re-register it.
        self._ensure_settings_watch()
        self._schedule_settings_reload()

    def _on_settings_directory_changed(self, _path: str) -> None:
        self._ensure_settings_watch()
        if SETTINGS_PATH.is_file():
            self._schedule_settings_reload()

    def _reload_settings_from_disk(self) -> None:
        if not SETTINGS_PATH.is_file():
            return
        try:
            mtime = SETTINGS_PATH.stat().st_mtime
        except OSError:
            return
        if self._settings_file_mtime is not None and mtime == self._settings_file_mtime:
            return
        saved = load_settings()
        self._apply_saved_settings(saved)
        self._settings_file_mtime = mtime
        self._set_status("Reloaded settings from disk")

    @Slot()
    def reloadSettingsFromDisk(self) -> None:
        """Force-reload ``data/settings.json`` (also used by the file watcher)."""
        self._settings_file_mtime = None
        self._reload_settings_from_disk()

    def _stats_watch_paths(self) -> list[Path]:
        from mudae.event_log import jsonl_path
        from mudae.minigame_log import log_path

        return [jsonl_path(), log_path()]

    def _ensure_stats_watch(self) -> None:
        paths = self._stats_watch_paths()
        for path in paths:
            text = str(path)
            if path.is_file() and text not in self._stats_watcher.files():
                self._stats_watcher.addPath(text)
            directory = str(path.parent)
            if path.parent.is_dir() and directory not in self._stats_watcher.directories():
                self._stats_watcher.addPath(directory)

    def _schedule_stats_reload(self) -> None:
        self._ensure_stats_watch()
        self._stats_reload_timer.start()

    def _on_stats_file_changed(self, _path: str) -> None:
        self._ensure_stats_watch()
        self._schedule_stats_reload()

    def _on_stats_directory_changed(self, _path: str) -> None:
        self._schedule_stats_reload()

    def _reload_stats_from_disk(self) -> None:
        from mudae import event_log
        from mudae import minigame_log

        self._ensure_stats_watch()
        events_changed = event_log.refresh_from_disk()
        minigames_changed = minigame_log.refresh_from_disk()
        if events_changed:
            self.kakeraChanged.emit()
            self.spheresChanged.emit()
            self.keysChanged.emit()
            self.soulmatesChanged.emit()
            self._notify_run_summary()
        if minigames_changed:
            self.minigamesChanged.emit()

    def _notify_servers(self) -> None:
        # Defer to the next event-loop tick so a value-returning Slot (e.g.
        # addChannel/addServer) fully returns to QML before the QML
        # Connections handlers re-enter the engine. Synchronous re-entry while
        # a slot is still on the call stack can hang the UI thread.
        if self._servers_emit_pending:
            return
        self._servers_emit_pending = True
        QTimer.singleShot(0, self._emit_servers_changed)

    def _emit_servers_changed(self) -> None:
        self._servers_emit_pending = False
        self.serversChanged.emit()

    def _notify_config(self) -> None:
        if self._config_emit_pending:
            return
        self._config_emit_pending = True
        QTimer.singleShot(0, self._emit_config_changed)

    def _emit_config_changed(self) -> None:
        self._config_emit_pending = False
        self.configChanged.emit()
        self.serversChanged.emit()
        self.usModeOptionsChanged.emit()

    def _sync_engine_config(self) -> None:
        """Reload the active run-target preset and push it to a live engine."""
        resolved = resolve_run_target(
            self._accounts,
            self._profiles,
            self._presets,
            self._targets,
        )
        if resolved:
            self._macro_config = resolved.macro_config
            self._run_preset_id = resolved.preset_id
        else:
            self._macro_config = self._presets.active_preset()
        if self._engine:
            self._engine.update_config(self._macro_config)

    def _apply_active_preset_to_engine(self) -> None:
        self._sync_engine_config()

    def _ensure_target_for_active(self) -> None:
        account = self._accounts.active_account()
        channel = self._profiles.active_channel()
        if account and channel:
            self._targets.ensure_target(
                account.id,
                channel.id,
                self._presets.active_preset_id,
            )

    def _set_status(self, text: str) -> None:
        self._status = text
        self.statusChanged.emit(text)

    def _set_connected(self, value: bool) -> None:
        if self._connected != value:
            self._connected = value
            self.connectedChanged.emit(value)
        self._set_connecting(False)
        self._set_disconnecting(False)

    def _set_connecting(self, value: bool) -> None:
        if self._connecting == value:
            return
        self._connecting = value
        self.connectingChanged.emit()

    def _set_disconnecting(self, value: bool) -> None:
        if self._disconnecting == value:
            return
        self._disconnecting = value
        self.disconnectingChanged.emit()

    def _set_notification_standby(self, value: bool) -> None:
        if self._notification_standby == value:
            return
        self._notification_standby = value
        self.notificationStandbyChanged.emit()
        if value:
            self._set_status(
                "Disconnected for notifications — macro waiting for next rolls"
            )
        elif self._connected:
            self._set_status("Connected")
        elif not self._thread or not self._thread.is_alive():
            self._set_status("Disconnected")

    def _on_notification_standby(self, value: bool) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_notification_standby",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(bool, value),
        )

    @Slot(bool)
    def _deliver_notification_standby(self, value: bool) -> None:
        self._set_notification_standby(value)

    @Slot()
    def _emit_session_active(self) -> None:
        self.sessionActiveChanged.emit()

    def _set_run_action_pending(self, action: str) -> None:
        action = str(action or "").strip()
        if self._run_action_pending == action:
            return
        self._run_action_pending = action
        self.runActionPendingChanged.emit()
        self._action_timer.stop()
        if action:
            self._action_timer.start(20_000)
        else:
            self._tu_pending_active = False

    def _on_run_action_timeout(self) -> None:
        if self._run_action_pending:
            self._set_run_action_pending("")

    def _sync_run_action_pending(self) -> None:
        pending = self._run_action_pending
        if not pending:
            return
        phase = self._macro_state.phase
        running = bool(self._engine and self._engine.is_running)

        if pending in {"start", "us"}:
            if running or phase != MacroPhase.IDLE:
                self._set_run_action_pending("")
        elif pending == "stop":
            if not running and phase == MacroPhase.IDLE:
                self._set_run_action_pending("")
        elif pending == "tu":
            if phase == MacroPhase.CHECKING_TU:
                self._tu_pending_active = True
            elif phase == MacroPhase.IDLE and self._tu_pending_active:
                self._set_run_action_pending("")
        elif pending == "oh" and not self._oh_running and not self._minigames_running:
            self._set_run_action_pending("")
        elif pending == "oc" and not self._oc_running and not self._minigames_running:
            self._set_run_action_pending("")
        elif pending == "oq" and not self._oq_running and not self._minigames_running:
            self._set_run_action_pending("")
        elif pending == "ot" and not self._ot_running:
            self._set_run_action_pending("")
        elif pending == "minigames" and not self._minigames_running:
            self._set_run_action_pending("")

    def _notify_macro(self) -> None:
        self._sync_run_action_pending()
        self.macroPhaseChanged.emit(self._macro_state.phase.value)
        self.macroStateChanged.emit()
        self.macroLogChanged.emit()
        self._notify_run_summary()

    @Slot(str)
    def setToken(self, value: str) -> None:
        account = self._accounts.active_account()
        if account:
            account.token = value.strip()
            self._notify_config()
            self._persist()

    @Slot(result=str)
    def getToken(self) -> str:
        return self._accounts.active_token()

    @Slot(result=str)
    def getChannelId(self) -> str:
        return self._profiles.active_discord_channel_id()

    @Slot(str, str)
    def setActiveServerChannel(self, server_id: str, channel_profile_id: str) -> None:
        self._profiles.set_active(server_id, channel_profile_id)
        preset_id = self._targets.preset_for(
            self._accounts.active_account_id,
            channel_profile_id,
            self._presets.active_preset_id,
        )
        if preset_id in self._presets.presets:
            self._presets.set_active(preset_id)
        self._apply_active_preset_to_engine()
        self._notify_config()
        self._persist()
        self._schedule_run_target_switch()

    @Slot(str)
    def setActiveAccount(self, account_id: str) -> None:
        self._accounts.set_active(account_id)
        channel = self._profiles.active_channel()
        if channel:
            preset_id = self._targets.preset_for(
                account_id,
                channel.id,
                self._presets.active_preset_id,
            )
            if preset_id in self._presets.presets:
                self._presets.set_active(preset_id)
        self._apply_active_preset_to_engine()
        self._notify_config()
        self._persist()
        self._schedule_run_target_switch()

    @Slot(str)
    def setActivePreset(self, preset_id: str) -> None:
        if preset_id not in self._presets.presets:
            return
        self._presets.set_active(preset_id)
        self._ensure_target_for_active()
        self._apply_active_preset_to_engine()
        self._notify_config()
        self._persist()

    @Slot(str, str, str, str)
    def setRunTarget(
        self,
        account_id: str,
        server_id: str,
        channel_profile_id: str,
        preset_id: str,
    ) -> None:
        self._accounts.set_active(account_id)
        self._profiles.set_active(server_id, channel_profile_id)
        if preset_id in self._presets.presets:
            self._presets.set_active(preset_id)
        self._ensure_target_for_active()
        self._apply_active_preset_to_engine()
        self._notify_config()
        self._persist()
        self._schedule_run_target_switch()

    @Slot(str, str, result=str)
    def addAccount(self, name: str, account_type: str) -> str:
        account_id = self._accounts.add_account(name, account_type=account_type or "Main")
        self._notify_config()
        self._persist()
        return account_id

    @Slot(str)
    def removeAccount(self, account_id: str) -> None:
        self._targets.remove_targets_for_account(account_id)
        self._accounts.remove_account(account_id)
        self._notify_config()
        self._persist()

    @Slot(str, str, str, str)
    def updateAccount(
        self,
        account_id: str,
        name: str,
        token: str,
        account_type: str,
    ) -> None:
        self._accounts.update_account(
            account_id,
            name=name,
            token=token,
            account_type=account_type,
        )
        self._notify_config()
        self._persist()

    @Slot(str, str)
    def setAccountDailyChannel(self, account_id: str, channel_profile_id: str) -> None:
        self._accounts.update_account(account_id, daily_channel_id=channel_profile_id)
        self._notify_config()
        self._persist()

    @Slot(str, str)
    def setAccountEnabledChannels(self, account_id: str, channel_ids_json: str) -> None:
        try:
            raw = json.loads(channel_ids_json) if channel_ids_json else []
            ids = [str(x) for x in raw if x]
        except json.JSONDecodeError:
            return
        self._accounts.update_account(account_id, enabled_channel_ids=ids)
        default_preset = self._presets.default_preset_id
        for channel_id in ids:
            self._targets.ensure_target(account_id, channel_id, default_preset)
        self._notify_config()
        self._persist()

    @Slot(str, result=str)
    def addPreset(self, name: str) -> str:
        preset_id = self._presets.add_preset(name)
        self._notify_config()
        self._persist()
        return preset_id

    @Slot(str)
    def removePreset(self, preset_id: str) -> None:
        if self._presets.remove_preset(preset_id):
            for target in self._targets.targets:
                if target.preset_id == preset_id:
                    target.preset_id = self._presets.default_preset_id
            if self._presets.active_preset_id == preset_id:
                self._apply_active_preset_to_engine()
            self._notify_config()
            self._persist()

    @Slot(str, str, result=str)
    def duplicatePreset(self, preset_id: str, new_name: str) -> str:
        new_id = self._presets.add_preset(new_name, copy_from=preset_id)
        self._notify_config()
        self._persist()
        return new_id

    @Slot(str, result=str)
    def addServer(self, name: str) -> str:
        server_id = self._profiles.add_server(name)
        self._notify_servers()
        self._persist()
        return server_id

    @Slot(str)
    def removeServer(self, server_id: str) -> None:
        self._profiles.remove_server(server_id)
        self._notify_servers()
        self._persist()

    @Slot(str, str)
    def renameServer(self, server_id: str, name: str) -> None:
        self._profiles.rename_server(server_id, name)
        self._notify_servers()
        self._persist()

    @Slot(str, str, str, result=str)
    def addChannel(self, server_id: str, name: str, discord_channel_id: str) -> str:
        try:
            self._parse_int(discord_channel_id, "channel ID")
        except ValueError as exc:
            self._set_status(str(exc))
            return ""
        channel_id = self._profiles.add_channel(server_id, name, discord_channel_id)
        if channel_id:
            self._notify_servers()
            self._persist()
        return channel_id or ""

    @Slot(str, str)
    def removeChannel(self, server_id: str, channel_profile_id: str) -> None:
        self._targets.remove_targets_for_channel(channel_profile_id)
        self._profiles.remove_channel(server_id, channel_profile_id)
        self._notify_config()
        self._persist()

    @Slot(str, str, str, str)
    def updateChannel(
        self,
        server_id: str,
        channel_profile_id: str,
        name: str,
        discord_channel_id: str,
    ) -> None:
        if discord_channel_id.strip():
            try:
                self._parse_int(discord_channel_id, "channel ID")
            except ValueError as exc:
                self._set_status(str(exc))
                return
        self._profiles.update_channel(
            server_id,
            channel_profile_id,
            name=name,
            channel_id=discord_channel_id if discord_channel_id.strip() else None,
        )
        self._notify_servers()
        self._persist()

    @Slot(result=str)
    def getMacroConfigJson(self) -> str:
        return json.dumps(self._presets.active_preset().to_dict())

    @Slot(str)
    def setMacroConfigJson(self, value: str) -> None:
        try:
            data = json.loads(value) if value else {}
            config = MacroConfig.from_dict(data)
            self._presets.update_preset(self._presets.active_preset_id, config)
            self._apply_active_preset_to_engine()
            self._notify_config()
            self._persist()
        except json.JSONDecodeError:
            pass

    @Slot(str, result=str)
    def macroConfigField(self, key: str) -> str:
        return self.presetConfigField(self._presets.active_preset_id, key)

    @Slot(str, str)
    def setMacroConfigField(self, key: str, value: str) -> None:
        self.setPresetConfigField(self._presets.active_preset_id, key, value)

    @Slot(str, str, result=str)
    def presetConfigField(self, preset_id: str, key: str) -> str:
        preset = self._presets.find_preset(preset_id)
        if not preset:
            return ""
        data = preset.to_dict()
        # Legacy aliases used by MacroConfigForm.qml (read from character_claim).
        character = data.get("character_claim") or {}
        if key == "auto_claim_wish":
            return "true" if character.get("claim_on_wish_ping") else "false"
        if key in {"claim_best_at_claim_reset", "auto_claim"}:
            return "true" if character.get("enabled") else "false"
        val = data.get(key, "")
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val)

    @Slot(str, str, str)
    def setPresetConfigField(self, preset_id: str, key: str, value: str) -> None:
        preset = self._presets.find_preset(preset_id)
        if not preset:
            return
        data = preset.to_dict()
        character = data.get("character_claim") or {}
        if key == "auto_claim_wish":
            character["claim_on_wish_ping"] = value.lower() in {"1", "true", "yes", "on"}
            data["character_claim"] = character
        elif key in {"claim_best_at_claim_reset", "auto_claim"}:
            character["enabled"] = value.lower() in {"1", "true", "yes", "on"}
            data["character_claim"] = character
        elif key == "roll_delay_sec":
            data[key] = float(value) if value.strip() else 0.6
        elif key == "humanize_roll_delay":
            data[key] = value.lower() in {"1", "true", "yes", "on"}
        elif key == "roll_delay_jitter_sec":
            data[key] = float(value) if value.strip() else 0.4
        else:
            data[key] = value
        self._presets.update_preset(preset_id, MacroConfig.from_dict(data))
        self._sync_engine_config()
        self._notify_config()
        self._persist()

    @Slot(str, result=str)
    def getPresetRulesJson(self, preset_id: str) -> str:
        """Return the full rules tree for a preset (all three blocks)."""
        preset = self._presets.find_preset(preset_id)
        if not preset:
            return ""
        data = preset.to_dict()
        return json.dumps(
            {
                "preset_id": preset_id,
                "basic": {
                    "roll_command": data["roll_command"],
                    "prefix": data["prefix"],
                    "roll_delay_sec": data["roll_delay_sec"],
                    "humanize_roll_delay": data.get("humanize_roll_delay", False),
                    "roll_delay_jitter_sec": data.get("roll_delay_jitter_sec", 0.4),
                    "notification_mode": data["notification_mode"],
                },
                "character_claim": data["character_claim"],
                "kakera_reaction": data["kakera_reaction"],
                "sphere_reaction": data["sphere_reaction"],
                "us_roll_kakera": data["us_roll_kakera"],
                "us_mode": {
                    "us_batch_size": data["us_batch_size"],
                    "us_reset_margin_minutes": data["us_reset_margin_minutes"],
                    "us_keep_draining": data.get("us_keep_draining", False),
                    "us_stop_on_power_exhausted": data.get(
                        "us_stop_on_power_exhausted", False
                    ),
                    "us_stop_after_rolls_enabled": data.get(
                        "us_stop_after_rolls_enabled", False
                    ),
                    "us_stop_after_rolls": data.get("us_stop_after_rolls", 100),
                    "us_schedule_enabled": data.get("us_schedule_enabled", False),
                    "us_schedule_start": data.get("us_schedule_start", "04:00"),
                    "us_schedule_end": data.get("us_schedule_end", "06:00"),
                },
                "expert": {
                    "claim_expire_sec": data["claim_expire_sec"],
                    "us_read_before_add_delay_sec": data["us_read_before_add_delay_sec"],
                    "us_add_delay_sec": data["us_add_delay_sec"],
                    "us_roll_timeout_retry_sec": data["us_roll_timeout_retry_sec"],
                },
            }
        )

    @Slot(str, int, result=str)
    def perk9ThresholdPreview(self, preset_id: str, spawns: int) -> str:
        """Threshold ladder for a preset, so Presets can show the DP's own numbers."""
        from macro.perk9_threshold import (
            build_perk9_threshold_context,
            click_threshold,
            estimate_opportunities_left,
            estimate_sphere_colour_frequency,
            normalize_frequency,
            sphere_base_values,
        )

        preset = self._presets.find_preset(preset_id)
        if not preset:
            return "{}"
        rules = preset.sphere_reaction
        state = self._macro_state
        clicks = int(getattr(state, "perk9_click_max", 20) or 20)
        pool = getattr(state, "perk9_roll_pool", None)
        rolled = getattr(state, "perk9_rolled_today", None)
        live = estimate_opportunities_left(
            state,
            manual_override=rules.expected_daily_opportunities,
            rolls_per_hour=getattr(state, "rolls_per_hour_net", None),
        )
        total = int(spawns) if int(spawns) > 0 else (live or 120)
        ctx = build_perk9_threshold_context(
            opportunities_left=total,
            clicks_left=clicks,
            base_values=rules.sphere_values or None,
            frequency=rules.sphere_frequency or None,
            double_chance_pct=float(
                getattr(self._macro_state, "sphere_double_chance_pct", 0.0) or 0.0
            ),
            additional_spheres=float(
                getattr(self._macro_state, "additional_spheres", 0.0) or 0.0
            ),
            shop9_bonus_pct=float(
                getattr(self._macro_state, "perk9_sphere_value_pct", 0.0) or 0.0
            ),
        )
        if ctx is None:
            return "{}"
        order = sorted(ctx.ev_by_emoji, key=lambda e: ctx.ev_by_emoji[e])
        steps = sorted({total, total // 2, total // 4, clicks * 2, clicks})
        ladder = []
        for left in steps:
            if not 1 <= left <= total:
                continue
            bar = click_threshold(ctx.value_table, left, clicks)
            ladder.append(
                {
                    "left": left,
                    "threshold": round(bar, 1),
                    "clicks": [e for e in order if ctx.ev_by_emoji[e] >= bar],
                }
            )
        measured = estimate_sphere_colour_frequency()
        freq = normalize_frequency(rules.sphere_frequency or None)
        base_values = sphere_base_values(rules.sphere_values or None)
        return json.dumps(
            {
                "spawns": total,
                "clicks_left": clicks,
                "clicks_used": int(getattr(state, "perk9_clicks_today", 0) or 0),
                "ev": {e: round(v, 1) for e, v in ctx.ev_by_emoji.items()},
                "base": dict(base_values),
                "freq": {e: round(v * 100.0, 2) for e, v in freq.items()},
                "ladder": ladder,
                "estimate": {
                    "value": live,
                    "pool": pool,
                    "rolled": rolled,
                    "manual": rules.expected_daily_opportunities or 0,
                },
                "measured": (
                    {e: round(v * 100.0, 2) for e, v in measured.items()}
                    if measured
                    else None
                ),
            }
        )

    @Slot(str, str)
    def updatePresetRules(self, preset_id: str, patch_json: str) -> None:
        """Deep-merge a JSON patch into a preset's rules tree and persist."""
        preset = self._presets.find_preset(preset_id)
        if not preset:
            return
        try:
            patch = json.loads(patch_json) if patch_json else {}
        except json.JSONDecodeError:
            return
        if not isinstance(patch, dict):
            return

        data = preset.to_dict()
        basic_patch = patch.get("basic")
        if isinstance(basic_patch, dict):
            for key in (
                "roll_command",
                "prefix",
                "roll_delay_sec",
                "humanize_roll_delay",
                "roll_delay_jitter_sec",
                "notification_mode",
            ):
                if key in basic_patch:
                    data[key] = basic_patch[key]

        us_mode_patch = patch.get("us_mode")
        if isinstance(us_mode_patch, dict):
            for key in (
                "us_batch_size",
                "us_reset_margin_minutes",
                "us_keep_draining",
                "us_stop_on_power_exhausted",
                "us_stop_after_rolls_enabled",
                "us_stop_after_rolls",
                "us_schedule_enabled",
                "us_schedule_start",
                "us_schedule_end",
            ):
                if key in us_mode_patch:
                    data[key] = us_mode_patch[key]

        expert_patch = patch.get("expert")
        if isinstance(expert_patch, dict):
            for key in (
                "claim_expire_sec",
                "us_read_before_add_delay_sec",
                "us_add_delay_sec",
                "us_roll_timeout_retry_sec",
            ):
                if key in expert_patch:
                    data[key] = expert_patch[key]

        for block in ("character_claim", "kakera_reaction", "sphere_reaction", "us_roll_kakera"):
            block_patch = patch.get(block)
            if isinstance(block_patch, dict):
                current = data.get(block) or {}
                if not isinstance(current, dict):
                    current = {}
                data[block] = _deep_merge(current, block_patch)

        self._presets.update_preset(preset_id, MacroConfig.from_dict(data))
        self._sync_engine_config()
        self._notify_config()
        self._persist()

    def _persist(self) -> None:
        save_app_settings(
            accounts=self._accounts.to_settings_fragment(),
            presets=self._presets.to_settings_fragment(),
            mudae_settings=self._mudae_settings_presets.to_settings_fragment(),
            targets=self._targets.to_settings_fragment(),
            servers=self._profiles.to_settings_fragment(),
            run_ui={
                "minimize_to_tray": self._minimize_to_tray,
            },
            appearance={
                "ui_layout": self._ui_layout,
                "ui_palette": self._ui_palette,
                "ui_palette_pinned": self._ui_palette_pinned,
                "ui_system_fonts": self._ui_system_fonts,
            },
            updates={
                "update_dismissed_sha": self._update_dismissed_sha,
                "update_notified_sha": self._update_notified_sha,
                "update_auto_check_enabled": self._update_auto_check,
            },
        )
        self._record_settings_file_mtime()

    def _patch_run_us_policy(self, **fields: Any) -> None:
        preset_id = self._run_preset_id or self._presets.active_preset_id
        preset = self._presets.find_preset(preset_id)
        if not preset:
            return
        data = preset.to_dict()
        data.update(fields)
        self._presets.update_preset(preset_id, MacroConfig.from_dict(data))
        self._sync_engine_config()
        self._notify_config()
        self._persist()

    @Slot(bool)
    def setUsKeepDraining(self, enabled: bool) -> None:
        self._patch_run_us_policy(us_keep_draining=bool(enabled))

    @Slot(bool)
    def setUsStopOnPowerExhausted(self, enabled: bool) -> None:
        self._patch_run_us_policy(us_stop_on_power_exhausted=bool(enabled))

    @Slot(bool)
    def setUsStopAfterRollsEnabled(self, enabled: bool) -> None:
        self._patch_run_us_policy(us_stop_after_rolls_enabled=bool(enabled))

    @Slot(int)
    def setUsStopAfterRolls(self, count: int) -> None:
        self._patch_run_us_policy(us_stop_after_rolls=max(1, int(count)))

    @Property(str, constant=False, notify=appearanceChanged)
    def uiLayout(self) -> str:
        return self._ui_layout

    @Property(str, constant=False, notify=appearanceChanged)
    def uiPalette(self) -> str:
        return self._ui_palette

    @Property(bool, constant=False, notify=appearanceChanged)
    def uiSystemFonts(self) -> bool:
        return self._ui_system_fonts

    @Property(str, constant=True)
    def systemFontFamily(self) -> str:
        return self._system_font.family()

    @Slot(str)
    def setUiLayout(self, layout: str) -> None:
        layout = str(layout)
        if layout not in _UI_LAYOUTS or layout == self._ui_layout:
            return
        self._ui_layout = layout
        if not self._ui_palette_pinned:
            self._ui_palette = _LAYOUT_PALETTE.get(layout, self._ui_palette)
        self.appearanceChanged.emit()
        self._persist()

    @Slot(str)
    def setUiPalette(self, palette: str) -> None:
        palette = str(palette)
        if palette not in _UI_PALETTES:
            return
        self._ui_palette_pinned = True
        if palette == self._ui_palette:
            self._persist()
            return
        self._ui_palette = palette
        self.appearanceChanged.emit()
        self._persist()

    @Slot(bool)
    def setUiSystemFonts(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._ui_system_fonts == enabled:
            return
        self._ui_system_fonts = enabled
        self.appearanceChanged.emit()
        self._persist()

    @Slot(str)
    def applyUiFont(self, family: str) -> None:
        """Set the default application font for the current design.

        The design's font lives in gui/skins.js, so QML pushes it here rather
        than the mapping being duplicated in Python. Setting it application-wide
        means the ~50 views that never specify a family follow the design too.
        An empty family (or system-fonts mode) restores the desktop default
        captured at startup.
        """
        app = QGuiApplication.instance()
        if app is None:
            return
        family = str(family).strip()
        font = QFont(self._system_font)
        if family:
            font.setFamily(family)
        current = app.font()
        if current.family() == font.family() and current.pointSize() == font.pointSize():
            return
        app.setFont(font)

    @Slot()
    def resetUiPalette(self) -> None:
        """Re-link the palette to the current design."""
        self._ui_palette_pinned = False
        palette = _LAYOUT_PALETTE.get(self._ui_layout, _DEFAULT_UI_PALETTE)
        if palette != self._ui_palette:
            self._ui_palette = palette
            self.appearanceChanged.emit()
        self._persist()

    @Property(str, constant=False, notify=runSummaryChanged)
    def runSummaryJson(self) -> str:
        return json.dumps(
            build_run_summary(
                self._macro_state,
                self._session_started_at,
                kakera_rules=(
                    getattr(self._macro_config, "kakera_reaction", None)
                    if self._macro_config
                    else None
                ),
                sphere_rules=(
                    getattr(self._macro_config, "sphere_reaction", None)
                    if self._macro_config
                    else None
                ),
            )
        )

    def _notify_run_summary(self) -> None:
        if not self._run_summary_timer.isActive():
            self._run_summary_timer.start()

    @Slot(bool)
    def setMinimizeToTray(self, enabled: bool) -> None:
        if not self._tray_available and enabled:
            self._set_status("System tray is not available on this desktop")
            return
        enabled = bool(enabled)
        if self._minimize_to_tray == enabled:
            return
        self._minimize_to_tray = enabled
        self.minimizeToTrayChanged.emit()
        self._persist()

    def attach_tray(self, tray: Any) -> None:
        self._tray = tray
        self._tray_available = bool(getattr(tray, "available", False))
        self.minimizeToTrayChanged.emit()
        if self._minimize_to_tray and not self._tray_available:
            self._minimize_to_tray = False
            self.minimizeToTrayChanged.emit()

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parent.parent

    @Slot(bool)
    def setAutoUpdateCheckEnabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._update_auto_check == enabled:
            return
        self._update_auto_check = enabled
        self.autoUpdateCheckChanged.emit()
        self._persist()
        if enabled:
            self._update_timer.start(_UPDATE_CHECK_INTERVAL_MS)
            self.checkForUpdates()
        else:
            self._update_timer.stop()

    @Slot()
    @Slot(bool)
    def checkForUpdates(self, redisplay: bool = False) -> None:
        if self._update_checking:
            return
        if redisplay:
            self._update_dismissed_sha = ""
            self.updateStatusChanged.emit()
            self._persist()
        self._update_checking = True
        self.updateCheckingChanged.emit()
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _check_updates_worker(self) -> None:
        status = check_for_updates(self._repo_root())
        payload = json.dumps(status.to_dict())
        QMetaObject.invokeMethod(
            self,
            "_deliver_update_status",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, payload),
        )

    @Slot(str)
    def _deliver_update_status(self, payload_json: str) -> None:
        data = json.loads(payload_json)
        self._update_status = UpdateStatus(
            checked_at=float(data.get("checked_at") or time.time()),
            error=data.get("error"),
            branch=data.get("branch"),
            current_sha=data.get("current_sha"),
            remote_sha=data.get("remote_sha"),
            behind=int(data.get("behind") or 0),
            ahead=int(data.get("ahead") or 0),
            dirty=bool(data.get("dirty")),
            commits=list(data.get("commits") or []),
        )
        self._update_checking = False
        self.updateCheckingChanged.emit()
        self.updateStatusChanged.emit()
        status = self._update_status
        if status.available and status.remote_sha != self._update_notified_sha:
            self._update_notified_sha = status.remote_sha
            self._persist()
            tray = self._tray
            notify = getattr(tray, "notify", None) if tray is not None else None
            if callable(notify):
                count = len(status.commits)
                change_word = "change" if count == 1 else "changes"
                notify(
                    "FinalMacro update available",
                    f"{count} {change_word} ready — open Settings to update.",
                )

    @Slot()
    def dismissUpdate(self) -> None:
        status = self._update_status
        if not status or not status.remote_sha:
            return
        self._update_dismissed_sha = status.remote_sha
        self.updateStatusChanged.emit()
        self._persist()

    @Slot()
    def pullUpdate(self) -> None:
        if self._update_pulling:
            return
        if self.sessionActive:
            self._update_pull_message = "Disconnect first — updating while connected could interrupt the macro"
            self._update_pull_ok = False
            self.updateStatusChanged.emit()
            return
        status = self._update_status
        if not status or not status.can_pull:
            return
        self._update_pulling = True
        self.updatePullingChanged.emit()
        branch = status.branch
        threading.Thread(target=self._pull_update_worker, args=(branch,), daemon=True).start()

    def _pull_update_worker(self, branch: str | None) -> None:
        result = pull_update(self._repo_root(), branch=branch)
        payload = json.dumps({"ok": result.ok, "message": result.message, "new_sha": result.new_sha})
        QMetaObject.invokeMethod(
            self,
            "_deliver_pull_result",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, payload),
        )

    @Slot(str)
    def _deliver_pull_result(self, payload_json: str) -> None:
        data = json.loads(payload_json)
        self._update_pulling = False
        self.updatePullingChanged.emit()
        self._update_pull_message = str(data.get("message") or "")
        self._update_pull_ok = bool(data.get("ok"))
        self.updateStatusChanged.emit()
        if data.get("ok"):
            self.checkForUpdates()

    @Slot()
    def showMainWindow(self) -> None:
        if self._tray is not None:
            show = getattr(self._tray, "show_window", None)
            if callable(show):
                show()

    @Slot()
    def requestQuit(self) -> None:
        if self._tray is not None:
            quit_fn = getattr(self._tray, "request_quit", None)
            if callable(quit_fn):
                quit_fn()
                return
        self.shutdown()
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QGuiApplication.instance()
        if app is not None:
            app.quit()

    def _get_daily_resets_for(
        self,
        account_id: str,
        channel_profile_id: str,
    ) -> dict[str, Any]:
        from macro.daily_store import get_account_daily_slice

        found = self._profiles.find_channel_by_profile_id(channel_profile_id)
        if not found:
            return {}
        return get_account_daily_slice(found[1].daily_resets, account_id)

    def _save_daily_resets_for(
        self,
        account_id: str,
        channel_profile_id: str,
        account_daily: dict[str, Any],
    ) -> None:
        """Store daily reset data for one account on one channel.

        Safe to call from the reader thread: the dict swap is atomic and the
        settings write is marshalled to the GUI thread.
        """
        from macro.daily_store import set_account_daily_slice

        found = self._profiles.find_channel_by_profile_id(channel_profile_id)
        if not found or not account_id:
            return
        channel = found[1]
        channel.daily_resets = set_account_daily_slice(
            channel.daily_resets,
            account_id,
            account_daily,
        )
        self._request_persist()

    def _request_persist(self) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_persist",
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot()
    def _deliver_persist(self) -> None:
        self._persist()

    def _parse_int(self, value: str, label: str) -> int:
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid {label}: must be a numeric Discord ID") from exc

    def _daily_resets_callbacks_for(
        self,
        account_id: str,
        channel_profile_id: str,
    ) -> tuple[Callable[[], dict[str, Any]], Callable[[dict[str, Any]], None]]:
        return (
            lambda: self._get_daily_resets_for(account_id, channel_profile_id),
            lambda daily: self._save_daily_resets_for(
                account_id,
                channel_profile_id,
                daily,
            ),
        )

    def _bind_run_target_metadata(self, resolved: ResolvedRunTarget) -> None:
        """Update session labels, log recorders, and engine persistence for a target."""
        from mudae.chaos_capture import set_recording_account as set_chaos_account
        from mudae.kakera_log import set_recording_account as set_kakera_account
        from mudae.key_log import set_recording_account as set_key_account
        from mudae.soulmate_log import set_recording_account
        from mudae.sphere_log import set_recording_account as set_sphere_account
        from mudae.minigame_log import set_recording_account as set_minigame_account

        self._run_token = resolved.token.strip()
        self._run_account_id = resolved.account_id
        self._run_channel_profile_id = resolved.channel_profile_id
        self._run_preset_id = resolved.preset_id
        self._macro_config = resolved.macro_config

        account = self._accounts.find_account(resolved.account_id)
        account_name = account.name if account else "Main"
        self._run_account_name = account_name
        set_recording_account(resolved.account_id, account_name)
        set_kakera_account(resolved.account_id, account_name)
        set_key_account(resolved.account_id, account_name)
        set_sphere_account(resolved.account_id, account_name)
        set_minigame_account(resolved.account_id, account_name)
        set_chaos_account(resolved.account_id, account_name)

        self._restore_known_run_state(resolved.account_id, resolved.channel_profile_id)

        channel_profile = self._profiles.find_channel_by_profile_id(
            resolved.channel_profile_id
        )
        channel = channel_profile[1] if channel_profile else None
        server = (
            channel_profile[0]
            if channel_profile
            else self._profiles.find_server(self._profiles.active_server_id)
        )
        self._run_channel_name = channel.name if channel else None
        self._run_guild_name = (
            (channel.guild_name if channel else None)
            or (server.name if server else None)
        )
        guild_raw = None
        if channel and channel.guild_id:
            guild_raw = channel.guild_id
        elif server and server.guild_id:
            guild_raw = server.guild_id
        try:
            self._run_guild_id = int(guild_raw) if guild_raw else None
        except (TypeError, ValueError):
            self._run_guild_id = None

        if self._engine:
            daily_get, daily_save = self._daily_resets_callbacks_for(
                resolved.account_id,
                resolved.channel_profile_id,
            )
            settings: dict[str, Any] | None = None
            bundle = self._channel_settings_bundle(resolved.channel_profile_id)
            if bundle:
                _channel, settings = bundle
            self._engine.update_run_target(
                account_id=resolved.account_id,
                daily_resets_get=daily_get,
                daily_resets_save=daily_save,
                channel_settings=settings,
            )
            self._engine.update_config(resolved.macro_config)

    def _reset_macro_state_preserve_identity(self) -> None:
        """Clear channel-specific runtime state while keeping user identity and log."""
        state = self._macro_state
        state.rolls_left = None
        state.rolls_us_bonus = None
        state.us_stacked = None
        state.claim_available = None
        state.claim_cooldown_minutes = None
        state.claim_cooldown_at = ""
        state.power_percent = None
        state.power_tracked_at = 0.0
        state.power_updated_at = ""
        state.dk_stock = None
        state.dk_next_minutes = None
        state.dk_reset_at = ""
        state.rolls_reset_minutes = None
        state.rolls_reset_at = ""
        state.next_claim_reset_minutes = None
        state.claim_reset_at = ""
        state.claim_expire_sec = None
        state.rt_available = None
        state.rt_next_minutes = None
        state.rt_reset_at = ""
        state.phase = MacroPhase.IDLE
        state.kakera_clicks_today = 0
        state.kakera_clicks_day = ""
        state.perk8_priority_mode = "inactive"
        state.perk8_click_max = None
        state.perk9_clicks_today = 0
        state.perk9_clicks_day = ""

    def _restore_known_run_state(
        self,
        account_id: str,
        channel_profile_id: str,
    ) -> None:
        """Fill perk 8/9, roll cap, and cached reset times for this account/channel.

        A new Connect used to start from a blank ``AccountState``. We still do
        not know rolls *left* or claim *ready* until ``$tu``, but the daily
        perk counters, ``$bonus`` roll pool, and last reset deadlines are
        already on disk.
        """
        from macro.minigame_daily import load_minigame_record, refresh_minigames_if_refill_passed
        from macro.perk8_daily import apply_record_to_state, load_perk8_record
        from macro.perk9_daily import (
            apply_record_to_state as apply_perk9_record_to_state,
            load_perk9_record,
            sync_perk9_clicks_from_log,
        )
        from macro.runtime_store import (
            apply_timers_to_state,
            apply_to_state,
            load_runtime_record,
        )

        if not account_id or not channel_profile_id:
            self._apply_sheet_caps_to_run_state(channel_profile_id)
            return

        daily = self._get_daily_resets_for(account_id, channel_profile_id)
        apply_record_to_state(self._macro_state, load_perk8_record(daily))
        self._apply_sheet_caps_to_run_state(channel_profile_id)
        apply_perk9_record_to_state(self._macro_state, load_perk9_record(daily))
        refresh_minigames_if_refill_passed(load_minigame_record(daily))
        sync_perk9_clicks_from_log(self._macro_state)

        settings: dict[str, Any] | None = None
        bundle = self._channel_settings_bundle(channel_profile_id)
        if bundle:
            settings = bundle[1]
        record = load_runtime_record(daily)
        persist_tu = bool(self._macro_config.character_claim.persist_tu_state)
        restored_tu = False
        had_rolls = self._macro_state.rolls_left is not None
        if persist_tu:
            result = apply_to_state(self._macro_state, record, settings=settings)
            if result.applied:
                restored_tu = True
                if not had_rolls:
                    self._append_activity_log(
                        f"Restored saved $tu state — {result.message}"
                    )
        if not restored_tu:
            apply_timers_to_state(
                self._macro_state,
                record,
                settings=settings,
            )
        self._notify_macro()
        self._notify_run_summary()

    def _append_activity_log(
        self,
        text: str,
        *,
        severity: ActivitySeverity | None = None,
    ) -> None:
        ActivityLog(self._macro_state, on_update=self._notify_macro).write(
            text, severity=severity
        )

    def _write_live_feed(
        self,
        snapshot: MudaeMessageSnapshot,
        parsed: ParseResult,
    ) -> None:
        """Mirror Mudae channel text into the Run feed (not macro skip chatter)."""
        if parsed.kind == MessageKind.ROLL:
            if snapshot.edited:
                return
            # The roll loop logs the card after a button refresh so reacts are
            # complete; skip the first-parse copy while a session is running.
            if self._engine is not None and self._engine.is_running:
                return
        formatted = format_live_feed(snapshot, parsed)
        if not formatted:
            return
        text, severity = formatted
        if self._engine is not None:
            self._engine.write_activity(text, severity=severity)  # type: ignore[arg-type]
        else:
            self._append_activity_log(text, severity=severity)  # type: ignore[arg-type]

    def _schedule_run_target_switch(self) -> None:
        """Move the live Discord session to the newly selected run target."""
        if not self._loop or not self._thread or not self._thread.is_alive():
            return
        if not self._monitor or not self._engine:
            return
        resolved = resolve_run_target(
            self._accounts,
            self._profiles,
            self._presets,
            self._targets,
        )
        if not resolved:
            return
        asyncio.run_coroutine_threadsafe(
            self._apply_run_target_switch(resolved),
            self._loop,
        )

    async def _apply_run_target_switch(self, resolved: ResolvedRunTarget) -> None:
        if not self._monitor or not self._engine or not self._actions:
            return

        channel_id = self._parse_int(resolved.discord_channel_id, "channel ID")
        token = resolved.token.strip()
        same_binding = (
            token == self._run_token
            and resolved.account_id == self._run_account_id
            and resolved.channel_profile_id == self._run_channel_profile_id
            and channel_id == self._monitor.channel_id
        )
        if same_binding:
            self._bind_run_target_metadata(resolved)
            self._on_macro_state()
            return

        was_notification_standby = self._notification_standby

        if self._engine.is_running:
            self._engine.end_session("channel switch")
            self._engine.stop()
            for _ in range(100):
                if not self._engine.is_running:
                    break
                await asyncio.sleep(0.05)

        self._actions.drain_queue()
        token_changed = token != self._run_token
        if token_changed:
            self._monitor.token = token
            ready = await self._monitor.reconnect(channel_id=channel_id)
        elif self._monitor.is_connected:
            ready = await self._monitor.switch_channel(channel_id)
        else:
            # Gateway was dropped (notification standby) — reconnect on the new channel.
            ready = await self._monitor.reconnect(channel_id=channel_id)

        if token_changed and not ready:
            self._on_status("Channel switch failed")
            self._on_connected(False)
            return

        self._reset_macro_state_preserve_identity()
        if ready:
            self._macro_state.own_usernames = self._monitor.get_own_usernames()
            own_id = self._monitor.get_own_user_id()
            self._macro_state.own_user_ids = [own_id] if own_id is not None else []

        self._bind_run_target_metadata(resolved)
        suffix = " (reconnected from notification standby)" if was_notification_standby else ""
        self._append_activity_log(f"Switched to {resolved.label}{suffix}")

        if was_notification_standby:
            self._on_notification_standby(False)
        if ready:
            self._on_connected(True)
        else:
            self._on_status(f"Switched · {resolved.label}")
        self._on_macro_state()

    @Slot(str)
    def _deliver_entry_json(self, payload_json: str) -> None:
        entry = json.loads(payload_json)
        self._parse_lab_entries.insert(0, entry)
        if len(self._parse_lab_entries) > 500:
            del self._parse_lab_entries[500:]
        self.entryReceived.emit(entry)

    @Slot()
    def clearParseLabLog(self) -> None:
        self._parse_lab_entries.clear()

    @Slot(result=int)
    def parseLabLogCount(self) -> int:
        return len(self._parse_lab_entries)

    @Slot(result=str)
    def getDataDirUrl(self) -> str:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return QUrl.fromLocalFile(str(data_dir)).toString()

    @Slot(result=str)
    def getParseLabDefaultSaveUrl(self) -> str:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        default_name = f"parse_lab_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return QUrl.fromLocalFile(str(data_dir / default_name)).toString()

    def _parse_lab_log_payload(self) -> dict[str, Any]:
        return {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "channel_id": self.getChannelId(),
            "channel_label": self.activeChannelLabel,
            "status": self._status,
            "entry_count": len(self._parse_lab_entries),
            "entries": list(reversed(self._parse_lab_entries)),
        }

    @Slot(str, result=str)
    def saveParseLabLogToPath(self, path_or_url: str) -> str:
        if not self._parse_lab_entries:
            return "No messages to save"

        path = QUrl(path_or_url).toLocalFile() if path_or_url.startswith("file:") else path_or_url
        if not path:
            return "Save cancelled"
        if not path.lower().endswith(".json"):
            path += ".json"

        payload = self._parse_lab_log_payload()
        try:
            Path(path).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            return f"Save failed: {exc}"
        return f"Saved {len(self._parse_lab_entries)} entries to {path}"

    @Slot(str)
    def _deliver_status(self, text: str) -> None:
        self._set_status(text)

    @Slot(bool)
    def _deliver_connected(self, value: bool) -> None:
        self._set_connected(value)
        if not value and not self._notification_standby and self._status.startswith("Connected"):
            self._set_status("Disconnected")

    @Slot()
    def _clear_run_action_pending(self) -> None:
        self._set_run_action_pending("")

    @Slot()
    def _deliver_macro_notify(self) -> None:
        self._notify_macro()

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

    def _on_macro_state(self) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_macro_notify",
            Qt.ConnectionType.QueuedConnection,
        )

    def _on_parsed(self, snapshot: MudaeMessageSnapshot, parsed: ParseResult) -> None:
        if self._actions:
            self._actions.feed(snapshot, parsed)
        from mudae.chaos_capture import note_parsed as note_chaos_parsed

        note_chaos_parsed(snapshot, parsed)
        if parsed.kind == MessageKind.TU:
            minutes = parsed.fields.get("daily_reset_minutes")
            if minutes is not None:
                self._sync_daily_from_tu(int(minutes))
        profile_kind = profile_kind_from_parse(parsed)
        if profile_kind:
            payload = json.dumps(
                {
                    "discord_channel_id": snapshot.channel_id,
                    "kind": profile_kind,
                    "fields": profile_fields_from_parse(parsed, profile_kind),
                    "summary": parsed.summary,
                    "guild_id": snapshot.guild_id,
                    "guild_name": snapshot.guild_name,
                    "channel_name": snapshot.channel_name,
                }
            )
            QMetaObject.invokeMethod(
                self,
                "_deliver_profile_update",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, payload),
            )
        if self._engine and parsed.fields.get("settimer") is not None:
            self._engine.apply_settings_fields(parsed.fields)
        if parsed.fields.get("new_soulmate"):
            QMetaObject.invokeMethod(
                self,
                "_deliver_soulmates_notify",
                Qt.ConnectionType.QueuedConnection,
            )
        if self._try_record_kakera_earning(snapshot, parsed):
            QMetaObject.invokeMethod(
                self,
                "_deliver_kakera_notify",
                Qt.ConnectionType.QueuedConnection,
            )
            if parsed.fields.get("spheres"):
                QMetaObject.invokeMethod(
                    self,
                    "_deliver_spheres_notify",
                    Qt.ConnectionType.QueuedConnection,
                )
        elif self._try_record_sphere_earning(snapshot, parsed):
            QMetaObject.invokeMethod(
                self,
                "_deliver_spheres_notify",
                Qt.ConnectionType.QueuedConnection,
            )
        if self._try_record_key_events(snapshot, parsed):
            QMetaObject.invokeMethod(
                self,
                "_deliver_keys_notify",
                Qt.ConnectionType.QueuedConnection,
            )
        self._write_live_feed(snapshot, parsed)

    @Slot()
    def _deliver_soulmates_notify(self) -> None:
        self.soulmatesChanged.emit()

    @Slot()
    def _deliver_kakera_notify(self) -> None:
        self.kakeraChanged.emit()
        self._notify_run_summary()

    @Slot()
    def _deliver_spheres_notify(self) -> None:
        self.spheresChanged.emit()
        self._notify_run_summary()

    @Slot()
    def _deliver_minigames_notify(self) -> None:
        self.minigamesChanged.emit()

    @Slot()
    def _deliver_keys_notify(self) -> None:
        self.keysChanged.emit()
        self._notify_run_summary()

    def _on_keys_recorded(self) -> None:
        QMetaObject.invokeMethod(
            self,
            "_deliver_keys_notify",
            Qt.ConnectionType.QueuedConnection,
        )

    def _try_record_kakera_earning(
        self,
        snapshot: MudaeMessageSnapshot,
        parsed: ParseResult,
    ) -> bool:
        from mudae.kakera_log import (
            earn_method_from_parse,
            record_kakera_earning,
            record_roll_bku_earning,
            should_record_earning,
            should_record_roll_bku,
        )

        if parsed.fields.get("bku") is not None:
            if not should_record_roll_bku(
                parsed.fields,
                self._macro_state.own_usernames,
                self._macro_state.phase,
            ):
                return False
            record_roll_bku_earning(snapshot, parsed.fields)
            return True

        if not should_record_earning(
            parsed.kind,
            parsed.fields,
            self._macro_state.own_usernames,
        ):
            return False
        method = earn_method_from_parse(parsed.kind, parsed.fields)
        if not method:
            return False
        record_kakera_earning(snapshot, parsed.fields, earn_method=method)
        spheres = parsed.fields.get("spheres")
        if spheres is not None:
            try:
                bonus = int(spheres)
            except (TypeError, ValueError):
                bonus = 0
            if bonus > 0:
                from mudae.sphere_log import record_sphere_earning

                record_sphere_earning(
                    snapshot,
                    parsed.fields,
                    source="kakera_bonus",
                    amount=bonus,
                )
        return True

    def _try_record_sphere_earning(
        self,
        snapshot: MudaeMessageSnapshot,
        parsed: ParseResult,
    ) -> bool:
        from mudae.sphere_log import record_sphere_earning, should_record_sphere_click

        if parsed.kind != MessageKind.SPHERE_CLICK:
            return False
        if not should_record_sphere_click(
            parsed.kind,
            parsed.fields,
            self._macro_state.own_usernames,
        ):
            return False
        record_sphere_earning(snapshot, parsed.fields, source="sphere_click")
        from macro.perk9_daily import apply_perk9_click_from_parse

        if apply_perk9_click_from_parse(self._macro_state, parsed.fields):
            self._persist_perk9_progress()
        return True

    def _try_record_key_events(
        self,
        snapshot: MudaeMessageSnapshot,
        parsed: ParseResult,
    ) -> bool:
        from mudae.key_log import record_roll_key_events, should_record_roll_keys

        if not should_record_roll_keys(
            parsed.kind,
            parsed.fields,
            self._macro_state.own_usernames,
            self._macro_state.phase,
            macro_running=bool(self._engine and self._engine.is_running),
        ):
            return False
        return bool(record_roll_key_events(snapshot, parsed.fields))

    def _record_minigame_spheres(self, game: str, amount: int, *, clicks: int = 0) -> None:
        if amount <= 0 or not self._monitor:
            return
        from mudae.sphere_log import record_minigame_earning

        record_minigame_earning(
            game=game,
            amount=amount,
            clicks=clicks or None,
            channel_id=self._monitor.channel_id,
            channel_name=self._run_channel_name,
            guild_id=self._run_guild_id,
            guild_name=self._run_guild_name,
        )
        QMetaObject.invokeMethod(
            self,
            "_deliver_spheres_notify",
            Qt.ConnectionType.QueuedConnection,
        )

    def _record_perk10_spheres(self, amount: int) -> None:
        if amount <= 0 or not self._monitor:
            return
        from mudae.sphere_log import record_perk10_earning

        record_perk10_earning(
            amount=amount,
            channel_id=self._monitor.channel_id,
            channel_name=self._run_channel_name,
            guild_id=self._run_guild_id,
            guild_name=self._run_guild_name,
        )
        QMetaObject.invokeMethod(
            self,
            "_deliver_spheres_notify",
            Qt.ConnectionType.QueuedConnection,
        )

    def _apply_minigame_play_status(self, result: dict[str, Any] | None) -> None:
        if not result or result.get("reason") != "exhausted":
            return
        from mudae.parsers.minigame_exhausted import format_exhausted_activity

        self._persist_minigame_exhausted(result)
        self._set_status(format_exhausted_activity(result))

    def _persist_minigame_exhausted(self, result: dict[str, Any] | None) -> None:
        if not result:
            return
        game = str(result.get("game") or "").lstrip("$").lower()
        if game not in {"oh", "oc", "oq", "ot"}:
            return
        from macro.minigame_daily import (
            load_minigame_record,
            mark_game_exhausted,
            save_minigame_record,
        )

        daily_get, daily_save = self._daily_resets_callbacks_for(
            self._run_account_id, self._run_channel_profile_id
        )
        refill = result.get("refill_minutes")
        try:
            refill_minutes = int(refill) if refill is not None else None
        except (TypeError, ValueError):
            refill_minutes = None
        daily = dict(daily_get())
        daily_save(
            save_minigame_record(
                daily,
                mark_game_exhausted(
                    load_minigame_record(daily),
                    game,
                    refill_minutes=refill_minutes,
                ),
            )
        )

    def _persist_perk9_progress(self) -> None:
        from macro.perk9_daily import (
            load_perk9_record,
            persist_click_progress,
            save_perk9_record,
        )

        daily_get, daily_save = self._daily_resets_callbacks_for(
            self._run_account_id, self._run_channel_profile_id
        )
        daily = dict(daily_get())
        daily_save(
            save_perk9_record(
                daily,
                persist_click_progress(
                    load_perk9_record(daily),
                    clicked_today=int(self._macro_state.perk9_clicks_today),
                    click_max=int(self._macro_state.perk9_click_max),
                ),
            )
        )

    async def _play_daily_minigames_from_engine(self) -> None:
        if not self._actions or not self._monitor:
            return
        if self._minigames_busy():
            return
        daily_get, daily_save = self._daily_resets_callbacks_for(
            self._run_account_id, self._run_channel_profile_id
        )
        self._minigames_running = True
        try:
            runner = PlayAllMinigames(
                self._actions,
                self._monitor,
                log=self._append_activity_log,
                on_game_reward=lambda game, amount, clicks: self._record_minigame_spheres(
                    game, amount, clicks=clicks
                ),
                on_game_result=lambda _game, result: self._record_minigame_session(
                    result, log=self._append_activity_log
                ),
                daily_get=daily_get,
                daily_save=daily_save,
                state=self._macro_state,
            )
            result = await runner.play(prefix=self._macro_config.prefix)
            self._minigame_availability = dict(result.get("availability") or {})
            for game_result in (result.get("played") or {}).values():
                if game_result.get("reason") == "exhausted":
                    self._apply_minigame_play_status(game_result)
                    break
        except Exception as exc:  # noqa: BLE001 - surface to the activity log
            self._append_activity_log(f"play-all error: {exc}")
        finally:
            self._minigames_running = False

    def _record_minigame_session(
        self,
        result: dict[str, Any] | None,
        *,
        recorder: Any | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        if not result or not self._monitor:
            if log:
                log("minigame stats skipped (no result or not connected)")
            return
        # "no fleet" is $ot failing to read the colour count off the grid —
        # nothing was clicked, so there is no board to record.
        if result.get("reason") in {"exhausted", "no grid", "no fleet"}:
            return
        session = result.get("session")
        if not isinstance(session, dict):
            if log:
                log("minigame stats skipped (no board on this result)")
            return
        from mudae.minigame_log import log_path, record_minigame_session

        try:
            entry = record_minigame_session(
                session,
                channel_id=self._monitor.channel_id,
                channel_name=self._run_channel_name,
                guild_id=self._run_guild_id,
                guild_name=self._run_guild_name,
            )
        except Exception as exc:  # noqa: BLE001 - stats must not kill the game
            if log:
                log(f"minigame stats failed: {exc}")
            return
        if entry is None:
            if log:
                log("minigame stats skipped (empty board)")
            return
        if recorder is not None:
            recorder.attach_minigame(session)
        if log:
            log(f"Minigame stats saved: {log_path()}")
        perk10 = int(session.get("spheres_bonus") or result.get("spheres_bonus") or 0)
        if perk10 > 0:
            self._record_perk10_spheres(perk10)
        QMetaObject.invokeMethod(
            self,
            "_deliver_minigames_notify",
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot(str)
    def _deliver_profile_update(self, payload_json: str) -> None:
        data = json.loads(payload_json)
        self._profiles.apply_parsed(
            int(data["discord_channel_id"]),
            kind=str(data["kind"]),
            fields=dict(data.get("fields") or {}),
            summary=str(data.get("summary") or ""),
            guild_id=data.get("guild_id"),
            guild_name=data.get("guild_name"),
            channel_name=data.get("channel_name"),
        )
        self._notify_config()
        self._persist()
        if str(data.get("kind") or "") in {"bonus", "shop"}:
            self._apply_sheet_caps_if_discord_channel(int(data["discord_channel_id"]))

    async def _notification_disconnect(self) -> bool:
        """Drop the Discord gateway between hourly sessions (notification mode)."""
        if not self._monitor or not self._connected:
            return True
        await self._monitor.stop_background()
        from mudae.kakera_log import flush_disk_log
        from mudae.key_log import flush_disk_log as flush_key_log
        from mudae.sphere_log import flush_disk_log as flush_sphere_log
        from mudae.minigame_log import flush_disk_log as flush_minigame_log
        from mudae.chaos_capture import (
            close_open_window,
            flush_disk_log as flush_chaos_log,
        )

        close_open_window("disconnect")
        flush_disk_log()
        flush_key_log()
        flush_sphere_log()
        flush_minigame_log()
        flush_chaos_log()
        self._on_connected(False)
        self._on_notification_standby(True)
        return True

    async def _notification_reconnect(self) -> bool:
        """Restore the Discord gateway before the next hourly roll session."""
        if not self._monitor:
            return False
        if self._engine and self._engine.is_running and self._engine.stop_requested:
            return False
        if self._monitor.is_connected:
            self._on_notification_standby(False)
            return True
        ready = await self._monitor.start_background()
        if ready:
            self._macro_state.own_usernames = self._monitor.get_own_usernames()
            own_id = self._monitor.get_own_user_id()
            self._macro_state.own_user_ids = [own_id] if own_id is not None else []
            self._on_connected(True)
            self._on_notification_standby(False)
            self._on_macro_state()
        else:
            self._on_status("Reconnect timed out (notification mode)")
            self._on_connected(False)
        return ready

    def _reader_thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._stop_event = asyncio.Event()

        resolved = resolve_run_target(
            self._accounts, self._profiles, self._presets, self._targets
        )
        if not resolved:
            raise ValueError("Select account, server, channel, and preset on Run")
        channel_id = self._parse_int(resolved.discord_channel_id, "channel ID")
        daily_get, daily_save = self._daily_resets_callbacks_for(
            resolved.account_id,
            resolved.channel_profile_id,
        )
        channel_settings: dict[str, Any] | None = None
        bundle = self._channel_settings_bundle(resolved.channel_profile_id)
        if bundle:
            _channel, channel_settings = bundle

        self._bind_run_target_metadata(resolved)

        self._monitor = ChannelMonitor(
            token=resolved.token,
            channel_id=channel_id,
            on_entry=self._on_entry,
            on_status=self._on_status,
            on_parsed=self._on_parsed,
        )
        self._actions = DiscordActions(self._monitor)
        from macro.account_dailies import seconds_until_due
        from macro.roll_scheduler import earliest_wake_seconds

        self._engine = RollCycleEngine(
            self._actions,
            self._macro_config,
            self._macro_state,
            self._monitor,
            on_state=self._on_macro_state,
            on_keys=self._on_keys_recorded,
            on_persist=self._request_persist,
            daily_resets_get=daily_get,
            daily_resets_save=daily_save,
            notification_disconnect=self._notification_disconnect,
            notification_reconnect=self._notification_reconnect,
            account_id=resolved.account_id,
            on_priority_pause=lambda: self._run_account_dailies(from_engine=True),
            priority_wake_hint=earliest_wake_seconds(
                lambda: seconds_until_due(self._accounts.accounts),
                self._us_schedule_wake_seconds,
            ),
            play_daily_minigames=self._play_daily_minigames_from_engine,
            notification_connection_held=self._minigames_busy,
            minigames_busy=self._minigames_busy,
        )
        if channel_settings is not None:
            self._engine.update_run_target(
                account_id=resolved.account_id,
                daily_resets_get=daily_get,
                daily_resets_save=daily_save,
                channel_settings=channel_settings,
            )

        async def runner() -> None:
            from macro.account_daily_runtime import AccountDailyRuntime

            self._account_daily_lock = asyncio.Lock()
            self._account_daily_runtime = AccountDailyRuntime(
                switch_to=self._switch_monitor_for_dailies,
                send_command=self._send_daily_command,
                wait_for_tick=self._wait_daily_tick,
                wait_for=self._actions.wait_for,
                sleep=asyncio.sleep,
                log=self._append_activity_log,
                persist_account=self._persist_account_daily_fields,
                drain=self._actions.drain_queue,
            )
            daily_task = asyncio.create_task(
                self._account_daily_loop(),
                name="account-dailies",
            )
            us_task = asyncio.create_task(
                self._us_schedule_loop(),
                name="us-schedule",
            )
            try:
                ready = await self._monitor.start_background()
                if ready:
                    self._macro_state.own_usernames = self._monitor.get_own_usernames()
                    own_id = self._monitor.get_own_user_id()
                    self._macro_state.own_user_ids = [own_id] if own_id is not None else []
                    self._on_connected(True)
                    self._on_macro_state()
                else:
                    self._on_status("Connection timed out")
                    self._on_connected(False)
                await self._stop_event.wait()
                if self._engine:
                    self._engine.save_runtime_state()
                if self._engine and self._engine.is_running:
                    self._engine.stop()
                await self._monitor.stop_background()
                self._on_connected(False)
            finally:
                for task in (daily_task, us_task):
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                self._account_daily_runtime = None
                self._account_daily_lock = None

        try:
            loop.run_until_complete(runner())
        except Exception as exc:
            self._on_status(f"Error: {exc}")
            self._on_connected(False)
        finally:
            from mudae.kakera_log import clear_recording_account, flush_disk_log
            from mudae.key_log import (
                clear_recording_account as clear_key_account,
                flush_disk_log as flush_key_log,
            )
            from mudae.soulmate_log import clear_recording_account as clear_soulmate_account
            from mudae.sphere_log import (
                clear_recording_account as clear_sphere_account,
                flush_disk_log as flush_sphere_log,
            )
            from mudae.minigame_log import (
                clear_recording_account as clear_minigame_account,
                flush_disk_log as flush_minigame_log,
            )
            from mudae.chaos_capture import (
                clear_recording_account as clear_chaos_account,
                close_open_window,
                flush_disk_log as flush_chaos_log,
            )

            close_open_window("disconnect")
            clear_recording_account()
            clear_soulmate_account()
            clear_key_account()
            clear_sphere_account()
            clear_minigame_account()
            clear_chaos_account()
            flush_disk_log()
            flush_key_log()
            flush_sphere_log()
            flush_minigame_log()
            flush_chaos_log()
            self._run_guild_id = None
            self._run_guild_name = None
            self._run_channel_name = None
            self._run_account_name = ""
            self._run_preset_id = ""
            self._run_account_id = ""
            self._run_channel_profile_id = ""
            self._run_token = ""
            loop.close()
            self._loop = None
            self._on_notification_standby(False)
            QMetaObject.invokeMethod(
                self,
                "_emit_session_active",
                Qt.ConnectionType.QueuedConnection,
            )

    @Slot()
    def connect(self) -> None:
        if self._thread and self._thread.is_alive():
            self._set_status("Already connected or connecting")
            return
        resolved = resolve_run_target(
            self._accounts, self._profiles, self._presets, self._targets
        )
        if not resolved:
            self._set_status("Select account, server, channel, and preset on Run")
            return
        if not resolved.token:
            self._set_status("Active account needs a token (Accounts tab)")
            return

        self._ensure_target_for_active()
        self._macro_config = resolved.macro_config
        self._run_preset_id = resolved.preset_id
        self._persist()
        self._macro_state = AccountState()
        self._session_started_at = datetime.now(timezone.utc)
        self._restore_known_run_state(
            resolved.account_id,
            resolved.channel_profile_id,
        )
        self._set_connecting(True)
        self._set_status("Connecting…")
        self._thread = threading.Thread(
            target=self._reader_thread_main,
            name="channel-monitor",
            daemon=True,
        )
        self._thread.start()
        self._emit_session_active()

    @Slot()
    def disconnect(self) -> None:
        if self._loop and self._stop_event:
            self._set_disconnecting(True)
            self._set_status("Disconnecting…")
            self._set_notification_standby(False)

            def _shutdown() -> None:
                if self._engine and self._engine.is_running:
                    self._engine.stop()
                self._stop_event.set()

            self._loop.call_soon_threadsafe(_shutdown)
        else:
            self._set_status("Not connected")

    @Slot()
    def runTu(self) -> None:
        if not self._loop or not self._engine:
            self._set_status("Connect first")
            return
        self._persist()
        self._engine.update_config(self._macro_config)
        self._set_run_action_pending("tu")

        async def _run() -> None:
            await self._engine.run_tu()

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot()
    def runUsCheck(self) -> None:
        if not self._loop or not self._engine:
            self._set_status("Connect first")
            return
        if self._engine.is_running:
            self._set_status("Stop the macro first")
            return
        self._persist()
        self._engine.update_config(self._macro_config)
        self._set_run_action_pending("us_check")

        async def _run() -> None:
            try:
                await self._engine.run_us_check()
            finally:
                QMetaObject.invokeMethod(
                    self,
                    "_clear_run_action_pending",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    def _session_meta(self) -> dict[str, str]:
        channel = self._run_channel_name or self._profiles.active_label() or "?"
        guild = self._run_guild_name or "?"
        return {
            "account": self._run_account_name or "?",
            "channel": channel,
            "guild": guild,
            "preset": self._presets.active_preset_id or "?",
        }

    def _begin_minigame_session(self, mode: str) -> tuple[ActivityLog, Any]:
        from macro.session_log import SessionLogRecorder

        meta = self._session_meta()
        recorder = SessionLogRecorder()
        recorder.start(mode=mode, **meta)
        activity = ActivityLog(
            self._macro_state,
            on_update=self._notify_macro,
            session=recorder,
        )
        activity.clear()
        activity.write(
            "Session started · "
            f"{mode} · {meta['account']} · {meta['preset']} · {meta['channel']}"
        )
        return activity, recorder

    @staticmethod
    def _finish_minigame_session(activity: ActivityLog, recorder: Any, reason: str) -> None:
        if not recorder.active:
            return
        activity.write(f"Session ending ({reason})")
        path = recorder.finish(reason)
        activity.set_session(None)
        if path is not None:
            activity.write(f"Session log saved: {path.name}")

    def _minigames_busy(self) -> bool:
        return bool(
            self._oh_running
            or self._oc_running
            or self._oq_running
            or self._ot_running
            or self._minigames_running
        )

    def _manual_minigame_blocked_status(self, *, game: str | None) -> str | None:
        """Refuse GUI minigames while the engine is mid-roll (idle wait is ok)."""
        if not self._loop or not self._actions or not self._monitor:
            return "Connect first"
        if self._minigames_busy():
            if game is None:
                return "Stop the minigame before playing all"
            return f"Stop the minigame before playing ${game}"
        engine = self._engine
        if engine and engine.is_running and not engine.waiting_for_hourly_refill:
            if game is None:
                return "Stop the macro before playing minigames"
            return f"Stop the macro before playing ${game}"
        return None

    async def _ensure_gateway_for_manual_minigame(self) -> str | None:
        """Reconnect when the hourly loop is sitting in notification idle."""
        engine = self._engine
        if engine is None or not engine.is_running:
            if not (self._monitor and self._monitor.is_connected):
                return "Connect first"
            return None
        if not engine.waiting_for_hourly_refill:
            return "Stop the macro before playing minigames"
        if not await self._notification_reconnect():
            return "Reconnect failed — cannot play minigame"
        return None

    async def _release_gateway_after_manual_minigame(self) -> None:
        engine = self._engine
        if not (
            engine
            and engine.is_running
            and engine.waiting_for_hourly_refill
            and self._macro_config.notification_mode
        ):
            return
        await self._notification_disconnect()

    def _apply_sheet_caps_to_run_state(self, channel_profile_id: str = "") -> None:
        from macro.sheet_caps import apply_sheet_caps

        profile_id = channel_profile_id or self._run_channel_profile_id
        found = (
            self._profiles.find_channel_by_profile_id(profile_id) if profile_id else None
        )
        bonus = found[1].bonus if found else {}
        shop = found[1].shop if found else {}
        apply_sheet_caps(self._macro_state, bonus=bonus, shop=shop)

    def _apply_sheet_caps_if_discord_channel(self, discord_channel_id: int) -> None:
        if not self._run_channel_profile_id:
            return
        found = self._profiles.find_channel_by_profile_id(self._run_channel_profile_id)
        if not found:
            return
        try:
            stored = int(str(found[1].channel_id or "").strip() or "0")
        except ValueError:
            return
        if stored != int(discord_channel_id):
            return
        self._apply_sheet_caps_to_run_state(self._run_channel_profile_id)
        self._notify_macro()

    def _sync_daily_from_tu(self, minutes: int) -> None:
        from macro.account_dailies import iso_ready, ready_after_minutes

        if not self._run_account_id:
            return
        ready = ready_after_minutes(int(minutes))
        self._accounts.update_account(
            self._run_account_id,
            daily_next_ready_at=iso_ready(ready),
        )
        self._request_persist()

    def _persist_account_daily_fields(self, account_id: str, fields: dict[str, str]) -> None:
        kwargs: dict[str, str] = {}
        if "p_next_ready_at" in fields:
            kwargs["p_next_ready_at"] = fields["p_next_ready_at"]
        if "daily_next_ready_at" in fields:
            kwargs["daily_next_ready_at"] = fields["daily_next_ready_at"]
        if not kwargs:
            return
        self._accounts.update_account(account_id, **kwargs)
        self._request_persist()

    async def _wait_daily_tick(self, message_id: int, timeout: float) -> bool:
        if not self._actions:
            return False
        return await self._actions.wait_for_mudae_tick(message_id, timeout=timeout)

    async def _send_daily_command(self, command: str) -> int | None:
        if self._engine:
            return await self._engine._send_command_with_reconnect(
                command,
                label=f"${command}",
            )
        if not self._actions:
            return None
        return await self._actions.send_command(
            command,
            prefix=self._macro_config.prefix,
        )

    async def _switch_monitor_for_dailies(self, token: str, discord_channel_id: int) -> bool:
        monitor = self._monitor
        if not monitor:
            return False
        if self._actions:
            self._actions.drain_queue()
        token = token.strip()
        current_token = str(getattr(monitor, "token", "") or "").strip()
        token_changed = token != current_token
        same_channel = int(monitor.channel_id) == int(discord_channel_id)
        if not token_changed and same_channel and monitor.is_connected:
            return True
        try:
            if token_changed:
                monitor.token = token
                ready = await monitor.reconnect(channel_id=int(discord_channel_id))
            elif monitor.is_connected:
                ready = await monitor.switch_channel(int(discord_channel_id))
            else:
                ready = await monitor.reconnect(channel_id=int(discord_channel_id))
        except Exception as exc:
            self._append_activity_log(f"$p/$daily: switch error ({exc})")
            reconnect = getattr(monitor, "force_reconnect", None)
            if reconnect is not None:
                try:
                    await reconnect()
                except Exception:
                    pass
            return False
        if self._actions:
            self._actions.drain_queue()
        if ready:
            self._macro_state.own_usernames = monitor.get_own_usernames()
            own_id = monitor.get_own_user_id()
            self._macro_state.own_user_ids = [own_id] if own_id is not None else []
            self._on_connected(True)
        return bool(ready)

    def _home_discord_channel_id(self) -> int | None:
        found = self._profiles.find_channel_by_profile_id(self._run_channel_profile_id)
        if found and found[1].channel_id:
            try:
                return int(found[1].channel_id)
            except ValueError:
                return None
        if self._monitor:
            return int(self._monitor.channel_id)
        return None

    async def _run_account_dailies(self, *, from_engine: bool = False) -> None:
        if not self._monitor or not self._actions or not self._account_daily_runtime:
            return
        if self._minigames_busy() or self._settings_apply_running:
            return
        if not from_engine and self._engine and self._engine.is_running:
            return
        lock = self._account_daily_lock
        if lock is None:
            return
        from macro.account_dailies import plans_due

        async with lock:
            plans = plans_due(
                self._accounts.accounts,
                prefer_account_id=self._run_account_id,
            )
            if not plans:
                return
            was_disconnected = not self._monitor.is_connected
            if was_disconnected:
                if not await self._notification_reconnect():
                    self._append_activity_log("$p/$daily: reconnect failed")
                    return
            home_channel = self._home_discord_channel_id()
            home_token = self._run_token or str(getattr(self._monitor, "token", "") or "")
            if home_channel is None or not home_token.strip():
                return

            def discord_id_for(plan: Any) -> int | None:
                pair = self._profiles.find_channel_by_profile_id(plan.channel_profile_id)
                if not pair or not pair[1].channel_id:
                    return None
                try:
                    return int(pair[1].channel_id)
                except ValueError:
                    return None

            await self._account_daily_runtime.run_plans(
                plans,
                home_token=home_token,
                home_channel_id=home_channel,
                discord_channel_id_for=discord_id_for,
            )
            if self._monitor:
                self._macro_state.own_usernames = self._monitor.get_own_usernames()
                own_id = self._monitor.get_own_user_id()
                self._macro_state.own_user_ids = [own_id] if own_id is not None else []
            if (
                was_disconnected
                and self._engine
                and self._engine.is_running
                and self._macro_config.notification_mode
            ):
                await self._notification_disconnect()

    async def _account_daily_loop(self) -> None:
        from macro.account_dailies import seconds_until_due

        while True:
            try:
                await self._run_account_dailies(from_engine=False)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._append_activity_log(f"$p/$daily: {exc}")
            delay = seconds_until_due(self._accounts.accounts)
            if delay is None:
                sleep_for = 30.0
            elif delay <= 0:
                sleep_for = 5.0
            else:
                sleep_for = min(delay, 30.0)
            await asyncio.sleep(sleep_for)

    def _us_schedule_wake_seconds(self) -> float | None:
        """Seconds until the next automatic ``$us`` window, if one is armed."""
        from macro.us_schedule import in_local_window, seconds_until_window_start

        cfg = self._macro_config
        if not cfg.us_schedule_enabled:
            return None
        start = cfg.us_schedule_start
        end = cfg.us_schedule_end
        if in_local_window(start, end):
            # Already open — the auto loop starts it. A 0s hint would spam $p.
            return None
        return seconds_until_window_start(start, end)

    def _us_schedule_consumed_id(self) -> str:
        from macro.us_schedule import load_consumed_window_id

        if not self._run_account_id or not self._run_channel_profile_id:
            return ""
        daily = self._get_daily_resets_for(
            self._run_account_id, self._run_channel_profile_id
        )
        return load_consumed_window_id(daily)

    def _mark_us_schedule_consumed(self, window_id: str | None = None) -> None:
        from macro.us_schedule import (
            containing_window_id,
            store_consumed_window_id,
        )

        if not self._run_account_id or not self._run_channel_profile_id:
            return
        cfg = self._macro_config
        wid = window_id or containing_window_id(
            cfg.us_schedule_start, cfg.us_schedule_end
        )
        if not wid:
            return
        daily = dict(
            self._get_daily_resets_for(
                self._run_account_id, self._run_channel_profile_id
            )
        )
        self._save_daily_resets_for(
            self._run_account_id,
            self._run_channel_profile_id,
            store_consumed_window_id(daily, wid),
        )

    def _us_schedule_loop_delay(self) -> float:
        from macro.us_schedule import (
            containing_window_id,
            in_local_window,
            seconds_until_window_end,
            seconds_until_window_start,
        )

        cfg = self._macro_config
        if not cfg.us_schedule_enabled:
            return 30.0
        start = cfg.us_schedule_start
        end = cfg.us_schedule_end
        if in_local_window(start, end):
            current = containing_window_id(start, end)
            if current and current == self._us_schedule_consumed_id():
                until_end = seconds_until_window_end(start, end)
                if until_end is None:
                    return 30.0
                return min(max(1.0, until_end), 30.0)
            return 5.0
        until = seconds_until_window_start(start, end)
        if until <= 0:
            return 5.0
        return min(until, 30.0)

    async def _wait_engine_idle(self, *, timeout: float | None = 30.0) -> bool:
        started = time.monotonic()
        while self._engine and self._engine.is_running:
            if timeout is not None and time.monotonic() - started > timeout:
                return False
            await asyncio.sleep(0.05)
        return True

    async def _ensure_connected_for_us_schedule(self) -> bool:
        if not self._monitor:
            return False
        if self._monitor.is_connected:
            return True
        if not await self._notification_reconnect():
            self._append_activity_log("$us schedule: reconnect failed")
            return False
        return True

    async def _us_schedule_loop(self) -> None:
        while True:
            try:
                await self._maybe_run_scheduled_us()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._append_activity_log(f"$us schedule: {exc}")
            await asyncio.sleep(self._us_schedule_loop_delay())

    async def _maybe_run_scheduled_us(self) -> None:
        from macro.us_schedule import containing_window_id, in_local_window

        if not self._monitor or not self._engine:
            return
        if self._minigames_busy() or self._settings_apply_running:
            return
        if not self._connected and not self._notification_standby:
            return
        cfg = self._macro_config
        if not cfg.us_schedule_enabled:
            return
        start = cfg.us_schedule_start
        end = cfg.us_schedule_end
        if not in_local_window(start, end):
            return
        window_id = containing_window_id(start, end)
        if not window_id:
            return
        if self._us_schedule_consumed_id() == window_id:
            return

        engine = self._engine
        if engine.is_running and engine.running_mode == "us":
            self._mark_us_schedule_consumed(window_id)
            return
        if engine.is_running and engine.running_mode != "hourly":
            return
        if engine.is_running and not engine.waiting_for_hourly_refill:
            return

        resume_hourly = False
        self._us_schedule_skip_hourly_resume = False
        try:
            if engine.is_running and engine.running_mode == "hourly":
                resume_hourly = True
                self._append_activity_log(
                    f"$us schedule: pausing hourly for {start}–{end} local"
                )
                engine.end_session("scheduled $us")
                engine.stop()
                if not await self._wait_engine_idle(timeout=30.0):
                    self._append_activity_log(
                        "$us schedule: hourly did not stop — skipping"
                    )
                    resume_hourly = False
                    return

            if (
                not self._minigames_busy()
                and not self._settings_apply_running
                and not engine.is_running
                and await self._ensure_connected_for_us_schedule()
            ):
                self._mark_us_schedule_consumed(window_id)
                engine.update_config(self._macro_config)
                self._us_schedule_session_active = True
                self._append_activity_log(
                    f"$us schedule: starting ({start}–{end} local)"
                )
                engine.start_us_mode(
                    session_meta=self._session_meta(),
                    us_stop=us_stop_from_config(self._macro_config),
                )
                await self._wait_engine_idle(timeout=None)
        except asyncio.CancelledError:
            self._us_schedule_skip_hourly_resume = True
            raise
        finally:
            self._us_schedule_session_active = False
            if (
                resume_hourly
                and not self._us_schedule_skip_hourly_resume
                and self._engine
                and not self._engine.is_running
                and not self._minigames_busy()
                and (self._connected or self._notification_standby)
            ):
                self._append_activity_log("$us schedule: resuming hourly")
                self._engine.update_config(self._macro_config)
                self._engine.start(session_meta=self._session_meta())

    @Slot()
    def startMacro(self) -> None:
        if not self._loop or not self._engine:
            self._set_status("Connect first")
            return
        if self._engine.is_running:
            self._set_status("Macro already running")
            return
        if self._minigames_busy():
            self._set_status("Stop the minigame before starting the hourly macro")
            return
        self._persist()
        self._engine.update_config(self._macro_config)
        self._set_run_action_pending("start")
        meta = self._session_meta()

        def _start() -> None:
            self._engine.start(session_meta=meta)

        self._loop.call_soon_threadsafe(_start)

    @Slot()
    def startUsMode(self) -> None:
        if not self._loop or not self._engine:
            self._set_status("Connect first")
            return
        if self._engine.is_running:
            self._set_status("Macro already running")
            return
        if self._minigames_busy():
            self._set_status("Stop the minigame before rolling $us")
            return
        self._persist()
        self._engine.update_config(self._macro_config)
        self._set_run_action_pending("us")
        meta = self._session_meta()

        def _start() -> None:
            self._engine.start_us_mode(
                session_meta=meta,
                us_stop=us_stop_from_config(self._macro_config, apply_schedule=False),
            )

        self._loop.call_soon_threadsafe(_start)
        from macro.us_schedule import in_local_window

        if self._macro_config.us_schedule_enabled and in_local_window(
            self._macro_config.us_schedule_start,
            self._macro_config.us_schedule_end,
        ):
            self._mark_us_schedule_consumed()

    @Slot()
    def stopMacro(self) -> None:
        if not self._engine or not self._loop:
            return
        self._set_run_action_pending("stop")
        if self._us_schedule_session_active:
            self._us_schedule_skip_hourly_resume = True
        release_session = self._notification_standby

        def _stop() -> None:
            self._engine.stop()
            if release_session and self._stop_event:
                self._stop_event.set()

        self._loop.call_soon_threadsafe(_stop)

    @Slot()
    def playOhSphere(self) -> None:
        blocked = self._manual_minigame_blocked_status(game="oh")
        if blocked:
            self._set_status(blocked)
            return

        activity, recorder = self._begin_minigame_session("oh")
        game = OhSphereGame(self._actions, self._monitor, log=activity.write)
        self._oh_running = True
        self._set_run_action_pending("oh")

        async def _run() -> None:
            reason = "finished"
            try:
                gate = await self._ensure_gateway_for_manual_minigame()
                if gate:
                    reason = "error"
                    activity.write(gate)
                    self._set_status(gate)
                    return
                result = await game.play(prefix=self._macro_config.prefix)
                self._apply_minigame_play_status(result)
                self._record_minigame_session(
                    result, recorder=recorder, log=activity.write
                )
                reward = int(result.get("reward") or 0)
                clicks = int(result.get("clicks") or 0)
                if reward > 0:
                    self._record_minigame_spheres("oh", reward, clicks=clicks)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"$oh error: {exc}")
            finally:
                await self._release_gateway_after_manual_minigame()
                self._finish_minigame_session(activity, recorder, reason)
                self._oh_running = False
                QMetaObject.invokeMethod(
                    self,
                    "_clear_run_action_pending",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot()
    def playOcSphere(self) -> None:
        blocked = self._manual_minigame_blocked_status(game="oc")
        if blocked:
            self._set_status(blocked)
            return

        activity, recorder = self._begin_minigame_session("oc")
        game = OcSphereGame(self._actions, self._monitor, log=activity.write)
        self._oc_running = True
        self._set_run_action_pending("oc")

        async def _run() -> None:
            reason = "finished"
            try:
                gate = await self._ensure_gateway_for_manual_minigame()
                if gate:
                    reason = "error"
                    activity.write(gate)
                    self._set_status(gate)
                    return
                result = await game.play(prefix=self._macro_config.prefix)
                self._apply_minigame_play_status(result)
                self._record_minigame_session(
                    result, recorder=recorder, log=activity.write
                )
                reward = int(result.get("reward") or 0)
                clicks = int(result.get("clicks") or 0)
                if reward > 0:
                    self._record_minigame_spheres("oc", reward, clicks=clicks)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"$oc error: {exc}")
            finally:
                await self._release_gateway_after_manual_minigame()
                self._finish_minigame_session(activity, recorder, reason)
                self._oc_running = False
                QMetaObject.invokeMethod(
                    self,
                    "_clear_run_action_pending",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot()
    def playOqSphere(self) -> None:
        blocked = self._manual_minigame_blocked_status(game="oq")
        if blocked:
            self._set_status(blocked)
            return

        activity, recorder = self._begin_minigame_session("oq")
        game = OqSphereGame(self._actions, self._monitor, log=activity.write)
        self._oq_running = True
        self._set_run_action_pending("oq")

        async def _run() -> None:
            reason = "finished"
            try:
                gate = await self._ensure_gateway_for_manual_minigame()
                if gate:
                    reason = "error"
                    activity.write(gate)
                    self._set_status(gate)
                    return
                result = await game.play(prefix=self._macro_config.prefix)
                self._apply_minigame_play_status(result)
                self._record_minigame_session(
                    result, recorder=recorder, log=activity.write
                )
                reward = int(result.get("reward") or 0)
                clicks = int(result.get("clicks") or 0)
                if reward > 0:
                    self._record_minigame_spheres("oq", reward, clicks=clicks)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"$oq error: {exc}")
            finally:
                await self._release_gateway_after_manual_minigame()
                self._finish_minigame_session(activity, recorder, reason)
                self._oq_running = False
                QMetaObject.invokeMethod(
                    self,
                    "_clear_run_action_pending",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot()
    def playOtSphere(self) -> None:
        """Play one ``$ot`` by hand.

        Deliberately manual-only: ``$ot`` is not in ``PLAYABLE_MINIGAMES``, so
        play-all skips it and it never runs itself after the daily refill. The
        solver is new and wants real boards before it is trusted unattended.
        """
        blocked = self._manual_minigame_blocked_status(game="ot")
        if blocked:
            self._set_status(blocked)
            return

        activity, recorder = self._begin_minigame_session("ot")
        game = OtSphereGame(self._actions, self._monitor, log=activity.write)
        self._ot_running = True
        self._set_run_action_pending("ot")

        async def _run() -> None:
            reason = "finished"
            try:
                gate = await self._ensure_gateway_for_manual_minigame()
                if gate:
                    reason = "error"
                    activity.write(gate)
                    self._set_status(gate)
                    return
                result = await game.play(prefix=self._macro_config.prefix)
                self._apply_minigame_play_status(result)
                self._record_minigame_session(
                    result, recorder=recorder, log=activity.write
                )
                reward = int(result.get("reward") or 0)
                clicks = int(result.get("clicks") or 0)
                if reward > 0:
                    self._record_minigame_spheres("ot", reward, clicks=clicks)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"$ot error: {exc}")
            finally:
                await self._release_gateway_after_manual_minigame()
                self._finish_minigame_session(activity, recorder, reason)
                self._ot_running = False
                QMetaObject.invokeMethod(
                    self,
                    "_clear_run_action_pending",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot()
    def playAllMinigames(self) -> None:
        blocked = self._manual_minigame_blocked_status(game=None)
        if blocked:
            self._set_status(blocked)
            return

        activity, recorder = self._begin_minigame_session("minigames")
        self._minigames_running = True
        self._set_run_action_pending("minigames")

        def _on_reward(game: str, amount: int, clicks: int) -> None:
            self._record_minigame_spheres(game, amount, clicks=clicks)

        def _on_result(_game: str, result: dict[str, Any]) -> None:
            self._record_minigame_session(
                result, recorder=recorder, log=activity.write
            )

        daily_get, daily_save = self._daily_resets_callbacks_for(
            self._run_account_id, self._run_channel_profile_id
        )
        runner = PlayAllMinigames(
            self._actions,
            self._monitor,
            log=activity.write,
            on_game_reward=_on_reward,
            on_game_result=_on_result,
            daily_get=daily_get,
            daily_save=daily_save,
            state=self._macro_state,
        )

        async def _run() -> None:
            reason = "finished"
            try:
                gate = await self._ensure_gateway_for_manual_minigame()
                if gate:
                    reason = "error"
                    activity.write(gate)
                    self._set_status(gate)
                    return
                result = await runner.play(
                    prefix=self._macro_config.prefix,
                    ignore_daily_skip=True,
                )
                self._minigame_availability = dict(result.get("availability") or {})
                if result.get("reason") == "ohu failed":
                    reason = "error"
                elif result.get("reason") == "skipped until refill":
                    reason = "finished"
                for game_result in (result.get("played") or {}).values():
                    if game_result.get("reason") == "exhausted":
                        self._apply_minigame_play_status(game_result)
                        break
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"play-all error: {exc}")
            finally:
                await self._release_gateway_after_manual_minigame()
                self._finish_minigame_session(activity, recorder, reason)
                self._minigames_running = False
                QMetaObject.invokeMethod(
                    self,
                    "_clear_run_action_pending",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    def _notify_mudae_settings_presets(self) -> None:
        self.mudaeSettingsPresetsChanged.emit()

    def _append_settings_apply_log(self, line: str) -> None:
        self._settings_apply_log.append(line)
        if len(self._settings_apply_log) > 200:
            del self._settings_apply_log[: len(self._settings_apply_log) - 200]
        self.settingsApplyChanged.emit()

    def _clear_settings_apply_log(self) -> None:
        self._settings_apply_log.clear()
        self.settingsApplyChanged.emit()

    def _channel_settings_bundle(
        self,
        channel_profile_id: str,
    ) -> tuple[Any, Any] | None:
        found = self._profiles.find_channel_by_profile_id(channel_profile_id)
        if not found:
            return None
        _server, channel = found
        return channel, normalize_settings_fields(dict(channel.settings or {}))

    @Slot(str, result=str)
    def addMudaeSettingsPreset(self, name: str) -> str:
        preset_id = self._mudae_settings_presets.add_preset(name.strip() or "Preset")
        self._notify_mudae_settings_presets()
        self._persist()
        return preset_id

    @Slot(str, result=bool)
    def removeMudaeSettingsPreset(self, preset_id: str) -> bool:
        removed = self._mudae_settings_presets.remove_preset(preset_id)
        if removed:
            self._notify_mudae_settings_presets()
            self._persist()
        return removed

    @Slot(str, str, result=str)
    def duplicateMudaeSettingsPreset(self, preset_id: str, new_name: str) -> str:
        source = self._mudae_settings_presets.find(preset_id)
        if source is None:
            return ""
        new_id = self._mudae_settings_presets.add_preset(
            new_name.strip() or f"{source.name} copy",
            copy_from=preset_id,
        )
        self._notify_mudae_settings_presets()
        self._persist()
        return new_id

    @Slot(str, str, result=str)
    def saveChannelSettingsAsPreset(self, channel_profile_id: str, name: str) -> str:
        bundle = self._channel_settings_bundle(channel_profile_id)
        if bundle is None:
            return ""
        _channel, settings = bundle
        if not settings:
            return ""
        preset_id = self._mudae_settings_presets.add_preset(
            name.strip() or "From channel",
            fields=settings,
            created_from_channel_id=channel_profile_id,
        )
        self._notify_mudae_settings_presets()
        self._persist()
        return preset_id

    @Slot(str, result=str)
    def formatChannelSettingsDisplayJson(self, channel_profile_id: str) -> str:
        bundle = self._channel_settings_bundle(channel_profile_id)
        if bundle is None:
            return json.dumps({"sections": [], "field_count": 0})
        _channel, settings = bundle
        return json.dumps(fields_to_display_dict(settings))

    @Slot(str, result=str)
    def formatChannelBonusDisplayJson(self, channel_profile_id: str) -> str:
        found = self._profiles.find_channel_by_profile_id(channel_profile_id)
        if found is None:
            return json.dumps({"sections": [], "field_count": 0})
        _server, channel = found
        return json.dumps(fields_to_bonus_display_dict(dict(channel.bonus or {})))

    @Slot(str, result=str)
    def formatChannelShopDisplayJson(self, channel_profile_id: str) -> str:
        found = self._profiles.find_channel_by_profile_id(channel_profile_id)
        if found is None:
            return json.dumps({"sections": [], "field_count": 0})
        _server, channel = found
        return json.dumps(fields_to_shop_display_dict(dict(channel.shop or {})))

    @Slot(str, result=str)
    def getMudaeSettingsPresetEditorJson(self, preset_id: str) -> str:
        preset = self._mudae_settings_presets.find(preset_id)
        if preset is None:
            return json.dumps({"sections": [], "preset_id": "", "preset_name": ""})
        display = fields_to_display_dict(preset.fields)
        display["preset_id"] = preset.id
        display["preset_name"] = preset.name
        return json.dumps(display)

    @Slot(str, str, str, result=bool)
    def updateMudaeSettingsPresetField(
        self,
        preset_id: str,
        field: str,
        value_json: str,
    ) -> bool:
        preset = self._mudae_settings_presets.find(preset_id)
        if preset is None or field not in CATALOG_BY_FIELD:
            return False
        try:
            raw = json.loads(value_json)
        except json.JSONDecodeError:
            return False
        if raw is None:
            preset.fields.pop(field, None)
        else:
            preset.fields[field] = coerce_editor_value(field, raw)
        preset.fields = normalize_settings_fields(dict(preset.fields))
        self._notify_mudae_settings_presets()
        self._persist()
        return True

    @Slot(str, str, result=bool)
    def copyChannelSettingsToMudaePreset(
        self,
        channel_profile_id: str,
        preset_id: str,
    ) -> bool:
        bundle = self._channel_settings_bundle(channel_profile_id)
        preset = self._mudae_settings_presets.find(preset_id)
        if bundle is None or preset is None:
            return False
        _channel, settings = bundle
        if not settings:
            return False
        preset.fields = merge_preset_fields(preset.fields, settings)
        self._notify_mudae_settings_presets()
        self._persist()
        return True

    @Slot(str, str, result=bool)
    def copyMudaePresetToPreset(self, source_id: str, target_id: str) -> bool:
        source = self._mudae_settings_presets.find(source_id)
        target = self._mudae_settings_presets.find(target_id)
        if source is None or target is None or source_id == target_id:
            return False
        target.fields = normalize_settings_fields(dict(source.fields))
        self._notify_mudae_settings_presets()
        self._persist()
        return True

    @Slot(str, result=bool)
    def setDefaultMudaeSettingsPreset(self, preset_id: str) -> bool:
        if preset_id not in self._mudae_settings_presets.presets:
            return False
        self._mudae_settings_presets.set_default(preset_id)
        self._notify_mudae_settings_presets()
        self._persist()
        return True

    @Slot(str, str, result=bool)
    def renameMudaeSettingsPreset(self, preset_id: str, new_name: str) -> bool:
        result = self._mudae_settings_presets.rename_preset(preset_id, new_name)
        if result:
            self._notify_mudae_settings_presets()
            self._persist()
        return result is not None

    @Slot(str, str, result=str)
    def getChannelComplianceStatus(self, channel_profile_id: str, preset_id: str) -> str:
        bundle = self._channel_settings_bundle(channel_profile_id)
        preset = self._mudae_settings_presets.find(preset_id)
        if bundle is None or preset is None:
            return "partial"
        _channel, current = bundle
        if not current:
            return "partial"
        return compliance_status(current, preset.fields)

    @Slot(str, str, result=str)
    def diffMudaeSettingsPreset(self, channel_profile_id: str, preset_id: str) -> str:
        bundle = self._channel_settings_bundle(channel_profile_id)
        preset = self._mudae_settings_presets.find(preset_id)
        if bundle is None or preset is None:
            return json.dumps({"items": [], "command_count": 0})
        _channel, current = bundle
        items = diff_settings(
            current,
            preset.fields,
            groups=self._settings_apply_groups,
        )
        commands = [item.command for item in items if item.command]
        return json.dumps(
            {
                "items": [item.to_dict() for item in items],
                "command_count": len(commands),
            }
        )

    @Slot(str)
    def setMudaeSettingsApplyGroups(self, groups_json: str) -> None:
        try:
            parsed = json.loads(groups_json or "[]")
        except json.JSONDecodeError:
            self._settings_apply_groups = None
            return
        if not parsed:
            self._settings_apply_groups = None
            return
        self._settings_apply_groups = frozenset(str(g) for g in parsed if g)

    @Slot(str, str, bool)
    def applyMudaeSettingsPreset(
        self,
        channel_profile_id: str,
        preset_id: str,
        dry_run: bool,
    ) -> None:
        if self._settings_apply_running:
            self._set_status("Settings apply already running")
            return
        if not self._loop or not self._actions or not self._monitor:
            self._set_status("Connect first")
            return
        if self._engine and self._engine.is_running:
            self._set_status("Stop the macro before applying settings")
            return

        bundle = self._channel_settings_bundle(channel_profile_id)
        preset = self._mudae_settings_presets.find(preset_id)
        if bundle is None or preset is None:
            self._set_status("Channel or preset not found")
            return
        channel, _cached_settings = bundle
        if channel.id != self._run_channel_profile_id:
            self._set_status("Select this channel on Run → Run target first")
            return
        if str(self._monitor.channel_id) != str(channel.channel_id):
            self._set_status("Connected channel does not match profile")
            return

        self._clear_settings_apply_log()
        self._settings_apply_running = True
        self.settingsApplyChanged.emit()
        prefix = str(channel.settings.get("prefix") or self._macro_config.prefix or "$")

        async def _run() -> None:
            runner = SettingsApplyRunner(
                self._actions,
                log=self._append_settings_apply_log,
                prefix=prefix,
                stop_check=lambda: not self._settings_apply_running,
            )
            try:
                current = normalize_settings_fields(dict(channel.settings or {}))
                if not current:
                    current = await runner.fetch_current_settings()
                premium = current.get("server_premium")
                result = await runner.apply(
                    preset.fields,
                    current=current,
                    dry_run=dry_run,
                    groups=self._settings_apply_groups,
                    server_premium=int(premium) if premium is not None else None,
                )
                if not dry_run and result.verified_fields:
                    channel.settings = dict(result.verified_fields)
                    timer = result.verified_fields.get("settimer")
                    if self._engine is not None and timer is not None:
                        self._engine.apply_settings_fields(result.verified_fields)
                    self._notify_servers()
                    self._persist()
                summary = (
                    f"Dry run: {result.applied_count} command(s)"
                    if dry_run
                    else f"Applied {result.applied_count} command(s)"
                )
                if result.remaining_mismatches:
                    summary += f"; still mismatched: {', '.join(result.remaining_mismatches)}"
                self._on_status(summary)
            except Exception as exc:  # noqa: BLE001
                self._append_settings_apply_log(f"Error: {exc}")
                self._on_status(f"Settings apply failed: {exc}")
            finally:
                self._settings_apply_running = False
                QMetaObject.invokeMethod(
                    self,
                    "_emit_settings_apply_done",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot()
    def _emit_settings_apply_done(self) -> None:
        self.settingsApplyChanged.emit()

    @Slot()
    def fetchSettings(self) -> None:
        self._send_mudae_command("settings")

    @Slot()
    def fetchBonus(self) -> None:
        self._send_mudae_command("bonus")

    @Slot()
    def fetchShop(self) -> None:
        self._send_mudae_command("shop")

    def _send_mudae_command(self, command: str) -> None:
        if not self._loop or not self._monitor:
            self._set_status("Connect first")
            return
        active = self._profiles.active_discord_channel_id()
        if not active:
            self._set_status("Select a channel first")
            return

        async def _run() -> None:
            if str(self._monitor.channel_id) != active:
                resolved = resolve_run_target(
                    self._accounts,
                    self._profiles,
                    self._presets,
                    self._targets,
                )
                if resolved is None:
                    self._on_status("Select a channel first")
                    return
                await self._apply_run_target_switch(resolved)
                if str(self._monitor.channel_id) != active:
                    self._on_status("Channel switch failed")
                    return
            await self._monitor.send_command(command)

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot(str, result=str)
    def formatMudaeCharacterList(self, text: str) -> str:
        return format_mudae_character_list(text)

    @Slot(str, result=str)
    def parseMudaeCharacterListJson(self, text: str) -> str:
        names = extract_character_names(text)
        return json.dumps({"names": names, "count": len(names), "formatted": "$".join(names)})

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    @Slot(result=str)
    def importLegacyConfig(self) -> str:
        from gui.import_legacy import import_legacy_config

        message = import_legacy_config(
            self._accounts,
            self._profiles,
            self._presets,
            self._targets,
        )
        self._sync_initial_target()
        self._apply_active_preset_to_engine()
        self._notify_config()
        self._persist()
        self._set_status(message)
        return message

    @Slot()
    def shutdown(self) -> None:
        self._persist()
        self.disconnect()
