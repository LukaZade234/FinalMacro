import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

RowLayout {
    id: root
    property var serverData: ({ servers: [], active_server_id: "", active_channel_id: "" })
    property int serverIndex: 0
    property int channelIndex: 0
    property bool updating: false

    spacing: 10
    Layout.fillWidth: true

    function reload() {
        updating = true
        try {
            serverData = JSON.parse(App.serversJson)
        } catch (e) {
            serverData = { servers: [], active_server_id: "", active_channel_id: "" }
        }
        var servers = serverData.servers || []
        serverIndex = 0
        for (var i = 0; i < servers.length; i++) {
            if (servers[i].id === serverData.active_server_id) {
                serverIndex = i
                break
            }
        }
        syncChannelIndex()
        serverCombo.currentIndex = serverIndex
        channelCombo.currentIndex = channelIndex
        updating = false
    }

    function currentServer() {
        var servers = serverData.servers || []
        if (serverIndex < 0 || serverIndex >= servers.length)
            return null
        return servers[serverIndex]
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

    function applySelection() {
        if (updating)
            return
        var server = currentServer()
        if (!server || !server.channels || channelIndex < 0 || channelIndex >= server.channels.length)
            return
        var ch = server.channels[channelIndex]
        App.setActiveServerChannel(server.id, ch.id)
    }

    Connections {
        target: App
        function onServersChanged() {
            root.reload()
        }
    }

    Label {
        text: "Server"
        color: Theme.fgSecondary
        font.pixelSize: 11
    }

    ThemedComboBox {
        id: serverCombo
        Layout.preferredWidth: 180
        Layout.fillWidth: true
        model: (serverData.servers || []).map(function(s) { return s.name })
        currentIndex: root.serverIndex
        enabled: model.length > 0
        onActivated: function(index) {
            root.serverIndex = index
            root.syncChannelIndex()
            channelCombo.currentIndex = root.channelIndex
            root.applySelection()
        }
    }

    Label {
        text: "Channel"
        color: Theme.fgSecondary
        font.pixelSize: 11
    }

    ThemedComboBox {
        id: channelCombo
        Layout.preferredWidth: 160
        Layout.fillWidth: true
        property var channelList: {
            var s = root.currentServer()
            if (!s || !s.channels)
                return []
            return s.channels.map(function(c) { return "#" + c.name })
        }
        model: channelList
        currentIndex: root.channelIndex
        enabled: channelList.length > 0
        onActivated: function(index) {
            root.channelIndex = index
            root.applySelection()
        }
    }

    Component.onCompleted: reload()
}
