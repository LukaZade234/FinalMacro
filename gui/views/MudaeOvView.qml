import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Mudae › $ov — personal settings.

    The account-side twin of `$settings`, and like it something you configure
    and copy between servers, which is why it belongs on this page rather than
    with the read-only totals.

    There is no parser yet: `$ov` appears twice in `TODO.md` and nowhere in the
    code, and `TODO.md` is explicit that we do not send it unless asked. The tab
    is here so the section has its final shape and the gap is visible instead of
    implied. Once parsed it reuses everything `$settings` already has — the same
    sheet panel, the same diff-preview-apply pipeline — keyed to the account
    rather than the server.
*/
Item {
    id: root
    clip: true

    property string accountName: ""

    readonly property var plannedFields: [
        "Personal roll display",
        "Emoji / reaction style",
        "Notification preferences",
        "Display language"
    ]

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            // An explicit share: without it the two cards are sized from their
            // implicit widths, and a card of wrapping prose asks for the row.
            Layout.preferredWidth: 420
            Layout.minimumWidth: 260
            title: "$ov (personal settings)"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Rectangle {
                        Layout.preferredHeight: 18
                        Layout.preferredWidth: notParsed.implicitWidth + 14
                        radius: Theme.radiusXs
                        color: Theme.fade(Theme.warn, 0.16)
                        border.width: 1
                        border.color: Theme.fade(Theme.warn, 0.4)

                        Label {
                            id: notParsed
                            anchors.centerIn: parent
                            text: Theme.sectionLabel("parser not written")
                            color: Theme.warn
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                Repeater {
                    model: root.plannedFields

                    delegate: RowLayout {
                        required property string modelData

                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        spacing: 10
                        opacity: 0.45

                        Rectangle {
                            Layout.preferredWidth: 4
                            Layout.preferredHeight: 14
                            Layout.alignment: Qt.AlignVCenter
                            radius: 2
                            color: Theme.mute
                            opacity: 0.35
                        }

                        Label {
                            Layout.fillWidth: true
                            text: modelData
                            color: Theme.dim
                            font.pixelSize: Theme.sizeSmall
                            elide: Text.ElideRight
                        }

                        Label {
                            text: "—"
                            color: Theme.mute
                            font.pixelSize: Theme.sizeSmall
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Label {
                    Layout.fillWidth: true
                    text: "Illustrative field names — nothing is fetched or stored yet."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            // An explicit share: without it the two cards are sized from their
            // implicit widths, and a card of wrapping prose asks for the row.
            Layout.preferredWidth: 420
            Layout.minimumWidth: 260
            title: "Before this tab works"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                Label {
                    Layout.fillWidth: true
                    text: "$ov has no parser, no command alias and no stored fields. "
                          + "It needs a parser in mudae/parsers/, a response detector in "
                          + "mudae/commands.py and a MessageKind, like every other sheet."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: "Once it parses, this page reuses the $settings machinery "
                          + "unchanged: the same sheet panel, and the same "
                          + "diff → preview → dry run → apply → verify pipeline, keyed "
                          + "to the account instead of the server."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
