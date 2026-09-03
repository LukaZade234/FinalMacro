import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Mudae › $bonus — the account's totals.

    The only sheet on this page you cannot set: `$bonus` is the *result* of the
    server's settings plus this account's perks. It earns its place beside them
    because it is how you check a setting actually landed, and because five of
    its fields are what the perk-8 and perk-9 engines run on.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""
    property string accountName: ""

    readonly property var drivenBy: [
        { field: "rolls_per_hour", drives: "perk-9 spawn forecast" },
        { field: "power_max_percent", drives: "perk-8 reserve, kakera budget" },
        { field: "sphere_double_chance_pct", drives: "perk-9 EV bar" },
        { field: "additional_spheres", drives: "perk-9 EV bar" },
        { field: "dk_cooldown_minutes", drives: "$dk hold policy" }
    ]

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 320
            title: "$bonus (parsed)"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            MudaeSheetPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                sheetKind: "bonus"
                channelProfileId: root.channelProfileId
                accountId: root.accountId
            }
        }

        // A fixed sidebar rather than a share of the row: this side is a fixed
        // list of five field names, so any width it wins beyond them is width
        // the sheet's own label/value rows needed.
        PanelCard {
            Layout.preferredWidth: 360
            Layout.minimumWidth: 260
            Layout.maximumWidth: 420
            Layout.fillHeight: true
            title: "Where these are used"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "$bonus is read-only — it is what the server's settings and "
                          + (root.accountName ? root.accountName + "'s" : "this account's")
                          + " perks add up to. These fields are wired into decisions today."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Repeater {
                    model: root.drivenBy

                    delegate: RowLayout {
                        required property var modelData

                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        spacing: 10

                        Label {
                            Layout.preferredWidth: 150
                            text: modelData.field
                            color: Theme.accent2
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeMicro
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            text: modelData.drives
                            color: Theme.dim
                            font.pixelSize: Theme.sizeSmall
                            elide: Text.ElideRight
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Label {
                    Layout.fillWidth: true
                    text: "Stored per account: $bonus mixes server settings with this "
                          + "account's own perks, so a second account on the same channel "
                          + "keeps its own copy."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
