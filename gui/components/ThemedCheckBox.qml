import QtQuick
import QtQuick.Controls
import gui 1.0

// Theme-consistent CheckBox: accent-filled indicator with a check mark and
// a wrapping themed label (replaces the per-site contentItem boilerplate).
CheckBox {
    id: control
    property int textSize: 12

    spacing: 6

    indicator: Rectangle {
        implicitWidth: 16
        implicitHeight: 16
        x: control.leftPadding
        y: control.topPadding + (control.availableHeight - height) / 2
        radius: 4
        color: control.checked ? Theme.accentPrimary : Theme.inputBg
        border.color: control.checked ? Theme.accentPrimary : Theme.bgHover
        border.width: 1
        opacity: control.enabled ? 1 : 0.5

        Text {
            anchors.centerIn: parent
            visible: control.checked
            text: "\u2713"
            color: Theme.bgDark
            font.pixelSize: 11
            font.weight: Font.Bold
        }
    }

    contentItem: Text {
        text: control.text
        color: control.enabled ? Theme.fgPrimary : Theme.fgMuted
        font.pixelSize: control.textSize
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
    }
}
