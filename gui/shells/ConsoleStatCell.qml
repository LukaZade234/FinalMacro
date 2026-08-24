import QtQuick

import gui 1.0

/*
    One reading in the Console status line: a muted key, the value, and an
    optional ten-segment meter. Cells are separated by a hairline drawn on the
    left of every cell but the first.
*/
Item {
    id: cell

    property string key: ""
    property string value: "—"
    property string tone: "neutral"      // neutral | accent | good | violet
    property real fraction: -1           // < 0 hides the meter
    property bool firstCell: false

    implicitWidth: row.implicitWidth + 30
    implicitHeight: 34

    readonly property color valueColor: {
        switch (tone) {
        case "accent": return Theme.accent
        case "good": return Theme.good
        case "violet": return Theme.accent2
        default: return Theme.fg
        }
    }

    Rectangle {
        visible: !cell.firstCell
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 9
        anchors.bottomMargin: 9
        width: 1
        color: Theme.line
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: cell.key
            color: Theme.mute
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeSmall
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: cell.value
            color: cell.valueColor
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeSmall
            font.weight: Font.DemiBold
        }

        Row {
            visible: cell.fraction >= 0
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Repeater {
                model: 10

                delegate: Rectangle {
                    required property int index

                    width: 4
                    height: 11
                    color: (index + 1) <= Math.round(cell.fraction * 10)
                        ? cell.valueColor
                        : Theme.line
                }
            }
        }
    }
}
