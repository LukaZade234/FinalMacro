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

        // Summary totals — one PanelCard per key type, the same shape Kakera
        // and Spheres use for their own totals row.
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Repeater {
                model: keyCards

                delegate: PanelCard {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumWidth: 100
                    Layout.preferredHeight: 68
                    contentMargins: 12
                    title: modelData.label
                    titleSize: 11

                    headerAccessory: KeyTypeBadge {
                        keyType: modelData.key
                        size: 14
                    }

                    Label {
                        text: "+" + formatAmount(displayTotalsForType(modelData.key).all_time || 0)
                        color: modelData.color
                        font.pixelSize: 16
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

        // Filters — a plain row, matching Kakera and Spheres: no card of its
        // own, just the combos and a trailing count.
        Item {
            Layout.fillWidth: true
            implicitHeight: filterFlow.implicitHeight

            Flow {
                id: filterFlow
                width: parent.width
                spacing: 8

                ThemedComboBox {
                    width: 170
                    model: ["All accounts"].concat(uniqueAccounts().map(function(a) { return a.label }))
                    currentIndex: accountComboIndex()
                    onActivated: function(index) {
                        accountFilter = index <= 0 ? "all" : uniqueAccounts()[index - 1].id
                        reload(true)
                    }
                }
                ThemedComboBox {
                    width: 180
                    model: ["All servers"].concat(uniqueServers().map(function(s) { return s.label }))
                    currentIndex: serverComboIndex()
                    onActivated: function(index) {
                        serverFilter = index <= 0 ? "all" : uniqueServers()[index - 1].id
                        reload(true)
                    }
                }
                ThemedComboBox {
                    width: 130
                    model: ["All types"].concat(uniqueKeyTypes().map(function(t) { return t.label }))
                    currentIndex: typeComboIndex()
                    onActivated: function(index) {
                        keyTypeFilter = index <= 0 ? "all" : uniqueKeyTypes()[index - 1].id
                        reload(true)
                    }
                }
                ThemedComboBox {
                    width: 150
                    model: ["All sources"].concat(uniqueSources().map(function(s) { return s.label }))
                    currentIndex: sourceComboIndex()
                    onActivated: function(index) {
                        sourceFilter = index <= 0 ? "all" : uniqueSources()[index - 1].id
                        reload(true)
                    }
                }
                ThemedComboBox {
                    width: 110
                    model: ["7 days", "30 days", "90 days", "1 year", "All"]
                    currentIndex: 1
                    onActivated: function(index) {
                        trendRangeDays = [7, 30, 90, 365, 0][index]
                    }
                }

                Label {
                    text: (payload.event_count || 0) + " events"
                    color: Theme.fgSecondary
                    font.pixelSize: 12
                }
            }
        }

        // Chart + sources side by side when wide enough
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            PanelCard {
                Layout.fillWidth: true
                Layout.preferredWidth: 2
                title: "Trends"
                titleSize: 14

                headerAccessory: Repeater {
                    model: [
                        { label: "Daily", mode: 0 },
                        { label: "Monthly", mode: 1 },
                        { label: "Omega", mode: 2 }
                    ]
                    delegate: Item {
                        required property var modelData
                        readonly property bool on: keysRoot.chartMode === modelData.mode

                        implicitHeight: 26
                        implicitWidth: modeLabel.implicitWidth + (Theme.flatPanels ? 6 : 16)

                        Rectangle {
                            visible: !Theme.flatPanels
                            anchors.fill: parent
                            radius: 13
                            color: parent.on ? Theme.accentPrimary : Theme.bgDark
                            border.color: parent.on ? Theme.accentPrimary : Theme.border
                            border.width: 1
                        }

                        // Quiet marks the active mode with an accent underline
                        // instead of a filled pill, the same mark every other
                        // selector in this design uses.
                        Rectangle {
                            visible: Theme.flatPanels && parent.on
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: Theme.accent
                        }

                        Label {
                            id: modeLabel
                            anchors.centerIn: parent
                            text: modelData.label
                            color: Theme.flatPanels
                                   ? (parent.on ? Theme.fg : Theme.mute)
                                   : (parent.on ? Theme.bgDark : Theme.fgSecondary)
                            font.pixelSize: 11
                            font.weight: parent.on ? Font.DemiBold : Font.Normal
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: keysRoot.chartMode = modelData.mode
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

            PanelCard {
                Layout.preferredWidth: 220
                Layout.maximumWidth: 260
                Layout.fillHeight: true
                Layout.minimumHeight: 180
                visible: keysRoot.width >= 900
                title: "By source"
                titleSize: 13
                fillContentVertically: true

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

        // Recent activity as clean rows instead of a dense table
        PanelCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 280
            title: "Recent gains"
            titleSize: 14
            fillContentVertically: true

            headerAccessory: Label {
                text: payload.has_more ? "Newest first" : "Newest first · all loaded"
                color: Theme.fgMuted
                font.pixelSize: 10
            }

            ListView {
                id: recentList
                Layout.fillWidth: true
                Layout.fillHeight: true
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

                        KeyTypeBadge {
                            keyType: modelData.key_type || ""
                            size: 22
                            Layout.preferredWidth: 22
                            Layout.preferredHeight: 22
                            Layout.alignment: Qt.AlignVCenter
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
