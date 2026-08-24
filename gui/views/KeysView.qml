import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../emptyStates.js" as Empty
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
        recent: [],
        totals_by_type: {},
        daily_series: [],
        monthly_series: [],
        omega_daily_series: [],
        by_source: [],
        event_count: 0,
        has_more: false,
        filter_options: { accounts: [], servers: [], methods: [], types: [] }
    })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string keyTypeFilter: "all"
    property string sourceFilter: "all"
    property int trendRangeDays: 30
    property int chartMode: 0  // 0 daily, 1 monthly, 2 omega
    property int pageSize: 80

    readonly property var keyCards: [
        { label: "Bronze", key: "bronze", color: "#cd7f32" },
        { label: "Silver", key: "silver", color: "#a9b1d6" },
        { label: "Gold", key: "gold", color: "#e0af68" },
        { label: "Chaos", key: "chaos", color: "#bb9af7" },
        { label: "Omega", key: "omega", color: "#7aa2f7" }
    ]

    function queryPayload(offset, limit) {
        try {
            return JSON.parse(App.statsQuery(
                "key",
                accountFilter,
                serverFilter,
                sourceFilter,
                keyTypeFilter,
                offset,
                limit
            ))
        } catch (e) {
            return {
                recent: [],
                totals_by_type: {},
                daily_series: [],
                monthly_series: [],
                omega_daily_series: [],
                by_source: [],
                event_count: 0,
                has_more: false,
                filter_options: { accounts: [], servers: [], methods: [], types: [] }
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

    function totalsByType() {
        return payload.totals_by_type || {}
    }

    function formatAmount(value) {
        var n = Number(value) || 0
        return n.toLocaleString(Qt.locale(), "f", 0)
    }

    function uniqueSources() {
        return (payload.filter_options && payload.filter_options.methods) || []
    }

    function uniqueKeyTypes() {
        return (payload.filter_options && payload.filter_options.types) || []
    }

    function sourceBreakdown() {
        return payload.by_source || []
    }

    function filteredDailySeries() {
        return payload.daily_series || []
    }

    function filteredMonthlySeries() {
        return payload.monthly_series || []
    }

    function filteredOmegaDailySeries() {
        return payload.omega_daily_series || []
    }

    function displayTotalsForType(keyType) {
        return totalsByType()[keyType] || {}
    }

    function uniqueAccounts() {
        return (payload.filter_options && payload.filter_options.accounts) || []
    }

    function uniqueServers() {
        return (payload.filter_options && payload.filter_options.servers) || []
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

    function keyColor(typeId) {
        for (var i = 0; i < keyCards.length; i++) {
            if (keyCards[i].key === typeId)
                return keyCards[i].color
        }
        return Theme.accentPrimary
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

    function typeComboIndex() {
        if (keyTypeFilter === "all")
            return 0
        var list = uniqueKeyTypes()
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === keyTypeFilter)
                return i + 1
        }
        return 0
    }

    function sourceComboIndex() {
        if (sourceFilter === "all")
            return 0
        var list = uniqueSources()
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === sourceFilter)
                return i + 1
        }
        return 0
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
        contentSpacing: 14

        // Summary totals
        Flow {
            Layout.fillWidth: true
            spacing: 10

            Repeater {
                model: keyCards

                delegate: Rectangle {
                    required property var modelData
                    width: Math.max(120, (keysRoot.width - 40) / 5 - 10)
                    height: 78
                    radius: 10
                    color: Theme.bgMedium
                    border.color: Theme.border
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 2

                        Label {
                            text: modelData.label
                            color: Theme.fgMuted
                            font.pixelSize: 11
                        }
                        Label {
                            text: "+" + formatAmount(displayTotalsForType(modelData.key).all_time || 0)
                            color: modelData.color
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                        }
                        Label {
                            text: "today +" + formatAmount(displayTotalsForType(modelData.key).today || 0)
                            color: Theme.fgSecondary
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }

        // Filters
        Rectangle {
            Layout.fillWidth: true
            radius: 10
            color: Theme.bgMedium
            border.color: Theme.border
            border.width: 1
            implicitHeight: filterCol.implicitHeight + 20

            ColumnLayout {
                id: filterCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: "Filters"
                        color: Theme.fgPrimary
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: (payload.event_count || 0) + " events"
                        color: Theme.fgMuted
                        font.pixelSize: 11
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: 8

                    ThemedComboBox {
                        implicitWidth: 170
                        model: ["All accounts"].concat(uniqueAccounts().map(function(a) { return a.label }))
                        currentIndex: accountComboIndex()
                        onActivated: function(index) {
                            accountFilter = index <= 0 ? "all" : uniqueAccounts()[index - 1].id
                            reload(true)
                        }
                    }
                    ThemedComboBox {
                        implicitWidth: 180
                        model: ["All servers"].concat(uniqueServers().map(function(s) { return s.label }))
                        currentIndex: serverComboIndex()
                        onActivated: function(index) {
                            serverFilter = index <= 0 ? "all" : uniqueServers()[index - 1].id
                            reload(true)
                        }
                    }
                    ThemedComboBox {
                        implicitWidth: 130
                        model: ["All types"].concat(uniqueKeyTypes().map(function(t) { return t.label }))
                        currentIndex: typeComboIndex()
                        onActivated: function(index) {
                            keyTypeFilter = index <= 0 ? "all" : uniqueKeyTypes()[index - 1].id
                            reload(true)
                        }
                    }
                    ThemedComboBox {
                        implicitWidth: 150
                        model: ["All sources"].concat(uniqueSources().map(function(s) { return s.label }))
                        currentIndex: sourceComboIndex()
                        onActivated: function(index) {
                            sourceFilter = index <= 0 ? "all" : uniqueSources()[index - 1].id
                            reload(true)
                        }
                    }
                    ThemedComboBox {
                        implicitWidth: 110
                        model: ["7 days", "30 days", "90 days", "1 year", "All"]
                        currentIndex: 1
                        onActivated: function(index) {
                            trendRangeDays = [7, 30, 90, 365, 0][index]
                        }
                    }
                }
            }
        }

        // Chart + sources side by side when wide enough
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredWidth: 2
                Layout.preferredHeight: chartInner.implicitHeight + 24
                radius: 10
                color: Theme.bgMedium
                border.color: Theme.border
                border.width: 1

                ColumnLayout {
                    id: chartInner
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Label {
                            text: "Trends"
                            color: Theme.fgPrimary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Item { Layout.fillWidth: true }

                        Repeater {
                            model: [
                                { label: "Daily", mode: 0 },
                                { label: "Monthly", mode: 1 },
                                { label: "Omega", mode: 2 }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                implicitHeight: 26
                                implicitWidth: modeLabel.implicitWidth + 16
                                radius: 13
                                color: keysRoot.chartMode === modelData.mode ? Theme.accentPrimary : Theme.bgDark
                                border.color: keysRoot.chartMode === modelData.mode ? Theme.accentPrimary : Theme.border
                                border.width: 1

                                Label {
                                    id: modeLabel
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    color: keysRoot.chartMode === modelData.mode ? Theme.bgDark : Theme.fgSecondary
                                    font.pixelSize: 11
                                    font.weight: keysRoot.chartMode === modelData.mode ? Font.DemiBold : Font.Normal
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: keysRoot.chartMode = modelData.mode
                                }
                            }
                        }
                    }

                    KeyGainCharts {
                        Layout.fillWidth: true
                        dailySeries: keysRoot.chartMode === 0 ? filteredDailySeries() : []
                        monthlySeries: keysRoot.chartMode === 1 ? filteredMonthlySeries() : []
                        omegaDailySeries: keysRoot.chartMode === 2 ? filteredOmegaDailySeries() : []
                        rangeDays: trendRangeDays
                        emptyText: Empty.chartRangeEmpty(App.connected, (payload.event_count || 0) > 0, "key gains")
                        showOnly: keysRoot.chartMode
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: 220
                Layout.maximumWidth: 260
                Layout.fillHeight: true
                Layout.minimumHeight: 180
                radius: 10
                color: Theme.bgMedium
                border.color: Theme.border
                border.width: 1
                visible: keysRoot.width >= 900

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Label {
                        text: "By source"
                        color: Theme.fgPrimary
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: sourceBreakdown()
                        spacing: 6

                        delegate: RowLayout {
                            required property var modelData
                            width: ListView.view.width
                            spacing: 8

                            Label {
                                Layout.fillWidth: true
                                text: modelData.label
                                color: Theme.fgSecondary
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            Label {
                                text: "+" + formatAmount(modelData.amount)
                                color: Theme.accentSecondary
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: sourceBreakdown().length === 0
                            text: Empty.statsBreakdownEmpty(App.connected, (payload.event_count || 0) > 0)
                            color: Theme.fgMuted
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }

        // Recent activity as clean cards instead of a dense table
        Rectangle {
            Layout.fillWidth: true
            radius: 10
            color: Theme.bgMedium
            border.color: Theme.border
            border.width: 1
            implicitHeight: Math.min(420, recentHeader.implicitHeight + recentList.contentHeight + 36)

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8

                RowLayout {
                    id: recentHeader
                    Layout.fillWidth: true
                    Label {
                        text: "Recent gains"
                        color: Theme.fgPrimary
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: payload.has_more ? "Newest first" : "Newest first · all loaded"
                        color: Theme.fgMuted
                        font.pixelSize: 10
                    }
                }

                ListView {
                    id: recentList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: Math.min(340, Math.max(80, contentHeight))
                    clip: true
                    model: recentEntries()
                    spacing: 4

                    delegate: Rectangle {
                        required property var modelData
                        width: recentList.width
                        height: 44
                        radius: 8
                        color: Theme.bgDark

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 10

                            Rectangle {
                                width: 8
                                height: 8
                                radius: 4
                                color: keyColor(modelData.key_type)
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Label {
                                    Layout.fillWidth: true
                                    text: (modelData.character_name || "Unknown") + " · +"
                                          + formatAmount(modelData.amount) + " "
                                          + (modelData.key_type_label || modelData.key_type || "")
                                    color: Theme.fgPrimary
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: (modelData.date_key || "") + " "
                                          + (modelData.time || "") + " · "
                                          + (modelData.account_name || "Main") + " · "
                                          + (modelData.guild_name || modelData.guild_id || "—") + " · "
                                          + (modelData.source_label || modelData.source || "—")
                                    color: Theme.fgMuted
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: recentEntries().length === 0
                        text: Empty.statsLogEmpty(App.connected, (payload.event_count || 0) > 0, "keys")
                        color: Theme.fgMuted
                        font.pixelSize: 12
                    }
                }

                ThemedButton {
                    visible: payload.has_more === true
                    text: "Load more"
                    Layout.alignment: Qt.AlignHCenter
                    onClicked: loadMore()
                }
            }
        }
    }
}
