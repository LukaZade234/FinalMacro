import QtQuick

import gui 1.0

/*
    The `.cap` key from the Console command bar: a flat cap with a heavier bottom
    edge so it reads as a physical key, and an optional keyboard hint.
*/
Item {
    id: button

    property string text: ""
    property string hint: ""
    property string variant: "default"   // default | go | kill

    signal clicked()

    readonly property bool solid: variant === "go" || variant === "kill"
    readonly property color solidColor: variant === "kill" ? Theme.bad : Theme.accent

    implicitWidth: row.implicitWidth + 26
    implicitHeight: 34
    opacity: enabled ? 1 : 0.4

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusLg
        color: button.solid ? button.solidColor : Theme.raised
        border.width: 1
        border.color: button.solid
            ? button.solidColor
            : (mouse.containsMouse ? Theme.mute : Theme.line)

        // `border-bottom-width:2px` — a second rule along the bottom edge.
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: button.solid ? button.solidColor : Theme.line
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: button.text
            color: button.solid
                ? Theme.bg
                : (mouse.containsMouse ? Theme.fg : Theme.dim)
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeBody
            font.weight: button.variant === "kill" ? Font.Bold
                : (button.solid ? Font.DemiBold : Font.Normal)
        }

        Rectangle {
            visible: button.hint !== ""
            anchors.verticalCenter: parent.verticalCenter
            width: hintText.implicitWidth + 10
            height: hintText.implicitHeight + 4
            radius: Theme.radiusXs
            color: button.solid ? Theme.fade(Theme.bg, 0.25) : Theme.bg
            border.width: 1
            border.color: button.solid ? "transparent" : Theme.line

            Text {
                id: hintText
                anchors.centerIn: parent
                text: button.hint
                color: button.solid ? Theme.bg : Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeMicro
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
