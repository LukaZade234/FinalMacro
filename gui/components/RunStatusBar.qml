import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Rectangle {
    id: bar
    property string rollsValue: "—"
    property string claimValue: "—"
    property string powerValue: "—"
    property string dkValue: "—"
    property string resetValue: "—"
    property string phase: "Idle"
    property string rollsTone: "neutral"
    property string claimTone: "neutral"
    property string powerTone: "neutral"
    property string dkTone: "neutral"

    implicitHeight: 52
    radius: 10
    color: Theme.bgMedium
    border.color: Theme.border
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        StatusChip {
            label: "Rolls"
            value: bar.rollsValue
            tone: bar.rollsTone
            Layout.fillWidth: false
        }
        StatusChip {
            label: "Claim"
            value: bar.claimValue
            tone: bar.claimTone
            Layout.fillWidth: false
        }
        StatusChip {
            label: "Power"
            value: bar.powerValue
            tone: bar.powerTone
            Layout.fillWidth: false
        }
        StatusChip {
            label: "DK"
            value: bar.dkValue
            tone: bar.dkTone
            Layout.fillWidth: false
        }
        StatusChip {
            label: "Reset"
            value: bar.resetValue
            Layout.fillWidth: false
        }

        Item { Layout.fillWidth: true }

        PhasePill {
            phase: bar.phase
        }
    }
}
