import QtQuick

import gui 1.0

/*
    The `.cbtn` control-bar button from the Haul mockup.

    variant: "default" | "stop" | "ghost" | "hourly" | "go"
*/
Item {
    id: button

    property string text: ""
    property string variant: "default"

    signal clicked()

    // A filled button that is unavailable drops back to the plain style rather
    // than keeping a bright fill it cannot act on.
    readonly property bool emphasised: enabled
        && (variant === "stop" || variant === "go" || variant === "hourly")
    readonly property color baseColor: {
        if (!enabled) return variant === "ghost" ? "transparent" : Theme.raised
        switch (variant) {
        case "stop": return Theme.bad
        case "go": return Theme.accent
        case "hourly": return Theme.good
        case "ghost": return "transparent"
        default: return Theme.raised
        }
    }
    readonly property color labelColor: {
        if (!enabled) return Theme.mute
        if (emphasised) return Theme.bg
        return variant === "ghost" ? Theme.dim : Theme.fg
    }

    implicitWidth: label.implicitWidth + (variant === "stop" ? 48 : 32)
    implicitHeight: 38

    Rectangle {
        anchors.fill: parent
        radius: 9
        color: button.emphasised && mouse.containsMouse
            ? Qt.lighter(button.baseColor, 1.12)
            : button.baseColor
        border.width: 1
        border.color: {
            if (button.emphasised) return button.baseColor
            if (mouse.containsMouse && button.enabled) return Theme.mute
            return Theme.line
        }

        Behavior on border.color {
            ColorAnimation { duration: 120 }
        }
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: button.text
        color: button.labelColor
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeBody
        font.weight: button.emphasised ? Font.Bold : Font.DemiBold
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: button.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
