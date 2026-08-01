import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Shows on the Run page when the checked-out branch is behind origin, and
// stays visible after a successful pull so the user sees the restart notice.
Item {
    id: banner

    readonly property bool hasUpdate: App.updateAvailable
    readonly property bool hasPullMessage: App.updatePullMessage !== ""
    visible: hasUpdate || hasPullMessage || App.updatePulling
    implicitHeight: visible ? content.implicitHeight + 20 : 0

    property bool expanded: false
    property var commits: []

    function refreshCommits() {
        try {
            commits = JSON.parse(App.updateCommitsJson)
        } catch (e) {
            commits = []
        }
    }

    Connections {
        target: App
        function onUpdateStatusChanged() { banner.refreshCommits() }
    }

    Component.onCompleted: refreshCommits()

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: Theme.bgMedium
        border.color: Theme.accentSecondary
        border.width: 1
    }

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Label {
                Layout.fillWidth: true
                text: banner.hasUpdate
                    ? "Update available — " + App.updateBehindCount
                        + (App.updateBehindCount === 1 ? " change" : " changes")
                        + " on " + App.updateBranch
                    : "FinalMacro update"
                color: Theme.fgPrimary
                font.pixelSize: 12
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }

            ThemedButton {
                text: banner.expanded ? "Hide changes" : "Show changes"
                visible: banner.hasUpdate && banner.commits.length > 0
                onClicked: banner.expanded = !banner.expanded
            }

            ThemedButton {
                text: "Dismiss"
                visible: banner.hasUpdate
                onClicked: App.dismissUpdate()
            }

            ThemedButton {
                text: App.updatePulling ? "Updating…" : "Update now"
                accent: true
                loading: App.updatePulling
                visible: banner.hasUpdate && App.updateCanPull
                enabled: !App.updatePulling && !App.sessionActive
                onClicked: App.pullUpdate()
            }

            ThemedButton {
                text: "Restart now"
                accent: true
                visible: !banner.hasUpdate && banner.hasPullMessage
                onClicked: App.requestQuit()
            }
        }

        Label {
            Layout.fillWidth: true
            visible: banner.hasUpdate && !App.updateCanPull
            text: "Local changes or commits are blocking an automatic update — run `git pull` yourself when ready."
            color: Theme.warning
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            visible: banner.hasUpdate && App.updateCanPull && App.sessionActive
            text: "Disconnect first — updating while connected could interrupt the macro."
            color: Theme.warning
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            visible: banner.hasPullMessage
            text: App.updatePullMessage
            color: App.updatePullOk ? Theme.success : Theme.warning
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: banner.hasUpdate && banner.expanded
            spacing: 3

            Repeater {
                model: banner.commits
                delegate: Label {
                    Layout.fillWidth: true
                    text: "• " + modelData
                    color: Theme.fgSecondary
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
