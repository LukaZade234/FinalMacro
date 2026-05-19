import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

ColumnLayout {
    id: root
    spacing: 8
    Layout.fillWidth: true

    property var accountData: ({ accounts: [], active_account_id: "" })
    property var presetData: ({ presets: [], active_preset_id: "" })
    property var serverData: ({ servers: [], active_server_id: "", active_channel_id: "" })
    property int accountIndex: 0
    property int serverIndex: 0
    property int channelIndex: 0
    property int presetIndex: 0
    property bool updating: false

    function reload() {
        updating = true
        try {
            accountData = JSON.parse(App.accountsJson)
        } catch (e) {
            accountData = { accounts: [], active_account_id: "" }
        }
        try {
            presetData = JSON.parse(App.presetsJson)
        } catch (e) {
            presetData = { presets: [], active_preset_id: "" }
        }
        try {
            serverData = JSON.parse(App.serversJson)
        } catch (e) {
            serverData = { servers: [], active_server_id: "", active_channel_id: "" }
        }
        syncIndices()
        updating = false
    }

    function accounts() {
        return accountData.accounts || []
    }

    function presets() {
        return presetData.presets || []
    }

    function servers() {
        return serverData.servers || []
    }

    function currentServer() {
        var list = servers()
        if (serverIndex < 0 || serverIndex >= list.length)
            return null
        return list[serverIndex]
    }

    function channelsForServer() {
        var s = currentServer()
        return s ? (s.channels || []) : []
    }

    function syncIndices() {
        var accs = accounts()
        accountIndex = 0
        for (var i = 0; i < accs.length; i++) {
            if (accs[i].id === accountData.active_account_id) {
                accountIndex = i
                break
            }
        }
        var srvs = servers()
        serverIndex = 0
        for (var j = 0; j < srvs.length; j++) {
            if (srvs[j].id === serverData.active_server_id) {
                serverIndex = j
                break
            }
        }
        syncChannelIndex()
        var prs = presets()
        presetIndex = 0
        for (var k = 0; k < prs.length; k++) {
            if (prs[k].id === presetData.active_preset_id) {
                presetIndex = k
                break
            }
        }
        accountCombo.currentIndex = accountIndex
        serverCombo.currentIndex = serverIndex
        channelCombo.currentIndex = channelIndex
        presetCombo.currentIndex = presetIndex
    }

    function syncChannelIndex() {
        var server = currentServer()
        channelIndex = 0
        if (!server || !server.channels)
            return
        for (var j = 0; j < server.channels.length; j++) {
            if (server.channels[j].id === serverData.active_channel_id) {
                channelIndex = j
                return
            }
        }
    }

    function applyRunTarget() {
        if (updating)
            return
        var accs = accounts()
        var srv = currentServer()
        var chs = channelsForServer()
        var prs = presets()
        if (accountIndex < 0 || accountIndex >= accs.length)
            return
        if (!srv || channelIndex < 0 || channelIndex >= chs.length)
            return
        if (presetIndex < 0 || presetIndex >= prs.length)
            return
        App.setRunTarget(
            accs[accountIndex].id,
            srv.id,
            chs[channelIndex].id,
            prs[presetIndex].id
        )
    }

    Connections {
        target: App
        function onConfigChanged() {
            root.reload()
        }
        function onServersChanged() {
            root.reload()
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Label { text: "Account"; color: Theme.fgSecondary; font.pixelSize: 11 }
        ComboBox {
            id: accountCombo
            Layout.preferredWidth: 140
            Layout.fillWidth: true
            model: root.accounts().map(function(a) { return a.name + " (" + a.type + ")" })
            enabled: model.length > 0
            onActivated: function(index) {
                root.accountIndex = index
                root.applyRunTarget()
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Label { text: "Server"; color: Theme.fgSecondary; font.pixelSize: 11 }
        ComboBox {
            id: serverCombo
            Layout.preferredWidth: 120
            Layout.fillWidth: true
            model: root.servers().map(function(s) { return s.name })
            enabled: model.length > 0
            onActivated: function(index) {
                root.serverIndex = index
                root.syncChannelIndex()
                channelCombo.currentIndex = root.channelIndex
                root.applyRunTarget()
            }
        }

        Label { text: "Channel"; color: Theme.fgSecondary; font.pixelSize: 11 }
        ComboBox {
            id: channelCombo
            Layout.preferredWidth: 120
            Layout.fillWidth: true
            property var channelList: {
                var chs = root.channelsForServer()
                return chs.map(function(c) { return "#" + c.name })
            }
            model: channelList
            enabled: channelList.length > 0
            onActivated: function(index) {
                root.channelIndex = index
                root.applyRunTarget()
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Label { text: "Preset"; color: Theme.fgSecondary; font.pixelSize: 11 }
        ComboBox {
            id: presetCombo
            Layout.preferredWidth: 160
            Layout.fillWidth: true
            model: root.presets().map(function(p) { return p.id })
            enabled: model.length > 0
            onActivated: function(index) {
                root.presetIndex = index
                root.applyRunTarget()
            }
        }
    }

    Component.onCompleted: reload()
}
