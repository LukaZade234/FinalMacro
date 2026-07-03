import QtQuick
import QtQuick.Controls
import gui 1.0

// Theme-consistent SpinBox: dark input field with − / + steppers.
SpinBox {
    id: control
    editable: true

    implicitHeight: 32

    contentItem: TextInput {
        z: 2
        text: control.textFromValue(control.value, control.locale)
        font.pixelSize: 12
        color: control.enabled ? Theme.fgPrimary : Theme.fgMuted
        selectionColor: Theme.accentPrimary
        selectedTextColor: Theme.bgDark
        horizontalAlignment: Qt.AlignHCenter
        verticalAlignment: Qt.AlignVCenter
        readOnly: !control.editable
        validator: control.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
        clip: true
    }

    down.indicator: Rectangle {
        x: 0
        height: parent.height
        implicitWidth: 28
        radius: 6
        color: control.down.pressed ? Theme.bgHover : Theme.bgLight
        opacity: control.enabled ? 1 : 0.4

        Text {
            anchors.centerIn: parent
            text: "\u2212"
            color: Theme.fgPrimary
            font.pixelSize: 14
        }
    }

    up.indicator: Rectangle {
        x: parent.width - width
        height: parent.height
        implicitWidth: 28
        radius: 6
        color: control.up.pressed ? Theme.bgHover : Theme.bgLight
        opacity: control.enabled ? 1 : 0.4

        Text {
            anchors.centerIn: parent
            text: "+"
            color: Theme.fgPrimary
            font.pixelSize: 14
        }
    }

    background: Rectangle {
        implicitWidth: 120
        radius: 6
        color: Theme.inputBg
        border.color: Theme.border
        border.width: 1
    }
}
