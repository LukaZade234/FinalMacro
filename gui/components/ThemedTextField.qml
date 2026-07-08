import QtQuick
import QtQuick.Controls
import gui 1.0

// Theme-consistent TextField: dark input, readable placeholder, focus ring.
TextField {
    id: control

    implicitHeight: 32

    color: Theme.fgPrimary
    placeholderTextColor: Theme.fgMuted
    selectionColor: Theme.accentPrimary
    selectedTextColor: Theme.bgDark

    background: Rectangle {
        radius: 6
        color: Theme.inputBg
        border.color: control.activeFocus ? Theme.accentPrimary : Theme.border
        border.width: 1
    }
}
