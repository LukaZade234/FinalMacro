import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../emptyStates.js" as Empty
import "../components"

Item {
    id: soulmatesRoot
    clip: true
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var payload: ({
        recent: [],
        event_count: 0,
        has_more: false,
        by_account: [],
        by_server: [],
        by_server_accounts: {},
        filter_options: { accounts: [], servers: [] }
    })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string chartMode: "account"          // "account" | "server"
    property string chartServerFocus: ""          // drill-down: accounts within this server
    property int pageSize: 80

    function queryPayload(offset, limit) {
        try {
            return JSON.parse(App.statsQuery(
                "soulmate",
                accountFilter,
                serverFilter,
                "all",
                "all",
                offset,
                limit
            ))
        } catch (e) {
            return {
                recent: [],
                event_count: 0,
                has_more: false,
                by_account: [],
                by_server: [],
                by_server_accounts: {},
                filter_options: { accounts: [], servers: [] }
            }
        }
    }

    function reload(resetPage) {
        var limit = pageSize
        if (!resetPage)
            limit = Math.max(pageSize, (payload.recent || []).length || pageSize)
        payload = queryPayload(0, limit)
        refreshServerFilter()
        refreshChartServerFocus()
    }

    function loadMore() {
        if (!payload.has_more)
            return
        var extra = queryPayload((payload.recent || []).length, pageSize)
        extra.recent = (payload.recent || []).concat(extra.recent || [])
        payload = extra
    }

    function recentEntries() {
        return payload.recent || []
    }

    function toChartData(counts, labels) {
        var total = 0
        var keys = Object.keys(counts)
        for (var i = 0; i < keys.length; i++)
            total += counts[keys[i]]
        var items = []
        for (var j = 0; j < keys.length; j++) {
            var k = keys[j]
            items.push({
                id: k,
                label: labels[k] || k,
                count: counts[k],
                percent: total > 0 ? (counts[k] / total * 100) : 0
            })
        }
        items.sort(function(a, b) { return b.count - a.count })
        return { total: total, items: items }
    }

    function seriesToChartData(items) {
        var counts = {}
        var labels = {}
        var list = items || []
        for (var i = 0; i < list.length; i++) {
            counts[list[i].id] = list[i].count
            labels[list[i].id] = list[i].label || list[i].id
        }
        return toChartData(counts, labels)
    }

    function accountChartData() {
        return seriesToChartData(payload.by_account)
    }

    function serverChartData() {
        return seriesToChartData(payload.by_server)
    }

    function serverDrillChartData() {
        if (!chartServerFocus)
            return ({ total: 0, items: [] })
        var nested = (payload.by_server_accounts || {})[chartServerFocus] || []
        return seriesToChartData(nested)
    }

    function activeChartData() {
        if (chartServerFocus)
            return serverDrillChartData()
        if (chartMode === "server")
            return serverChartData()
        return accountChartData()
    }

    function chartTotal() {
        var items = payload.by_account || []
        var total = 0
        for (var i = 0; i < items.length; i++)
            total += Number(items[i].count || 0)
        return total
    }

    function chartTitle() {
        if (chartServerFocus)
            return "Accounts on " + chartServerFocus
        if (chartMode === "server")
            return "Share by server (of " + chartTotal() + " total)"
        return "Share by account (of " + chartTotal() + " total)"
    }

    function chartHint() {
        if (chartServerFocus)
            return "Soulmates on this server split by account."
        if (chartMode === "server")
            return "Click a server row or bar to see account breakdown within that server."
        return "Each account's share of all logged soulmates."
    }

    function uniqueAccounts() {
        return (payload.filter_options && payload.filter_options.accounts) || []
    }

    function uniqueServers() {
        return (payload.filter_options && payload.filter_options.servers) || []
    }

    function accountComboIndex() {
        if (accountFilter === "all")
            return 0
        var list = uniqueAccounts()
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === accountFilter)
                return i + 1
        }
        return 0
    }

    function serverComboIndex() {
        if (serverFilter === "all")
            return 0
        var list = uniqueServers()
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === serverFilter)
                return i + 1
        }
        return 0
    }

    function refreshServerFilter() {
        var servers = uniqueServers()
        if (serverFilter !== "all") {
            var found = false
            for (var i = 0; i < servers.length; i++) {
                if (servers[i].id === serverFilter) {
                    found = true
                    break
                }
            }
            if (!found)
                serverFilter = "all"
        }
    }

    function refreshChartServerFocus() {
        if (!chartServerFocus)
            return
        var servers = uniqueServers()
        for (var i = 0; i < servers.length; i++) {
            if (servers[i].id === chartServerFocus)
                return
        }
        chartServerFocus = ""
    }

    function setChartMode(mode) {
        chartMode = mode
        if (mode === "account")
            chartServerFocus = ""
    }

    function focusServer(serverId) {
        chartServerFocus = serverId
        chartMode = "server"
        serverFocusCombo.currentIndex = serverFocusIndexFor(serverId)
    }

    function clearServerFocus() {
        chartServerFocus = ""
        serverFocusCombo.currentIndex = 0
    }

    function serverFocusIndexFor(serverId) {
        var servers = uniqueServers()
        for (var i = 0; i < servers.length; i++) {
            if (servers[i].id === serverId)
                return i + 1
        }
        return 0
    }

    Component.onCompleted: reload()

    Connections {
        target: App
        function onSoulmatesChanged() {
            soulmatesRoot.reload()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        Label {
            text: "Soulmates rolled while connected — stats use the full log; table filters below are independent."
            color: Theme.fgMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Distribution"
            titleSize: 14

            ColumnLayout {
                width: parent.width
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Repeater {
                        model: [
                            { id: "account", label: "By account" },
                            { id: "server", label: "By server" }
                        ]
                        delegate: Rectangle {
                            required property var modelData

                            implicitHeight: 28
                            implicitWidth: chipLabel.implicitWidth + 18
                            radius: 14
                            color: !chartServerFocus && chartMode === modelData.id
                                   ? Theme.accentPrimary : Theme.bgDark
                            border.color: !chartServerFocus && chartMode === modelData.id
                                          ? Theme.accentPrimary : Theme.border
                            border.width: 1

                            Label {
                                id: chipLabel
                                anchors.centerIn: parent
                                text: modelData.label
                                color: !chartServerFocus && chartMode === modelData.id
                                       ? Theme.bgDark : Theme.fgSecondary
                                font.pixelSize: 11
                                font.weight: !chartServerFocus && chartMode === modelData.id
                                             ? Font.DemiBold : Font.Normal
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: setChartMode(modelData.id)
                            }
                        }
                    }

                    ThemedComboBox {
                        id: serverFocusCombo
                        Layout.preferredWidth: 240
                        visible: chartMode === "server" || chartServerFocus !== ""
                        model: ["All servers — overview"].concat(uniqueServers().map(function(s) { return s.label }))
                        onActivated: function(index) {
                            if (index <= 0) {
                                clearServerFocus()
                                return
                            }
                            var servers = uniqueServers()
                            focusServer(servers[index - 1].id)
                        }
                    }

                    ThemedButton {
                        visible: chartServerFocus !== ""
                        text: "Back to servers"
                        onClicked: clearServerFocus()
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        text: chartTitle()
                        color: Theme.fgSecondary
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.maximumWidth: 280
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: chartHint()
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                SoulmateShareChart {
                    id: shareChart
                    Layout.fillWidth: true
                    Layout.preferredHeight: shareChart.bodyHeight
                    Layout.minimumHeight: 130
                    chartData: activeChartData()
                    selectable: chartMode === "server" && chartServerFocus === ""
                    selectedId: chartServerFocus
                    emptyText: Empty.soulmateChartEmpty(App.connected, chartTotal() > 0)
                    onSliceClicked: function(id, label) {
                        if (chartMode === "server" && chartServerFocus === "")
                            focusServer(id)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ThemedComboBox {
                id: accountCombo
                Layout.preferredWidth: 220
                model: ["All accounts"].concat(uniqueAccounts().map(function(a) { return a.label }))
                currentIndex: accountComboIndex()
                onActivated: function(index) {
                    accountFilter = index <= 0 ? "all" : uniqueAccounts()[index - 1].id
                    reload(true)
                }
            }

            ThemedComboBox {
                id: serverCombo
                Layout.preferredWidth: 260
                model: ["All servers"].concat(uniqueServers().map(function(s) { return s.label }))
                currentIndex: serverComboIndex()
                onActivated: function(index) {
                    serverFilter = index <= 0 ? "all" : uniqueServers()[index - 1].id
                    reload(true)
                }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: recentEntries().length + " shown · " + (payload.event_count || 0) + " total"
                color: Theme.fgSecondary
                font.pixelSize: 12
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 280
            title: "Soulmate log"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                width: parent.width
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 32
                    color: Theme.bgDark
                    radius: 6

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 8

                        Label { Layout.preferredWidth: 72; text: "Time"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 110; text: "Account"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 130; text: "Server"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 90; text: "Channel"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 138; text: "Character"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.fillWidth: true; text: "Series"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ListView {
                        id: soulmateList
                        width: parent.width
                        model: recentEntries()
                        spacing: 2

                        delegate: Rectangle {
                            required property var modelData
                            required property int index

                            width: soulmateList.width
                            implicitHeight: 36
                            color: index % 2 === 0 ? "transparent" : Theme.bgDark
                            radius: 4

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8

                                Label {
                                    Layout.preferredWidth: 72
                                    text: modelData.time || "—"
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 110
                                    text: modelData.account_name || "Unknown"
                                    color: modelData.account_inferred ? Theme.fgMuted : Theme.accentPrimary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 130
                                    text: modelData.guild_name || String(modelData.guild_id || "—")
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 90
                                    text: modelData.channel_name ? ("#" + modelData.channel_name) : "—"
                                    color: Theme.fgMuted
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                RowLayout {
                                    Layout.preferredWidth: 138
                                    spacing: 4
                                    Image {
                                        visible: !!modelData.starwish
                                        source: MudaeEmoji.urlFor("starwish")
                                        Layout.preferredWidth: 14
                                        Layout.preferredHeight: 14
                                        sourceSize.width: 14
                                        sourceSize.height: 14
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: modelData.character_name || "—"
                                        color: Theme.fgPrimary
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.series || "—"
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: soulmateList.count === 0
                            text: Empty.statsLogEmpty(App.connected, (payload.event_count || 0) > 0, "soulmates")
                            color: Theme.fgMuted
                            font.pixelSize: 12
                        }
                    }
                }

                ThemedButton {
                    visible: payload.has_more === true
                    text: "Load more"
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 8
                    onClicked: loadMore()
                }
            }
        }
    }
}
