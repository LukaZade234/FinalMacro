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
    property bool connectionOnly: false
    property bool actionsOnly: false

    readonly property bool showConnection: !bar.actionsOnly
    readonly property bool showActions: !bar.connectionOnly

    readonly property bool minigameBusy:
        App.runActionPending === "oh"
        || App.runActionPending === "oc"
        || App.runActionPending === "oq"
        || App.runActionPending === "minigames"

    readonly property bool checkBusy:
        App.runActionPending === "tu"
        || App.runActionPending === "us_check"

    signal connectClicked()
    signal disconnectClicked()
    signal runTuClicked()
    signal runUsCheckClicked()
    signal startClicked()
    signal stopClicked()
    signal playOhClicked()
    signal playOcClicked()
    signal playOqClicked()
    signal playAllMinigamesClicked()
    signal playUsClicked()

    spacing: 10

    Label {
        visible: bar.notificationStandby && bar.showConnection
        Layout.fillWidth: true
        text: "Notification mode: temporarily disconnected while the macro waits for rolls. Use Stop to exit, or Disconnect to end the session."
        color: Theme.warning
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }

    RowLayout {
        spacing: 6
        Layout.fillWidth: true
        visible: bar.showConnection

        ActionButton {
            text: "Connect"
            loading: App.connecting
            enabled: !bar.sessionActive && !App.connecting
            Layout.fillWidth: true
            buttonHeight: 34
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
            buttonHeight: 34
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.disconnectClicked()
        }
    }

    ActionButton {
        visible: bar.showConnection
        text: "Stop"
        loading: App.runActionPending === "stop"
        enabled: bar.macroEngineRunning && App.runActionPending !== "stop"
        Layout.fillWidth: true
        buttonHeight: 34
        fillColor: Theme.error
        textColor: "#ffffff"
        labelWeight: Font.Bold
        onClicked: bar.stopClicked()
    }

    RowLayout {
        spacing: 6
        Layout.fillWidth: true
        visible: bar.showActions

        ActionButton {
            text: "Run $tu"
            loading: App.runActionPending === "tu"
            enabled: bar.connected && !bar.macroEngineRunning && !bar.checkBusy && !bar.minigameBusy
            Layout.fillWidth: true
            buttonHeight: 34
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.runTuClicked()
        }

        ActionButton {
            text: "Run $us"
            loading: App.runActionPending === "us_check"
            enabled: bar.connected && !bar.macroEngineRunning && !bar.checkBusy && !bar.minigameBusy
            Layout.fillWidth: true
            buttonHeight: 34
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.runUsCheckClicked()
        }
    }

    Label {
        visible: bar.showActions
        Layout.fillWidth: true
        text: "Hourly macro"
        color: Theme.fgMuted
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }

    ActionButton {
        visible: bar.showActions
        text: "Start hourly macro"
        loading: App.runActionPending === "start"
        enabled: bar.connected && !bar.macroEngineRunning && App.runActionPending !== "start"
                 && !bar.checkBusy && !bar.minigameBusy
        Layout.fillWidth: true
        buttonHeight: 36
        fillColor: Theme.success
        textColor: Theme.bgDark
        labelWeight: Font.Bold
        onClicked: bar.startClicked()
    }

    Label {
        visible: bar.showActions
        Layout.fillWidth: true
        text: "$us"
        color: Theme.fgMuted
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }

    ActionButton {
        visible: bar.showActions
        text: "Roll $us"
        loading: App.runActionPending === "us"
        enabled: bar.connected && !bar.macroEngineRunning && App.runActionPending !== "us"
                 && !bar.checkBusy && !bar.minigameBusy
        Layout.fillWidth: true
        buttonHeight: 34
        fillColor: Theme.bgLight
        textColor: Theme.fgPrimary
        onClicked: bar.playUsClicked()
    }

    Label {
        visible: bar.showActions
        Layout.fillWidth: true
        text: "Minigames"
        color: Theme.fgMuted
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }

    RowLayout {
        spacing: 6
        Layout.fillWidth: true
        visible: bar.showActions

        ActionButton {
            text: "Play $oh"
            loading: App.runActionPending === "oh"
            enabled: bar.connected && !bar.macroEngineRunning && !bar.minigameBusy && !bar.checkBusy
            Layout.fillWidth: true
            buttonHeight: 32
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playOhClicked()
        }

        ActionButton {
            text: "Play $oc"
            loading: App.runActionPending === "oc"
            enabled: bar.connected && !bar.macroEngineRunning && !bar.minigameBusy && !bar.checkBusy
            Layout.fillWidth: true
            buttonHeight: 32
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playOcClicked()
        }

        ActionButton {
            text: "Play $oq"
            loading: App.runActionPending === "oq"
            enabled: bar.connected && !bar.macroEngineRunning && !bar.minigameBusy && !bar.checkBusy
            Layout.fillWidth: true
            buttonHeight: 32
            fillColor: Theme.bgLight
            textColor: Theme.fgPrimary
            onClicked: bar.playOqClicked()
        }
    }

    ActionButton {
        visible: bar.showActions
        text: "Play all minigames available"
        loading: App.runActionPending === "minigames"
        enabled: bar.connected && !bar.macroEngineRunning && !bar.minigameBusy && !bar.checkBusy
        Layout.fillWidth: true
        buttonHeight: 34
        fillColor: Theme.accentPrimary
        textColor: Theme.bgDark
        labelWeight: Font.DemiBold
        onClicked: bar.playAllMinigamesClicked()
    }

    Label {
        visible: bar.showActions
        Layout.fillWidth: true
        text: "Single play buttons run one minigame each. Play all uses every minigame you have available."
        color: Theme.fgMuted
        font.pixelSize: 10
        wrapMode: Text.WordWrap
    }
}
