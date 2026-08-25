"""Field-by-field ``$settings`` parse vs SETTINGS_FIELD_KEYS + capture skip list."""

from __future__ import annotations

import re

from mudae.parsers.settings import SETTINGS_FIELD_KEYS, _command_keys, parse_settings
from mudae.parsers.settings_normalize import normalize_settings_fields
from mudae.settings_commands import (
    DIRECT_TOGGLE_FIELDS,
    HELP_ONLY_SETTINGS_FIELDS,
    capture_help_action,
)
from tests.mudae_sheet_fixtures import SETTINGS_GM1_PLAIN, SETTINGS_KS1_REPLY, SETTINGS_REPLY

_CMD_IN_TEXT_RE = re.compile(r"\(\$([^)]+)\)")

EXPECTED_KS0 = {
    "server_premium": 3,
    "prefix": "$",
    "lang": "en",
    "setclaim": 60,
    "setinterval": 0,
    "shifthour": 0,
    "setrolls": 21,
    "settimer": 45,
    "setrare": 10,
    "setkakerabonus": 100,
    "setspherebonus": 100,
    "gamemode": 2,
    "servlimroul": {"wa": 7000, "ha": 7000, "wg": 5000, "hg": 5000},
    "channelinstance": 1,
    "toggleslash": True,
    "toggleclaimrank": True,
    "togglelikerank": True,
    "togglerolls": "claims and likes",
    "toggleclaimrolls": True,
    "togglelikerolls": True,
    "togglensfw": True,
    "toggledisturbing": True,
    "togglechildtag": True,
    "togglesnipe": {"mode": 0, "seconds": None},
    "togglekakerasnipe": {"mode": 0, "seconds": None},
    "haremlimit": 12000,
    "removecopylimit": False,
    "togglebutton": 2,
    "claimreact": False,
    "kakerabutton": False,
    "spherebutton": False,
    "togglekakeratrade": True,
    "togglekakeraclaim": True,
    "togglekakeralike": True,
    "togglekakerarolls": True,
    "togglewishprotect": True,
    "togglewishfree": True,
    "togglespheretrade": True,
}

EXPECTED_KS1 = {
    "server_premium": None,
    "prefix": "$",
    "lang": "en",
    "setclaim": 180,
    "setinterval": 41,
    "shifthour": 0,
    "setrolls": 8,
    "settimer": 45,
    "setrare": 2,
    "setkakerabonus": 0,
    "setspherebonus": 0,
    "gamemode": 2,
    "servlimroul": {"wa": 47560, "ha": 48912, "wg": 35615, "hg": 30906},
    "channelinstance": 1,
    "toggleslash": True,
    "toggleclaimrank": True,
    "togglelikerank": True,
    "togglerolls": False,
    "toggleclaimrolls": False,
    "togglelikerolls": False,
    "togglensfw": True,
    "toggledisturbing": True,
    "togglechildtag": True,
    "togglesnipe": {"mode": 0, "seconds": None},
    "togglekakerasnipe": {"mode": 0, "seconds": None},
    "haremlimit": 12000,
    "removecopylimit": False,
    "togglebutton": 0,
    "claimreact": False,
    "kakerabutton": False,
    "spherebutton": False,
    "togglekakeratrade": True,
    "togglekakeraclaim": True,
    "togglekakeralike": True,
    "togglekakerarolls": False,
    "togglewishprotect": True,
    "togglewishfree": True,
    "togglespheretrade": True,
}


def test_settings_field_keys_cover_fixture_commands():
    for suffix in _CMD_IN_TEXT_RE.findall(SETTINGS_REPLY):
        for key in _command_keys(suffix):
            assert key in SETTINGS_FIELD_KEYS, key


def test_settings_ks0_every_field():
    result = parse_settings(SETTINGS_REPLY)
    assert not result.warnings
    assert set(EXPECTED_KS0) == set(SETTINGS_FIELD_KEYS)
    for key in SETTINGS_FIELD_KEYS:
        assert result.fields[key] == EXPECTED_KS0[key], key


def test_settings_ks1_every_field():
    result = parse_settings(SETTINGS_KS1_REPLY)
    assert not result.warnings
    for key in SETTINGS_FIELD_KEYS:
        assert result.fields[key] == EXPECTED_KS1[key], key


def test_settings_gm1_servlimroul_absent():
    result = parse_settings(SETTINGS_GM1_PLAIN)
    assert result.fields["gamemode"] == 1
    assert result.fields["servlimroul"] is None
    assert result.fields["togglebutton"] == 2
    assert result.fields["kakerabutton"] is False
    assert result.fields["spherebutton"] is False
    assert result.fields["claimreact"] is False


def test_normalize_legacy_ks1_stored_types():
    """Older channel.settings stored raw strings; normalize must coerce them."""
    raw = {
        "togglebutton": "for public wishes only",
        "servlimroul": "47,560 $wa, 48,912 $ha, 35,615 $wg, 30,906 $hg",
        "togglesnipe": 0,
        "togglekakerasnipe": 0,
        "togglerolls": False,
        "togglekakeraclaim": "claim and like ranks (and number of claimed characters)",
        "togglekakeralike": "claim and like ranks (and number of claimed characters)",
        "claimreact": "no",
        "kakerabutton": "no",
        "spherebutton": "no",
    }
    out = normalize_settings_fields(raw)
    assert out["togglebutton"] == 0
    assert out["servlimroul"] == {"wa": 47560, "ha": 48912, "wg": 35615, "hg": 30906}
    assert out["togglesnipe"] == {"mode": 0, "seconds": None}
    assert out["toggleclaimrolls"] is False
    assert out["togglelikerolls"] is False
    assert out["togglekakeraclaim"] is True
    assert out["togglekakeralike"] is True
    assert out["claimreact"] is False
    assert out["kakerabutton"] is False
    assert out["spherebutton"] is False


def test_unknown_settings_command_warns():
    result = parse_settings("· Brand new option: **1** ($brandnewcmd)\n")
    assert any("Unknown settings command" in w for w in result.warnings)
    assert result.fields["brandnewcmd"] == 1


def test_unparsed_settings_line_warns():
    result = parse_settings("· Decorative line with no command\n")
    assert any("Unparsed settings line" in w for w in result.warnings)


def test_direct_toggle_capture_skips_by_default():
    assert len(DIRECT_TOGGLE_FIELDS) == 16
    assert "togglerolls" not in DIRECT_TOGGLE_FIELDS
    assert HELP_ONLY_SETTINGS_FIELDS == frozenset({"togglerolls"})
    for field in DIRECT_TOGGLE_FIELDS:
        assert capture_help_action(field) == "skip"
        assert capture_help_action(field, include_toggles=True) == "send_and_revert"
    assert capture_help_action("togglerolls") == "send"
    assert capture_help_action("setrolls") == "send"
    assert capture_help_action("prefix") == "send"
