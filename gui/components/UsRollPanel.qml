import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// $us mode: kakera override policy and batch sizing.
ColumnLayout {
    id: root
    spacing: 12

    Layout.fillWidth: true

    property var rules: ({})
    property var kakeraOptions: []
    property var onPatch: function(block, key, value) {}
    property var onPatchUsMode: function(key, value) {}

    function intField(block, key) {
        if (!rules[block])
            return ""
        var v = rules[block][key]
        return (v === null || v === undefined) ? "" : v.toString()
    }

    function parseIntOrNull(text) {
        if (!text || text.trim().length === 0)
            return null
        var n = parseInt(text)
        return isNaN(n) ? null : n
    }

    function boolField(block, key) {
        if (!rules[block])
            return false
        return !!rules[block][key]
    }

    function stringField(block, key, fallback) {
        if (!rules[block] || rules[block][key] === undefined || rules[block][key] === null)
            return fallback
        var s = String(rules[block][key]).trim()
        return s.length === 0 ? fallback : s
    }

    function parseLocalTime(text, fallback) {
        var raw = (text || "").trim()
        var m = raw.match(/^(\d{1,2})(?::(\d{2}))?$/)
        if (!m)
            return fallback
        var hour = parseInt(m[1], 10)
        var minute = m[2] !== undefined ? parseInt(m[2], 10) : 0
        if (hour > 23 || minute > 59)
            return fallback
        return (hour < 10 ? "0" : "") + hour + ":" + (minute < 10 ? "0" : "") + minute
    }

    PanelCard {
        Layout.fillWidth: true
        title: "Kakera on $us rolls"
        titleSize: 13

        Label {
            Layout.fillWidth: true
            text: "Hourly rolls always use the kakera settings on the Reactions tab. These options apply only to rolls added via $us. Perk-8 characters always follow the Reactions perk-8 color rules."
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        ThemedCheckBox {
            Layout.fillWidth: true
            text: "Use separate kakera rules for $us rolls"
            checked: rules.us_roll_kakera ? !!rules.us_roll_kakera.override : false
            onToggled: onPatch("us_roll_kakera", "override", checked)
        }

        ThemedCheckBox {
            Layout.fillWidth: true
            visible: rules.us_roll_kakera && !!rules.us_roll_kakera.override
            text: "Don't claim kakera on $us rolls"
            checked: rules.us_roll_kakera ? !!rules.us_roll_kakera.skip_kakera : false
            onToggled: onPatch("us_roll_kakera", "skip_kakera", checked)
        }

        ColorChipPicker {
            Layout.fillWidth: true
            visible: rules.us_roll_kakera && rules.us_roll_kakera.override
                && !rules.us_roll_kakera.skip_kakera
            title: "Kakera colors on $us rolls (none = any)"
            options: kakeraOptions
            selected: rules.us_roll_kakera ? (rules.us_roll_kakera.types_allowed || []) : []
            onSelectionChanged: function(ids) {
                onPatch("us_roll_kakera", "types_allowed", ids)
            }
        }
    }

    PanelCard {
        Layout.fillWidth: true
        title: "Batch sizing"
        titleSize: 13

        GridLayout {
            columns: 2
            columnSpacing: 12
            rowSpacing: 8
            Layout.fillWidth: true

            Label {
                text: "Rolls per $us command"
                color: Theme.fgSecondary
                font.pixelSize: 11
                Layout.preferredWidth: 180
                wrapMode: Text.WordWrap
            }
            ThemedTextField {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                placeholderText: "1–20"
                text: intField("us_mode", "us_batch_size") || "20"
                onEditingFinished: onPatchUsMode("us_batch_size", parseInt(text) || 20)
            }

            Label {
                text: "Stop adding $us this many minutes before reset"
                color: Theme.fgSecondary
                font.pixelSize: 11
                Layout.preferredWidth: 180
                wrapMode: Text.WordWrap
            }
            ThemedTextField {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                placeholderText: "e.g. 2"
                text: intField("us_mode", "us_reset_margin_minutes") || "2"
                onEditingFinished: onPatchUsMode("us_reset_margin_minutes", parseInt(text) || 2)
            }
        }
    }

    PanelCard {
        Layout.fillWidth: true
        title: "Drain policy"
        titleSize: 13

        Label {
            Layout.fillWidth: true
            text: "Roll $us on the Run page uses this preset. Manual quits when the stack is empty or a stop fires. Keep draining pauses on reset (and on power if that stop is on) instead of quitting. A session roll cap and a local schedule window are hard stops — leftover $us stays on the stack."
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        ThemedCheckBox {
            Layout.fillWidth: true
            text: "Keep draining (pause on reset / power instead of quitting)"
            checked: boolField("us_mode", "us_keep_draining")
            onToggled: onPatchUsMode("us_keep_draining", checked)
        }

        ThemedCheckBox {
            Layout.fillWidth: true
            text: "Stop when out of paid-kakera power ($dk counted)"
            checked: boolField("us_mode", "us_stop_on_power_exhausted")
            onToggled: onPatchUsMode("us_stop_on_power_exhausted", checked)
        }

        RowLayout {
            spacing: 6
            Layout.fillWidth: true

            ThemedCheckBox {
                id: presetStopAfterCheck
                text: "Stop after"
                checked: boolField("us_mode", "us_stop_after_rolls_enabled")
                onToggled: onPatchUsMode("us_stop_after_rolls_enabled", checked)
            }

            ThemedTextField {
                Layout.preferredWidth: 90
                Layout.preferredHeight: 32
                enabled: presetStopAfterCheck.checked
                placeholderText: "1000"
                text: intField("us_mode", "us_stop_after_rolls") || "100"
                onEditingFinished: onPatchUsMode("us_stop_after_rolls", parseInt(text) || 100)
            }

            Label {
                text: "rolls this session"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Item { Layout.fillWidth: true }
        }
    }

    PanelCard {
        Layout.fillWidth: true
        title: "Local schedule"
        titleSize: 13

        Label {
            Layout.fillWidth: true
            text: "Like $p and $daily: while connected, $us drains itself in this local-time window (not UTC). Roll $us on the Run page always starts immediately and ignores this window, even if a slot is set for later. Leftover hourly rolls still go first. When the end time hits, leftover $us stays on the stack. If hourly is waiting for a refill, scheduled $us takes over until the window or cap, then hourly continues."
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        ThemedCheckBox {
            Layout.fillWidth: true
            text: "Drain $us automatically in a local time window"
            checked: boolField("us_mode", "us_schedule_enabled")
            onToggled: onPatchUsMode("us_schedule_enabled", checked)
        }

        GridLayout {
            columns: 2
            columnSpacing: 12
            rowSpacing: 8
            Layout.fillWidth: true
            visible: boolField("us_mode", "us_schedule_enabled")

            Label {
                text: "Start (local)"
                color: Theme.fgSecondary
                font.pixelSize: 11
                Layout.preferredWidth: 180
            }
            ThemedTextField {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                placeholderText: "04:00"
                text: stringField("us_mode", "us_schedule_start", "04:00")
                onEditingFinished: onPatchUsMode("us_schedule_start", parseLocalTime(text, "04:00"))
            }

            Label {
                text: "End (local)"
                color: Theme.fgSecondary
                font.pixelSize: 11
                Layout.preferredWidth: 180
            }
            ThemedTextField {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                placeholderText: "06:00"
                text: stringField("us_mode", "us_schedule_end", "06:00")
                onEditingFinished: onPatchUsMode("us_schedule_end", parseLocalTime(text, "06:00"))
            }
        }
    }
}
