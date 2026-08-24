import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
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

    property var payload: ({
        recent: [],
        totals: {},
        daily_series: [],
        monthly_series: [],
        by_method: [],
        event_count: 0,
        has_more: false,
        filter_options: { accounts: [], servers: [], methods: [] }
    })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string methodFilter: "all"
    property int trendRangeDays: 30
    property int pageSize: 80

    function queryPayload(offset, limit) {
        try {
            return JSON.parse(App.statsQuery(
                "kakera",
                accountFilter,
                serverFilter,
                methodFilter,
                "all",
                offset,
                limit
            ))
        } catch (e) {
            return {
                recent: [],
                totals: {},
                daily_series: [],
                monthly_series: [],
                by_method: [],
                event_count: 0,
                has_more: false,
                filter_options: { accounts: [], servers: [], methods: [] }
            }
        }
    }

    function reload(resetPage) {
        var limit = pageSize
        if (!resetPage)
            limit = Math.max(pageSize, (payload.recent || []).length || pageSize)
        payload = queryPayload(0, limit)
        refreshServerFilter()
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

    function totals() {
        return payload.totals || {}
    }

    function formatKakera(value) {
        var n = Number(value) || 0
        return n.toLocaleString(Qt.locale(), "f", 0)
    }

    function methodBreakdown() {
        return payload.by_method || []
    }

    function filteredDailySeries() {
        return payload.daily_series || []
    }

    function filteredMonthlySeries() {
        return payload.monthly_series || []
    }

    function displayTotals() {
        return totals()
    }

    function uniqueAccounts() {
        return (payload.filter_options && payload.filter_options.accounts) || []
    }

    function uniqueServers() {
        return (payload.filter_options && payload.filter_options.servers) || []
    }

    function uniqueMethods() {
        return (payload.filter_options && payload.filter_options.methods) || []
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

    function methodComboIndex() {
        if (methodFilter === "all")
            return 0
        var list = uniqueMethods()
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === methodFilter)
                return i + 1
        }
        return 0
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
                    currentIndex: accountComboIndex()
                    onActivated: function(index) {
                        accountFilter = index <= 0 ? "all" : uniqueAccounts()[index - 1].id
                        reload(true)
                    }
                }

                ThemedComboBox {
                    width: 220
                    model: ["All servers"].concat(uniqueServers().map(function(s) { return s.label }))
                    currentIndex: serverComboIndex()
                    onActivated: function(index) {
                        serverFilter = index <= 0 ? "all" : uniqueServers()[index - 1].id
                        reload(true)
                    }
                }

                ThemedComboBox {
                    width: 180
                    model: ["All earn methods"].concat(uniqueMethods().map(function(m) { return m.label }))
                    currentIndex: methodComboIndex()
                    onActivated: function(index) {
                        methodFilter = index <= 0 ? "all" : uniqueMethods()[index - 1].id
                        reload(true)
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
                    text: (payload.event_count || 0) + " events · "
                          + formatKakera(displayTotals().all_time) + " $k"
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
                    text: Empty.statsBreakdownEmpty(App.connected, (payload.event_count || 0) > 0)
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
                emptyText: Empty.chartRangeEmpty(App.connected, (payload.event_count || 0) > 0, "kakera earnings")
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
                        model: recentEntries()
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
                            text: Empty.statsLogEmpty(App.connected, (payload.event_count || 0) > 0, "kakera")
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
