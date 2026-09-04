import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    One wishlist column — the character list and the series list are the same
    thing twice over, so they are one component rather than two near-copies.

    The input box takes a whole list at a time: `macro/wishlist.py` splits on
    `$`, commas and newlines, so the Formatter tab's `$`-joined output pastes
    straight in. `addRequested` therefore carries raw text, not a name.
*/
PanelCard {
    id: section

    property string subtitle: ""
    property string placeholder: ""
    property var names: []

    signal addRequested(string text)
    signal removeRequested(string name)

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
                text: section.subtitle
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                wrapMode: Text.WordWrap
            }

            Rectangle {
                Layout.preferredHeight: 18
                Layout.preferredWidth: countLabel.implicitWidth + 14
                Layout.alignment: Qt.AlignTop
                radius: Theme.radiusPill
                color: Theme.bgLight

                Label {
                    id: countLabel
                    anchors.centerIn: parent
                    text: section.names.length
                    color: Theme.mute
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeMicro
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            ThemedTextField {
                id: input
                Layout.fillWidth: true
                enabled: section.enabled
                placeholderText: section.placeholder
                onAccepted: section.commit()
            }

            ActionButton {
                text: "Add"
                buttonHeight: 32
                Layout.preferredWidth: 64
                enabled: section.enabled && input.text.trim().length > 0
                fillColor: Theme.accentPrimary
                textColor: Theme.bgDark
                labelWeight: Font.DemiBold
                onClicked: section.commit()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusSm
            color: "transparent"
            border.width: 1
            border.color: Theme.border
            clip: true

            ListView {
                id: list
                anchors.fill: parent
                anchors.margins: 6
                visible: section.names.length > 0
                model: section.names
                spacing: 4
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                    required property string modelData

                    width: list.width - (list.ScrollBar.vertical.visible ? 10 : 0)
                    height: 30
                    radius: Theme.radiusSm
                    color: Theme.bgLight

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 4
                        spacing: 8

                        Label {
                            Layout.fillWidth: true
                            text: modelData
                            color: Theme.fgPrimary
                            font.pixelSize: Theme.sizeSmall
                            elide: Text.ElideRight
                        }

                        ToolButton {
                            implicitWidth: 22
                            implicitHeight: 22
                            text: "✕"
                            font.pixelSize: Theme.sizeMicro
                            onClicked: section.removeRequested(modelData)

                            contentItem: Label {
                                text: parent.text
                                color: parent.hovered ? Theme.bgDark : Theme.mute
                                font.pixelSize: Theme.sizeSmall
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            background: Rectangle {
                                radius: Theme.radiusXs
                                color: parent.hovered ? Theme.error : "transparent"
                            }
                        }
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                width: parent.width - 40
                visible: section.names.length === 0
                text: section.enabled
                    ? "Nothing here yet. A name added above is claimed the moment it rolls unclaimed."
                    : "Pick an account and a server above — this list belongs to one pair."
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }

    function commit() {
        if (!section.enabled)
            return
        const text = input.text.trim()
        if (!text)
            return
        section.addRequested(text)
        input.text = ""
    }
}
