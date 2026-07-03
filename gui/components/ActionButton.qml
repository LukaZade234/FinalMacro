import QtQuick
import QtQuick.Controls
import gui 1.0

// Run-page action button with optional loading spinner (text stays centered).
Button {
    id: control
    property bool loading: false
    property color fillColor: Theme.bgLight
    property color textColor: Theme.fgPrimary
    property int labelWeight: Font.Normal
    property real buttonHeight: 40

    implicitHeight: buttonHeight

    background: Rectangle {
        radius: 8
        color: control.fillColor
        opacity: !control.enabled ? 0.45
               : control.loading ? 0.8
               : control.down ? 0.65
               : control.hovered ? 0.88
               : 1
        Behavior on opacity { NumberAnimation { duration: 80 } }
    }

    contentItem: Item {
        Text {
            anchors.fill: parent
            text: control.text
            color: control.textColor
            font.weight: control.labelWeight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        BusyIndicator {
            anchors.left: parent.left
            anchors.leftMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            visible: control.loading
            running: control.loading
            width: 14
            height: 14
        }
    }
}
