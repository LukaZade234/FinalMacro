import QtQuick
import QtQuick.Controls

import gui 1.0

/*
    The `.sel` picker from the Haul and Console mockups: a small uppercase key
    above the current value, an optional leading icon tile, and a caret that
    opens a themed list.
*/
Item {
    id: selector

    property string label: ""
    property string value: ""
    property string iconName: ""
    property var options: []
    property int currentIndex: -1
    property bool showIcon: true
    property bool highlight: false

    signal picked(int index)

    implicitHeight: showIcon ? 46 : 40

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: Theme.radiusMd
        color: selector.highlight
            ? Theme.blend(Theme.accent, Theme.surface, 0.08)
            : Theme.surface
        border.width: 1
        border.color: selector.highlight
            ? Theme.fade(Theme.accent, 0.38)
            : (mouse.containsMouse ? Theme.mute : Theme.line)

        Behavior on border.color {
            ColorAnimation { duration: 120 }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (selector.options.length > 0)
                popup.open()
        }
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 13
        anchors.rightMargin: 13
        spacing: 11

        Rectangle {
            visible: selector.showIcon
            width: 26
            height: 26
            anchors.verticalCenter: parent.verticalCenter
            radius: Theme.radiusSm
            color: selector.highlight ? Theme.fade(Theme.accent, 0.20) : Theme.raised

            NavIcon {
                anchors.centerIn: parent
                name: selector.iconName
                size: 13
                strokeWidth: 1.7
                color: selector.highlight ? Theme.accent : Theme.dim
            }
        }

        Column {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - (selector.showIcon ? 26 + 11 : 0) - caret.width - 11
            spacing: 2

            Text {
                width: parent.width
                text: Theme.sectionLabel(selector.label)
                color: Theme.mute
                font.family: Theme.fontFamily
                font.pixelSize: Theme.sizeMicro
                font.weight: Font.DemiBold
                font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                elide: Text.ElideRight
            }

            Text {
                width: parent.width
                text: selector.value
                color: Theme.fg
                font.family: Theme.fontFamily
                font.pixelSize: Theme.sizeBody
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
        }

        Text {
            id: caret
            anchors.verticalCenter: parent.verticalCenter
            text: "▾"
            color: Theme.mute
            font.family: Theme.fontFamily
            font.pixelSize: 10
        }
    }

    Popup {
        id: popup
        y: selector.height + 4
        width: Math.max(selector.width, 200)
        padding: 4
        modal: false

        background: Rectangle {
            color: Theme.surface
            radius: Theme.radiusMd
            border.width: 1
            border.color: Theme.line
        }

        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 260)
            model: selector.options
            clip: true
            currentIndex: selector.currentIndex
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
                required property int index
                required property var modelData

                width: ListView.view.width
                height: 32
                radius: Theme.radiusSm
                color: hover.containsMouse
                    ? Theme.raised
                    : (index === selector.currentIndex ? Theme.fade(Theme.accent, 0.14) : "transparent")

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    verticalAlignment: Text.AlignVCenter
                    text: modelData
                    color: index === selector.currentIndex ? Theme.fg : Theme.dim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.sizeSmall
                    elide: Text.ElideRight
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        selector.picked(index)
                        popup.close()
                    }
                }
            }
        }
    }
}
