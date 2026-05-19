import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Rectangle {
    id: chip
    property string label: ""
    property string value: "—"
    property bool highlighted: false

    implicitHeight: chipRow.implicitHeight + 16
    implicitWidth: Math.max(100, chipRow.implicitWidth + 24)
    radius: 8
    color: chip.highlighted ? Theme.bgLight : Theme.bgDark
    border.color: chip.highlighted ? Theme.accentPrimary : Theme.border
    border.width: 1

    RowLayout {
        id: chipRow
        anchors.centerIn: parent
        spacing: 6

        Text {
            text: chip.label + ":"
            color: Theme.fgMuted
            font.pixelSize: 11
        }
        Text {
            text: chip.value
            color: chip.highlighted ? Theme.accentPrimary : Theme.fgPrimary
            font.pixelSize: 12
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
    }
}
