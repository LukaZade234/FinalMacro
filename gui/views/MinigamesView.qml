import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: minigamesRoot
    clip: true
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var payload: ({ entries: [], totals: {}, by_game: [], spawn: [], clicked: [] })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property string gameFilter: "all"
    property int selectedIndex: 0

    function reload() {
        try {
            payload = JSON.parse(App.minigamesJson)
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

    function totals() {
        return payload.totals || {}
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

    function selectedEntry() {
        var list = filteredEntries()
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

    Component.onCompleted: reload()

    Connections {
        target: App
        function onMinigamesChanged() {
            minigamesRoot.reload()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        Label {
            text: "One row per $oh / $oc / $oq, stored in data/minigame_log.json (not the Run session log). Value is base SP (purple 5, blue 10, …) — not the chat total. Light/dark count as themselves; the colour they became is shown after the badge. Won means we clicked red or rainbow. Hidden $oh clicks that show spU in chat grant $oc (spent on play-all like bonus $oq)."
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
                    { label: "Games", key: "games" },
                    { label: "Wins", key: "wins" },
                    { label: "Win rate", key: "win_rate" },
                    { label: "Avg base SP", key: "avg_base_value" },
                    { label: "Total base SP", key: "base_value" },
                    { label: "$oc from $oh", key: "oc_grants" }
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
                        text: modelData.key === "win_rate"
                              ? formatPct(totals()[modelData.key] || 0)
                              : (modelData.key === "avg_base_value"
                                 ? formatSp(totals()[modelData.key] || 0)
                                 : formatSp(totals()[modelData.key] || 0))
                        color: Theme.accentPrimary
                        font.pixelSize: 18
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
                    width: 140
                    model: ["All games", "$oh", "$oc", "$oq"]
                    onActivated: function(index) {
                        gameFilter = index <= 0 ? "all" : ["oh", "oc", "oq"][index - 1]
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Repeater {
                model: payload.by_game || []
                delegate: PanelCard {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumWidth: 120
                    Layout.preferredHeight: 72
                    contentMargins: 12
                    title: modelData.label
                    titleSize: 11

                    Label {
                        text: modelData.wins + "/" + modelData.games
                              + " · " + formatPct(modelData.win_rate)
                              + " · " + formatSp(modelData.avg_base_value) + " sp"
                        color: Theme.fgPrimary
                        font.pixelSize: 12
                    }
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Spawn rate (revealed board cells)"
            titleSize: 14

            Flow {
                Layout.fillWidth: true
                spacing: 12

                Repeater {
                    model: payload.spawn || []
                    delegate: RowLayout {
                        required property var modelData
                        spacing: 6
                        SphereTypeBadge { sphereId: modelData.emoji }
                        Label {
                            text: modelData.label + "  " + modelData.count
                                  + "  " + formatPct(modelData.rate)
                            color: Theme.fgSecondary
                            font.pixelSize: 11
                        }
                    }
                }

                Label {
                    visible: (payload.spawn || []).length === 0
                    text: "Play minigames while connected to record spawn rates."
                    color: Theme.fgMuted
                    font.pixelSize: 12
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            title: "Clicked mix (light/dark stay themselves; hidden $oh clicks are $oc)"
            titleSize: 14

            Flow {
                Layout.fillWidth: true
                spacing: 12

                Repeater {
                    model: payload.clicked || []
                    delegate: RowLayout {
                        required property var modelData
                        spacing: 6
                        SphereTypeBadge { sphereId: modelData.emoji }
                        Label {
                            text: modelData.label + "  " + modelData.count
                                  + "  " + formatPct(modelData.rate)
                            color: Theme.fgSecondary
                            font.pixelSize: 11
                        }
                    }
                }

                Label {
                    visible: (payload.clicked || []).length === 0
                    text: "Click colours appear here after a recorded game."
                    color: Theme.fgMuted
                    font.pixelSize: 12
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
                    model: filteredEntries()
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
                                text: modelData.won ? "win" : "—"
                                color: modelData.won ? Theme.accentPrimary : Theme.fgMuted
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
                            ? "No minigames logged yet — play $oh / $oc / $oq while connected. Rows are written to data/minigame_log.json."
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

                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: selectedEntry() ? (selectedEntry().clicks || []) : []
                            delegate: RowLayout {
                                required property var modelData
                                required property int index
                                spacing: 4
                                Label {
                                    text: (index + 1) + "."
                                    color: Theme.fgMuted
                                    font.pixelSize: 10
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
                                    text: cellLabel(modelData.cell)
                                          + (modelData.paid ? "" : " free")
                                          + (modelData.oc_bonus ? " +$oc" : "")
                                    color: Theme.fgSecondary
                                    font.pixelSize: 10
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
