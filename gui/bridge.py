"""Qt bridge between QML UI and Discord channel monitor."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Q_ARG, QMetaObject, Qt, QUrl, Signal, Slot

from gui.accounts import AccountStore
from gui.presets import PresetStore
from gui.run_target import resolve_run_target
from gui.server_profiles import ServerProfileStore
from gui.settings import load_settings, save_app_settings
from gui.targets import TargetStore
from macro.actions import DiscordActions
from macro.activity_log import ActivityLog
from macro.config import MacroConfig
from macro.roll_cycle import RollCycleEngine
from macro.sphere_game import OhSphereGame
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
    macroPhaseChanged = Signal(str)
    macroStateChanged = Signal()
    macroLogChanged = Signal()
    serversChanged = Signal()
    configChanged = Signal()

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
        self._status = "Idle"
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._monitor: ChannelMonitor | None = None
        self._actions: DiscordActions | None = None
        self._engine: RollCycleEngine | None = None
        self._stop_event: asyncio.Event | None = None
        self._parse_lab_entries: list[dict[str, Any]] = []
        self._oh_running = False

    @Property(str, constant=False, notify=statusChanged)
    def statusText(self) -> str:
        return self._status

    @Property(bool, constant=False, notify=connectedChanged)
    def connected(self) -> bool:
        return self._connected

    @Property(str, constant=False, notify=macroPhaseChanged)
    def macroPhase(self) -> str:
        return self._macro_state.phase.value

    @Property(str, constant=False, notify=macroStateChanged)
    def macroStateJson(self) -> str:
        return json.dumps(self._macro_state.to_dict())

    @Property(str, constant=False, notify=macroLogChanged)
    def macroActivityLog(self) -> str:
        return "\n".join(self._macro_state.activity_log)

    @Property(str, constant=False, notify=macroLogChanged)
    def ruleTraceJson(self) -> str:
        return json.dumps([entry.to_dict() for entry in self._macro_state.rule_trace[-12:]])

    @Property(int, constant=False, notify=macroStateChanged)
    def macroRollsLeft(self) -> int:
        return self._macro_state.rolls_left if self._macro_state.rolls_left is not None else -1

    @Property(str, constant=False, notify=macroStateChanged)
    def macroClaimStatus(self) -> str:
        return self._macro_state.claim_label()

    @Property(int, constant=False, notify=macroStateChanged)
    def macroPowerPercent(self) -> int:
        return self._macro_state.power_percent if self._macro_state.power_percent is not None else -1

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
        self.serversChanged.emit()

    def _notify_config(self) -> None:
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

    def _notify_macro(self) -> None:
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
        elif key == "rolls_left_stop":
            data[key] = int(value) if value.strip().isdigit() else data.get(key, 0)
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
                    "rolls_left_stop": data["rolls_left_stop"],
                    "claim_expire_sec": data["claim_expire_sec"],
                    "claim_reset_margin_minutes": data["claim_reset_margin_minutes"],
                },
                "character_claim": data["character_claim"],
                "kakera_reaction": data["kakera_reaction"],
                "sphere_reaction": data["sphere_reaction"],
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
                "rolls_left_stop",
                "claim_expire_sec",
                "claim_reset_margin_minutes",
            ):
                if key in basic_patch:
                    data[key] = basic_patch[key]

        for block in ("character_claim", "kakera_reaction", "sphere_reaction"):
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
            on_persist=self._persist,
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
    def runTu(self) -> None:
        if not self._loop or not self._engine:
            self._set_status("Connect first")
            return
        self._persist()
        self._engine.update_config(self._macro_config)

        async def _run() -> None:
            await self._engine.run_tu()

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

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
        self._loop.call_soon_threadsafe(self._engine.start)

    @Slot()
    def stopMacro(self) -> None:
        if self._engine and self._loop:
            self._loop.call_soon_threadsafe(self._engine.stop)

    @Slot()
    def playOhSphere(self) -> None:
        if not self._loop or not self._actions or not self._monitor:
            self._set_status("Connect first")
            return
        if self._engine and self._engine.is_running:
            self._set_status("Stop the macro before playing $oh")
            return
        if self._oh_running:
            self._set_status("$oh game already running")
            return

        activity = ActivityLog(self._macro_state, on_update=self._notify_macro)
        game = OhSphereGame(self._actions, self._monitor, log=activity.write)
        self._oh_running = True

        async def _run() -> None:
            try:
                await game.play(prefix=self._macro_config.prefix)
            except Exception as exc:  # noqa: BLE001 - surface to the activity log
                activity.write(f"$oh error: {exc}")
            finally:
                self._oh_running = False

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
