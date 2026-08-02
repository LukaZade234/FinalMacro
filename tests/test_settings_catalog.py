"""Tests for Mudae settings catalog display and coercion."""

from mudae.settings_catalog import (
    coerce_editor_value,
    fields_to_display_dict,
    format_field_value,
    format_settings_line,
    merge_preset_fields,
)


def test_format_togglebutton():
    assert format_field_value("togglebutton", 2) == "for all your rolls"


def test_format_servlimroul():
    limits = {"wa": 7000, "ha": 7000, "wg": 5000, "hg": 5000}
    text = format_field_value("servlimroul", limits)
    assert "7,000 $wa" in text
    assert "5,000 $hg" in text


def test_format_settings_line():
    line = format_settings_line("setrolls", 21)
    assert "Rolls per hour" in line
    assert "21" in line
    assert "$setrolls" in line


def test_fields_to_display_dict_sections():
    payload = fields_to_display_dict({"setrolls": 21, "togglebutton": 2})
    sections = payload["sections"]
    assert any(section["id"] == "rolls" for section in sections)
    rolls = next(section for section in sections if section["id"] == "rolls")
    rolls_row = next(row for row in rolls["rows"] if row["field"] == "setrolls")
    assert rolls_row["display"] == "21"
    assert rolls_row["has_value"] is True


def test_coerce_snipe():
    value = coerce_editor_value("togglesnipe", {"mode": 2, "seconds": 5.5})
    assert value == {"mode": 2, "seconds": 5.5}


def test_merge_preset_fields():
    merged = merge_preset_fields({"setrolls": 8}, {"setrolls": 21, "togglebutton": 2})
    assert merged["setrolls"] == 21
    assert merged["togglebutton"] == 2
