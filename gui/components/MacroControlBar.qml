import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

ColumnLayout {
    id: bar
    property bool connected: false
    property bool macroRunning: false

    signal connectClicked()
    signal disconnectClicked()
    signal runTuClicked()
    signal startClicked()
    signal stopClicked()
    signal playOhClicked()

    spacing: 10

    RowLayout {
        spacing: 8
        Layout.fillWidth: true

        Button {
            text: "Connect"
            enabled: !bar.connected
            Layout.fillWidth: true
            implicitHeight: 40
            background: Rectangle {
                radius: 8
                color: parent.enabled ? Theme.accentPrimary : Theme.bgLight
                opacity: parent.enabled ? 1 : 0.5
            }
            contentItem: Text {
                text: parent.text
                color: Theme.bgDark
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: bar.connectClicked()
        }

        Button {
            text: "Disconnect"
            enabled: bar.connected
            Layout.fillWidth: true
            implicitHeight: 40
            background: Rectangle {
                radius: 8
                color: Theme.bgLight
                opacity: parent.enabled ? 1 : 0.5
            }
            contentItem: Text {
                text: parent.text
                color: Theme.fgPrimary
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: bar.disconnectClicked()
        }
    }

    RowLayout {
        spacing: 8
        Layout.fillWidth: true

        Button {
            text: "Run $tu"
            enabled: bar.connected && !bar.macroRunning
            Layout.fillWidth: true
            implicitHeight: 40
            background: Rectangle {
                radius: 8
                color: Theme.bgLight
                opacity: parent.enabled ? 1 : 0.45
            }
            contentItem: Text {
                text: parent.text
                color: Theme.fgPrimary
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: bar.runTuClicked()
        }

        Button {
            text: "Start macro"
            enabled: bar.connected && !bar.macroRunning
            Layout.fillWidth: true
            implicitHeight: 40
            background: Rectangle {
                radius: 8
                color: Theme.success
                opacity: parent.enabled ? 1 : 0.45
            }
            contentItem: Text {
                text: parent.text
                color: Theme.bgDark
                font.weight: Font.Bold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: bar.startClicked()
        }

        Button {
            text: "Stop"
            enabled: bar.connected && bar.macroRunning
            Layout.fillWidth: true
            implicitHeight: 40
            background: Rectangle {
                radius: 8
                color: Theme.error
                opacity: parent.enabled ? 1 : 0.45
            }
            contentItem: Text {
                text: parent.text
                color: "#ffffff"
                font.weight: Font.Bold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: bar.stopClicked()
        }
    }

    RowLayout {
        spacing: 8
        Layout.fillWidth: true

        Button {
            text: "Play $oh"
            enabled: bar.connected && !bar.macroRunning
            Layout.fillWidth: true
            implicitHeight: 40
            background: Rectangle {
                radius: 8
                color: Theme.bgLight
                opacity: parent.enabled ? 1 : 0.45
            }
            contentItem: Text {
                text: parent.text
                color: Theme.fgPrimary
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: bar.playOhClicked()
        }
    }
}
