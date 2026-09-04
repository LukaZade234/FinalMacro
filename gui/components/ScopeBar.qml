import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    Which account / server / channel a page is looking at.

    Deliberately *not* `ServerChannelSelectors`: that one calls
    `App.setActiveServerChannel`, i.e. it moves the Run target. This bar keeps
    its selection to itself, so you can read account B's sheets while account A
    is mid-session.

    It starts on the Run target and says so. Change either picker and it detaches
    — the chip becomes a button that snaps back. While attached it keeps
    following, so connecting to a different channel updates the page.
*/
Rectangle {
    id: scope

    property string accountId: ""
    property string channelProfileId: ""
    // Follows the Run target until the user picks something themselves.
    property bool followingRun: true
    property bool showChannel: true

    // The sheet this page fetches, if any — one of the commands in
    // `gui/scope_fetch.py`. It sits here rather than in the page body because
    // the pickers beside it are what a fetch is *for*: the pair on the bar is
    // the pair the command is sent as, whatever Run is doing.
    property string fetchCommand: ""
    property string fetchLabel: fetchCommand ? "$" + fetchCommand : ""

    readonly property var accounts: accountData.accounts || []
    readonly property var channels: {
        var out = []
        var servers = serverData.servers || []
        for (var i = 0; i < servers.length; i++) {
            var chans = servers[i].channels || []
            for (var j = 0; j < chans.length; j++) {
                out.push({
                    id: chans[j].id,
                    name: chans[j].name,
                    serverName: servers[i].name,
                    label: servers[i].name + " · #" + chans[j].name
                })
            }
        }
        return out
    }

    readonly property int accountIndex: indexOfId(accounts, accountId)
    readonly property int channelIndex: indexOfId(channels, channelProfileId)
    readonly property string accountName: accountIndex >= 0 ? accounts[accountIndex].name : "—"
    readonly property string channelLabel: channelIndex >= 0 ? channels[channelIndex].label : "—"

    property var accountData: ({ accounts: [], active_account_id: "" })
    property var serverData: ({ servers: [], active_channel_id: "" })

    signal scopeChanged()

    implicitHeight: bar.implicitHeight + Theme.cardPadding * 2
    Layout.fillWidth: true
    color: Theme.surface
    border.width: Theme.borderWidth
    border.color: Theme.line
    radius: Theme.radiusMd

    function indexOfId(list, wanted) {
        for (var i = 0; i < (list || []).length; i++) {
            if (list[i].id === wanted)
                return i
        }
        return -1
    }

    function reload() {
        try {
            accountData = JSON.parse(App.accountsJson)
        } catch (e) {
            accountData = { accounts: [], active_account_id: "" }
        }
        try {
            serverData = JSON.parse(App.serversJson)
        } catch (e2) {
            serverData = { servers: [], active_channel_id: "" }
        }
        if (followingRun)
            adoptRunTarget()
        else
            reconcile()
    }

    /* The active account / channel *are* the Run target. */
    function adoptRunTarget() {
        var nextAccount = String(accountData.active_account_id || "")
        var nextChannel = String(serverData.active_channel_id || "")
        if (!nextAccount && accounts.length > 0)
            nextAccount = accounts[0].id
        if (!nextChannel && channels.length > 0)
            nextChannel = channels[0].id
        if (nextAccount !== accountId || nextChannel !== channelProfileId) {
            accountId = nextAccount
            channelProfileId = nextChannel
            scope.scopeChanged()
        }
    }

    /* A detached scope still has to cope with its target being deleted. */
    function reconcile() {
        var changed = false
        if (indexOfId(accounts, accountId) < 0) {
            accountId = accounts.length > 0 ? accounts[0].id : ""
            changed = true
        }
        if (indexOfId(channels, channelProfileId) < 0) {
            channelProfileId = channels.length > 0 ? channels[0].id : ""
            changed = true
        }
        if (changed)
            scope.scopeChanged()
    }

    function detach() {
        followingRun = false
    }

    function followRun() {
        followingRun = true
        adoptRunTarget()
    }

    Connections {
        target: App
        function onServersChanged() { scope.reload() }
        function onConfigChanged() { scope.reload() }
    }

    Component.onCompleted: reload()

    RowLayout {
        id: bar
        anchors.fill: parent
        anchors.margins: Theme.cardPadding
        spacing: 8

        Label {
            text: Theme.sectionLabel("scope")
            color: Theme.mute
            font.pixelSize: Theme.sizeMicro
            font.weight: Font.DemiBold
            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
        }

        ThemedComboBox {
            Layout.preferredWidth: 170
            model: scope.accounts.map(function (a) { return a.name })
            currentIndex: scope.accountIndex
            enabled: scope.accounts.length > 0
            onActivated: function (index) {
                if (index < 0 || index >= scope.accounts.length)
                    return
                scope.detach()
                scope.accountId = scope.accounts[index].id
                scope.scopeChanged()
            }
        }

        ThemedComboBox {
            Layout.preferredWidth: 230
            Layout.fillWidth: true
            Layout.maximumWidth: 340
            visible: scope.showChannel
            model: scope.channels.map(function (c) { return c.label })
            currentIndex: scope.channelIndex
            enabled: scope.channels.length > 0
            onActivated: function (index) {
                if (index < 0 || index >= scope.channels.length)
                    return
                scope.detach()
                scope.channelProfileId = scope.channels[index].id
                scope.scopeChanged()
            }
        }

        Item { Layout.fillWidth: true; Layout.minimumWidth: 4 }

        // Attached: a status chip. Detached: the way back.
        Label {
            visible: scope.followingRun
            text: Theme.sectionLabel("following run")
            color: Theme.good
            font.pixelSize: Theme.sizeMicro
            font.weight: Font.DemiBold
            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
        }

        ThemedButton {
            visible: !scope.followingRun
            text: "Follow Run"
            implicitHeight: 26
            onClicked: scope.followRun()
        }

        ScopeFetchButton {
            visible: scope.fetchCommand !== ""
            command: scope.fetchCommand
            commandLabel: scope.fetchLabel
            accountId: scope.accountId
            channelProfileId: scope.channelProfileId
        }
    }
}
