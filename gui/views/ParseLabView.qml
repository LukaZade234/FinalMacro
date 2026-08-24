import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: parseRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    function syncConnectionButtons() {
        connectBtn.enabled = !App.connected
        disconnectBtn.enabled = App.connected
    }

    function modelValue(index, role) {
        if (index < 0 || index >= messageModel.count)
            return ""
        return messageModel.get(index)[role]
    }

    readonly property string activeAccountName: {
        try {
            var data = JSON.parse(App.accountsJson)
            return data.active_account_name || ""
        } catch (e) {
            return ""
        }
    }

    component ExpandingTextBox: TextEdit {
        property int minHeight: 40
        property int extraPadding: 8
        readOnly: true
        wrapMode: TextEdit.Wrap
        selectByMouse: true
        textFormat: TextEdit.PlainText
        color: Theme.fgSecondary
        height: Math.max(minHeight, contentHeight + topPadding + bottomPadding + extraPadding)
    }

    ListModel { id: messageModel }

    FileDialog {
        id: saveLogDialog
        title: "Save parse log"
        fileMode: FileDialog.SaveFile
        nameFilters: ["JSON files (*.json)"]
        defaultSuffix: "json"
        onAccepted: {
            connStatusLabel.text = App.saveParseLabLogToPath(selectedFile.toString())
        }
    }

    Connections {
        target: App
        function onEntryReceived(entry) {
            messageModel.insert(0, entry)
            if (messageModel.count > 500)
                messageModel.remove(500, messageModel.count - 500)
            messageList.currentIndex = 0
        }
        function onStatusChanged(text) {
            connStatusLabel.text = text
        }
        function onConnectedChanged(connected) {
            parseRoot.syncConnectionButtons()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        Label {
            text: "Parser debugger — uses the Run target (account token + channel from Run)."
            color: Theme.fgMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Connection"
            titleSize: 14

            GridLayout {
                columns: 4
                columnSpacing: 10
                rowSpacing: 8
                Layout.fillWidth: true

                Label { text: "Account"; color: Theme.fgSecondary; font.pixelSize: 11 }
                Label {
                    Layout.columnSpan: 3
                    Layout.fillWidth: true
                    text: parseRoot.activeAccountName
                        ? (parseRoot.activeAccountName + " — token is set on Accounts, not here")
                        : "Select account on Run / Accounts"
                    color: Theme.fgPrimary
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                Label { text: "Channel"; color: Theme.fgSecondary; font.pixelSize: 11 }
                Label {
                    Layout.columnSpan: 3
                    Layout.fillWidth: true
                    text: App.activeChannelLabel
                        ? (App.activeChannelLabel + " (" + App.getChannelId() + ")")
                        : "Select server and channel on Run"
                    color: Theme.fgPrimary
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillWidth: true }

                RowLayout {
                    spacing: 8
                    Button {
                        id: connectBtn
                        text: "Connect"
                        background: Rectangle {
                            radius: 8
                            color: Theme.accentPrimary
                        }
                        contentItem: Label {
                            text: parent.text
                            color: Theme.bgDark
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: App.connect()
                    }
                    Button {
                        id: disconnectBtn
                        text: "Disconnect"
                        enabled: false
                        background: Rectangle {
                            radius: 8
                            color: Theme.bgLight
                        }
                        contentItem: Label {
                            text: parent.text
                            color: Theme.fgPrimary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: App.disconnect()
                    }
                    Button {
                        text: "Save log"
                        flat: true
                        contentItem: Label {
                            text: parent.text
                            color: Theme.fgSecondary
                        }
                        onClicked: {
                            if (App.parseLabLogCount() === 0) {
                                connStatusLabel.text = "No messages to save"
                                return
                            }
                            saveLogDialog.currentFolder = App.getDataDirUrl()
                            saveLogDialog.currentFile = App.getParseLabDefaultSaveUrl()
                            saveLogDialog.open()
                        }
                    }
                    Button {
                        text: "Clear"
                        flat: true
                        contentItem: Label {
                            text: parent.text
                            color: Theme.fgSecondary
                        }
                        onClicked: {
                            messageModel.clear()
                            App.clearParseLabLog()
                        }
                    }
                }

                Label {
                    id: connStatusLabel
                    text: App.statusText
                    color: Theme.success
                    font.pixelSize: 11
                    Layout.columnSpan: 4
                    Layout.fillWidth: true
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.preferredHeight: 420
            orientation: Qt.Horizontal

            PanelCard {
                SplitView.preferredWidth: 380
                SplitView.minimumWidth: 280
                fillContentVertically: true
                title: "Captured messages"
                contentMargins: 8

                ListView {
                    id: messageList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: messageModel
                    spacing: 2
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: ItemDelegate {
                        id: rowDelegate
                        width: messageList.width
                        padding: 8
                        highlighted: messageList.currentIndex === index
                        onClicked: messageList.currentIndex = index

                        background: Rectangle {
                            radius: 6
                            color: rowDelegate.highlighted ? Theme.bgLight : "transparent"
                        }

                        contentItem: ColumnLayout {
                            spacing: 2
                            width: rowDelegate.width - rowDelegate.leftPadding - rowDelegate.rightPadding

                            Label {
                                text: model.time + " · " + model.author + (model.edited ? " · edited" : "")
                                color: Theme.fgMuted
                                font.pixelSize: 10
                                Layout.fillWidth: true
                            }
                            Label {
                                text: model.kind
                                color: model.kind === "channel" ? Theme.fgMuted : Theme.accentPrimary
                                font.pixelSize: 10
                                font.weight: Font.Medium
                                Layout.fillWidth: true
                            }
                            Label {
                                text: model.summary
                                color: Theme.fgPrimary
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            PanelCard {
                SplitView.fillWidth: true
                fillContentVertically: true
                title: "Parse detail"
                contentMargins: 12

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded

                    ColumnLayout {
                        id: detailCol
                        width: parent.width
                        spacing: 10
                        property int idx: messageList.currentIndex
                        property bool hasSelection: idx >= 0 && idx < messageModel.count

                        Label {
                            visible: !detailCol.hasSelection
                            text: "Select a message"
                            color: Theme.fgMuted
                            Layout.fillWidth: true
                        }

                        GroupBox {
                            visible: detailCol.hasSelection
                            title: "Summary"
                            Layout.fillWidth: true
                            label: Label { text: parent.title; color: Theme.fgSecondary; font.pixelSize: 11 }
                            background: Rectangle { color: "transparent"; border.color: Theme.border; radius: 6 }

                            ColumnLayout {
                                width: parent.availableWidth
                                Label {
                                    text: parseRoot.modelValue(detailCol.idx, "summary")
                                    color: Theme.fgPrimary
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                Label {
                                    property string warnText: parseRoot.modelValue(detailCol.idx, "warnings")
                                    visible: warnText !== "" && warnText !== "(none)"
                                    text: "⚠ " + warnText
                                    color: Theme.warning
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        GroupBox {
                            visible: detailCol.hasSelection
                            title: "Parsed fields (JSON)"
                            Layout.fillWidth: true
                            label: Label { text: parent.title; color: Theme.fgSecondary; font.pixelSize: 11 }
                            background: Rectangle { color: Theme.inputBg; border.color: Theme.border; radius: 6 }

                            ExpandingTextBox {
                                width: parent.availableWidth
                                text: parseRoot.modelValue(detailCol.idx, "parsedFields")
                                color: Theme.accentSecondary
                                font.family: "Consolas, monospace"
                                font.pixelSize: 11
                            }
                        }

                        GroupBox {
                            visible: detailCol.hasSelection
                            title: "Raw content"
                            Layout.fillWidth: true
                            label: Label { text: parent.title; color: Theme.fgSecondary; font.pixelSize: 11 }
                            background: Rectangle { color: Theme.inputBg; border.color: Theme.border; radius: 6 }

                            ExpandingTextBox {
                                width: parent.availableWidth
                                text: parseRoot.modelValue(detailCol.idx, "rawContent")
                            }
                        }

                        GroupBox {
                            visible: detailCol.hasSelection
                            title: "Raw embeds / buttons"
                            Layout.fillWidth: true
                            label: Label { text: parent.title; color: Theme.fgSecondary; font.pixelSize: 11 }
                            background: Rectangle { color: Theme.inputBg; border.color: Theme.border; radius: 6 }

                            ExpandingTextBox {
                                width: parent.availableWidth
                                text: parseRoot.modelValue(detailCol.idx, "rawEmbeds")
                                      + "\n\n--- buttons ---\n\n"
                                      + parseRoot.modelValue(detailCol.idx, "rawButtons")
                                font.pixelSize: 10
                                minHeight: 80
                            }
                        }
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        parseRoot.syncConnectionButtons()
    }
}
