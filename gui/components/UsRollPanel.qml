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
}
