import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: soulmatesRoot
    clip: true
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var entries: []
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string chartMode: "account"          // "account" | "server"
    property string chartServerFocus: ""          // drill-down: accounts within this server

    function reload() {
        try {
            entries = JSON.parse(App.soulmatesJson)
        } catch (e) {
            entries = []
        }
        refreshServerFilter()
        refreshChartServerFocus()
    }

    function serverKey(entry) {
        return entry.guild_name || String(entry.guild_id || "unknown")
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

    function aggregateByAccount(sourceEntries) {
        var counts = {}
        var labels = {}
        for (var i = 0; i < sourceEntries.length; i++) {
            var e = sourceEntries[i]
            var id = e.account_id || "unknown"
            counts[id] = (counts[id] || 0) + 1
            labels[id] = e.account_name || "Unknown"
        }
        return toChartData(counts, labels)
    }

    function aggregateByServer(sourceEntries) {
        var counts = {}
        var labels = {}
        for (var i = 0; i < sourceEntries.length; i++) {
            var e = sourceEntries[i]
            var key = serverKey(e)
            counts[key] = (counts[key] || 0) + 1
            labels[key] = key
        }
        return toChartData(counts, labels)
    }

    function aggregateAccountsInServer(sourceEntries, serverId) {
        var filtered = []
        for (var i = 0; i < sourceEntries.length; i++) {
            if (serverKey(sourceEntries[i]) === serverId)
                filtered.push(sourceEntries[i])
        }
        return aggregateByAccount(filtered)
    }

    function accountChartData() {
        return aggregateByAccount(entries)
    }

    function serverChartData() {
        return aggregateByServer(entries)
    }

    function serverDrillChartData() {
        if (!chartServerFocus)
            return ({ total: 0, items: [] })
        return aggregateAccountsInServer(entries, chartServerFocus)
    }

    function activeChartData() {
        if (chartServerFocus)
            return serverDrillChartData()
        if (chartMode === "server")
            return serverChartData()
        return accountChartData()
    }

    function chartTitle() {
        if (chartServerFocus)
            return "Accounts on " + chartServerFocus
        if (chartMode === "server")
            return "Share by server (of " + entries.length + " total)"
        return "Share by account (of " + entries.length + " total)"
    }

    function chartHint() {
        if (chartServerFocus)
            return "Soulmates on this server split by account."
        if (chartMode === "server")
            return "Click a server row or bar to see account breakdown within that server."
        return "Each account's share of all logged soulmates."
    }

    function filteredEntries() {
        return entries.filter(function(entry) {
            if (accountFilter !== "all" && entry.account_id !== accountFilter)
                return false
            var key = serverKey(entry)
            if (serverFilter !== "all" && key !== serverFilter)
                return false
            return true
        })
    }

    function uniqueAccounts() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries.length; i++) {
            var id = entries[i].account_id || ""
            if (!id || seen[id])
                continue
            seen[id] = true
            out.push({
                id: id,
                label: entries[i].account_name + (entries[i].account_inferred ? " (inferred)" : "")
            })
        }
        return out
    }

    function uniqueServers() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries.length; i++) {
            var key = serverKey(entries[i])
            if (seen[key])
                continue
            seen[key] = true
            out.push({ id: key, label: key })
        }
        return out
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
                    emptyText: entries.length === 0
                        ? "No soulmates logged yet."
                        : "No data for this view."
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
                onActivated: function(index) {
                    if (index <= 0) {
                        accountFilter = "all"
                        return
                    }
                    var accounts = uniqueAccounts()
                    accountFilter = accounts[index - 1].id
                }
            }

            ThemedComboBox {
                id: serverCombo
                Layout.preferredWidth: 260
                model: ["All servers"].concat(uniqueServers().map(function(s) { return s.label }))
                onActivated: function(index) {
                    if (index <= 0) {
                        serverFilter = "all"
                        return
                    }
                    var servers = uniqueServers()
                    serverFilter = servers[index - 1].id
                }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: filteredEntries().length + " shown · " + entries.length + " total"
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
                        Label { Layout.preferredWidth: 120; text: "Character"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
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
                        model: filteredEntries()
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
                                Label {
                                    Layout.preferredWidth: 120
                                    text: modelData.character_name || "—"
                                    color: Theme.fgPrimary
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
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
                            text: entries.length === 0
                                ? "No soulmates logged yet — roll while connected to record entries."
                                : "No entries match the current filters."
                            color: Theme.fgMuted
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }
}
