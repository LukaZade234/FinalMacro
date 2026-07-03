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
    signal playUsClicked()

    spacing: 10

    RowLayout {
        spacing: 8
        Layout.fillWidth: true

        ActionButton {
            text: "Connect"
            loading: App.connecting
            enabled: !bar.connected && !App.connecting
            Layout.fillWidth: true
            fillColor: Theme.accentPrimary
            textColor: Theme.bgDark
            labelWeight: Font.DemiBold
            onClicked: bar.connectClicked()
        }

        ActionButton {
            text: "Disconnect"
            loading: App.disconnecting
            enabled: bar.connected && !App.disconnecting
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.disconnectClicked()
        }
    }

    RowLayout {
        spacing: 8
        Layout.fillWidth: true

        ActionButton {
            text: "Run $tu"
            loading: App.runActionPending === "tu"
            enabled: bar.connected && !bar.macroRunning && App.runActionPending !== "tu"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.runTuClicked()
        }

        ActionButton {
            text: "Start macro"
            loading: App.runActionPending === "start"
            enabled: bar.connected && !bar.macroRunning && App.runActionPending !== "start"
            Layout.fillWidth: true
            fillColor: Theme.success
            textColor: Theme.bgDark
            labelWeight: Font.Bold
            onClicked: bar.startClicked()
        }

        ActionButton {
            text: "Stop"
            loading: App.runActionPending === "stop"
            enabled: bar.connected && bar.macroRunning && App.runActionPending !== "stop"
            Layout.fillWidth: true
            fillColor: Theme.error
            textColor: "#ffffff"
            labelWeight: Font.Bold
            onClicked: bar.stopClicked()
        }
    }

    RowLayout {
        spacing: 8
        Layout.fillWidth: true

        ActionButton {
            text: "Play $oh"
            loading: App.runActionPending === "oh"
            enabled: bar.connected && !bar.macroRunning && App.runActionPending !== "oh"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playOhClicked()
        }

        ActionButton {
            text: "Roll $us"
            loading: App.runActionPending === "us"
            enabled: bar.connected && !bar.macroRunning && App.runActionPending !== "us"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playUsClicked()
        }
    }
}
