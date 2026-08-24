import QtQuick
import QtQuick.Controls

import gui 1.0

/*
    One Haul-style rail tab: 36x34 icon chip that grows into icon + label
    when the parent IconRail is expanded.

    Hover visuals use HoverHandler so the parent rail can keep its own
    hover (MouseArea would steal it and collapse the menu).
*/
Item {
    id: button

    property string iconName: "run"
    property string label: ""
    property string tooltip: label
    property bool active: false
    property bool expanded: false

    signal clicked()

    implicitWidth: 36
    implicitHeight: 34
    clip: true

    readonly property color glyphColor: button.active
        ? Theme.fg
        : (itemHover.hovered ? Theme.dim : Theme.mute)

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: button.active
            ? Theme.fade(Theme.accent, 0.18)
            : (itemHover.hovered ? Theme.raised : "transparent")
        border.width: button.active ? 1 : 0
        border.color: Theme.fade(Theme.accent, 0.38)
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10

        NavIcon {
            anchors.verticalCenter: parent.verticalCenter
            name: button.iconName
            size: 16
            color: button.glyphColor
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: button.label
            color: button.glyphColor
            font.family: Theme.fontFamily
            font.pixelSize: Theme.sizeSmall
            font.weight: button.active ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
            width: Math.max(0, button.width - 36)
            opacity: button.expanded ? 1 : 0

            Behavior on opacity {
                NumberAnimation { duration: 120 }
            }
        }
    }

    HoverHandler {
        id: itemHover
        cursorShape: Qt.PointingHandCursor
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: false
        onClicked: button.clicked()
    }

    ToolTip {
        visible: itemHover.hovered && !button.expanded && button.tooltip !== ""
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
