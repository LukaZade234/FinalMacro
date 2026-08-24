import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: minigamesRoot
    clip: true
    anchors.fill: parent

    readonly property var winGames: ({ oc: true, oq: true })
    readonly property var sphereOrder: [
        "spP", "spB", "spT", "spG", "spY", "spO", "spR", "spW", "spL", "spD", "spU"
    ]
    readonly property var summaryCardModel: [
        { key: "games", label: "Games", winOnly: false },
        { key: "wins", label: "Wins", winOnly: true },
        { key: "win_rate", label: "Win rate", winOnly: true },
        { key: "avg_base_value", label: "Avg base SP", winOnly: false },
        { key: "base_value", label: "Total base SP", winOnly: false }
    ]

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var payload: ({ entries: [], totals: {}, by_game: [], spawn: [], clicked: [] })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string gameFilter: "all"
    property int selectedIndex: 0

    readonly property bool showWinStats: gameFilter === "all" || !!winGames[gameFilter]
    readonly property bool showTypeRates: gameFilter !== "all"

    readonly property var visibleEntries: {
        var _ = [accountFilter, serverFilter, gameFilter, payload]
        return filteredEntries()
    }
    readonly property var currentTotals: {
        var _ = [accountFilter, serverFilter, gameFilter, payload]
        return filteredTotals()
    }
    readonly property var spawnRows: {
        var _ = [accountFilter, serverFilter, gameFilter, payload]
        return spawnSeries()
    }
    readonly property var clickRows: {
        var _ = [accountFilter, serverFilter, gameFilter, payload]
        return clickSeries()
    }

    function reload() {
        try {
            payload = JSON.parse(String(App.minigamesJson))
        } catch (e) {
            payload = { entries: [], totals: {}, by_game: [], spawn: [], clicked: [] }
        }
        if (selectedIndex >= filteredEntries().length)
            selectedIndex = 0
        refreshServerFilter()
    }

    function entries() {
        return payload.entries || []
    }

    function formatSp(value) {
        var n = Number(value) || 0
        return n.toLocaleString(Qt.locale(), "f", 0)
    }

    function formatPct(value) {
        return ((Number(value) || 0) * 100).toFixed(1) + "%"
    }

    function serverKey(entry) {
        return entry.guild_name || String(entry.guild_id || "unknown")
    }

    function hasWinCondition(game) {
        return !!winGames[game]
    }

    function sphereLabel(emoji) {
        if (emoji === "spU" && gameFilter === "oh")
            return "Hidden ($oc)"
        return SphereAssets.label(emoji) || emoji
    }

    function filteredEntries() {
        return entries().filter(function(entry) {
            if (accountFilter !== "all" && entry.account_id !== accountFilter)
                return false
            if (serverFilter !== "all" && serverKey(entry) !== serverFilter)
                return false
            if (gameFilter !== "all" && entry.game !== gameFilter)
                return false
            return true
        })
    }

    function uniqueAccounts() {
        var seen = {}
        var out = []
        for (var i = 0; i < entries().length; i++) {
            var id = entries()[i].account_id || ""
            if (!id || seen[id])
                continue
            seen[id] = true
            out.push({ id: id, label: entries()[i].account_name || id })
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

    function ocGrantsFor(entry) {
        var grants = Number(entry.oc_bonus || 0)
        if (grants)
            return grants
        var clicks = entry.clicks || []
        for (var i = 0; i < clicks.length; i++)
            grants += Number(clicks[i].oc_bonus || 0)
        return grants
    }

    function filteredTotals() {
        var list = filteredEntries()
        var games = list.length
        var base = 0
        var ocGrants = 0
        var scored = 0
        var wins = 0
        for (var i = 0; i < list.length; i++) {
            var entry = list[i]
            base += Number(entry.base_value || 0)
            ocGrants += ocGrantsFor(entry)
            if (hasWinCondition(entry.game)) {
                scored += 1
                if (entry.won)
                    wins += 1
            }
        }
        return {
            games: games,
            wins: wins,
            scored_games: scored,
            win_rate: scored ? wins / scored : 0,
            base_value: base,
            avg_base_value: games ? base / games : 0,
            oc_grants: ocGrants
        }
    }

    function summaryText(key) {
        var t = currentTotals
        if (key === "games")
            return formatSp(t.games)
        if (key === "wins")
            return formatSp(t.wins)
        if (key === "win_rate")
            return t.scored_games ? formatPct(t.win_rate) : "—"
        if (key === "avg_base_value")
            return formatSp(t.avg_base_value)
        if (key === "base_value")
            return formatSp(t.base_value)
        return "—"
    }

    function countsToSeries(counts, total) {
        var series = []
        var seen = {}
        for (var i = 0; i < sphereOrder.length; i++) {
            var emoji = sphereOrder[i]
            var count = counts[emoji] || 0
            seen[emoji] = true
            if (count <= 0)
                continue
            series.push({
                emoji: emoji,
                label: sphereLabel(emoji),
                count: count,
                rate: total ? count / total : 0
            })
        }
        var extras = Object.keys(counts).sort()
        for (var j = 0; j < extras.length; j++) {
            var extra = extras[j]
            if (seen[extra])
                continue
            var extraCount = counts[extra] || 0
            if (extraCount <= 0)
                continue
            series.push({
                emoji: extra,
                label: sphereLabel(extra),
                count: extraCount,
                rate: total ? extraCount / total : 0
            })
        }
        return series
    }

    function spawnSeries() {
        if (gameFilter === "all")
            return []
        var list = filteredEntries()
        var counts = {}
        var total = 0
        for (var i = 0; i < list.length; i++) {
            var board = list[i].board || []
            for (var c = 0; c < board.length; c++) {
                var emoji = String(board[c] || "").trim()
                if (!emoji || emoji === "spU")
                    continue
                if (emoji === "sp")
                    emoji = "spR"
                counts[emoji] = (counts[emoji] || 0) + 1
                total += 1
            }
        }
        return countsToSeries(counts, total)
    }

    function clickSeries() {
        if (gameFilter === "all")
            return []
        var list = filteredEntries()
        var counts = {}
        var total = 0
        for (var i = 0; i < list.length; i++) {
            var clicks = list[i].clicks || []
            for (var c = 0; c < clicks.length; c++) {
                var emoji = String(clicks[c].emoji || "").trim()
                if (!emoji)
                    continue
                if (emoji === "sp")
                    emoji = "spR"
                counts[emoji] = (counts[emoji] || 0) + 1
                total += 1
            }
        }
        return countsToSeries(counts, total)
    }

    function selectedEntry() {
        var list = visibleEntries
        if (selectedIndex < 0 || selectedIndex >= list.length)
            return null
        return list[selectedIndex]
    }

    function cellLabel(index) {
        var n = Number(index)
        if (isNaN(n) || n < 0)
            return "?"
        return "(" + (Math.floor(n / 5) + 1) + "," + ((n % 5) + 1) + ")"
    }

    function filterHint() {
        if (gameFilter === "all")
            return "Win rate is $oc / $oq only. Pick a game to see spawn and click rates for that type."
        if (gameFilter === "oh")
            return "Hidden $oh clicks that resolve as Hidden grant $oc. Light and dark keep their own identity."
        if (hasWinCondition(gameFilter))
            return "Win means we clicked red or rainbow. Value is base SP, not the chat total."
        return "This game has no red/rainbow win. Value is base SP, not the chat total."
    }

    function resetSelection() {
        selectedIndex = 0
    }

    Component {
        id: sphereRateRow
        RowLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 8

            SphereTypeBadge { sphereId: modelData.emoji }

            Label {
                text: modelData.label
                color: Theme.fgPrimary
                font.pixelSize: 12
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Label {
                text: minigamesRoot.formatSp(modelData.count)
                color: Theme.fgSecondary
                font.pixelSize: 12
                Layout.preferredWidth: 36
                horizontalAlignment: Text.AlignRight
            }

            Label {
                text: minigamesRoot.formatPct(modelData.rate)
                color: Theme.fgPrimary
                font.pixelSize: 12
                font.weight: Font.DemiBold
                Layout.preferredWidth: 52
                horizontalAlignment: Text.AlignRight
            }
        }
    }

    Component.onCompleted: reload()

    Connections {
        target: App
        function onMinigamesChanged() {
            minigamesRoot.reload()
        }
    }

    ScrollablePage {
        anchors.fill: parent

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
                        resetSelection()
                    }
                }

                ThemedComboBox {
                    width: 220
                    model: ["All servers"].concat(uniqueServers().map(function(s) { return s.label }))
                    onActivated: function(index) {
                        serverFilter = index <= 0 ? "all" : uniqueServers()[index - 1].id
                        resetSelection()
                    }
                }

                ThemedComboBox {
                    width: 140
                    model: ["All games", "$oh", "$oc", "$oq", "$ot"]
                    onActivated: function(index) {
                        gameFilter = index <= 0 ? "all" : ["oh", "oc", "oq", "ot"][index - 1]
                        resetSelection()
                    }
                }

                Label {
                    height: 32
                    verticalAlignment: Text.AlignVCenter
                    text: currentTotals.games + " games · "
                          + formatSp(currentTotals.base_value) + " sp"
                    color: Theme.fgSecondary
                    font.pixelSize: 12
                }
            }
        }

        Label {
            text: filterHint()
            color: Theme.fgMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Repeater {
                model: minigamesRoot.summaryCardModel
                delegate: PanelCard {
                    required property var modelData
                    visible: !modelData.winOnly || minigamesRoot.showWinStats
                    Layout.fillWidth: visible
                    Layout.preferredWidth: visible ? 100 : 0
                    Layout.minimumWidth: visible ? 100 : 0
                    Layout.preferredHeight: 68
                    Layout.maximumHeight: visible ? 68 : 0
                    contentMargins: 12
                    title: modelData.label
                    titleSize: 11

                    Label {
                        text: {
                            minigamesRoot.currentTotals
                            return minigamesRoot.summaryText(modelData.key)
                        }
                        color: Theme.accentPrimary
                        font.pixelSize: 18
                        font.weight: Font.DemiBold
                    }
                }
            }
        }

        RowLayout {
            visible: minigamesRoot.showTypeRates
            Layout.fillWidth: true
            spacing: 10

            PanelCard {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "Spawn rate"
                titleSize: 14

                Repeater {
                    model: minigamesRoot.spawnRows
                    delegate: sphereRateRow
                }

                Label {
                    visible: minigamesRoot.spawnRows.length === 0
                    text: "No revealed cells in the selected games."
                    color: Theme.fgMuted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            PanelCard {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "Click rate"
                titleSize: 14

                Repeater {
                    model: minigamesRoot.clickRows
                    delegate: sphereRateRow
                }

                Label {
                    visible: gameFilter === "oh"
                    text: "$oc granted from hidden clicks: "
                          + formatSp(currentTotals.oc_grants)
                    color: Theme.fgMuted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                Label {
                    visible: minigamesRoot.clickRows.length === 0
                    text: "No clicks in the selected games."
                    color: Theme.fgMuted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 420
            spacing: 10

            PanelCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1
                title: "Games"
                titleSize: 14
                fillContentVertically: true

                ListView {
                    id: gameList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: minigamesRoot.visibleEntries
                    currentIndex: minigamesRoot.selectedIndex
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: ListView.view.width
                        height: 36
                        color: index === minigamesRoot.selectedIndex
                               ? Theme.bgHover : "transparent"

                        MouseArea {
                            anchors.fill: parent
                            onClicked: minigamesRoot.selectedIndex = index
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            spacing: 8
                            Label {
                                Layout.preferredWidth: 64
                                text: modelData.time || ""
                                color: Theme.fgMuted
                                font.pixelSize: 11
                            }
                            Label {
                                Layout.preferredWidth: 40
                                text: modelData.game_label || ("$" + modelData.game)
                                color: Theme.fgPrimary
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 48
                                text: hasWinCondition(modelData.game)
                                      ? (modelData.won ? "win" : "—")
                                      : ""
                                color: modelData.won && hasWinCondition(modelData.game)
                                       ? Theme.accentPrimary : Theme.fgMuted
                                font.pixelSize: 11
                            }
                            Label {
                                Layout.fillWidth: true
                                text: "+" + formatSp(modelData.base_value) + " sp"
                                color: Theme.fgSecondary
                                font.pixelSize: 12
                            }
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: gameList.count === 0
                        text: entries().length === 0
                            ? "No minigames logged yet. Play $oh / $oc / $oq while connected."
                            : "No entries match the current filters."
                        color: Theme.fgMuted
                        font.pixelSize: 12
                    }
                }
            }

            PanelCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1
                title: selectedEntry()
                      ? ((selectedEntry().game_label || "") + " board")
                      : "Board"
                titleSize: 14
                fillContentVertically: true

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 10

                    Grid {
                        Layout.alignment: Qt.AlignHCenter
                        columns: 5
                        rows: 5
                        spacing: 4
                        Repeater {
                            model: 25
                            delegate: Rectangle {
                                required property int index
                                width: 28
                                height: 28
                                radius: 4
                                color: Theme.inputBg
                                border.color: {
                                    var entry = selectedEntry()
                                    if (!entry)
                                        return Theme.border
                                    var clicks = entry.clicks || []
                                    for (var i = 0; i < clicks.length; i++) {
                                        if (clicks[i].cell === index)
                                            return Theme.accentPrimary
                                    }
                                    return Theme.border
                                }
                                SphereTypeBadge {
                                    anchors.centerIn: parent
                                    sphereId: {
                                        var entry = selectedEntry()
                                        if (!entry || !entry.board)
                                            return "spU"
                                        return entry.board[index] || "spU"
                                    }
                                }
                            }
                        }
                    }

                    Label {
                        text: "Clicks in order"
                        color: Theme.fgMuted
                        font.pixelSize: 10
                    }

                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        contentWidth: width
                        contentHeight: clickColumn.implicitHeight
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        ColumnLayout {
                            id: clickColumn
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: selectedEntry() ? (selectedEntry().clicks || []) : []
                                delegate: RowLayout {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Label {
                                        text: (index + 1) + "."
                                        color: Theme.fgMuted
                                        font.pixelSize: 11
                                        Layout.preferredWidth: 20
                                    }
                                    SphereTypeBadge { sphereId: modelData.emoji || "" }
                                    Repeater {
                                        model: modelData.resolved || []
                                        delegate: SphereTypeBadge {
                                            required property var modelData
                                            sphereId: modelData
                                        }
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: cellLabel(modelData.cell)
                                              + (modelData.paid ? "" : " free")
                                              + (modelData.oc_bonus ? " +$oc" : "")
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
}
