"""One-time import of existing Statistics JSON logs into events.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from mudae import event_log, kakera_log, soulmate_log


def _write_legacy(directory: Path) -> dict[str, list[dict]]:
    files = {
        "kakera": [{"amount": 420, "earn_method": "kakera_click", "date_key": "2026-08-01"}],
        "sphere": [{"amount": 9, "source": "sphere_click", "date_key": "2026-08-01"}],
        "key": [{"key_type": "chaos", "date_key": "2026-08-01"}],
        "soulmate": [{"character_name": "Alice", "time": "12:00:00"}],
    }
    for kind, rows in files.items():
        (directory / event_log.LEGACY_FILENAMES[kind]).write_text(
            json.dumps(rows, indent=2),
            encoding="utf-8",
        )
    return files


def test_first_launch_imports_legacy_json_and_leaves_files_untouched(tmp_path):
    originals = _write_legacy(tmp_path)

    event_log.load_from_data_dir(tmp_path)
    kakera_log._bind_events()
    soulmate_log._bind_events()

    assert event_log.imported_legacy() is True
    assert [row["amount"] for row in event_log.events("kakera")] == [420]
    assert [row["amount"] for row in event_log.events("sphere")] == [9]
    assert [row["key_type"] for row in event_log.events("key")] == ["chaos"]
    assert [row["character_name"] for row in event_log.events("soulmate")] == ["Alice"]
    assert kakera_log._events[0]["amount"] == 420

    jsonl = tmp_path / "events.jsonl"
    assert jsonl.is_file()
    kinds = [json.loads(line)["kind"] for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert kinds == ["kakera", "sphere", "key", "soulmate"]

    for kind, rows in originals.items():
        on_disk = json.loads((tmp_path / event_log.LEGACY_FILENAMES[kind]).read_text(encoding="utf-8"))
        assert on_disk == rows


def test_second_launch_uses_jsonl_and_does_not_duplicate(tmp_path):
    _write_legacy(tmp_path)
    event_log.load_from_data_dir(tmp_path)
    assert len(event_log.all_events()) == 4

    event_log.load_from_data_dir(tmp_path)
    assert event_log.imported_legacy() is False
    assert len(event_log.all_events()) == 4
    assert len(event_log.events("kakera")) == 1


def test_new_events_append_to_jsonl_not_legacy_json(tmp_path):
    originals = _write_legacy(tmp_path)
    event_log.load_from_data_dir(tmp_path)
    kakera_log._bind_events()

    event_log.append("kakera", {"amount": 7, "earn_method": "kakera_click"})
    event_log.flush()

    legacy = json.loads((tmp_path / "kakera_log.json").read_text(encoding="utf-8"))
    assert legacy == originals["kakera"]

    amounts = []
    for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("kind") == "kakera":
            amounts.append(row["amount"])
    assert amounts == [420, 7]
    assert [row["amount"] for row in kakera_log._events] == [420, 7]
