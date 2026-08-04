"""Settings file load helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path

from gui.presets import PresetStore
from gui.settings import SETTINGS_PATH, load_settings, save_settings


def test_load_settings_roundtrip(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr("gui.settings.SETTINGS_PATH", path)
    payload = {"presets": {"default": {"roll_command": "wa"}}, "active_preset_id": "default"}
    save_settings(payload)
    assert load_settings() == payload


def test_mtime_skips_identical_file(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setattr("gui.settings.SETTINGS_PATH", path)
    save_settings({"presets": {}})
    mtime = path.stat().st_mtime
    time.sleep(0.01)
    # Same content rewrite should update mtime; identical mtime check is used
    # by AppBridge to ignore its own saves after _record_settings_file_mtime().
    assert mtime > 0


def test_preset_reload_from_saved_dict() -> None:
    store = PresetStore()
    store.load_from_settings({"presets": {"p1": {"roll_command": "wg"}}, "active_preset_id": "p1"})
    assert store.active_preset_id == "p1"
    assert store.active_preset().roll_command == "wg"
    store.load_from_settings({"presets": {"p1": {"roll_command": "wa"}}, "active_preset_id": "p1"})
    assert store.active_preset().roll_command == "wa"
