import QtQuick
import QtQuick.Controls

import gui 1.0

/*
    The Boxed `.combo`: key, value and an accent arrow on one line.
*/
Item {
    id: combo

    property string label: ""
    property string value: ""
    property var options: []
    property int currentIndex: -1

    signal picked(int index)

    implicitHeight: 34

    Rectangle {
        anchors.fill: parent
        color: Theme.raised
        border.width: 1
        border.color: mouse.containsMouse ? Theme.mute : Theme.line
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 11
        anchors.rightMargin: 11
        spacing: 10

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: combo.label
            color: Theme.mute
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeMicro
            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - arrow.width - parent.spacing
            text: combo.value
            color: Theme.fg
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeSmall
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }

        Text {
            id: arrow
            anchors.verticalCenter: parent.verticalCenter
            text: "▼"
            color: Theme.accent
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeMicro
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (combo.options.length > 0)
                popup.open()
        }
    }

    Popup {
        id: popup
        y: combo.height
        width: Math.max(combo.width, 220)
        padding: 1
        modal: false

        background: Rectangle {
            color: Theme.surface
            border.width: 1
            border.color: Theme.line
        }

        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 260)
            model: combo.options
            clip: true
            currentIndex: combo.currentIndex
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
                required property int index
                required property var modelData

                width: ListView.view.width
                height: 28
                color: hover.containsMouse
                    ? Theme.accent
                    : (index === combo.currentIndex ? Theme.raised : "transparent")

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    verticalAlignment: Text.AlignVCenter
                    text: modelData
                    color: hover.containsMouse ? Theme.bg : Theme.dim
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeSmall
                    elide: Text.ElideRight
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        combo.picked(index)
                        popup.close()
                    }
                }
            }
        }
    }
}
