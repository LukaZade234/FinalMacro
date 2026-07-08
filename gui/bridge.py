"""Qt bridge between QML UI and Discord channel monitor."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Q_ARG, QMetaObject, Qt, QTimer, QUrl, Signal, Slot

from gui.accounts import AccountStore
from gui.presets import PresetStore
from gui.run_target import resolve_run_target
from gui.server_profiles import ServerProfileStore
from gui.settings import load_settings, save_app_settings
from gui.targets import TargetStore
from macro.actions import DiscordActions
from macro.activity_log import ActivityLog, activity_log_text
from macro.config import MacroConfig
from macro.roll_cycle import RollCycleEngine
from macro.sphere_game import OhSphereGame
from macro.oc_game import OcSphereGame
from macro.oq_game import OqSphereGame
from macro.state import AccountState, MacroPhase
from mudae.discord_reader import ChannelMonitor
from mudae.parsers.settings import SETTINGS_FIELD_KEYS
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

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
    if parsed.kind != MessageKind.COMMAND_RESPONSE:
        return None
    parser_cmd = str(parsed.fields.get("parser_command") or "").lower().lstrip("$")
    if parser_cmd in {"settings", "bonus"}:
        return parser_cmd
    label = str(parsed.fields.get("response_label") or "").lower()
    if "settings" in label:
        return "settings"
    if "bonus" in label:
        return "bonus"
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
    runActionPendingChanged = Signal()
    macroPhaseChanged = Signal(str)
    macroStateChanged = Signal()
    macroLogChanged = Signal()
    serversChanged = Signal()
    configChanged = Signal()
    soulmatesChanged = Signal()
    kakeraChanged = Signal()
    spheresChanged = Signal()
    keysChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        saved = load_settings()
        self._profiles = ServerProfileStore()
        self._profiles.load_from_settings(saved)
        self._accounts = AccountStore()
        self._accounts.load_from_settings(saved)
        self._presets = PresetStore()
        self._presets.load_from_settings(saved)
        self._targets = TargetStore()
        self._targets.load_from_settings(saved)
        self._sync_initial_target()
        self._macro_config = self._presets.active_preset()
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
        self._servers_emit_pending = False
        self._config_emit_pending = False
        self._run_guild_id: int | None = None
        self._run_guild_name: str | None = None
        self._run_channel_name: str | None = None
        self._run_account_name: str = ""

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

    @Property(str, constant=False, notify=macroStateChanged)
    def macroClaimStatus(self) -> str:
        return self._macro_state.claim_label()

    @Property(int, constant=False, notify=macroStateChanged)
    def macroPowerPercent(self) -> int:
        from macro.reaction_power import display_reaction_power

        return display_reaction_power(self._macro_state.power_percent)

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

    @Property(str, constant=False, notify=configChanged)
    def runTargetLabel(self) -> str:
        resolved = resolve_run_target(
            self._accounts, self._profiles, self._presets, self._targets
        )
        return resolved.label if resolved else ""

    @Property(str, constant=False, notify=soulmatesChanged)
    def soulmatesJson(self) -> str:
        from mudae.soulmate_log import events_for_client

        return json.dumps(events_for_client(self._accounts))

    @Property(str, constant=False, notify=kakeraChanged)
    def kakeraJson(self) -> str:
        from mudae.kakera_log import client_payload

        return json.dumps(client_payload(self._accounts))

    @Property(str, constant=False, notify=spheresChanged)
    def spheresJson(self) -> str:
        from mudae.sphere_log import client_payload

        return json.dumps(client_payload(self._accounts))

    @Property(str, constant=False, notify=keysChanged)
    def keysJson(self) -> str:
        from mudae.key_log import client_payload

        return json.dumps(client_payload(self._accounts))

    def _sync_initial_target(self) -> None:
        account = self._accounts.active_account()
        channel = self._profiles.active_channel()
        if account and channel and not self._targets.find_target(account.id, channel.id):
            self._targets.ensure_target(
                account.id,
                channel.id,
                self._presets.active_preset_id,
            )

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

    def _apply_active_preset_to_engine(self) -> None:
        self._macro_config = self._presets.active_preset()
        if self._engine:
            self._engine.update_config(self._macro_config)

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
        elif pending == "oh" and not self._oh_running:
            self._set_run_action_pending("")
        elif pending == "oc" and not self._oc_running:
            self._set_run_action_pending("")
        elif pending == "oq" and not self._oq_running:
            self._set_run_action_pending("")

    def _notify_macro(self) -> None:
        self._sync_run_action_pending()
        self.macroPhaseChanged.emit(self._macro_state.phase.value)
        self.macroStateChanged.emit()
        self.macroLogChanged.emit()

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
        else:
            data[key] = value
        self._presets.update_preset(preset_id, MacroConfig.from_dict(data))
        if preset_id == self._presets.active_preset_id:
            self._apply_active_preset_to_engine()
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
                    "claim_expire_sec": data["claim_expire_sec"],
                    "claim_reset_margin_minutes": data["claim_reset_margin_minutes"],
                },
                "character_claim": data["character_claim"],
                "kakera_reaction": data["kakera_reaction"],
                "sphere_reaction": data["sphere_reaction"],
                "us_roll_kakera": data["us_roll_kakera"],
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
                "claim_expire_sec",
                "claim_reset_margin_minutes",
            ):
                if key in basic_patch:
                    data[key] = basic_patch[key]

        for block in ("character_claim", "kakera_reaction", "sphere_reaction", "us_roll_kakera"):
            block_patch = patch.get(block)
            if isinstance(block_patch, dict):
                current = data.get(block) or {}
                if not isinstance(current, dict):
                    current = {}
                data[block] = _deep_merge(current, block_patch)

        self._presets.update_preset(preset_id, MacroConfig.from_dict(data))
        if preset_id == self._presets.active_preset_id:
            self._apply_active_preset_to_engine()
        self._notify_config()
        self._persist()

    def _persist(self) -> None:
        save_app_settings(
            accounts=self._accounts.to_settings_fragment(),
            presets=self._presets.to_settings_fragment(),
            targets=self._targets.to_settings_fragment(),
            servers=self._profiles.to_settings_fragment(),
        )

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
        if not value and self._status.startswith("Connected"):
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

    @Slot()
    def _deliver_soulmates_notify(self) -> None:
        self.soulmatesChanged.emit()

    @Slot()
    def _deliver_kakera_notify(self) -> None:
        self.kakeraChanged.emit()

    @Slot()
    def _deliver_spheres_notify(self) -> None:
        self.spheresChanged.emit()

    @Slot()
    def _deliver_keys_notify(self) -> None:
        self.keysChanged.emit()

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
        self._macro_config = resolved.macro_config
        channel_id = self._parse_int(resolved.discord_channel_id, "channel ID")
        run_account_id = resolved.account_id
        run_channel_profile_id = resolved.channel_profile_id

        from mudae.kakera_log import set_recording_account as set_kakera_account
        from mudae.key_log import set_recording_account as set_key_account
        from mudae.soulmate_log import set_recording_account
        from mudae.sphere_log import set_recording_account as set_sphere_account

        account = self._accounts.find_account(run_account_id)
        account_name = account.name if account else "Main"
        self._run_account_name = account_name
        set_recording_account(run_account_id, account_name)
        set_kakera_account(run_account_id, account_name)
        set_key_account(run_account_id, account_name)
        set_sphere_account(run_account_id, account_name)

        channel_profile = self._profiles.active_channel()
        server = self._profiles.find_server(self._profiles.active_server_id)
        self._run_channel_name = channel_profile.name if channel_profile else None
        self._run_guild_name = (
            (channel_profile.guild_name if channel_profile else None)
            or (server.name if server else None)
        )
        guild_raw = None
        if channel_profile and channel_profile.guild_id:
            guild_raw = channel_profile.guild_id
        elif server and server.guild_id:
            guild_raw = server.guild_id
        try:
            self._run_guild_id = int(guild_raw) if guild_raw else None
        except (TypeError, ValueError):
            self._run_guild_id = None

        self._monitor = ChannelMonitor(
            token=resolved.token,
            channel_id=channel_id,
            on_entry=self._on_entry,
            on_status=self._on_status,
            on_parsed=self._on_parsed,
        )
        self._actions = DiscordActions(self._monitor)
        self._engine = RollCycleEngine(
            self._actions,
            self._macro_config,
            self._macro_state,
            self._monitor,
            on_state=self._on_macro_state,
            on_keys=self._on_keys_recorded,
            on_persist=self._request_persist,
            daily_resets_get=lambda: self._get_daily_resets_for(
                run_account_id,
                run_channel_profile_id,
            ),
            daily_resets_save=lambda daily: self._save_daily_resets_for(
                run_account_id,
                run_channel_profile_id,
                daily,
            ),
        )

        async def runner() -> None:
            connect_task = asyncio.create_task(self._monitor.connect())
            ready = await self._monitor.wait_ready(timeout=30.0)
            if connect_task.done():
                exc = connect_task.exception()
                if exc is not None:
                    raise exc
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
            if self._engine and self._engine.is_running:
                self._engine.stop()
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

            clear_recording_account()
            clear_soulmate_account()
            clear_key_account()
            clear_sphere_account()
            flush_disk_log()
            flush_key_log()
            flush_sphere_log()
            self._run_guild_id = None
            self._run_guild_name = None
            self._run_channel_name = None
            self._run_account_name = ""
            loop.close()
            self._loop = None

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
        self._persist()
        self._macro_state = AccountState()
        self._set_connecting(True)
        self._set_status("Connecting…")
        self._thread = threading.Thread(
            target=self._reader_thread_main,
            name="channel-monitor",
            daemon=True,
        )
        self._thread.start()

    @Slot()
    def disconnect(self) -> None:
        if self._loop and self._stop_event:
            self._set_disconnecting(True)
            self._set_status("Disconnecting…")
            self._loop.call_soon_threadsafe(self._stop_event.set)
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

    @Slot()
    def startMacro(self) -> None:
        if not self._loop or not self._engine:
            self._set_status("Connect first")
            return
        if self._engine.is_running:
            self._set_status("Macro already running")
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
        if self._oh_running or self._oc_running or self._oq_running:
            self._set_status("Stop the minigame before rolling $us")
            return
        self._persist()
        self._engine.update_config(self._macro_config)
        self._set_run_action_pending("us")
        meta = self._session_meta()

        def _start() -> None:
            self._engine.start_us_mode(session_meta=meta)

        self._loop.call_soon_threadsafe(_start)

    @Slot()
    def stopMacro(self) -> None:
        if self._engine and self._loop:
            self._set_run_action_pending("stop")
            self._loop.call_soon_threadsafe(self._engine.stop)

    @Slot()
    def playOhSphere(self) -> None:
        if not self._loop or not self._actions or not self._monitor:
            self._set_status("Connect first")
            return
        if self._engine and self._engine.is_running:
            self._set_status("Stop the macro before playing $oh")
            return
        if self._oh_running or self._oc_running or self._oq_running:
            self._set_status("Stop the minigame before playing $oh")
            return

        activity, recorder = self._begin_minigame_session("oh")
        game = OhSphereGame(self._actions, self._monitor, log=activity.write)
        self._oh_running = True
        self._set_run_action_pending("oh")

        async def _run() -> None:
            reason = "finished"
            try:
                result = await game.play(prefix=self._macro_config.prefix)
                reward = int(result.get("reward") or 0)
                clicks = int(result.get("clicks") or 0)
                if reward > 0:
                    self._record_minigame_spheres("oh", reward, clicks=clicks)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"$oh error: {exc}")
            finally:
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
        if not self._loop or not self._actions or not self._monitor:
            self._set_status("Connect first")
            return
        if self._engine and self._engine.is_running:
            self._set_status("Stop the macro before playing $oc")
            return
        if self._oh_running or self._oc_running or self._oq_running:
            self._set_status("Stop the minigame before playing $oc")
            return

        activity, recorder = self._begin_minigame_session("oc")
        game = OcSphereGame(self._actions, self._monitor, log=activity.write)
        self._oc_running = True
        self._set_run_action_pending("oc")

        async def _run() -> None:
            reason = "finished"
            try:
                result = await game.play(prefix=self._macro_config.prefix)
                reward = int(result.get("reward") or 0)
                clicks = int(result.get("clicks") or 0)
                if reward > 0:
                    self._record_minigame_spheres("oc", reward, clicks=clicks)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"$oc error: {exc}")
            finally:
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
        if not self._loop or not self._actions or not self._monitor:
            self._set_status("Connect first")
            return
        if self._engine and self._engine.is_running:
            self._set_status("Stop the macro before playing $oq")
            return
        if self._oh_running or self._oc_running or self._oq_running:
            self._set_status("Stop the minigame before playing $oq")
            return

        activity, recorder = self._begin_minigame_session("oq")
        game = OqSphereGame(self._actions, self._monitor, log=activity.write)
        self._oq_running = True
        self._set_run_action_pending("oq")

        async def _run() -> None:
            reason = "finished"
            try:
                result = await game.play(prefix=self._macro_config.prefix)
                reward = int(result.get("reward") or 0)
                clicks = int(result.get("clicks") or 0)
                if reward > 0:
                    self._record_minigame_spheres("oq", reward, clicks=clicks)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                reason = "error"
                activity.write(f"$oq error: {exc}")
            finally:
                self._finish_minigame_session(activity, recorder, reason)
                self._oq_running = False
                QMetaObject.invokeMethod(
                    self,
                    "_clear_run_action_pending",
                    Qt.ConnectionType.QueuedConnection,
                )

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    @Slot()
    def fetchSettings(self) -> None:
        self._send_mudae_command("settings")

    @Slot()
    def fetchBonus(self) -> None:
        self._send_mudae_command("bonus")

    def _send_mudae_command(self, command: str) -> None:
        if not self._loop or not self._monitor:
            self._set_status("Connect first")
            return
        active = self._profiles.active_discord_channel_id()
        if not active:
            self._set_status("Select a channel first")
            return
        if str(self._monitor.channel_id) != active:
            self._set_status("Connected channel does not match selection")
            return

        async def _run() -> None:
            await self._monitor.send_command(command)

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

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
