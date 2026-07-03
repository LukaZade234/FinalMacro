import QtQuick
import QtQuick.Controls
import gui 1.0

// Theme-consistent Button. Variants:
//   default        — neutral gray
//   accent: true   — primary blue (confirm / main action)
//   danger: true   — red (destructive action)
//   loading: true  — small spinner in the corner; label stays centered
Button {
    id: control
    property bool accent: false
    property bool danger: false
    property bool loading: false

    implicitHeight: 32

    background: Rectangle {
        radius: 6
        color: control.danger ? Theme.error
             : control.accent ? Theme.accentPrimary
             : Theme.bgLight
        opacity: !control.enabled ? 0.35
               : control.loading ? 0.75
               : control.down ? 0.7
               : control.hovered ? 0.85
               : 1
    }

    contentItem: Item {
        Text {
            anchors.fill: parent
            text: control.text
            color: control.danger ? "#ffffff"
                 : control.accent ? Theme.bgDark
                 : Theme.fgPrimary
            font.pixelSize: 12
            font.weight: (control.accent || control.danger) ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        BusyIndicator {
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            visible: control.loading
            running: control.loading
            width: 12
            height: 12
        }
    }
}
