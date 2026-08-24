import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Compact strip across every layout: an update exists, or a pull just finished.
// Full changelog and Update live on Settings; this only points the user there.
Item {
    id: notice

    signal openSettings()

    readonly property bool hasUpdate: App.updateAvailable
    readonly property bool hasPullMessage: App.updatePullMessage !== ""
    readonly property bool showRestart: !hasUpdate && hasPullMessage && App.updatePullOk

    visible: hasUpdate || hasPullMessage || App.updatePulling
    implicitHeight: visible ? bar.implicitHeight + 16 : 0
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgMedium
        border.color: Theme.accentSecondary
        border.width: 1
    }

    RowLayout {
        id: bar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        spacing: 10

        Label {
            Layout.fillWidth: true
            text: {
                if (App.updatePulling)
                    return "Updating…"
                if (notice.showRestart)
                    return "Update applied — restart FinalMacro to finish."
                if (notice.hasPullMessage && !notice.hasUpdate)
                    return App.updatePullMessage
                var n = App.updateBehindCount
                var branch = App.updateBranch || "remote"
                return "Update available — " + n
                    + (n === 1 ? " change" : " changes")
                    + " on " + branch + ". Open Settings to review and update."
            }
            color: Theme.fgPrimary
            font.pixelSize: 12
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }

        ThemedButton {
            text: "Open Settings"
            visible: notice.hasUpdate
            onClicked: notice.openSettings()
        }

        ThemedButton {
            text: "Dismiss"
            visible: notice.hasUpdate
            onClicked: App.dismissUpdate()
        }

        ThemedButton {
            text: "Restart now"
            accent: true
            visible: notice.showRestart
            onClicked: App.requestQuit()
        }
    }
}
