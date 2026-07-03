import QtQuick
import QtQuick.Controls
import gui 1.0

// Theme-consistent list row for sidebar lists (presets, accounts, servers…).
ItemDelegate {
    id: control

    implicitHeight: 32

    contentItem: Text {
        text: control.text
        color: control.highlighted ? Theme.fgPrimary : Theme.fgSecondary
        font.pixelSize: 12
        font.weight: control.highlighted ? Font.DemiBold : Font.Normal
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 6
        color: control.highlighted ? Theme.bgLight
             : control.hovered ? Theme.bgMedium
             : "transparent"
    }
}
