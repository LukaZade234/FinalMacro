import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../clock.js" as Clock
import "../emptyStates.js" as Empty
import "../components"

Item {
    id: kakeraRoot
    clip: true
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var payload: ({ entries: [], totals: {}, daily_series: [], monthly_series: [] })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string methodFilter: "all"
    property int trendRangeDays: 30

    function reload() {
        try {
            payload = JSON.parse(App.kakeraJson)
        } catch (e) {
            payload = { entries: [], totals: {}, daily_series: [], monthly_series: [] }
        }
        refreshServerFilter()
    }

    function entries() {
        return payload.entries || []
    }

    function totals() {
        return payload.totals || {}
    }

    function formatKakera(value) {
        var n = Number(value) || 0
        return n.toLocaleString(Qt.locale(), "f", 0)
    }

    function serverKey(entry) {
        return entry.guild_name || String(entry.guild_id || "unknown")
    }

    function filteredEntries() {
        return entries().filter(function(entry) {
            if (accountFilter !== "all" && entry.account_id !== accountFilter)
                return false
            if (serverFilter !== "all" && serverKey(entry) !== serverFilter)
                return false
            if (methodFilter !== "all" && entry.earn_method !== methodFilter)
                return false
            return true
        })
    }

    function uniqueMethods() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries().length; i++) {
            var id = entries()[i].earn_method || ""
            if (!id || seen[id])
                continue
            seen[id] = true
            out.push({
                id: id,
                label: entries()[i].earn_method_label || id
            })
        }
        return out
    }

    function methodBreakdown() {
        var list = filteredEntries()
        var totals = {}
        for (var i = 0; i < list.length; i++) {
            var key = list[i].earn_method || "unknown"
            totals[key] = (totals[key] || 0) + Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(totals)
        for (var j = 0; j < keys.length; j++) {
            var methodId = keys[j]
            var label = methodId
            for (var k = 0; k < uniqueMethods().length; k++) {
                if (uniqueMethods()[k].id === methodId) {
                    label = uniqueMethods()[k].label
                    break
                }
            }
            out.push({ id: methodId, label: label, amount: totals[methodId] })
        }
        out.sort(function(a, b) { return b.amount - a.amount })
        return out
    }

    function filteredDailySeries() {
        var list = filteredEntries()
        var daily = {}
        for (var i = 0; i < list.length; i++) {
            var key = list[i].date_key || ""
            if (!key)
                continue
            daily[key] = (daily[key] || 0) + Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(daily).sort()
        for (var j = 0; j < keys.length; j++)
            out.push({ date: keys[j], amount: daily[keys[j]] })
        return out
    }

    function filteredMonthlySeries() {
        var list = filteredEntries()
        var monthly = {}
        for (var i = 0; i < list.length; i++) {
            var dk = list[i].date_key || ""
            if (dk.length < 7)
                continue
            var mk = dk.slice(0, 7)
            monthly[mk] = (monthly[mk] || 0) + Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(monthly).sort()
        for (var j = 0; j < keys.length; j++) {
            var parts = keys[j].split("-")
            var label = keys[j]
            if (parts.length === 2)
                label = Qt.formatDate(new Date(Number(parts[0]), Number(parts[1]) - 1, 1), "MMM yyyy")
            out.push({ month: keys[j], label: label, amount: monthly[keys[j]] })
        }
        return out
    }

    function filteredTotals() {
        var list = filteredEntries()
        var out = { all_time: 0, today: 0, week: 0, month: 0, year: 0 }
        var periods = Clock.periodKeys()
        for (var i = 0; i < list.length; i++) {
            var amount = Number(list[i].amount || 0)
            out.all_time += amount
            Clock.addDateKey(out, list[i].date_key, amount, periods)
        }
        return out
    }

    function displayTotals() {
        if (accountFilter === "all" && serverFilter === "all")
            return totals()
        return filteredTotals()
    }

    function uniqueAccounts() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries().length; i++) {
            var id = entries()[i].account_id || ""
            if (!id || seen[id])
                continue
            seen[id] = true
            out.push({
                id: id,
                label: entries()[i].account_name + (entries()[i].account_inferred ? " (inferred)" : "")
            })
        }
        return out
    }

    function uniqueServers() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries().length; i++) {
            var key = serverKey(entries()[i])
            if (seen[key])
                continue
            seen[key] = true
            out.push({ id: key, label: key })
        }
        return out
    }

    function refreshServerFilter() {
        if (serverFilter === "all")
            return
        var servers = uniqueServers()
        for (var i = 0; i < servers.length; i++) {
            if (servers[i].id === serverFilter)
                return
        }
        serverFilter = "all"
    }

    Component.onCompleted: reload()

    Connections {
        target: App
        function onKakeraChanged() {
            kakeraRoot.reload()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        Label {
            text: "Kakera from button clicks and BKU while connected. Bonus spheres from clicks are tracked on the Spheres tab."
            color: Theme.fgMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Repeater {
                model: [
                    { label: "Today", key: "today" },
                    { label: "This week", key: "week" },
                    { label: "This month", key: "month" },
                    { label: "This year", key: "year" },
                    { label: "All time", key: "all_time" }
                ]
                delegate: PanelCard {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumWidth: 100
                    Layout.preferredHeight: 68
                    contentMargins: 12
                    title: modelData.label
                    titleSize: 11

                    Label {
                        text: formatKakera(displayTotals()[modelData.key] || 0)
                        color: modelData.key === "all_time" ? Theme.accentPrimary : Theme.fgPrimary
                        font.pixelSize: modelData.key === "all_time" ? 20 : 16
                        font.weight: Font.DemiBold
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            implicitHeight: filterFlow.implicitHeight

            Flow {
                id: filterFlow
                width: parent.width
                spacing: 8

                ThemedComboBox {
                    width: 200
                    model: ["All accounts"].concat(uniqueAccounts().map(function(a) { return a.label }))
                    onActivated: function(index) {
                        accountFilter = index <= 0 ? "all" : uniqueAccounts()[index - 1].id
                    }
                }

                ThemedComboBox {
                    width: 220
                    model: ["All servers"].concat(uniqueServers().map(function(s) { return s.label }))
                    onActivated: function(index) {
                        serverFilter = index <= 0 ? "all" : uniqueServers()[index - 1].id
                    }
                }

                ThemedComboBox {
                    width: 180
                    model: ["All earn methods"].concat(uniqueMethods().map(function(m) { return m.label }))
                    onActivated: function(index) {
                        methodFilter = index <= 0 ? "all" : uniqueMethods()[index - 1].id
                    }
                }

                ThemedComboBox {
                    width: 120
                    model: ["7 days", "30 days", "90 days", "1 year", "All"]
                    currentIndex: 1
                    onActivated: function(index) {
                        trendRangeDays = [7, 30, 90, 365, 0][index]
                    }
                }

                Label {
                    width: Math.max(160, filterFlow.width)
                    text: filteredEntries().length + " events · "
                          + formatKakera(filteredTotals().all_time) + " $k filtered"
                    color: Theme.fgSecondary
                    font.pixelSize: 12
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Earned by method"
            titleSize: 14

            Item {
                Layout.fillWidth: true
                implicitHeight: methodFlow.implicitHeight

                Flow {
                    id: methodFlow
                    width: parent.width
                    spacing: 8

                Repeater {
                    model: methodBreakdown()

                    delegate: Rectangle {
                        required property var modelData

                        radius: 8
                        color: Theme.bgDark
                        border.color: Theme.border
                        border.width: 1
                        implicitHeight: 52
                        implicitWidth: methodLabel.implicitWidth + amountLabel.implicitWidth + 24

                        Column {
                            anchors.centerIn: parent
                            spacing: 2

                            Label {
                                id: methodLabel
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: modelData.label
                                color: Theme.fgSecondary
                                font.pixelSize: 10
                            }
                            Label {
                                id: amountLabel
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "+" + formatKakera(modelData.amount) + " $k"
                                color: Theme.accentPrimary
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }

                Label {
                    visible: methodBreakdown().length === 0
                    text: Empty.statsBreakdownEmpty(App.connected, entries().length > 0)
                    color: Theme.fgMuted
                    font.pixelSize: 12
                }
            }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Earnings charts"
            titleSize: 14

            KakeraRevenueCharts {
                Layout.fillWidth: true
                dailySeries: filteredDailySeries()
                monthlySeries: filteredMonthlySeries()
                rangeDays: trendRangeDays
                emptyText: Empty.chartRangeEmpty(App.connected, entries().length > 0, "kakera earnings")
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 280
            title: "Kakera log"
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

                        Label { Layout.preferredWidth: 88; text: "Date"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 64; text: "Time"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 96; text: "Account"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 120; text: "Server"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 72; text: "Amount"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 110; text: "Earned via"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 72; text: "Kakera"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.fillWidth: true; text: "Character"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ListView {
                        id: kakeraList
                        width: parent.width
                        model: filteredEntries()
                        spacing: 2

                        delegate: Rectangle {
                            required property var modelData
                            required property int index

                            width: kakeraList.width
                            implicitHeight: 34
                            color: index % 2 === 0 ? "transparent" : Theme.bgDark
                            radius: 4

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8

                                Label {
                                    Layout.preferredWidth: 88
                                    text: modelData.date_key || "—"
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 64
                                    text: modelData.time || "—"
                                    color: Theme.fgMuted
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 96
                                    text: modelData.account_name || "Main"
                                    color: modelData.account_inferred ? Theme.fgMuted : Theme.accentPrimary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 120
                                    text: modelData.guild_name || String(modelData.guild_id || "—")
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 72
                                    text: "+" + formatKakera(modelData.amount)
                                    color: Theme.success
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                }
                                Label {
                                    Layout.preferredWidth: 110
                                    text: modelData.earn_method_label || modelData.earn_method || "—"
                                    color: Theme.fgPrimary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 72
                                    text: modelData.kakera_type || "—"
                                    color: Theme.fgMuted
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.character_name || "—"
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: kakeraList.count === 0
                            text: Empty.statsLogEmpty(App.connected, entries().length > 0, "kakera")
                            color: Theme.fgMuted
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }
}
