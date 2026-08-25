"""Tests for Mudae settings preset diff and command building."""

from __future__ import annotations

from mudae.parsers.settings import parse_settings
from mudae.parsers.settings_normalize import normalize_settings_fields
from mudae.settings_commands import (
    build_command_for_field,
    commands_from_diff,
    compliance_status,
    diff_settings,
    validate_preset_for_premium,
)
from tests.mudae_sheet_fixtures import SETTINGS_REPLY


def _key_server_fields() -> dict:
    result = parse_settings(SETTINGS_REPLY)
    return dict(result.fields)


def test_togglebutton_normalized_to_enum():
    fields = _key_server_fields()
    assert fields["togglebutton"] == 2


def test_servlimroul_structured():
    fields = _key_server_fields()
    assert fields["servlimroul"]["wa"] == 7000


def test_diff_generates_setter_commands():
    current = _key_server_fields()
    desired = dict(current)
    desired["setrolls"] = 16
    items = diff_settings(current, desired)
    rolls = next(i for i in items if i.field == "setrolls")
    assert rolls.command == "$setrolls 16"


def test_diff_skips_matching_fields():
    current = _key_server_fields()
    items = diff_settings(current, current)
    assert commands_from_diff(items) == []


def test_toggle_flip_command():
    current = _key_server_fields()
    desired = dict(current)
    desired["togglensfw"] = False
    cmd, _ = build_command_for_field(
        "togglensfw",
        current=current["togglensfw"],
        desired=False,
    )
    assert cmd == "$togglensfw"


def test_togglebutton_enum_command():
    cmd, _ = build_command_for_field(
        "togglebutton",
        current=0,
        desired=2,
    )
    assert cmd == "$togglebutton 2"


def test_servlimroul_command():
    limits = {"wa": 7000, "ha": 7000, "wg": 5000, "hg": 5000}
    cmd, _ = build_command_for_field(
        "servlimroul",
        current={"wa": 1, "ha": 1, "wg": 1, "hg": 1},
        desired=limits,
    )
    assert cmd == "$servlimroul 7000 7000 5000 5000"


def test_premium_validation_blocks_high_rolls():
    warnings = validate_preset_for_premium({"setrolls": 21}, server_premium=1)
    assert warnings


def test_compliance_match():
    fields = _key_server_fields()
    assert compliance_status(fields, fields) == "match"


def test_normalize_preserves_toggleclaimrolls():
    raw = normalize_settings_fields({"togglerolls": "claims and likes"})
    assert raw["toggleclaimrolls"] is True
    assert raw["togglelikerolls"] is True
