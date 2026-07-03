import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

RowLayout {
    id: bar
    property string pageTitle: "Run"
    property string statusText: "Disconnected"
    property bool statusOnline: false

    spacing: 12
    Layout.fillWidth: true
    Layout.preferredHeight: 60

    Label {
        text: bar.pageTitle
        color: Theme.fgPrimary
        font.pixelSize: 24
        font.weight: Font.Bold
        Layout.fillWidth: true
    }

    Rectangle {
        implicitHeight: 36
        implicitWidth: statusRow.implicitWidth + 24
        radius: 18
        color: Theme.bgMedium
        border.color: bar.statusOnline ? Theme.success : Theme.border

        RowLayout {
            id: statusRow
            anchors.centerIn: parent
            spacing: 8

            Label {
                text: "●"
                color: bar.statusOnline ? Theme.success : Theme.fgMuted
                font.pixelSize: 14
            }
            Label {
                text: bar.statusOnline ? bar.statusText : "Disconnected"
                color: bar.statusOnline ? Theme.fgPrimary : Theme.fgMuted
                font.pixelSize: 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
        }
    }
}
