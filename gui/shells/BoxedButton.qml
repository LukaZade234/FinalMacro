import QtQuick

import gui 1.0

/*
    A key from the Boxed control pad: square, flat, with a doubled bottom edge.
*/
Item {
    id: button

    property string text: ""
    property string variant: "default"   // default | go | hourly | kill

    signal clicked()

    readonly property bool solid: variant !== "default"
    readonly property color solidColor: {
        switch (variant) {
        case "kill": return Theme.bad
        case "hourly": return Theme.good
        default: return Theme.accent
        }
    }

    implicitWidth: label.implicitWidth + 30
    implicitHeight: 36
    opacity: enabled ? 1 : 0.4

    Rectangle {
        anchors.fill: parent
        color: button.solid ? button.solidColor : Theme.raised
        border.width: 1
        border.color: button.solid
            ? button.solidColor
            : (mouse.containsMouse ? Theme.mute : Theme.line)

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: button.solid ? button.solidColor : Theme.line
        }
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: button.text
        color: button.solid
            ? Theme.bg
            : (mouse.containsMouse ? Theme.fg : Theme.dim)
        font.family: Theme.monoFamily
        font.pixelSize: Theme.sizeBody
        font.weight: button.solid ? Font.Bold : Font.Normal
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
