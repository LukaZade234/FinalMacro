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
    property var serverData: ({ servers: [] })
    property int selectedIndex: 0
    property bool showToken: false
    property bool updating: false
    property int dailyChannelIndex: 0
    property var dailyLabels: ["Not set"]

    function reload() {
        updating = true
        try {
            accountData = JSON.parse(App.accountsJson)
        } catch (e) {
            accountData = { accounts: [] }
        }
        try {
            serverData = JSON.parse(App.serversJson)
        } catch (e) {
            serverData = { servers: [] }
        }
        if (selectedIndex >= (accountData.accounts || []).length)
            selectedIndex = Math.max(0, (accountData.accounts || []).length - 1)
        if (accountList)
            accountList.currentIndex = selectedIndex
        dailyLabels = dailyChannelLabels()
        loadEditor()
        Qt.callLater(function() { accountsRoot.updating = false })
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

    function dailyChannelOptions() {
        var options = [{ id: "", label: "Not set" }]
        var servers = serverData.servers || []
        for (var i = 0; i < servers.length; i++) {
            var server = servers[i]
            var channels = server.channels || []
            for (var j = 0; j < channels.length; j++) {
                var ch = channels[j]
                options.push({
                    id: ch.id,
                    label: server.name + " · #" + ch.name
                })
            }
        }
        return options
    }

    function dailyChannelLabels() {
        return dailyChannelOptions().map(function(opt) { return opt.label })
    }

    function indexForDailyChannel(channelId) {
        var options = dailyChannelOptions()
        for (var i = 0; i < options.length; i++) {
            if (options[i].id === (channelId || ""))
                return i
        }
        return 0
    }

    function loadEditor() {
        var acc = currentAccount()
        if (!acc) {
            nameField.text = ""
            tokenField.text = ""
            typeCombo.currentIndex = 0
            dailyChannelIndex = 0
            return
        }
        nameField.text = acc.name
        tokenField.text = acc.token
        typeCombo.currentIndex = acc.type === "Alt" ? 1 : 0
        dailyChannelIndex = indexForDailyChannel(acc.daily_channel_id)
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
        reload()
    }

    Connections {
        target: App
        function onConfigChanged() {
            accountsRoot.reload()
        }
        function onServersChanged() {
            accountsRoot.reload()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PanelCard {
            Layout.preferredWidth: 220
            Layout.maximumWidth: 260
            Layout.fillHeight: true
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
                    Layout.minimumHeight: 80
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
            Layout.fillHeight: true
            Layout.maximumHeight: detailsCol.implicitHeight + 48
            Layout.alignment: Qt.AlignTop
            title: currentAccount() ? currentAccount().name : "Account details"
            titleSize: 14

            ColumnLayout {
                id: detailsCol
                Layout.fillWidth: true
                spacing: 10

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 10
                    rowSpacing: 8

                    Label { text: "Name"; color: Theme.fgSecondary; font.pixelSize: 11 }
                    ThemedTextField {
                        id: nameField
                        Layout.fillWidth: true
                    }

                    Label { text: "Type"; color: Theme.fgSecondary; font.pixelSize: 11 }
                    ThemedComboBox {
                        id: typeCombo
                        Layout.fillWidth: true
                        model: ["Main", "Alt"]
                    }

                    Label {
                        text: "$p / $daily channel"
                        color: Theme.fgSecondary
                        font.pixelSize: 11
                    }
                    ThemedComboBox {
                        id: dailyChannelCombo
                        Layout.fillWidth: true
                        model: accountsRoot.dailyLabels
                        currentIndex: accountsRoot.dailyChannelIndex
                        enabled: accountsRoot.currentAccount() !== null
                        onActivated: function(index) {
                            if (accountsRoot.updating)
                                return
                            var acc = accountsRoot.currentAccount()
                            var options = accountsRoot.dailyChannelOptions()
                            if (!acc || index < 0 || index >= options.length)
                                return
                            accountsRoot.dailyChannelIndex = index
                            App.setAccountDailyChannel(acc.id, options[index].id)
                        }
                    }
                }

                Label {
                    text: "Token"
                    color: Theme.fgSecondary
                    font.pixelSize: 11
                }

                // Always constrained to panel width; wrap when shown, mask when hidden.
                TextField {
                    id: tokenField
                    Layout.fillWidth: true
                    Layout.preferredHeight: accountsRoot.showToken ? 72 : 36
                    wrapMode: accountsRoot.showToken ? TextInput.WrapAnywhere : TextInput.NoWrap
                    verticalAlignment: accountsRoot.showToken ? TextInput.AlignTop : TextInput.AlignVCenter
                    selectByMouse: true
                    echoMode: accountsRoot.showToken ? TextInput.Normal : TextInput.Password
                    font.family: "Consolas, monospace"
                    font.pixelSize: 11
                    color: Theme.fgPrimary
                    placeholderText: "Discord user token"
                    placeholderTextColor: Theme.fgMuted
                    selectionColor: Theme.accentPrimary
                    selectedTextColor: Theme.bgDark
                    leftPadding: 10
                    rightPadding: 10
                    topPadding: accountsRoot.showToken ? 8 : 0
                    bottomPadding: accountsRoot.showToken ? 8 : 0
                    background: Rectangle {
                        radius: 6
                        color: Theme.inputBg
                        border.color: tokenField.activeFocus ? Theme.accentPrimary : Theme.border
                        border.width: 1
                    }
                }

                ThemedCheckBox {
                    text: "Show token"
                    textSize: 11
                    checked: accountsRoot.showToken
                    onToggled: accountsRoot.showToken = checked
                }

                Label {
                    Layout.fillWidth: true
                    text: "$p and $daily are per account, not per server. Pick one channel to send both; leave unset to skip."
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: "Active run target is chosen on the Run tab."
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                ThemedButton {
                    text: "Save"
                    accent: true
                    onClicked: saveCurrent()
                }
            }
        }
    }

    Component.onCompleted: reload()
}
