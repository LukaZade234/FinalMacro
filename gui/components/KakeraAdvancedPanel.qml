import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Grouped advanced kakera filters (perk-8 budget, low power, $us rolls, etc.).
ColumnLayout {
    id: root
    spacing: 12

    property var rules: ({})
    property var kakeraOptions: []
    property var onPatch: function(block, key, value) {}
    property var onPatchLowPower: function(key, value) {}
    property var onSetLowPowerEnabled: function(on) {}

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

    // --- Additional filters ---
    Rectangle {
        Layout.fillWidth: true
        radius: 8
        color: Theme.bgDark
        border.color: Theme.border
        implicitHeight: filtersCol.implicitHeight + 16

        ColumnLayout {
            id: filtersCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 10
            spacing: 8

            Label {
                text: "Additional filters"
                color: Theme.fgPrimary
                font.pixelSize: 12
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }

            ThemedCheckBox {
                Layout.fillWidth: true
                text: "Require perk 8 character"
                checked: rules.kakera_reaction ? !!rules.kakera_reaction.require_perk_8 : false
                onToggled: onPatch("kakera_reaction", "require_perk_8", checked)
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 12
                rowSpacing: 8

                Label {
                    text: "Min spheres on roll"
                    color: Theme.fgSecondary
                    font.pixelSize: 11
                    Layout.preferredWidth: 180
                }
                ThemedTextField {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    placeholderText: "off"
                    text: intField("kakera_reaction", "min_spheres")
                    onEditingFinished: onPatch("kakera_reaction", "min_spheres", parseIntOrNull(text))
                }
            }
        }
    }

    // --- Perk-8 budget ---
    Rectangle {
        Layout.fillWidth: true
        radius: 8
        color: Theme.bgDark
        border.color: Theme.border
        implicitHeight: perk8Col.implicitHeight + 16

        ColumnLayout {
            id: perk8Col
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 10
            spacing: 8

            Label {
                text: "Perk-8 budget"
                color: Theme.fgPrimary
                font.pixelSize: 12
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }

            Label {
                Layout.fillWidth: true
                text: "Save daily clicks for perk-8 rolls. Other rolls use the main color filter once the budget is used up."
                color: Theme.fgMuted
                font.pixelSize: 10
                wrapMode: Text.WordWrap
            }

            ThemedCheckBox {
                Layout.fillWidth: true
                text: "Save daily clicks for perk-8 rolls, then click equally"
                checked: rules.kakera_reaction ? !!rules.kakera_reaction.perk_8_budget_mode : false
                onToggled: onPatch("kakera_reaction", "perk_8_budget_mode", checked)
            }

            ColorChipPicker {
                Layout.fillWidth: true
                visible: rules.kakera_reaction && !!rules.kakera_reaction.perk_8_budget_mode
                title: "Kakera colors on perk 8 characters (none = any)"
                options: kakeraOptions
                selected: rules.kakera_reaction
                    ? (rules.kakera_reaction.perk_8_types_allowed || [])
                    : []
                onSelectionChanged: function(ids) {
                    onPatch("kakera_reaction", "perk_8_types_allowed", ids)
                }
            }

            ColorChipPicker {
                Layout.fillWidth: true
                visible: rules.kakera_reaction && !!rules.kakera_reaction.perk_8_budget_mode
                title: "Always click during budget saving (ignore perk-8 limit)"
                options: kakeraOptions
                selected: rules.kakera_reaction
                    ? (rules.kakera_reaction.perk_8_budget_bypass_types || ["kakeraP"])
                    : ["kakeraP"]
                onSelectionChanged: function(ids) {
                    onPatch("kakera_reaction", "perk_8_budget_bypass_types", ids)
                }
            }

            ThemedCheckBox {
                Layout.fillWidth: true
                visible: rules.kakera_reaction && !!rules.kakera_reaction.perk_8_budget_mode
                text: "Smart power and $dk saving"
                checked: rules.kakera_reaction
                    ? rules.kakera_reaction.perk_8_power_save !== false
                    : true
                onToggled: onPatch("kakera_reaction", "perk_8_power_save", checked)
            }

            Label {
                Layout.fillWidth: true
                visible: rules.kakera_reaction && !!rules.kakera_reaction.perk_8_budget_mode
                text: "Off keeps the old click and $dk rules. On keeps a full perk-8 dump payable in the first N hours after UTC midnight (the daily reset). Today's leftover clicks still expire at midnight, so they always get power and $dk first. After 40/40, normal kakera still click; $dk on those only if a new use is back by midnight. Purple stays free."
                color: Theme.fgMuted
                font.pixelSize: 10
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                visible: rules.kakera_reaction && !!rules.kakera_reaction.perk_8_budget_mode
                    && rules.kakera_reaction.perk_8_power_save !== false
                Label {
                    text: "Hours after daily reset"
                    color: Theme.fgSecondary
                    font.pixelSize: 11
                }
                ThemedSpinBox {
                    from: 1
                    to: 12
                    value: (rules.kakera_reaction && rules.kakera_reaction.perk_8_power_window_hours)
                        ? Math.round(rules.kakera_reaction.perk_8_power_window_hours)
                        : 4
                    onValueModified: onPatch("kakera_reaction", "perk_8_power_window_hours", value)
                }
                Item { Layout.fillWidth: true }
            }

            Label {
                Layout.fillWidth: true
                visible: rules.kakera_reaction && !!rules.kakera_reaction.perk_8_budget_mode
                    && rules.kakera_reaction.perk_8_power_save !== false
                text: "How long after midnight a 40-click perk-8 dump should still be payable. Not a stop time — slow perk-8 keeps rolling until 40/40 or reset."
                color: Theme.fgMuted
                font.pixelSize: 10
                wrapMode: Text.WordWrap
            }
        }
    }

    // --- Low power ---
    Rectangle {
        Layout.fillWidth: true
        radius: 8
        color: Theme.bgDark
        border.color: Theme.border
        implicitHeight: lpCol.implicitHeight + 16

        ColumnLayout {
            id: lpCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 10
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: "Low-power override"
                    color: Theme.fgPrimary
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                ThemedSwitch {
                    checked: rules.kakera_reaction
                        && rules.kakera_reaction.low_power !== null
                        && rules.kakera_reaction.low_power !== undefined
                    onToggled: onSetLowPowerEnabled(checked)
                }
            }

            Label {
                visible: rules.kakera_reaction && rules.kakera_reaction.low_power
                text: "When power drops below the threshold, only these colors are clicked."
                color: Theme.fgMuted
                font.pixelSize: 10
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            RowLayout {
                visible: rules.kakera_reaction && rules.kakera_reaction.low_power
                Layout.fillWidth: true
                Label { text: "Below power %"; color: Theme.fgSecondary; font.pixelSize: 11 }
                ThemedSpinBox {
                    from: 0
                    to: 100
                    value: (rules.kakera_reaction && rules.kakera_reaction.low_power)
                        ? (rules.kakera_reaction.low_power.below_percent || 30)
                        : 30
                    onValueModified: onPatchLowPower("below_percent", value)
                }
                Item { Layout.fillWidth: true }
            }

            ColorChipPicker {
                Layout.fillWidth: true
                visible: rules.kakera_reaction && rules.kakera_reaction.low_power
                title: "Allowed colors when low power"
                options: kakeraOptions
                selected: (rules.kakera_reaction && rules.kakera_reaction.low_power)
                    ? (rules.kakera_reaction.low_power.types_allowed || [])
                    : []
                onSelectionChanged: function(ids) {
                    onPatchLowPower("types_allowed", ids)
                }
            }
        }
    }
}
