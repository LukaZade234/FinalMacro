import QtQuick

import gui 1.0

// "CHECKS" / "MINIGAMES" caption inside the control bar.
Item {
    id: root

    property string text: ""

    implicitWidth: label.implicitWidth + 10
    implicitHeight: 38

    Text {
        id: label
        anchors.centerIn: parent
        text: Theme.sectionLabel(root.text)
        color: Theme.mute
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeMicro
        font.weight: Font.DemiBold
        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
    }
}
