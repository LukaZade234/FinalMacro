import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 1200
    height: 780
    minimumWidth: 900
    minimumHeight: 560
    visible: true
    title: "Mudae Reader — parse lab"
    color: "#0c0c0f"

    readonly property color cRaised: "#141419"
    readonly property color cBorder: "#27272f"
    readonly property color cMuted: "#71717a"
    readonly property color cText: "#e4e4e7"
    readonly property color cAccent: "#6366f1"

    function modelValue(index, role) {
        if (index < 0 || index >= messageModel.count)
            return ""
        return messageModel.get(index)[role]
    }

    Component.onCompleted: {
        tokenField.text = App.getToken()
        channelField.text = App.getChannelId()
    }

    Connections {
        target: App
        function onEntryReceived(entry) {
            messageModel.insert(0, entry)
            if (messageModel.count > 500) {
                messageModel.remove(500, messageModel.count - 500)
            }
            messageList.currentIndex = 0
        }
        function onStatusChanged(text) {
            statusLabel.text = text
        }
        function onConnectedChanged(connected) {
            connectBtn.enabled = !connected
            disconnectBtn.enabled = connected
        }
    }

    ListModel { id: messageModel }

    // Read-only text that grows with wrapped content (single outer scroll only).
    component ExpandingTextBox: TextEdit {
        property int minHeight: 40
        property int extraPadding: 8

        readOnly: true
        wrapMode: TextEdit.Wrap
        selectByMouse: true
        textFormat: TextEdit.PlainText

        height: Math.max(
            minHeight,
            contentHeight + topPadding + bottomPadding + extraPadding
        )
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Rectangle {
            Layout.fillWidth: true
            radius: 10
            color: cRaised
            border.color: cBorder
            implicitHeight: connCol.implicitHeight + 24

            ColumnLayout {
                id: connCol
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8

                Label {
                    text: "Monitors every message in the channel (Mudae messages are parsed; others shown as channel traffic)."
                    color: cMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                GridLayout {
                    columns: 4
                    columnSpacing: 10
                    rowSpacing: 8
                    Layout.fillWidth: true

                    Label { text: "Token"; color: cMuted; font.pixelSize: 11 }
                    TextField {
                        id: tokenField
                        Layout.columnSpan: 3
                        Layout.fillWidth: true
                        placeholderText: "User token"
                        echoMode: TextInput.Password
                        onTextChanged: App.setToken(text)
                        color: cText
                        background: Rectangle { radius: 6; color: "#0a0a0d"; border.color: cBorder }
                    }

                    Label { text: "Channel ID"; color: cMuted; font.pixelSize: 11 }
                    TextField {
                        id: channelField
                        Layout.columnSpan: 3
                        Layout.fillWidth: true
                        placeholderText: "Discord channel snowflake"
                        onTextChanged: App.setChannelId(text)
                        color: cText
                        background: Rectangle { radius: 6; color: "#0a0a0d"; border.color: cBorder }
                    }

                    Item { Layout.fillWidth: true }

                    RowLayout {
                        spacing: 8
                        Button {
                            id: connectBtn
                            text: "Connect"
                            onClicked: App.connect()
                        }
                        Button {
                            id: disconnectBtn
                            text: "Disconnect"
                            enabled: false
                            onClicked: App.disconnect()
                        }
                        Button {
                            text: "Clear"
                            flat: true
                            onClicked: messageModel.clear()
                        }
                    }
                }

                Label {
                    id: statusLabel
                    text: App.statusText
                    color: "#6ee7b7"
                    font.pixelSize: 11
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.preferredWidth: 380
                SplitView.minimumWidth: 280
                radius: 10
                color: cRaised
                border.color: cBorder

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 6

                    Label {
                        text: "Captured messages"
                        color: "white"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        id: messageList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: messageModel
                        currentIndex: 0
                        boundsBehavior: Flickable.StopAtBounds
                        spacing: 2
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        onCurrentIndexChanged: {
                            if (currentIndex >= 0)
                                positionViewAtIndex(currentIndex, ListView.Contain)
                        }

                        delegate: ItemDelegate {
                                id: rowDelegate
                                width: messageList.width
                                padding: 8
                                highlighted: messageList.currentIndex === index
                                onClicked: messageList.currentIndex = index

                                background: Rectangle {
                                    radius: 6
                                    color: rowDelegate.highlighted ? "#18ffffff" : "transparent"
                                }

                                contentItem: ColumnLayout {
                                    spacing: 2
                                    width: rowDelegate.width - rowDelegate.leftPadding - rowDelegate.rightPadding

                                    Label {
                                        text: model.time + " · " + model.author + (model.edited ? " · edited" : "")
                                        color: cMuted
                                        font.pixelSize: 10
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        text: model.kind
                                        color: model.kind === "channel" ? "#52525b" : cAccent
                                        font.pixelSize: 10
                                        font.weight: Font.Medium
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        text: model.summary
                                        color: cText
                                        font.pixelSize: 12
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true
                radius: 10
                color: cRaised
                border.color: cBorder

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Label {
                        text: "Parse detail"
                        color: "white"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }

                    ScrollView {
                        id: detailScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded
                        contentWidth: availableWidth

                        ColumnLayout {
                            id: detailCol
                            width: detailScroll.availableWidth
                            spacing: 10

                            property int idx: messageList.currentIndex
                            property bool hasSelection: idx >= 0 && idx < messageModel.count

                            Label {
                                visible: !detailCol.hasSelection
                                text: "Select a message"
                                color: cMuted
                                font.pixelSize: 12
                                Layout.fillWidth: true
                            }

                            GroupBox {
                                visible: detailCol.hasSelection
                                title: "Summary"
                                Layout.fillWidth: true
                                label: Label { text: parent.title; color: cMuted; font.pixelSize: 11 }
                                background: Rectangle { color: "transparent"; border.color: cBorder; radius: 6 }

                                contentItem: ColumnLayout {
                                    spacing: 6
                                    width: parent.availableWidth

                                    Label {
                                        text: win.modelValue(detailCol.idx, "summary")
                                        color: "white"
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        property string warnText: win.modelValue(detailCol.idx, "warnings")
                                        visible: warnText !== "" && warnText !== "(none)"
                                        text: "⚠ " + warnText
                                        color: "#fcd34d"
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }

                            GroupBox {
                                visible: detailCol.hasSelection
                                title: "Parsed fields (JSON)"
                                Layout.fillWidth: true
                                label: Label { text: parent.title; color: cMuted; font.pixelSize: 11 }
                                background: Rectangle { color: "#0a0a0d"; border.color: cBorder; radius: 6 }

                                contentItem: ExpandingTextBox {
                                    width: parent.availableWidth
                                    text: win.modelValue(detailCol.idx, "parsedFields")
                                    color: "#a5b4fc"
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: 11
                                    minHeight: 60
                                }
                            }

                            GroupBox {
                                visible: detailCol.hasSelection
                                title: "Raw content"
                                Layout.fillWidth: true
                                label: Label { text: parent.title; color: cMuted; font.pixelSize: 11 }
                                background: Rectangle { color: "#0a0a0d"; border.color: cBorder; radius: 6 }

                                contentItem: ExpandingTextBox {
                                    width: parent.availableWidth
                                    text: win.modelValue(detailCol.idx, "rawContent")
                                    color: cText
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: 11
                                }
                            }

                            GroupBox {
                                visible: detailCol.hasSelection
                                title: "Raw embeds / buttons"
                                Layout.fillWidth: true
                                label: Label { text: parent.title; color: cMuted; font.pixelSize: 11 }
                                background: Rectangle { color: "#0a0a0d"; border.color: cBorder; radius: 6 }

                                contentItem: ExpandingTextBox {
                                    width: parent.availableWidth
                                    text: win.modelValue(detailCol.idx, "rawEmbeds")
                                          + "\n\n--- buttons ---\n\n"
                                          + win.modelValue(detailCol.idx, "rawButtons")
                                    color: cMuted
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: 10
                                    minHeight: 80
                                }
                            }

                            Item { Layout.fillWidth: true; Layout.preferredHeight: 8 }
                        }
                    }
                }
            }
        }
    }
}
