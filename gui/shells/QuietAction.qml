import QtQuick
import QtQuick.Controls
import gui 1.0

/*
    Quiet's button: an outline and a label, nothing filled except the one
    primary action. `tone` picks which of the four roles it plays —
    "" ordinary, "go" primary, "stop" destructive, "accent" secondary.
*/
Item {
    id: btn

    property string text: ""
    property string tone: ""
    // `enabled` is Item's own — redeclaring it shadows the base property and
    // Qt warns about the override.

    signal clicked()

    readonly property bool primary: tone === "go"

    implicitHeight: Theme.controlHeight
    implicitWidth: label.implicitWidth + Theme.controlPadH * 2
    opacity: enabled ? 1 : 0.42

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSm
        color: btn.primary ? Theme.good : "transparent"
        border.width: 1
        border.color: {
            if (btn.primary)
                return Theme.good
            if (btn.tone === "stop")
                return Theme.fade(Theme.bad, 0.45)
            if (btn.tone === "accent")
                return Theme.fade(Theme.accent, 0.45)
            return hover.containsMouse && btn.enabled ? Theme.mute : Theme.line
        }
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }

    Label {
        id: label
        anchors.centerIn: parent
        text: btn.text
        color: {
            if (btn.primary)
                return Theme.bg
            if (btn.tone === "stop")
                return Theme.bad
            if (btn.tone === "accent")
                return Theme.accent
            return hover.containsMouse && btn.enabled ? Theme.fg : Theme.dim
        }
        font.pixelSize: Theme.sizeBody
        font.weight: btn.tone === "" ? Font.Medium : Font.DemiBold
    }

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        enabled: btn.enabled
        cursorShape: btn.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: btn.clicked()
    }
}
