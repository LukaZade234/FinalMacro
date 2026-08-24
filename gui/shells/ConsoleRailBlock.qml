import QtQuick

import gui 1.0

/*
    A titled group of label/value rows in the Console rail.
    `rows` is a list of { label, value, tone } where tone is "", "accent" or "good".
*/
Item {
    id: block

    property string title: ""
    property var rows: []

    implicitHeight: column.implicitHeight

    Column {
        id: column
        width: parent.width
        spacing: 0

        Text {
            text: Theme.sectionLabel(block.title)
            color: Theme.mute
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeMicro
            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
            bottomPadding: 7
        }

        Repeater {
            model: block.rows

            delegate: Item {
                required property var modelData

                width: column.width
                height: 22

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: Theme.dim
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                }

                Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.value
                    color: modelData.tone === "accent" ? Theme.accent
                        : (modelData.tone === "good" ? Theme.good : Theme.fg)
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    font.weight: Font.DemiBold
                }
            }
        }
    }
}
