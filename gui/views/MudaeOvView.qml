import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Mudae › $ov — the player's settings.

    The account-side twin of `$settings`, and like it something you configure
    rather than earn, which is why it sits between the server's rules and the
    read-only totals `$bonus` reports.

    Two fields here are load-bearing, and both are `$bw` inputs that page used to
    ask a person to type. `$persrare` is the rarity multiplier the sweep takes as
    `N`. And the sheet's last bullet — `Character pool limits: see $limroul` —
    points at the sheet in the right-hand card, whose limits are the sweep's base
    pool, the single input that decides which `$bw` wins.

    `$limroul` is a separate command and a separate stored sheet, shown here
    because this is the line that names it.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""
    property string accountName: ""

    // Re-read whenever a fetch lands: `limroulRevision` is referenced inside the
    // binding purely so bumping it re-runs this.
    property int limroulRevision: 0

    readonly property var limroul: {
        var _ = root.limroulRevision
        if (!channelProfileId)
            return { sections: [], field_count: 0 }
        try {
            return JSON.parse(
                App.formatChannelLimroulDisplayJson(channelProfileId, accountId))
        } catch (e) {
            return { sections: [], field_count: 0 }
        }
    }
    Connections {
        target: App
        function onServersChanged() { root.limroulRevision++ }
        function onConfigChanged() { root.limroulRevision++ }
    }

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 320
            title: "$ov (parsed)"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            MudaeSheetPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                sheetKind: "ov"
                channelProfileId: root.channelProfileId
                accountId: root.accountId
            }
        }
        // A fixed sidebar rather than a share of the row: it holds a short fixed
        // list, so any width it wins beyond that is width the sheet's own
        // label/value rows needed — and `$ov` values are phrases, not numbers.
        PanelCard {
            Layout.preferredWidth: 380
            Layout.minimumWidth: 280
            Layout.maximumWidth: 440
            Layout.fillHeight: true
            title: "Character pool limits ($limroul)"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        Layout.fillWidth: true
                        text: "How many different characters each roulette can roll — "
                              + "the $bw sweep's base pool, and the one input that decides "
                              + "which $bw wins."
                        color: Theme.mute
                        font.pixelSize: Theme.sizeSmall
                        wrapMode: Text.WordWrap
                    }

                    ScopeFetchButton {
                        Layout.alignment: Qt.AlignTop
                        command: "limroul"
                        commandLabel: "$limroul"
                        accountId: root.accountId
                        channelProfileId: root.channelProfileId
                    }
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.limroul.field_count === 0
                    text: "Not fetched yet."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Repeater {
                    model: (root.limroul.sections[0] || {}).rows || []

                    delegate: RowLayout {
                        required property var modelData

                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        spacing: 10
                        visible: !!modelData.has_value

                        Rectangle {
                            Layout.preferredWidth: 4
                            Layout.preferredHeight: 14
                            Layout.alignment: Qt.AlignVCenter
                            radius: 2
                            color: Theme.good
                            opacity: 0.85
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            Label {
                                Layout.fillWidth: true
                                text: modelData.label
                                color: Theme.fg
                                font.pixelSize: Theme.sizeSmall
                                elide: Text.ElideRight
                            }

                            Label {
                                Layout.fillWidth: true
                                visible: !!modelData.detail
                                text: modelData.detail
                                color: Theme.mute
                                font.pixelSize: Theme.sizeMicro
                                elide: Text.ElideRight
                            }
                        }

                        Label {
                            Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                            text: modelData.display
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                            font.weight: Font.Medium
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    Layout.topMargin: 2
                    visible: root.limroul.field_count > 0
                    text: root.limroul.limits_agree === null
                          || root.limroul.limits_agree === undefined
                          ? "The four differ, so Advisor › $bw has to be told which "
                            + "roulette you roll before it can take the pool from here."
                          : "All four agree, so Advisor › $bw takes the base pool from "
                            + "here without being asked which roulette you roll."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    Layout.preferredHeight: 1
                    color: Theme.border
                    opacity: 0.6
                }

                Label {
                    Layout.fillWidth: true
                    text: "$persrare is the other field here with consequences: the rarity "
                          + "multiplier on characters you already own, which raises wish "
                          + "spawn chance and favours a lower $bw. Its lowest setting is 1, "
                          + "which Mudae prints as none because multiplying by one changes "
                          + "nothing."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }

                Label {
                    Layout.fillWidth: true
                    text: "Read-only here. Neither sheet is ever sent on its own — the "
                          + "Fetch buttons are the only things that ask for them."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
