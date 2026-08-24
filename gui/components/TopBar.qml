import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

RowLayout {
    id: bar
    property string pageTitle: "Run"
    property string statusText: "Disconnected"
    property bool statusOnline: false
    property bool notificationStandby: false

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
        radius: Theme.radiusPill
        color: Theme.bgMedium
        border.color: bar.statusOnline
            ? Theme.success
            : (bar.notificationStandby ? Theme.warning : Theme.border)

        RowLayout {
            id: statusRow
            anchors.centerIn: parent
            spacing: 8

            Label {
                text: "●"
                color: bar.statusOnline
                    ? Theme.success
                    : (bar.notificationStandby ? Theme.warning : Theme.fgMuted)
                font.pixelSize: 14
            }
            Label {
                text: bar.statusOnline || bar.notificationStandby
                    ? bar.statusText
                    : "Disconnected"
                color: bar.statusOnline || bar.notificationStandby
                    ? Theme.fgPrimary
                    : Theme.fgMuted
                font.pixelSize: 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
        }
    }
}
