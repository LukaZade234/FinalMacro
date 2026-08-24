import QtQuick
import QtQuick.Controls

import gui 1.0

/*
    One icon button in the Haul rail: 36x34 with a rounded accent-tinted
    background and an inset ring when it is the current page.
*/
Item {
    id: button

    property string iconName: "run"
    property string tooltip: ""
    property bool active: false

    signal clicked()

    implicitWidth: 36
    implicitHeight: 34

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: button.active
            ? Theme.fade(Theme.accent, 0.18)
            : (mouse.containsMouse ? Theme.raised : "transparent")
        border.width: button.active ? 1 : 0
        border.color: Theme.fade(Theme.accent, 0.38)
    }

    NavIcon {
        anchors.centerIn: parent
        name: button.iconName
        size: 16
        color: button.active ? Theme.fg : (mouse.containsMouse ? Theme.dim : Theme.mute)
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }

    ToolTip {
        visible: mouse.containsMouse && button.tooltip !== ""
        text: button.tooltip
        delay: 400

        contentItem: Text {
            text: button.tooltip
            color: Theme.fg
            font.family: Theme.fontFamily
            font.pixelSize: Theme.sizeSmall
        }

        background: Rectangle {
            color: Theme.raised
            radius: Theme.radiusSm
            border.width: 1
            border.color: Theme.line
        }
    }
}
