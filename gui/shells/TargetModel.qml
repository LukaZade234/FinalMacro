import QtQuick

import gui 1.0

/*
    Account / channel / preset selection for the Run designs.

    The mockups show three pickers, with server and channel collapsed into one
    "Channel" entry, so the server list is flattened here into
    "Server · #channel" rows. Selection always goes through App.setRunTarget so
    the four ids stay consistent.
*/
Item {
    id: target

    visible: false
    width: 0
    height: 0

    property var accountData: ({ accounts: [], active_account_id: "" })
    property var presetData: ({ presets: [], active_preset_id: "" })
    property var serverData: ({ servers: [], active_server_id: "", active_channel_id: "" })
    property bool updating: false

    readonly property var accounts: accountData.accounts || []
    readonly property var presets: presetData.presets || []
    readonly property var servers: serverData.servers || []

    // [{ serverId, serverName, channelId, channelName, label }]
    readonly property var channels: {
        var out = []
        var list = servers
        for (var i = 0; i < list.length; i++) {
            var server = list[i]
            var chans = server.channels || []
            for (var j = 0; j < chans.length; j++) {
                out.push({
                    serverId: server.id,
                    serverName: server.name,
                    channelId: chans[j].id,
                    channelName: chans[j].name,
                    label: server.name + " · #" + chans[j].name
                })
            }
        }
        return out
    }

    readonly property int accountIndex: indexOfId(accounts, accountData.active_account_id)
    readonly property int presetIndex: indexOfId(presets, presetData.active_preset_id)
    readonly property int channelIndex: {
        var list = channels
        for (var i = 0; i < list.length; i++) {
            if (list[i].channelId === serverData.active_channel_id
                    && list[i].serverId === serverData.active_server_id)
                return i
        }
        return list.length > 0 ? 0 : -1
    }

    readonly property var accountNames: accounts.map(function(a) { return a.name })
    readonly property var presetNames: presets.map(function(p) { return p.name || p.id })
    readonly property var channelLabels: channels.map(function(c) { return c.label })

    readonly property string accountLabel: labelAt(accountNames, accountIndex, "No account")
    readonly property string presetLabel: labelAt(presetNames, presetIndex, "No preset")
    readonly property string channelLabel: labelAt(channelLabels, channelIndex, "No channel")

    readonly property bool ready: accountIndex >= 0 && channelIndex >= 0 && presetIndex >= 0
    readonly property string warning: {
        if (accounts.length === 0) return "Add an account on the Accounts page."
        if (servers.length === 0) return "Add a server on the Servers page."
        if (channels.length === 0) return "This server has no channels — add one on Servers."
        if (presets.length === 0) return "Add a preset on the Presets page."
        return ""
    }

    function indexOfId(list, id) {
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === id)
                return i
        }
        return list.length > 0 ? 0 : -1
    }

    function labelAt(list, index, fallback) {
        return (index >= 0 && index < list.length) ? list[index] : fallback
    }

    function selectAccount(index) {
        apply(index, channelIndex, presetIndex)
    }

    function selectChannel(index) {
        apply(accountIndex, index, presetIndex)
    }

    function selectPreset(index) {
        apply(accountIndex, channelIndex, index)
    }

    function apply(accountIdx, channelIdx, presetIdx) {
        if (updating)
            return
        if (accountIdx < 0 || accountIdx >= accounts.length)
            return
        if (channelIdx < 0 || channelIdx >= channels.length)
            return
        if (presetIdx < 0 || presetIdx >= presets.length)
            return
        var channel = channels[channelIdx]
        App.setRunTarget(
            accounts[accountIdx].id,
            channel.serverId,
            channel.channelId,
            presets[presetIdx].id
        )
    }

    function reload() {
        updating = true
        accountData = parse(App.accountsJson, { accounts: [], active_account_id: "" })
        presetData = parse(App.presetsJson, { presets: [], active_preset_id: "" })
        serverData = parse(App.serversJson, { servers: [], active_server_id: "", active_channel_id: "" })
        Qt.callLater(function() { target.updating = false })
    }

    function parse(text, fallback) {
        try {
            var value = JSON.parse(text)
            return value === null ? fallback : value
        } catch (e) {
            return fallback
        }
    }

    Connections {
        target: App
        function onConfigChanged() { target.reload() }
        function onServersChanged() { target.reload() }
    }

    Component.onCompleted: reload()
}
