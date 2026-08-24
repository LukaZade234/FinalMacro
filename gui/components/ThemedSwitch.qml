import QtQuick
import QtQuick.Controls
import gui 1.0

// Theme-consistent Switch: green track when on, gray when off, with a
// built-in On/Off label so the text always matches the visual state.
Switch {
    id: control
    property bool showLabel: true

    implicitHeight: 22

    indicator: Rectangle {
        implicitWidth: 36
        implicitHeight: 18
        x: control.leftPadding
        anchors.verticalCenter: parent.verticalCenter
        radius: height / 2
        color: control.checked ? Theme.success : Theme.bgLight
        border.color: control.checked ? Theme.success : Theme.bgHover
        border.width: 1
        opacity: control.enabled ? 1 : 0.5

        Behavior on color { ColorAnimation { duration: 120 } }

        Rectangle {
            x: control.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            width: 12
            height: 12
            radius: Theme.radiusSm
            color: control.checked ? Theme.bgDark : Theme.fgSecondary

            Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
        }
    }

    contentItem: Text {
        text: control.showLabel ? (control.checked ? "On" : "Off") : ""
        color: control.checked ? Theme.success : Theme.fgMuted
        font.pixelSize: 11
        verticalAlignment: Text.AlignVCenter
        leftPadding: control.indicator.width + (control.showLabel ? 6 : 0)
    }
}
