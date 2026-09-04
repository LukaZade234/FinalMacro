import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: serversRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var serverData: ({ servers: [] })
    property int selectedServerIndex: 0
    property int selectedChannelIndex: -1
    property int serverListCount: 0
    property int channelListCount: 0
    property bool _syncing: false
    property bool pendingSelectLastServer: false
    property string pendingChannelSelectId: ""
    property var mudaePresetData: ({ presets: [], default_preset_id: "" })

    function refreshMudaePresetData() {
        try {
            mudaePresetData = JSON.parse(App.mudaeSettingsPresetsJson)
        } catch (e) {
            mudaePresetData = { presets: [], default_preset_id: "" }
        }
    }

    function defaultMudaePresetId() {
        return mudaePresetData.default_preset_id || ""
    }

    function complianceColorForChannel(channelProfileId) {
        var pid = defaultMudaePresetId()
        if (!channelProfileId || !pid)
            return Theme.fgMuted
        var status = App.getChannelComplianceStatus(channelProfileId, pid)
        if (status === "match")
            return Theme.success
        if (status === "drift")
            return Theme.error
        return Theme.warning
    }

    function complianceTooltipForChannel(channelProfileId) {
        var pid = defaultMudaePresetId()
        if (!channelProfileId || !pid)
            return "No default settings preset"
        var status = App.getChannelComplianceStatus(channelProfileId, pid)
        if (status === "match")
            return "Matches default settings preset"
        if (status === "drift")
            return "Drift from default settings preset"
        return "Partial or unknown — fetch $settings"
    }

    function servers() {
        return serverData.servers || []
    }

    function currentServer() {
        var list = servers()
        if (selectedServerIndex < 0 || selectedServerIndex >= list.length)
            return null
        return list[selectedServerIndex]
    }

    function channelsForServer() {
        var s = currentServer()
        return s ? (s.channels || []) : []
    }

    function currentChannel() {
        var chs = channelsForServer()
        if (selectedChannelIndex < 0 || selectedChannelIndex >= chs.length)
            return null
        return chs[selectedChannelIndex]
    }

    function currentChannelProfileId() {
        var c = currentChannel()
        return c ? c.id : ""
    }

    function isActiveRunChannel() {
        var s = currentServer()
        var c = currentChannel()
        if (!s || !c)
            return false
        return s.id === serverData.active_server_id && c.id === serverData.active_channel_id
    }

    function clampServerIndex() {
        var list = servers()
        if (list.length === 0) {
            selectedServerIndex = -1
            return
        }
        if (selectedServerIndex >= list.length)
            selectedServerIndex = list.length - 1
        if (selectedServerIndex < 0)
            selectedServerIndex = 0
    }

    function clampChannelIndex() {
        var chs = channelsForServer()
        if (chs.length === 0) {
            selectedChannelIndex = -1
            return
        }
        if (selectedChannelIndex < 0 || selectedChannelIndex >= chs.length)
            selectedChannelIndex = 0
    }

    function selectChannelById(channelProfileId) {
        if (!channelProfileId)
            return false
        var chs = channelsForServer()
        for (var i = 0; i < chs.length; i++) {
            if (chs[i].id === channelProfileId) {
                selectedChannelIndex = i
                return true
            }
        }
        return false
    }

    function updateListCounts() {
        serverListCount = servers().length
        channelListCount = channelsForServer().length
    }

    function applyListIndices() {
        if (serverList)
            serverList.currentIndex = selectedServerIndex >= 0 ? selectedServerIndex : -1
        if (channelList)
            channelList.currentIndex = channelListCount > 0 ? selectedChannelIndex : -1
    }

    function refreshServerData() {
        _syncing = true
        try {
            serverData = JSON.parse(App.serversJson)
        } catch (e) {
            serverData = { servers: [] }
        }
        if (pendingSelectLastServer) {
            pendingSelectLastServer = false
            selectedServerIndex = Math.max(0, servers().length - 1)
            selectedChannelIndex = -1
        }
        clampServerIndex()
        if (pendingChannelSelectId) {
            if (!selectChannelById(pendingChannelSelectId))
                clampChannelIndex()
            pendingChannelSelectId = ""
        } else {
            clampChannelIndex()
        }
        updateListCounts()
        applyListIndices()
        _syncing = false
    }

    function syncFromActiveRunTarget() {
        _syncing = true
        try {
            serverData = JSON.parse(App.serversJson)
        } catch (e) {
            serverData = { servers: [] }
        }
        var list = servers()
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === serverData.active_server_id) {
                selectedServerIndex = i
                break
            }
        }
        var chs = channelsForServer()
        for (var j = 0; j < chs.length; j++) {
            if (chs[j].id === serverData.active_channel_id) {
                selectedChannelIndex = j
                break
            }
        }
        clampServerIndex()
        clampChannelIndex()
        updateListCounts()
        applyListIndices()
        _syncing = false
    }

    function onServerSelectionChanged() {
        if (_syncing)
            return
        _syncing = true
        if (servers().length === 0) {
            selectedServerIndex = -1
            selectedChannelIndex = -1
            updateListCounts()
            applyListIndices()
            _syncing = false
            return
        }
        selectedServerIndex = serverList.currentIndex
        clampChannelIndex()
        updateListCounts()
        applyListIndices()
        _syncing = false
    }

    function onChannelSelectionChanged() {
        if (_syncing)
            return
        selectedChannelIndex = channelList.currentIndex
    }

    Connections {
        target: App
        function onServersChanged() {
            refreshServerData()
        }
        function onMudaeSettingsPresetsChanged() {
            refreshMudaePresetData()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 250
            Layout.maximumHeight: 280
            Layout.minimumHeight: 200
            spacing: 12

            PanelCard {
                Layout.preferredWidth: 200
                Layout.maximumWidth: 240
                Layout.minimumWidth: 160
                Layout.fillHeight: true
                title: "Servers"
                titleSize: 14
                fillContentVertically: true

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8

                    ThemedTextField {
                        id: newServerField
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        placeholderText: "Server name"
                    }

                    ThemedButton {
                        Layout.fillWidth: true
                        text: "Add server"
                        accent: true
                        enabled: newServerField.text.trim().length > 0
                        onClicked: {
                            serversRoot.pendingSelectLastServer = true
                            App.addServer(newServerField.text.trim())
                            newServerField.text = ""
                        }
                    }

                    ListView {
                        id: serverList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 60
                        clip: true
                        model: serversRoot.serverListCount
                        onCurrentIndexChanged: serversRoot.onServerSelectionChanged()
                        delegate: ThemedListDelegate {
                            width: serverList.width
                            text: {
                                var list = servers()
                                return index >= 0 && index < list.length ? list[index].name : ""
                            }
                            highlighted: ListView.isCurrentItem
                            onClicked: serverList.currentIndex = index
                        }
                    }

                    ThemedButton {
                        Layout.fillWidth: true
                        text: "Remove server"
                        danger: true
                        enabled: servers().length > 0
                        onClicked: {
                            var s = currentServer()
                            if (!s)
                                return
                            App.removeServer(s.id)
                        }
                    }
                }
            }

            PanelCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 240
                title: {
                    var s = currentServer()
                    return s ? s.name : "Channels"
                }
                titleSize: 14
                fillContentVertically: true

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        ThemedTextField {
                            id: chNameField
                            Layout.preferredWidth: 100
                            Layout.minimumWidth: 72
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            placeholderText: "Label"
                        }
                        ThemedTextField {
                            id: chIdField
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            placeholderText: "Discord channel ID"
                        }
                    }

                    ThemedButton {
                        Layout.fillWidth: true
                        text: "Add channel"
                        accent: true
                        enabled: currentServer() && chNameField.text.trim() && chIdField.text.trim()
                        onClicked: {
                            var server = currentServer()
                            if (!server)
                                return
                            var newChannelId = App.addChannel(
                                server.id,
                                chNameField.text.trim(),
                                chIdField.text.trim()
                            )
                            chNameField.text = ""
                            chIdField.text = ""
                            if (newChannelId)
                                serversRoot.pendingChannelSelectId = newChannelId
                        }
                    }

                    ListView {
                        id: channelList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 60
                        clip: true
                        model: serversRoot.channelListCount
                        onCurrentIndexChanged: serversRoot.onChannelSelectionChanged()
                        delegate: ItemDelegate {
                            width: channelList.width
                            height: 32
                            property var channelItem: {
                                var chs = channelsForServer()
                                return index >= 0 && index < chs.length ? chs[index] : null
                            }
                            highlighted: ListView.isCurrentItem
                            onClicked: channelList.currentIndex = index

                            contentItem: RowLayout {
                                spacing: 6
                                Rectangle {
                                    width: 8
                                    height: 8
                                    radius: 4
                                    visible: channelItem && serversRoot.defaultMudaePresetId().length > 0
                                    color: channelItem
                                        ? serversRoot.complianceColorForChannel(channelItem.id)
                                        : Theme.fgMuted
                                    ToolTip.visible: chipMa.containsMouse
                                    ToolTip.text: channelItem
                                        ? serversRoot.complianceTooltipForChannel(channelItem.id)
                                        : ""
                                    MouseArea {
                                        id: chipMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        acceptedButtons: Qt.NoButton
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: channelItem ? ("#" + channelItem.name + "  (" + channelItem.channel_id + ")") : ""
                                    color: parent.parent.highlighted ? Theme.fgPrimary : Theme.fgSecondary
                                    font.pixelSize: 12
                                    font.weight: parent.parent.highlighted ? Font.DemiBold : Font.Normal
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }

                            background: Rectangle {
                                radius: 6
                                color: parent.highlighted ? Theme.bgLight
                                     : parent.hovered ? Theme.bgMedium
                                     : "transparent"
                            }
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        ThemedButton {
                            text: "Remove channel"
                            danger: true
                            enabled: currentChannel() !== null
                            onClicked: {
                                var s = currentServer()
                                var c = currentChannel()
                                if (!s || !c)
                                    return
                                App.removeChannel(s.id, c.id)
                            }
                        }
                    }

                    // Fetching moved to the scope bars on Mudae and Spheres:
                    // a sheet belongs to the page that reads it, and from
                    // there it can be fetched for any pair rather than only
                    // the connected one.
                    Label {
                        Layout.fillWidth: true
                        text: "Fetch $settings and $bonus on Mudae; $shop and $wl on Spheres."
                        color: Theme.fgMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 280
            spacing: 12

            PanelCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 220
                title: "$settings (parsed)"
                titleSize: 13
                fillContentVertically: true

                MudaeSheetPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    sheetKind: "settings"
                    channelProfileId: serversRoot.currentChannelProfileId()
                }
            }

            PanelCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 220
                title: "$bonus (parsed)"
                titleSize: 13
                fillContentVertically: true

                MudaeSheetPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    sheetKind: "bonus"
                    channelProfileId: serversRoot.currentChannelProfileId()
                }
            }

        }
    }

    Component.onCompleted: {
        refreshMudaePresetData()
        syncFromActiveRunTarget()
    }
}
