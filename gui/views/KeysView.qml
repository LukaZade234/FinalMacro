import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: keysRoot
    clip: true
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var payload: ({
        entries: [],
        totals_by_type: {},
        daily_series: [],
        monthly_series: [],
        omega_daily_series: []
    })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string keyTypeFilter: "all"
    property string sourceFilter: "all"
    property int trendRangeDays: 30

    readonly property var keyCards: [
        { label: "Bronze", key: "bronze", color: "#cd7f32" },
        { label: "Silver", key: "silver", color: "#a9b1d6" },
        { label: "Gold", key: "gold", color: "#e0af68" },
        { label: "Chaos", key: "chaos", color: "#bb9af7" },
        { label: "Omega", key: "omega", color: "#7aa2f7" }
    ]

    function reload() {
        try {
            payload = JSON.parse(App.keysJson)
        } catch (e) {
            payload = {
                entries: [],
                totals_by_type: {},
                daily_series: [],
                monthly_series: [],
                omega_daily_series: []
            }
        }
        refreshServerFilter()
    }

    function entries() {
        return payload.entries || []
    }

    function totalsByType() {
        return payload.totals_by_type || {}
    }

    function formatAmount(value) {
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
            if (keyTypeFilter !== "all" && entry.key_type !== keyTypeFilter)
                return false
            if (sourceFilter !== "all" && entry.source !== sourceFilter)
                return false
            return true
        })
    }

    function uniqueSources() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries().length; i++) {
            var id = entries()[i].source || ""
            if (!id || seen[id])
                continue
            seen[id] = true
            out.push({
                id: id,
                label: entries()[i].source_label || id
            })
        }
        return out
    }

    function uniqueKeyTypes() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries().length; i++) {
            var id = entries()[i].key_type || ""
            if (!id || seen[id])
                continue
            seen[id] = true
            out.push({
                id: id,
                label: entries()[i].key_type_label || id
            })
        }
        return out
    }

    function typeBreakdown() {
        var list = filteredEntries()
        var totals = {}
        for (var i = 0; i < list.length; i++) {
            var key = list[i].key_type || "unknown"
            totals[key] = (totals[key] || 0) + Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(totals)
        for (var j = 0; j < keys.length; j++) {
            var typeId = keys[j]
            var label = typeId
            for (var k = 0; k < uniqueKeyTypes().length; k++) {
                if (uniqueKeyTypes()[k].id === typeId) {
                    label = uniqueKeyTypes()[k].label
                    break
                }
            }
            out.push({ id: typeId, label: label, amount: totals[typeId] })
        }
        out.sort(function(a, b) { return b.amount - a.amount })
        return out
    }

    function sourceBreakdown() {
        var list = filteredEntries()
        var totals = {}
        for (var i = 0; i < list.length; i++) {
            var key = list[i].source || "unknown"
            totals[key] = (totals[key] || 0) + Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(totals)
        for (var j = 0; j < keys.length; j++) {
            var sourceId = keys[j]
            var label = sourceId
            for (var k = 0; k < uniqueSources().length; k++) {
                if (uniqueSources()[k].id === sourceId) {
                    label = uniqueSources()[k].label
                    break
                }
            }
            out.push({ id: sourceId, label: label, amount: totals[sourceId] })
        }
        out.sort(function(a, b) { return b.amount - a.amount })
        return out
    }

    function filteredDailySeries() {
        var list = filteredEntries()
        var daily = {}
        for (var i = 0; i < list.length; i++) {
            var dk = list[i].date_key || ""
            if (!dk)
                continue
            if (!daily[dk])
                daily[dk] = { bronze: 0, silver: 0, gold: 0, chaos: 0, omega: 0 }
            var kt = list[i].key_type || "unknown"
            if (daily[dk][kt] !== undefined)
                daily[dk][kt] += Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(daily).sort()
        for (var j = 0; j < keys.length; j++) {
            var row = daily[keys[j]]
            out.push({
                date: keys[j],
                bronze: row.bronze,
                silver: row.silver,
                gold: row.gold,
                chaos: row.chaos,
                omega: row.omega
            })
        }
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
            if (!monthly[mk])
                monthly[mk] = { bronze: 0, silver: 0, gold: 0, chaos: 0, omega: 0 }
            var kt = list[i].key_type || "unknown"
            if (monthly[mk][kt] !== undefined)
                monthly[mk][kt] += Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(monthly).sort()
        for (var j = 0; j < keys.length; j++) {
            var parts = keys[j].split("-")
            var label = keys[j]
            if (parts.length === 2)
                label = Qt.formatDate(new Date(Number(parts[0]), Number(parts[1]) - 1, 1), "MMM yyyy")
            var row = monthly[keys[j]]
            out.push({
                month: keys[j],
                label: label,
                bronze: row.bronze,
                silver: row.silver,
                gold: row.gold,
                chaos: row.chaos,
                omega: row.omega
            })
        }
        return out
    }

    function filteredOmegaDailySeries() {
        var list = filteredEntries().filter(function(entry) {
            return entry.key_type === "omega"
        })
        var daily = {}
        for (var i = 0; i < list.length; i++) {
            var dk = list[i].date_key || ""
            if (!dk)
                continue
            daily[dk] = (daily[dk] || 0) + Number(list[i].amount || 0)
        }
        var out = []
        var keys = Object.keys(daily).sort()
        for (var j = 0; j < keys.length; j++)
            out.push({ date: keys[j], amount: daily[keys[j]] })
        return out
    }

    function filteredTotalsForType(keyType) {
        var list = filteredEntries().filter(function(entry) {
            return entry.key_type === keyType
        })
        var out = { all_time: 0, today: 0, week: 0, month: 0, year: 0 }
        var now = new Date()
        var todayKey = Qt.formatDate(now, "yyyy-MM-dd")
        var weekStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        weekStart.setDate(weekStart.getDate() - ((now.getDay() + 6) % 7))
        weekStart.setHours(0, 0, 0, 0)
        var monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
        var yearStart = new Date(now.getFullYear(), 0, 1)

        for (var i = 0; i < list.length; i++) {
            var amount = Number(list[i].amount || 0)
            out.all_time += amount
            var dk = list[i].date_key
            if (!dk)
                continue
            var parts = dk.split("-")
            if (parts.length !== 3)
                continue
            var entryDate = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
            if (dk === todayKey)
                out.today += amount
            if (entryDate >= weekStart)
                out.week += amount
            if (entryDate >= monthStart)
                out.month += amount
            if (entryDate >= yearStart)
                out.year += amount
        }
        return out
    }

    function displayTotalsForType(keyType) {
        if (accountFilter === "all" && serverFilter === "all"
                && keyTypeFilter === "all" && sourceFilter === "all") {
            var stored = totalsByType()[keyType] || {}
            return stored
        }
        return filteredTotalsForType(keyType)
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
        function onKeysChanged() {
            keysRoot.reload()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        Label {
            text: "Keys gained on each roll: count key lines on the embed (1 line = 1 key), omega from explicit +N. Logged while the macro is connected."
            color: Theme.fgMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: keyCards

                delegate: PanelCard {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumWidth: 88
                    Layout.preferredHeight: 72
                    contentMargins: 10
                    title: modelData.label
                    titleSize: 10

                    Label {
                        text: "+" + formatAmount(displayTotalsForType(modelData.key).all_time || 0)
                        color: modelData.color
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: "today " + formatAmount(displayTotalsForType(modelData.key).today || 0)
                        color: Theme.fgMuted
                        font.pixelSize: 10
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            implicitHeight: keyFilterFlow.implicitHeight

            Flow {
                id: keyFilterFlow
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
                    width: 140
                    model: ["All key types"].concat(uniqueKeyTypes().map(function(t) { return t.label }))
                    onActivated: function(index) {
                        keyTypeFilter = index <= 0 ? "all" : uniqueKeyTypes()[index - 1].id
                    }
                }

                ThemedComboBox {
                    width: 160
                    model: ["All sources"].concat(uniqueSources().map(function(s) { return s.label }))
                    onActivated: function(index) {
                        sourceFilter = index <= 0 ? "all" : uniqueSources()[index - 1].id
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
                    width: Math.max(160, keyFilterFlow.width)
                    text: filteredEntries().length + " events"
                    color: Theme.fgSecondary
                    font.pixelSize: 12
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            PanelCard {
                Layout.fillWidth: true
                title: "By key type"
                titleSize: 14

                Flow {
                    width: parent.width
                    spacing: 8

                    Repeater {
                        model: typeBreakdown()

                        delegate: Rectangle {
                            required property var modelData
                            radius: 8
                            color: Theme.bgDark
                            border.color: Theme.border
                            border.width: 1
                            implicitHeight: 52
                            implicitWidth: typeLabel.implicitWidth + amountLabel.implicitWidth + 24

                            Column {
                                anchors.centerIn: parent
                                spacing: 2
                                Label {
                                    id: typeLabel
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: modelData.label
                                    color: Theme.fgSecondary
                                    font.pixelSize: 10
                                }
                                Label {
                                    id: amountLabel
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "+" + formatAmount(modelData.amount)
                                    color: Theme.accentPrimary
                                    font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }

                    Label {
                        visible: typeBreakdown().length === 0
                        text: "No keys logged yet."
                        color: Theme.fgMuted
                        font.pixelSize: 12
                    }
                }
            }

            PanelCard {
                Layout.fillWidth: true
                title: "By source"
                titleSize: 14

                Flow {
                    width: parent.width
                    spacing: 8

                    Repeater {
                        model: sourceBreakdown()

                        delegate: Rectangle {
                            required property var modelData
                            radius: 8
                            color: Theme.bgDark
                            border.color: Theme.border
                            border.width: 1
                            implicitHeight: 52
                            implicitWidth: srcLabel.implicitWidth + srcAmount.implicitWidth + 24

                            Column {
                                anchors.centerIn: parent
                                spacing: 2
                                Label {
                                    id: srcLabel
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: modelData.label
                                    color: Theme.fgSecondary
                                    font.pixelSize: 10
                                }
                                Label {
                                    id: srcAmount
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "+" + formatAmount(modelData.amount)
                                    color: Theme.accentSecondary
                                    font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }

                    Label {
                        visible: sourceBreakdown().length === 0
                        text: "No source data yet."
                        color: Theme.fgMuted
                        font.pixelSize: 12
                    }
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Key gain charts"
            titleSize: 14

            KeyGainCharts {
                Layout.fillWidth: true
                dailySeries: filteredDailySeries()
                monthlySeries: filteredMonthlySeries()
                omegaDailySeries: filteredOmegaDailySeries()
                rangeDays: trendRangeDays
                emptyText: "No key gains in this range."
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 280
            title: "Key log"
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
                        Label { Layout.preferredWidth: 100; text: "Server"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 64; text: "Type"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 56; text: "Gain"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.preferredWidth: 96; text: "Source"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Label { Layout.fillWidth: true; text: "Character"; color: Theme.fgMuted; font.pixelSize: 10; font.weight: Font.DemiBold }
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ListView {
                        id: keyList
                        width: parent.width
                        model: filteredEntries()
                        spacing: 2

                        delegate: Rectangle {
                            required property var modelData
                            required property int index

                            width: keyList.width
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
                                    Layout.preferredWidth: 100
                                    text: modelData.guild_name || String(modelData.guild_id || "—")
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 64
                                    text: modelData.key_type_label || modelData.key_type || "—"
                                    color: Theme.fgPrimary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 56
                                    text: "+" + formatAmount(modelData.amount)
                                    color: Theme.success
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                }
                                Label {
                                    Layout.preferredWidth: 96
                                    text: modelData.source_label || modelData.source || "—"
                                    color: Theme.fgSecondary
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
                    }
                }
            }
        }
    }
}
