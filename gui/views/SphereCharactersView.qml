import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Spheres › Characters — which characters carry which ouroperk.

    Nothing reads this today. `$shop` reports a perk's *level*, never how many
    characters are assigned to it, and that count is exactly what turns OP1 and
    OP9 from a level into a rate — which is why the Upgrades page abstains on
    OP1. Capturing it needs a new command and parser, so the page states the gap
    rather than pretending to a roster.
*/
Item {
    id: root
    clip: true

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "Characters with sphere perks"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Rectangle {
                        Layout.preferredHeight: 18
                        Layout.preferredWidth: gap.implicitWidth + 14
                        radius: Theme.radiusXs
                        color: Theme.fade(Theme.warn, 0.16)
                        border.width: 1
                        border.color: Theme.fade(Theme.warn, 0.4)

                        Label {
                            id: gap
                            anchors.centerIn: parent
                            text: Theme.sectionLabel("needs new capture")
                            color: Theme.warn
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                Label {
                    Layout.fillWidth: true
                    text: "The ouroperk sheet reports each perk's level, never how many "
                          + "characters carry it. That roster count is what turns OP1 and "
                          + "OP9 from a level into an actual rate."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: "Until it is captured, Upgrades prices only what it can defend "
                          + "and abstains on OP1 rather than guessing a per-character share."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "What it would take"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                Label {
                    Layout.fillWidth: true
                    text: "A command that lists ouroperk characters, a parser in "
                          + "mudae/parsers/, a response detector in mudae/commands.py, and "
                          + "a per-account store — the same shape every other sheet uses."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: "With it, OP1 spawn share becomes priceable and the Upgrades "
                          + "ranking covers most of the ladder instead of one perk."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
