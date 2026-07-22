import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

ColumnLayout {
    id: bar
    property bool connected: false
    property bool macroRunning: false
    property bool macroEngineRunning: false
    property bool notificationStandby: false
    property bool sessionActive: false

    signal connectClicked()
    signal disconnectClicked()
    signal runTuClicked()
    signal startClicked()
    signal stopClicked()
    signal playOhClicked()
    signal playOcClicked()
    signal playOqClicked()
    signal playUsClicked()

    spacing: 10

    Label {
        visible: bar.notificationStandby
        Layout.fillWidth: true
        text: "Notification mode: temporarily disconnected while the macro waits for rolls. Use Stop to exit, or Disconnect to end the session."
        color: Theme.warning
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }

    RowLayout {
        spacing: 8
        Layout.fillWidth: true

        ActionButton {
            text: "Connect"
            loading: App.connecting
            enabled: !bar.sessionActive && !App.connecting
            Layout.fillWidth: true
            fillColor: Theme.accentPrimary
            textColor: Theme.bgDark
            labelWeight: Font.DemiBold
            onClicked: bar.connectClicked()
        }

        ActionButton {
            text: "Disconnect"
            loading: App.disconnecting
            enabled: bar.sessionActive && !App.disconnecting
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
            enabled: bar.connected && !bar.macroEngineRunning && App.runActionPending !== "tu"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.runTuClicked()
        }

        ActionButton {
            text: "Start macro"
            loading: App.runActionPending === "start"
            enabled: bar.connected && !bar.macroEngineRunning && App.runActionPending !== "start"
            Layout.fillWidth: true
            fillColor: Theme.success
            textColor: Theme.bgDark
            labelWeight: Font.Bold
            onClicked: bar.startClicked()
        }

        ActionButton {
            text: "Stop"
            loading: App.runActionPending === "stop"
            enabled: bar.macroEngineRunning && App.runActionPending !== "stop"
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
            enabled: bar.connected && !bar.macroEngineRunning
                     && App.runActionPending !== "oh"
                     && App.runActionPending !== "oc"
                     && App.runActionPending !== "oq"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playOhClicked()
        }

        ActionButton {
            text: "Play $oc"
            loading: App.runActionPending === "oc"
            enabled: bar.connected && !bar.macroEngineRunning
                     && App.runActionPending !== "oh"
                     && App.runActionPending !== "oc"
                     && App.runActionPending !== "oq"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playOcClicked()
        }

        ActionButton {
            text: "Play $oq"
            loading: App.runActionPending === "oq"
            enabled: bar.connected && !bar.macroEngineRunning
                     && App.runActionPending !== "oh"
                     && App.runActionPending !== "oc"
                     && App.runActionPending !== "oq"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playOqClicked()
        }

        ActionButton {
            text: "Roll $us"
            loading: App.runActionPending === "us"
            enabled: bar.connected && !bar.macroEngineRunning && App.runActionPending !== "us"
            Layout.fillWidth: true
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playUsClicked()
        }
    }
}
