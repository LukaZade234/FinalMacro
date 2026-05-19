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
    property bool _syncing: false
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

    function buildSettingsPreview(ch) {
        if (!ch)
            return "No channel selected."
        var keys = Object.keys(ch.settings || {})
        if (keys.length === 0)
            return "No $settings yet — connect on Run, select this channel, then Fetch $settings."
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

    function syncListIndices() {
        _syncing = true
        if (serverList)
            serverList.currentIndex = selectedServerIndex
        if (channelList)
            channelList.currentIndex = selectedChannelIndex
        _syncing = false
    }

    function refreshServerData() {
        try {
            serverData = JSON.parse(App.serversJson)
        } catch (e) {
            serverData = { servers: [] }
        }
        var list = servers()
        if (selectedServerIndex >= list.length)
            selectedServerIndex = Math.max(0, list.length - 1)
        if (selectedChannelIndex >= channelsForServer().length)
            selectedChannelIndex = channelsForServer().length > 0 ? 0 : -1
        syncListIndices()
        updatePreviewText()
    }

    function syncFromActiveRunTarget() {
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
        if (selectedServerIndex >= list.length)
            selectedServerIndex = Math.max(0, list.length - 1)
        if (selectedChannelIndex >= channelsForServer().length)
            selectedChannelIndex = channelsForServer().length > 0 ? 0 : -1
        syncListIndices()
        updatePreviewText()
    }

    function onServerSelectionChanged() {
        if (_syncing)
            return
        selectedServerIndex = serverList.currentIndex
        selectedChannelIndex = channelsForServer().length > 0 ? 0 : -1
        syncListIndices()
        updatePreviewText()
    }

    function onChannelSelectionChanged() {
        if (_syncing)
            return
        selectedChannelIndex = channelList.currentIndex
        updatePreviewText()
    }

    Connections {
        target: App
        function onServersChanged() {
            refreshServerData()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PanelCard {
            Layout.preferredWidth: 240
            Layout.maximumWidth: 280
            Layout.fillHeight: true
            title: "Servers"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    TextField {
                        id: newServerField
                        Layout.fillWidth: true
                        placeholderText: "Server name"
                        color: Theme.fgPrimary
                        background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                    }
                    Button {
                        text: "Add"
                        enabled: newServerField.text.trim().length > 0
                        onClicked: {
                            App.addServer(newServerField.text.trim())
                            newServerField.text = ""
                            refreshServerData()
                            selectedServerIndex = servers().length - 1
                            syncListIndices()
                        }
                    }
                }

                ListView {
                    id: serverList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: servers().length
                    onCurrentIndexChanged: serversRoot.onServerSelectionChanged()
                    delegate: ItemDelegate {
                        width: serverList.width
                        text: servers()[index].name
                        highlighted: ListView.isCurrentItem
                        onClicked: serverList.currentIndex = index
                    }
                }

                Button {
                    Layout.fillWidth: true
                    text: "Remove server"
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
                        TextField {
                            id: chNameField
                            Layout.preferredWidth: 120
                            placeholderText: "Label"
                            color: Theme.fgPrimary
                            background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                        }
                        TextField {
                            id: chIdField
                            Layout.fillWidth: true
                            placeholderText: "Discord channel ID"
                            color: Theme.fgPrimary
                            background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                        }
                        Button {
                            text: "Add channel"
                            enabled: currentServer() && chNameField.text.trim() && chIdField.text.trim()
                            onClicked: {
                                var sid = currentServer().id
                                App.addChannel(sid, chNameField.text.trim(), chIdField.text.trim())
                                chNameField.text = ""
                                chIdField.text = ""
                            }
                        }
                    }

                    ListView {
                        id: channelList
                        Layout.fillWidth: true
                        Layout.preferredHeight: 100
                        clip: true
                        model: channelsForServer().length
                        onCurrentIndexChanged: serversRoot.onChannelSelectionChanged()
                        delegate: ItemDelegate {
                            width: channelList.width
                            property var channelItem: channelsForServer()[index]
                            text: channelItem ? ("#" + channelItem.name + "  (" + channelItem.channel_id + ")") : ""
                            highlighted: ListView.isCurrentItem
                            onClicked: channelList.currentIndex = index
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Button {
                            text: "Use on Run"
                            enabled: currentChannel() !== null
                            onClicked: {
                                var s = currentServer()
                                var c = currentChannel()
                                if (s && c)
                                    App.setActiveServerChannel(s.id, c.id)
                            }
                        }
                        Button {
                            text: "Fetch $settings"
                            enabled: App.connected && currentChannel() !== null
                            onClicked: {
                                var s = currentServer()
                                var c = currentChannel()
                                if (s && c)
                                    App.setActiveServerChannel(s.id, c.id)
                                App.fetchSettings()
                            }
                        }
                        Button {
                            text: "Fetch $bonus"
                            enabled: App.connected && currentChannel() !== null
                            onClicked: {
                                var s = currentServer()
                                var c = currentChannel()
                                if (s && c)
                                    App.setActiveServerChannel(s.id, c.id)
                                App.fetchBonus()
                            }
                        }
                        Button {
                            text: "Remove channel"
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
                        text: "Parsed data fills in when Mudae replies to $settings / $bonus on the connected channel. Add channels by name + snowflake ID."
                        color: Theme.fgMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12

                PanelCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    title: "$settings"
                    titleSize: 13
                    fillContentVertically: true

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        TextArea {
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
                    title: "$bonus"
                    titleSize: 13
                    fillContentVertically: true

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        TextArea {
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

    Component.onCompleted: syncFromActiveRunTarget()
}
