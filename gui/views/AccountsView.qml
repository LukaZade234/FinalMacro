import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: accountsRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var accountData: ({ accounts: [] })
    property int selectedIndex: 0

    function reload() {
        try {
            accountData = JSON.parse(App.accountsJson)
        } catch (e) {
            accountData = { accounts: [] }
        }
        if (selectedIndex >= (accountData.accounts || []).length)
            selectedIndex = Math.max(0, (accountData.accounts || []).length - 1)
        if (accountList)
            accountList.currentIndex = selectedIndex
        loadEditor()
    }

    function accounts() {
        return accountData.accounts || []
    }

    function currentAccount() {
        var list = accounts()
        if (selectedIndex < 0 || selectedIndex >= list.length)
            return null
        return list[selectedIndex]
    }

    function allChannels() {
        try {
            var srv = JSON.parse(App.serversJson)
            var out = []
            var servers = srv.servers || []
            for (var i = 0; i < servers.length; i++) {
                var chs = servers[i].channels || []
                for (var j = 0; j < chs.length; j++) {
                    out.push({
                        id: chs[j].id,
                        label: servers[i].name + " · #" + chs[j].name
                    })
                }
            }
            return out
        } catch (e) {
            return []
        }
    }

    function loadEditor() {
        var acc = currentAccount()
        if (!acc) {
            nameField.text = ""
            tokenField.text = ""
            typeCombo.currentIndex = 0
            return
        }
        nameField.text = acc.name
        tokenField.text = acc.token
        typeCombo.currentIndex = acc.type === "Alt" ? 1 : 0
        refreshChannelChecks()
    }

    function refreshChannelChecks() {
        channelModel.clear()
        var acc = currentAccount()
        var enabled = acc ? (acc.enabled_channel_ids || []) : []
        var channels = allChannels()
        for (var i = 0; i < channels.length; i++) {
            channelModel.append({
                channelId: channels[i].id,
                label: channels[i].label,
                enabled: enabled.indexOf(channels[i].id) >= 0
            })
        }
    }

    function saveCurrent() {
        var acc = currentAccount()
        if (!acc)
            return
        App.updateAccount(
            acc.id,
            nameField.text.trim(),
            tokenField.text,
            typeCombo.currentText
        )
        var ids = []
        for (var i = 0; i < channelModel.count; i++) {
            if (channelModel.get(i).enabled)
                ids.push(channelModel.get(i).channelId)
        }
        App.setAccountEnabledChannels(acc.id, JSON.stringify(ids))
        reload()
    }

    ListModel { id: channelModel }

    Connections {
        target: App
        function onConfigChanged() {
            accountsRoot.reload()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 520
            spacing: 16

        PanelCard {
            Layout.preferredWidth: 220
            Layout.maximumWidth: 260
            Layout.preferredHeight: 520
            title: "Accounts"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                ThemedTextField {
                    id: newAccountField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    placeholderText: "Account name"
                }

                ThemedButton {
                    Layout.fillWidth: true
                    text: "Add account"
                    accent: true
                    enabled: newAccountField.text.trim().length > 0
                    onClicked: {
                        App.addAccount(newAccountField.text.trim(), "Main")
                        newAccountField.text = ""
                        reload()
                        accountList.currentIndex = accounts().length - 1
                        selectedIndex = accountList.currentIndex
                    }
                }

                ListView {
                    id: accountList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 120
                    Layout.preferredHeight: 320
                    clip: true
                    model: accounts().length
                    currentIndex: selectedIndex
                    onCurrentIndexChanged: {
                        selectedIndex = currentIndex
                        loadEditor()
                    }
                    delegate: ThemedListDelegate {
                        width: accountList.width
                        text: accounts()[index].name + " (" + accounts()[index].type + ")"
                        highlighted: accountList.currentIndex === index
                        onClicked: accountList.currentIndex = index
                    }
                }

                ThemedButton {
                    Layout.fillWidth: true
                    text: "Remove account"
                    danger: true
                    enabled: accounts().length > 0
                    onClicked: {
                        var acc = currentAccount()
                        if (!acc)
                            return
                        App.removeAccount(acc.id)
                        reload()
                    }
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 520
            title: currentAccount() ? currentAccount().name : "Account details"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10

                GridLayout {
                    Layout.fillWidth: true
                    columns: 4
                    columnSpacing: 10
                    rowSpacing: 8

                    Label { text: "Name"; color: Theme.fgSecondary; font.pixelSize: 11 }
                    ThemedTextField {
                        id: nameField
                        Layout.columnSpan: 3
                        Layout.fillWidth: true
                    }

                    Label { text: "Type"; color: Theme.fgSecondary; font.pixelSize: 11 }
                    ThemedComboBox {
                        id: typeCombo
                        Layout.columnSpan: 3
                        model: ["Main", "Alt"]
                    }

                    Label { text: "Token"; color: Theme.fgSecondary; font.pixelSize: 11 }
                    ThemedTextField {
                        id: tokenField
                        Layout.columnSpan: 3
                        Layout.fillWidth: true
                        echoMode: TextInput.Password
                    }
                }

                Label {
                    text: "Enabled channels (used for quick filtering; Run can use any channel)"
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(200, Math.max(60, channelModel.count * 32))
                    clip: true
                    model: channelModel
                    delegate: ThemedCheckBox {
                        width: parent.width
                        text: model.label
                        textSize: 11
                        checked: model.enabled
                        onToggled: channelModel.setProperty(index, "enabled", checked)
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: "Active run target is chosen on the Run tab."
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    ThemedButton {
                        text: "Save"
                        accent: true
                        onClicked: saveCurrent()
                    }
                }
            }
        }
        }
    }

    Component.onCompleted: reload()
}
