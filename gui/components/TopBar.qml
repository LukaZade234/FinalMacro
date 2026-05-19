import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

RowLayout {
    id: bar
    property string pageTitle: "Run"
    property string statusText: "Ready"
    property bool statusOnline: false
    property bool showMacroPhase: false
    property string macroPhaseText: "Idle"

    spacing: 12
    Layout.fillWidth: true
    Layout.preferredHeight: 60

    ColumnLayout {
        spacing: 2
        Layout.fillWidth: true

        Label {
            text: bar.pageTitle
            color: Theme.fgPrimary
            font.pixelSize: 24
            font.weight: Font.Bold
        }
        Label {
            visible: bar.showMacroPhase
            text: "Macro: " + bar.macroPhaseText
            color: Theme.fgMuted
            font.pixelSize: 11
        }
    }

    Rectangle {
        implicitHeight: 36
        implicitWidth: statusRow.implicitWidth + 24
        radius: 18
        color: Theme.bgMedium
        border.color: Theme.border

        RowLayout {
            id: statusRow
            anchors.centerIn: parent
            spacing: 8

            Label {
                text: "●"
                color: bar.statusOnline ? Theme.success : Theme.fgSecondary
                font.pixelSize: 14
            }
            Label {
                text: bar.statusText
                color: Theme.fgSecondary
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }
        }
    }
}
