pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Adaptive perk-9 threshold. Spawn rates and values are measured constants, so
// they are shown but not editable; the ladder preview is the Python DP's own
// output so the panel can never drift from the live decision.
ColumnLayout {
    id: root

    property var rules: null
    property string presetId: ""

    signal fieldChanged(string key, var value)

    readonly property bool on: !!(rules && rules.budget_aware)
    readonly property var colourOrder: ["spB", "spT", "spG", "spY", "spL", "spO", "spD", "spR", "spW"]

    readonly property int colColour: 104
    readonly property int colNumber: 66

    property var preview: ({})

    spacing: 8

    function num(map, emoji, digits) {
        if (!map || map[emoji] === undefined || map[emoji] === null)
            return "—"
        return Number(map[emoji]).toFixed(digits)
    }

    function estimateText() {
        var e = preview ? preview.estimate : null
        if (!e)
            return "Connect and run $ohu9 to read this from Mudae."
        if (e.manual > 0)
            return "Using your override of " + e.manual + " spawns per day."
        if (e.pool !== null && e.pool !== undefined
                && e.rolled !== null && e.rolled !== undefined)
            return "Last known from $ohu9: " + e.rolled + " of " + e.pool
                + " rolled, so " + (e.pool - e.rolled) + " spawns left today."
        if (e.value !== null && e.value !== undefined)
            return "Estimated from rolls left today: " + e.value + " spawns."
        return "Not known yet — $ohu9 has not been read this session."
    }

    function refreshPreview() {
        if (!on || !presetId) {
            preview = ({})
            return
        }
        try {
            preview = JSON.parse(App.perk9ThresholdPreview(presetId, 0))
        } catch (e) {
            preview = ({})
        }
    }

    onOnChanged: refreshPreview()
    onPresetIdChanged: refreshPreview()
    Component.onCompleted: refreshPreview()

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Label {
            Layout.fillWidth: true
            text: "Spend the daily clicks by expected value"
            color: Theme.fgSecondary
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }

        ThemedSwitch {
            checked: root.on
            onToggled: root.fieldChanged("budget_aware", checked)
        }
    }

    Label {
        Layout.fillWidth: true
        text: "Skip cheap spheres while plenty of perk-9 characters are still coming, "
            + "then take anything rather than let clicks expire at the UTC reset. "
            + "The bar falls on its own as the day runs out."
        color: Theme.fgMuted
        font.pixelSize: 10
        wrapMode: Text.WordWrap
    }

    ColumnLayout {
        Layout.fillWidth: true
        visible: root.on
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Label {
                Layout.fillWidth: true
                text: "Expected perk-9 spawns per day (0 = read from $ohu9)"
                color: Theme.fgSecondary
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            ThemedSpinBox {
                from: 0
                to: 2000
                stepSize: 10
                value: root.rules ? (root.rules.expected_daily_opportunities || 0) : 0
                onValueModified: root.fieldChanged("expected_daily_opportunities", value)
            }
        }

        Label {
            Layout.fillWidth: true
            text: root.estimateText()
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            Layout.topMargin: 4
            text: "Spawn rate and value per colour"
            color: Theme.fgSecondary
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }

        Label {
            Layout.fillWidth: true
            text: "EV folds in this account's sphere double chance, flat bonus, "
                + "and OP9 value from $bonus / $shop."
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                Layout.preferredWidth: root.colColour
                text: "Colour"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Label {
                Layout.preferredWidth: root.colNumber
                horizontalAlignment: Text.AlignRight
                text: "Spawn %"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Label {
                Layout.preferredWidth: root.colNumber
                horizontalAlignment: Text.AlignRight
                text: "Base SP"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Label {
                Layout.preferredWidth: root.colNumber
                horizontalAlignment: Text.AlignRight
                text: "EV"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Label {
                Layout.preferredWidth: root.colNumber
                horizontalAlignment: Text.AlignRight
                visible: !!(root.preview && root.preview.measured)
                text: "Yours %"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            Item { Layout.fillWidth: true }
        }

        Repeater {
            model: root.colourOrder

            delegate: RowLayout {
                id: colourRow

                required property string modelData

                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    // Nested layouts default to fillWidth, which would stretch
                    // this cell and push every number off its header.
                    Layout.fillWidth: false
                    Layout.preferredWidth: root.colColour
                    spacing: 6

                    ThemeSphere {
                        size: 18
                        sphereId: colourRow.modelData
                    }

                    Label {
                        Layout.fillWidth: true
                        text: SphereAssets.label(colourRow.modelData)
                        color: Theme.fgSecondary
                        font.pixelSize: 11
                    }
                }

                Label {
                    Layout.preferredWidth: root.colNumber
                    horizontalAlignment: Text.AlignRight
                    text: root.num(root.preview.freq, colourRow.modelData, 2)
                    color: Theme.fgSecondary
                    font.pixelSize: 11
                }

                Label {
                    Layout.preferredWidth: root.colNumber
                    horizontalAlignment: Text.AlignRight
                    text: root.num(root.preview.base, colourRow.modelData, 1)
                    color: Theme.fgSecondary
                    font.pixelSize: 11
                }

                Label {
                    Layout.preferredWidth: root.colNumber
                    horizontalAlignment: Text.AlignRight
                    text: root.num(root.preview.ev, colourRow.modelData, 1)
                    color: Theme.fgMuted
                    font.pixelSize: 11
                }

                Label {
                    Layout.preferredWidth: root.colNumber
                    horizontalAlignment: Text.AlignRight
                    visible: !!(root.preview && root.preview.measured)
                    text: root.num(root.preview.measured, colourRow.modelData, 2)
                    color: Theme.fgMuted
                    font.pixelSize: 11
                }

                Item { Layout.fillWidth: true }
            }
        }

        Label {
            Layout.fillWidth: true
            visible: !!(root.preview && root.preview.measured)
            text: "\"Yours\" is your own logged click mix, for comparison only — "
                + "the rates above are what the macro uses."
            color: Theme.fgMuted
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            Layout.topMargin: 4
            visible: !!(root.preview && root.preview.ladder)
            text: "What gets clicked, over a "
                + (root.preview.spawns || 0) + "-spawn day ("
                + (root.preview.clicks_left || 0) + " clicks)"
            color: Theme.fgSecondary
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }

        Repeater {
            model: (root.preview && root.preview.ladder) ? root.preview.ladder : []

            delegate: RowLayout {
                id: rung

                required property var modelData

                Layout.fillWidth: true
                spacing: 8

                Label {
                    Layout.preferredWidth: root.colColour
                    text: rung.modelData.left + " left"
                    color: Theme.fgMuted
                    font.pixelSize: 10
                }

                Label {
                    Layout.preferredWidth: root.colNumber
                    horizontalAlignment: Text.AlignRight
                    text: "≥ " + rung.modelData.threshold
                    color: Theme.fgMuted
                    font.pixelSize: 10
                }

                Row {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6
                    spacing: 3

                    Repeater {
                        model: rung.modelData.clicks

                        delegate: ThemeSphere {
                            required property string modelData

                            size: 16
                            sphereId: modelData
                        }
                    }
                }
            }
        }

        ThemedButton {
            Layout.topMargin: 4
            text: "Refresh preview"
            onClicked: root.refreshPreview()
        }
    }
}
