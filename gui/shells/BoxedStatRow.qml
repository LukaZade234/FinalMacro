import QtQuick

import gui 1.0

/*
    One `label ......... value` line inside a Boxed panel, with an optional
    block meter drawn from full/empty cells the way the mockup does.
*/
Item {
    id: row

    property string label: ""
    property string value: "—"
    property string tone: ""             // "" | accent | good | bad
    property real fraction: -1           // < 0 hides the meter
    property int meterCells: 14

    implicitHeight: 21

    Text {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        text: row.label
        color: Theme.dim
        font.family: Theme.monoFamily
        font.pixelSize: Theme.sizeSmall
    }

    Row {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        Row {
            visible: row.fraction >= 0
            anchors.verticalCenter: parent.verticalCenter
            spacing: 1

            Repeater {
                model: row.meterCells

                delegate: Rectangle {
                    required property int index

                    width: 4
                    height: 9
                    color: (index + 1) <= Math.round(row.fraction * row.meterCells)
                        ? Theme.accent
                        : Theme.line
                }
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: row.value
            color: row.tone === "accent" ? Theme.accent
                : (row.tone === "good" ? Theme.good
                : (row.tone === "bad" ? Theme.bad : Theme.fg))
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeSmall
            font.weight: Font.DemiBold
        }
    }
}
