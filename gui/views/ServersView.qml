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
    property string settingsPreviewText: "No channel selected."
    property string bonusPreviewText: "No channel selected."

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

    function isActiveRunChannel() {
        var s = currentServer()
        var c = currentChannel()
        if (!s || !c)
            return false
        return s.id === serverData.active_server_id && c.id === serverData.active_channel_id
    }

    function buildSettingsPreview(ch) {
        if (!ch)
            return "No channel selected."
        var keys = Object.keys(ch.settings || {})
        if (keys.length === 0)
            return "No $settings yet — set this channel on Run, connect, then Fetch $settings."
        var body = JSON.stringify(ch.settings, null, 2)
        if (ch.settings_summary)
            return ch.settings_summary + "\n\n" + body
        return body
    }

    function buildBonusPreview(ch) {
        if (!ch)
            return "No channel selected."
        var keys = Object.keys(ch.bonus || {})
        if (keys.length === 0)
            return "No $bonus yet — run Fetch $bonus while connected (fetch $settings first for full rolls/h math)."
        var body = JSON.stringify(ch.bonus, null, 2)
        if (ch.bonus_summary)
            return ch.bonus_summary + "\n\n" + body
        return body
    }

    function updatePreviewText() {
        var ch = currentChannel()
        settingsPreviewText = buildSettingsPreview(ch)
        bonusPreviewText = buildBonusPreview(ch)
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

    function syncListIndices() {
        _syncing = true
        clampServerIndex()
        clampChannelIndex()
        updateListCounts()
        applyListIndices()
        _syncing = false
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
        updatePreviewText()
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
        updatePreviewText()
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
            updatePreviewText()
            return
        }
        selectedServerIndex = serverList.currentIndex
        clampChannelIndex()
        updateListCounts()
        applyListIndices()
        _syncing = false
        updatePreviewText()
    }

    function onChannelSelectionChanged() {
        if (_syncing)
            return
        selectedChannelIndex = channelList.currentIndex
        updatePreviewText()
    }

    readonly property int workspaceHeight: Math.max(
        360,
        Math.min(560, Math.floor(height - 40))
    )

    Connections {
        target: App
        function onServersChanged() {
            refreshServerData()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: serversRoot.workspaceHeight
            Layout.minimumHeight: 360
            spacing: 16

        PanelCard {
            Layout.preferredWidth: 240
            Layout.maximumWidth: 280
            Layout.minimumWidth: 200
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
                    Layout.minimumHeight: 100
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

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 280
            spacing: 12

            PanelCard {
                Layout.fillWidth: true
                title: {
                    var s = currentServer()
                    return s ? s.name : "Channels"
                }
                titleSize: 14

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        ThemedTextField {
                            id: chNameField
                            Layout.preferredWidth: 120
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
                        Layout.preferredHeight: 100
                        Layout.minimumHeight: 60
                        clip: true
                        model: serversRoot.channelListCount
                        onCurrentIndexChanged: serversRoot.onChannelSelectionChanged()
                        delegate: ThemedListDelegate {
                            width: channelList.width
                            property var channelItem: {
                                var chs = channelsForServer()
                                return index >= 0 && index < chs.length ? chs[index] : null
                            }
                            text: channelItem ? ("#" + channelItem.name + "  (" + channelItem.channel_id + ")") : ""
                            highlighted: ListView.isCurrentItem
                            onClicked: channelList.currentIndex = index
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        ThemedButton {
                            text: "Fetch $settings"
                            enabled: App.connected && serversRoot.isActiveRunChannel()
                            onClicked: App.fetchSettings()
                        }
                        ThemedButton {
                            text: "Fetch $bonus"
                            enabled: App.connected && serversRoot.isActiveRunChannel()
                            onClicked: App.fetchBonus()
                        }
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

                    Label {
                        Layout.fillWidth: true
                        text: serversRoot.isActiveRunChannel()
                            ? "This channel is the active Run target. Fetch works while connected."
                            : "Fetch is only available for the channel selected on Run → Run target."
                        color: Theme.fgMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 160
                spacing: 12

                PanelCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 100
                    title: "$settings"
                    titleSize: 13
                    fillContentVertically: true

                    ScrollView {
                        id: settingsScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        TextArea {
                            width: settingsScroll.availableWidth
                            readOnly: true
                            wrapMode: TextArea.Wrap
                            font.family: "Consolas, monospace"
                            font.pixelSize: 10
                            color: Theme.fgSecondary
                            text: serversRoot.settingsPreviewText
                            background: Rectangle { color: "transparent" }
                        }
                    }
                }

                PanelCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 100
                    title: "$bonus"
                    titleSize: 13
                    fillContentVertically: true

                    ScrollView {
                        id: bonusScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        TextArea {
                            width: bonusScroll.availableWidth
                            readOnly: true
                            wrapMode: TextArea.Wrap
                            font.family: "Consolas, monospace"
                            font.pixelSize: 10
                            color: Theme.fgSecondary
                            text: serversRoot.bonusPreviewText
                            background: Rectangle { color: "transparent" }
                        }
                    }
                }
            }
        }
        }
    }

    Component.onCompleted: syncFromActiveRunTarget()
}
