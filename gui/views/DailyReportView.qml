import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Statistics › Report — one UTC day, as a mosaic rather than a stack.

    Every other Statistics sub-page slices the event cube by *kind*; this one
    slices the same day every way at once, so it is read by scanning rather than
    top to bottom. Tiles are therefore sized to what they hold — keys is five
    numbers and gets a third of a row; the hourly chart is the day's shape and
    anchors the middle — and no two neighbouring tiles use the same chart form.

    Comparisons are against the **all-time** mean of days that saw activity, not
    a trailing window: a gap where the macro was not running is not a run of
    zero-earning days, so averaging it in would flatter every day after it.
*/
Item {
    id: report
    clip: true

    // Never `data` — that is Item's default property, and shadowing it stops
    // children from being parented and renders the page blank.
    property var reportData: ({
        date: "", available_days: [], kinds: {}, trend: [], breakdowns: {},
        hourly: {}, tapes: {}, soulmates: [], minigames: {}, today: "",
        filter_options: { accounts: [], servers: [] }
    })
    property string accountFilter: "all"
    property string serverFilter: "all"
    property int dayOffset: 0

    readonly property var days: reportData.available_days || []
    readonly property var trend: reportData.trend || []
    readonly property var breakdowns: reportData.breakdowns || ({})
    readonly property var hourly: reportData.hourly || ({})
    readonly property var tapes: reportData.tapes || ({})
    readonly property var minigames: reportData.minigames || ({})

    // A report narrowed to one account on one server. Everything on this page
    // sums honestly across accounts *except* the perk-8 and perk-9 tapes, which
    // measure a per-pairing daily allowance — so those two read this.
    readonly property bool scoped: (reportData.scope || {}).scoped === true
    readonly property var scopeAccounts: (reportData.filter_options || {}).accounts || []
    readonly property var scopeServers: (reportData.filter_options || {}).servers || []

    // Domain hues. Not free choices — a purple kakera has to read purple.
    // Checked for colour-vision separation (deutan ΔE 13.0, normal ΔE 15.5).
    readonly property var kakeraColour: ({
        "kakeraP": "#8b63e8", "kakeraO": "#dd7a26", "kakeraL": "#f06898",
        "kakeraC": "#d9a52f", "kakeraD": "#6f7ba8", "kakeraR": "#e94f5f",
        "kakera": "#5b8dd9", "kakeraT": "#2ac3de", "kakeraG": "#4fae6a",
        "kakeraY": "#c9a63c", "kakeraW": "#c0caf5"
    })
    readonly property var keyColour: ({
        "chaos": "#8b6cf0", "omega": "#5b8dd9", "gold": "#f2a83c",
        "silver": "#9aa3bd", "bronze": "#c0793f"
    })

    // Eight slots, so a seven-way sphere split never wraps back onto its own
    // first colour. Checked for separation: worst adjacent pair ΔE 13.2 under
    // deuteranopia, 20.2 with normal vision, all ≥3:1 against the surface.
    function seriesColour(index) {
        var ramp = ["#e8479e", "#8b6cf0", "#dd7a26", "#3ed6b8",
                    "#d9a52f", "#5b8dd9", "#8fbf4a", "#b06a5a"]
        return ramp[index % ramp.length]
    }

    // Every source shows what it earned and its share. Only clicks and $bku
    // resets also show a count: those are discrete actions worth tallying,
    // where a $bku roll gain or a $dk is one payout with nothing to count.
    function sourceHasCount(id) {
        return id === "kakera_click" || id === "bku_reset"
    }

    function kind(name) {
        var all = reportData.kinds || {}
        return all[name] || { total: 0, count: 0, all_time: {} }
    }

    function allTime(name) {
        return kind(name).all_time || { average: null, delta_pct: null, active_days: 0 }
    }

    function fmt(n) {
        return Number(n || 0).toLocaleString(Qt.locale(), "f", 0)
    }

    function pct(n, digits) {
        return Number(n || 0).toFixed(digits === undefined ? 1 : digits) + "%"
    }

    function deltaColour(value) {
        if (value === null || value === undefined) return Theme.mute
        if (value > 2) return Theme.good
        if (value < -2) return Theme.bad
        return Theme.mute
    }

    // One scale for every minigame row, so the rows and the axis beneath them
    // cannot drift apart.
    function minigameScaleTop() {
        var rows = (reportData.minigames || {}).games || []
        var m = 1
        for (var i = 0; i < rows.length; i++) {
            m = Math.max(m, rows[i].sp_per_use || 0,
                         rows[i].benchmark_sp_per_use || 0)
        }
        return report.niceCeiling(m * 1.12)
    }

    // True once any row has a per-use rate to plot. Until a full day has
    // recorded its use counts there is nothing on the track, and an axis
    // under an empty track just prints a scale for marks that are not there.
    function minigamesHaveRate() {
        var rows = (reportData.minigames || {}).games || []
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].sp_per_use !== null || rows[i].benchmark_sp_per_use !== null)
                return true
        }
        return false
    }

    // Round an axis top up to 1, 2, 2.5 or 5 x 10^n, so every tick beneath it
    // is a number a reader can hold in their head.
    function niceCeiling(value) {
        if (!(value > 0)) return 1
        var power = Math.pow(10, Math.floor(Math.log(value) / Math.LN10))
        var steps = [1, 2, 2.5, 5, 10]
        for (var i = 0; i < steps.length; i++) {
            if (value <= steps[i] * power)
                return steps[i] * power
        }
        return 10 * power
    }

    function deltaText(value) {
        if (value === null || value === undefined) return "—"
        return (value > 0 ? "+" : "") + Math.round(value) + "%"
    }

    function optionIndex(list, wanted) {
        if (wanted === "all")
            return 0
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === wanted)
                return i + 1
        }
        return 0
    }

    function optionLabels(list, allLabel) {
        return [allLabel].concat(list.map(function (row) { return row.label }))
    }

    // Which days exist depends on the scope, so a scope change can move the day
    // under the reader. Hold the date they were looking at where it still exists.
    function alignToDate(wanted) {
        if (!wanted)
            return
        for (var i = 0; i < days.length; i++) {
            if (days[i] === wanted) {
                var offset = days.length - 1 - i
                if (offset !== dayOffset) {
                    dayOffset = offset
                    refresh()
                }
                return
            }
        }
        if (dayOffset !== 0) {
            dayOffset = 0
            refresh()
        }
    }

    function setScope(account, server) {
        if (account === accountFilter && server === serverFilter)
            return
        var keep = reportData.date || ""
        accountFilter = account
        serverFilter = server
        dayOffset = 0
        refresh()
        alignToDate(keep)
    }

    function selectedDay() {
        if (days.length === 0)
            return ""
        var index = days.length - 1 - dayOffset
        if (index < 0) index = 0
        if (index >= days.length) index = days.length - 1
        return days[index]
    }

    function refresh() {
        try {
            reportData = JSON.parse(
                App.dailyReportJson(selectedDay(), accountFilter, serverFilter))
        } catch (e) {
            reportData = { date: "", available_days: [], kinds: {}, trend: [],
                           breakdowns: {}, hourly: {}, tapes: {}, soulmates: [],
                           minigames: {}, today: "",
                           filter_options: { accounts: [], servers: [] } }
        }
        repaintAll()
    }

    function repaintAll() {
        sparkCanvas.requestPaint()
        heroCanvas.requestPaint()
        keyPie.requestPaint()
        scatterCanvas.requestPaint()
    }

    function shiftDay(delta) {
        var next = dayOffset + delta
        if (next < 0) next = 0
        if (next > Math.max(0, days.length - 1)) next = Math.max(0, days.length - 1)
        if (next === dayOffset)
            return
        dayOffset = next
        refresh()
    }

    Connections {
        target: App
        function onKakeraChanged() { report.refresh() }
        function onSpheresChanged() { report.refresh() }
        function onKeysChanged() { report.refresh() }
    }

    Component.onCompleted: refresh()

    // ---- reusable pieces -----------------------------------------------------

    component Tile: Rectangle {
        id: tile
        default property alias body: bodyColumn.data
        property string title: ""
        property string subtitle: ""
        property string total: ""
        property string totalUnit: ""
        property string footnote: ""

        color: Theme.surface
        border.width: Theme.borderWidth
        border.color: Theme.line
        radius: Theme.radiusMd
        Layout.fillWidth: true
        Layout.fillHeight: true
        implicitHeight: inner.implicitHeight + Theme.cardPadding * 2

        ColumnLayout {
            id: inner
            anchors.fill: parent
            anchors.margins: Theme.cardPadding
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Label {
                    text: Theme.sectionLabel(tile.title)
                    color: Theme.fg
                    font.pixelSize: Theme.sizeSmall
                    font.weight: Font.DemiBold
                    font.letterSpacing: Theme.tracking(Theme.sizeSmall)
                }
                Label {
                    Layout.fillWidth: true
                    visible: tile.subtitle !== ""
                    text: tile.subtitle
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    elide: Text.ElideRight
                }
                Item { Layout.fillWidth: tile.subtitle === "" }
                Label {
                    visible: tile.total !== ""
                    text: tile.total
                    color: Theme.fg
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeLarge
                    font.weight: Font.DemiBold
                }
                Label {
                    visible: tile.totalUnit !== ""
                    text: tile.totalUnit
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                }
            }

            ColumnLayout {
                id: bodyColumn
                Layout.fillWidth: true
                spacing: 9
            }

            // A tile stretches to its row's height; the slack belongs under the
            // content, not spread through it.
            Item { Layout.fillWidth: true; Layout.fillHeight: true }

            Label {
                Layout.fillWidth: true
                visible: tile.footnote !== ""
                text: tile.footnote
                color: Theme.mute
                font.pixelSize: Theme.sizeMicro
                wrapMode: Text.WordWrap
                lineHeight: 1.25
            }
        }
    }

    component DeltaChip: Rectangle {
        property real value: 0
        property bool known: true
        implicitWidth: chipText.implicitWidth + 12
        implicitHeight: 17
        radius: Theme.radiusXs
        color: Qt.rgba(report.deltaColour(known ? value : null).r,
                       report.deltaColour(known ? value : null).g,
                       report.deltaColour(known ? value : null).b, 0.12)
        Label {
            id: chipText
            anchors.centerIn: parent
            text: known ? report.deltaText(value) : "—"
            color: report.deltaColour(known ? value : null)
            font.family: Theme.monoFamily
            font.pixelSize: Theme.sizeMicro
            font.weight: Font.DemiBold
        }
    }

    component BarRow: ColumnLayout {
        property string label: ""
        property string value: ""
        property string suffix: ""
        property string extra: ""
        property real fraction: 0
        property color barColour: Theme.accent
        property bool big: false
        Layout.fillWidth: true
        spacing: big ? 6 : 4
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Label {
                text: label
                color: big ? Theme.fg : Theme.dim
                font.pixelSize: big ? Theme.sizeBody : Theme.sizeSmall
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Label {
                text: value
                color: Theme.fg
                font.family: Theme.monoFamily
                font.pixelSize: big ? Theme.sizeMedium : Theme.sizeSmall
                font.weight: big ? Font.DemiBold : Font.Normal
            }
            Label {
                visible: suffix !== ""
                text: suffix
                color: Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: big ? Theme.sizeSmall : Theme.sizeMicro
                Layout.minimumWidth: 34
                horizontalAlignment: Text.AlignRight
            }
            Label {
                visible: extra !== ""
                text: extra
                color: Theme.dim
                font.family: Theme.monoFamily
                font.pixelSize: big ? Theme.sizeBody : Theme.sizeSmall
                font.weight: Font.DemiBold
                Layout.minimumWidth: 40
                horizontalAlignment: Text.AlignRight
            }
        }
        Rectangle {
            Layout.fillWidth: true
            height: big ? 11 : 7
            radius: big ? 5 : 3
            color: Theme.bg
            Rectangle {
                width: Math.max(0, Math.min(1, fraction)) * parent.width
                height: parent.height
                radius: parent.radius
                color: barColour
            }
        }
    }

    Rectangle { anchors.fill: parent; color: Theme.bg }

    ScrollView {
        id: page
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        readonly property int tier: page.availableWidth >= 1100
                                    ? 2 : (page.availableWidth >= 720 ? 1 : 0)
        function span(full, mid) {
            return page.tier === 2 ? full : (page.tier === 1 ? mid : 12)
        }
        /*
            GridLayout sizes columns from content, and `uniformCellWidths` still
            yields to a tile whose content wants more — so a wide chart in one
            row quietly narrowed the tiles above and below it. A hard maximum
            per span is the only thing that holds: every row then sits on the
            same twelve columns whatever any one tile contains.
        */
        function colWidth(n) {
            var unit = (page.availableWidth - Theme.gap * 11) / 12
            return Math.max(1, unit * n + Theme.gap * (n - 1))
        }

        GridLayout {
            width: page.availableWidth
            columns: 12
            columnSpacing: Theme.gap
            rowSpacing: Theme.gap

            // ================= scope =================
            Tile {
                Layout.columnSpan: 12
                Layout.preferredWidth: page.colWidth(12)
                Layout.maximumWidth: page.colWidth(12)
                title: "scope"
                subtitle: report.scoped
                          ? "one account on one server"
                          : "general — everything, added up across accounts and servers"

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    ThemedComboBox {
                        Layout.preferredWidth: 200
                        model: report.optionLabels(report.scopeAccounts, "All accounts")
                        currentIndex: report.optionIndex(report.scopeAccounts,
                                                         report.accountFilter)
                        onActivated: function (index) {
                            report.setScope(
                                index <= 0 ? "all" : report.scopeAccounts[index - 1].id,
                                report.serverFilter)
                        }
                    }

                    ThemedComboBox {
                        Layout.preferredWidth: 220
                        model: report.optionLabels(report.scopeServers, "All servers")
                        currentIndex: report.optionIndex(report.scopeServers,
                                                         report.serverFilter)
                        onActivated: function (index) {
                            report.setScope(
                                report.accountFilter,
                                index <= 0 ? "all" : report.scopeServers[index - 1].id)
                        }
                    }

                    ThemedButton {
                        text: "General"
                        implicitHeight: 26
                        enabled: report.accountFilter !== "all"
                                 || report.serverFilter !== "all"
                        onClicked: report.setScope("all", "all")
                    }

                    Item { Layout.fillWidth: true; Layout.minimumWidth: 4 }

                    Label {
                        text: Theme.sectionLabel(report.scoped ? "scoped"
                                                               : "perk 8 · 9 hidden")
                        color: report.scoped ? Theme.good : Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }
                }
            }

            // ================= day band =================
            Tile {
                Layout.columnSpan: 12
                Layout.preferredWidth: page.colWidth(12)
                Layout.maximumWidth: page.colWidth(12)
                title: "day"

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 20

                    RowLayout {
                        spacing: 9
                        ThemedButton {
                            text: "‹"
                            implicitHeight: 26
                            implicitWidth: 30
                            enabled: report.dayOffset < Math.max(0, report.days.length - 1)
                            onClicked: report.shiftDay(1)
                        }
                        ColumnLayout {
                            spacing: 1
                            Label {
                                text: report.reportData.date || "—"
                                color: Theme.fg
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeLarge
                                font.weight: Font.DemiBold
                            }
                            Label {
                                text: report.reportData.date === report.reportData.today
                                      ? Theme.sectionLabel("today · still running")
                                      : Theme.sectionLabel(report.days.length + " days logged")
                                color: report.reportData.date === report.reportData.today
                                       ? Theme.warn : Theme.mute
                                font.pixelSize: Theme.sizeMicro
                                font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                            }
                        }
                        ThemedButton {
                            text: "›"
                            implicitHeight: 26
                            implicitWidth: 30
                            enabled: report.dayOffset > 0
                            onClicked: report.shiftDay(-1)
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: 22
                        Repeater {
                            model: [
                                { id: "kakera", label: "Kakera", unit: "" },
                                { id: "sphere", label: "Spheres", unit: "SP" },
                                { id: "key", label: "Keys", unit: "" },
                                { id: "soulmate", label: "Soulmates", unit: "" }
                            ]
                            ColumnLayout {
                                spacing: 2
                                required property var modelData
                                readonly property var entry: report.kind(modelData.id)
                                readonly property var at: report.allTime(modelData.id)
                                Label {
                                    text: Theme.sectionLabel(modelData.label)
                                    color: Theme.dim
                                    font.pixelSize: Theme.sizeMicro
                                    font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                                }
                                RowLayout {
                                    spacing: 7
                                    Label {
                                        text: report.fmt(modelData.id === "soulmate"
                                                         ? entry.count : entry.total)
                                        color: Theme.fg
                                        font.family: Theme.monoFamily
                                        font.pixelSize: Theme.sizeXLarge
                                        font.weight: Font.DemiBold
                                    }
                                    DeltaChip {
                                        value: at.delta_pct === null ? 0 : at.delta_pct
                                        known: at.delta_pct !== null
                                               && at.delta_pct !== undefined
                                    }
                                }
                                Label {
                                    text: at.average === null || at.average === undefined
                                          ? "no history yet"
                                          : "all-time avg " + report.fmt(at.average)
                                            + (modelData.unit ? " " + modelData.unit : "")
                                    color: Theme.mute
                                    font.pixelSize: Theme.sizeMicro
                                }
                            }
                        }
                    }

                    Canvas {
                        id: sparkCanvas
                        Layout.preferredWidth: 210
                        Layout.preferredHeight: 50
                        Layout.alignment: Qt.AlignVCenter
                        onWidthChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            var rows = report.trend
                            if (!rows || rows.length < 2) return
                            var max = 1
                            for (var i = 0; i < rows.length; i++)
                                max = Math.max(max, Number(rows[i].kakera) || 0)
                            var px = function (i) {
                                return 3 + i * (width - 6) / (rows.length - 1)
                            }
                            var py = function (v) { return height - 6 - (v / max) * (height - 12) }
                            ctx.beginPath()
                            ctx.moveTo(px(0), height)
                            for (i = 0; i < rows.length; i++)
                                ctx.lineTo(px(i), py(Number(rows[i].kakera) || 0))
                            ctx.lineTo(px(rows.length - 1), height)
                            ctx.closePath()
                            ctx.fillStyle = Qt.rgba(Theme.accent.r, Theme.accent.g,
                                                    Theme.accent.b, 0.14)
                            ctx.fill()
                            ctx.beginPath()
                            for (i = 0; i < rows.length; i++) {
                                var y = py(Number(rows[i].kakera) || 0)
                                if (i === 0) ctx.moveTo(px(i), y); else ctx.lineTo(px(i), y)
                            }
                            ctx.strokeStyle = Theme.accent
                            ctx.lineWidth = 2
                            ctx.lineJoin = "round"
                            ctx.stroke()
                            var last = rows.length - 1
                            ctx.beginPath()
                            ctx.arc(px(last), py(Number(rows[last].kakera) || 0), 3.5, 0, Math.PI * 2)
                            ctx.fillStyle = Theme.accent
                            ctx.fill()
                        }
                    }
                }
            }

            // ================= hero: the day, hour by hour =================
            Tile {
                Layout.columnSpan: page.span(8, 12)
                Layout.preferredWidth: page.colWidth(page.span(8, 12))
                Layout.maximumWidth: page.colWidth(page.span(8, 12))
                title: "the day, hour by hour"
                subtitle: "kakera stacked by source · spheres and keys on their own scales"

                Canvas {
                    id: heroCanvas
                    Layout.fillWidth: true
                    Layout.preferredHeight: 330
                    onWidthChanged: requestPaint()
                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.reset()
                        var padL = 44, padR = 8
                        var iw = width - padL - padR
                        if (iw <= 0) return
                        var bw = iw / 24
                        var bar = bw * 0.66, off = (bw - bar) / 2

                        var stacked = report.hourly.kakera_by_method || []
                        var panels = [
                            { y0: 36, h: 146, label: "KAKERA", stacked: stacked },
                            { y0: 208, h: 48, label: "SPHERES  SP",
                              single: report.hourly.sphere || [], colour: Theme.accent2 },
                            { y0: 278, h: 32, label: "KEYS",
                              single: report.hourly.key || [], colour: Theme.good }
                        ]

                        var mono = Theme.monoFamily
                        for (var p = 0; p < panels.length; p++) {
                            var panel = panels[p]
                            var totals = []
                            var h
                            for (h = 0; h < 24; h++) {
                                var sum = 0
                                if (panel.stacked) {
                                    for (var s = 0; s < panel.stacked.length; s++)
                                        sum += Number(panel.stacked[s].values[h]) || 0
                                } else {
                                    sum = Number((panel.single || [])[h]) || 0
                                }
                                totals.push(sum)
                            }
                            var max = 1
                            for (h = 0; h < 24; h++) max = Math.max(max, totals[h])
                            var step = Math.pow(10, Math.floor(Math.log(max) / Math.LN10))
                            var top = Math.ceil(max / (step / 2)) * (step / 2)
                            var base = panel.y0 + panel.h

                            ctx.strokeStyle = Theme.line
                            ctx.lineWidth = 1
                            ctx.beginPath()
                            ctx.moveTo(padL, base + 0.5); ctx.lineTo(width - padR, base + 0.5)
                            ctx.stroke()

                            ctx.fillStyle = Theme.mute
                            ctx.font = "9px '" + mono + "'"
                            ctx.textAlign = "right"
                            ctx.fillText(top >= 1000 ? (top / 1000) + "k" : String(top),
                                         padL - 6, panel.y0 + 4)
                            ctx.fillText("0", padL - 6, base + 4)
                            ctx.textAlign = "left"
                            ctx.fillStyle = Theme.dim
                            ctx.fillText(panel.label, padL, panel.y0 - 6)

                            for (h = 0; h < 24; h++) {
                                var x = padL + h * bw + off
                                if (panel.stacked) {
                                    var cursor = base
                                    for (s = 0; s < panel.stacked.length; s++) {
                                        var v = Number(panel.stacked[s].values[h]) || 0
                                        if (v <= 0) continue
                                        var hh = (v / top) * panel.h
                                        cursor -= hh
                                        ctx.fillStyle = report.seriesColour(s)
                                        ctx.fillRect(x, cursor, bar, Math.max(1, hh - 1.6))
                                        cursor -= 1.6
                                    }
                                } else {
                                    var val = Number((panel.single || [])[h]) || 0
                                    if (val <= 0) continue
                                    var bh = Math.max(2, (val / top) * panel.h)
                                    ctx.fillStyle = panel.colour
                                    ctx.fillRect(x, base - bh, bar, bh)
                                }
                            }
                        }

                        ctx.fillStyle = Theme.mute
                        ctx.font = "9px '" + mono + "'"
                        ctx.textAlign = "center"
                        for (h = 0; h < 24; h++)
                            ctx.fillText(h < 10 ? "0" + h : String(h),
                                         padL + h * bw + bw / 2, height - 4)

                        // legend — four series, so one is always present
                        ctx.textAlign = "left"
                        var lx = padL
                        for (var i = 0; i < stacked.length; i++) {
                            ctx.fillStyle = report.seriesColour(i)
                            ctx.fillRect(lx, 2, 8, 8)
                            ctx.fillStyle = Theme.dim
                            ctx.font = "10px '" + mono + "'"
                            ctx.fillText(stacked[i].label, lx + 12, 10)
                            lx += 18 + ctx.measureText(stacked[i].label).width
                        }
                    }
                }
            }

            // ================= right column: keys + soulmates =================
            ColumnLayout {
                Layout.columnSpan: page.span(4, 12)
                Layout.preferredWidth: page.colWidth(page.span(4, 12))
                Layout.maximumWidth: page.colWidth(page.span(4, 12))
                Layout.fillHeight: true
                spacing: Theme.gap

                Tile {
                    title: "keys"
                    total: report.fmt(report.kind("key").total)
                    Layout.fillHeight: false

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 140

                        Canvas {
                            id: keyPie
                            anchors.left: parent.left
                            width: 140
                            height: 140
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                var rows = (report.breakdowns.key || {}).by_type || []
                                var total = 0
                                for (var i = 0; i < rows.length; i++) total += rows[i].amount
                                var cx = width / 2, cy = height / 2, R = 62, r = 34
                                if (total <= 0) {
                                    ctx.strokeStyle = Theme.line
                                    ctx.lineWidth = R - r
                                    ctx.beginPath()
                                    ctx.arc(cx, cy, (R + r) / 2, 0, Math.PI * 2)
                                    ctx.stroke()
                                    return
                                }
                                var a0 = -Math.PI / 2
                                for (i = 0; i < rows.length; i++) {
                                    var a1 = a0 + (rows[i].amount / total) * Math.PI * 2
                                    ctx.beginPath()
                                    ctx.arc(cx, cy, R, a0, a1)
                                    ctx.arc(cx, cy, r, a1, a0, true)
                                    ctx.closePath()
                                    ctx.fillStyle = report.keyColour[rows[i].id] || Theme.mute
                                    ctx.fill()
                                    ctx.strokeStyle = Theme.surface
                                    ctx.lineWidth = 2
                                    ctx.stroke()
                                    a0 = a1
                                }
                                var lead = rows[0]
                                ctx.textAlign = "center"
                                ctx.fillStyle = Theme.fg
                                ctx.font = "600 20px '" + Theme.monoFamily + "'"
                                ctx.fillText(Math.round(lead.amount / total * 100) + "%", cx, cy + 2)
                                ctx.fillStyle = Theme.mute
                                ctx.font = "9px '" + Theme.monoFamily + "'"
                                ctx.fillText(String(lead.label).toUpperCase(), cx, cy + 16)
                            }
                        }

                        ColumnLayout {
                            anchors.left: keyPie.right
                            anchors.leftMargin: 10
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 5
                            Repeater {
                                model: (report.breakdowns.key || {}).by_type || []
                                RowLayout {
                                    required property var modelData
                                    spacing: 7
                                    Layout.fillWidth: true
                                    Image {
                                        source: MudaeEmoji.keyUrl(modelData.id)
                                        sourceSize.width: 15
                                        sourceSize.height: 15
                                        width: 15; height: 15
                                        fillMode: Image.PreserveAspectFit
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: modelData.label
                                        color: Theme.dim
                                        font.pixelSize: Theme.sizeSmall
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: report.fmt(modelData.amount)
                                        color: Theme.fg
                                        font.family: Theme.monoFamily
                                        font.pixelSize: Theme.sizeSmall
                                    }
                                }
                            }
                        }
                    }
                }

                Tile {
                    title: "new soulmates"
                    subtitle: (report.reportData.soulmates || []).length === 0
                              ? "" : (report.reportData.soulmates || []).length + " today"

                    Label {
                        Layout.fillWidth: true
                        visible: (report.reportData.soulmates || []).length === 0
                        text: "None on this day."
                        color: Theme.mute
                        font.pixelSize: Theme.sizeSmall
                        topPadding: 8
                        bottomPadding: 8
                    }

                    // Five fit; a busy day scrolls rather than pushing every
                    // tile below it down the page.
                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: count === 0 ? 0
                                                : Math.min(count, 5) * 47
                        visible: count > 0
                        clip: true
                        spacing: 5
                        id: soulList
                        model: report.reportData.soulmates || []
                        boundsBehavior: Flickable.StopAtBounds
                        // Without this the wheel reaches the page's ScrollView and
                        // the whole report moves instead of the list.
                        WheelHandler {
                            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                            onWheel: function (event) {
                                var step = event.angleDelta.y / 2
                                soulList.contentY = Math.max(
                                    0, Math.min(soulList.contentHeight - soulList.height,
                                                soulList.contentY - step))
                            }
                        }
                        ScrollBar.vertical: ScrollBar {
                            policy: parent.contentHeight > parent.height
                                    ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                        }
                        delegate: Rectangle {
                            required property var modelData
                            width: ListView.view.width
                            height: 42
                            color: Theme.raised
                            radius: Theme.radiusSm
                            Rectangle {
                                width: 2
                                height: parent.height
                                color: modelData.starwish ? Theme.warn : Theme.accent
                                radius: Theme.radiusSm
                            }

                            RowLayout {
                                id: soulRow
                                anchors.fill: parent
                                anchors.margins: 7
                                anchors.leftMargin: 11
                                spacing: 8
                                ColumnLayout {
                                    spacing: 1
                                    Layout.fillWidth: true
                                    Label {
                                        text: modelData.character
                                        color: Theme.fg
                                        font.pixelSize: Theme.sizeSmall
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        text: modelData.series
                                        color: Theme.mute
                                        font.pixelSize: Theme.sizeMicro
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                }
                                Label {
                                    text: modelData.time
                                    color: Theme.mute
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeMicro
                                }
                            }
                        }
                    }
                }
            }

            // ================= kakera by colour — bubble scatter =================
            Tile {
                Layout.columnSpan: page.span(6, 12)
                Layout.preferredWidth: page.colWidth(page.span(6, 12))
                Layout.maximumWidth: page.colWidth(page.span(6, 12))
                title: "kakera by colour"
                subtitle: {
                    var rows = (report.breakdowns.kakera || {}).by_type || []
                    var clicks = 0
                    for (var i = 0; i < rows.length; i++) clicks += rows[i].count
                    return clicks + " clicks · circle area is the colour's total kakera"
                }

                Item {
                    id: scatterBox
                    Layout.fillWidth: true
                    Layout.preferredHeight: 292

                    readonly property var rows: (report.breakdowns.kakera || {}).by_type || []
                    readonly property int padL: 42
                    readonly property int padR: 26
                    // The topmost bubble sits exactly on the axis maximum, so the
                    // margin has to clear its radius or it renders half cut off.
                    readonly property int padT: 30
                    readonly property int padB: 30
                    readonly property real maxClicks: {
                        var m = 1
                        for (var i = 0; i < rows.length; i++) m = Math.max(m, rows[i].count)
                        return m * 1.12
                    }
                    readonly property real xTop: report.niceCeiling(maxClicks)
                    readonly property real maxTotal: {
                        var m = 1
                        for (var i = 0; i < rows.length; i++) m = Math.max(m, rows[i].amount)
                        return m
                    }
                    function px(clicks) {
                        return padL + (clicks / xTop) * (width - padL - padR)
                    }
                    /*
                        A square-root scale, so the axis starts at a true zero and
                        still separates a 900-kakera purple from a 20,000-kakera
                        red. A plain linear axis would pile every colour but one
                        onto the baseline; a log axis cannot show zero at all.
                    */
                    // The top of the axis is always one of the ticks below, so
                    // no bubble can sit above the highest label. Rounding to a
                    // nearby "nice" number instead left the axis running past
                    // 10k with nothing marking where it ended.
                    readonly property var yTicks: [0, 1000, 2000, 5000, 10000,
                                                   20000, 50000, 100000]
                    readonly property real yTop: {
                        var m = 0
                        for (var i = 0; i < rows.length; i++)
                            m = Math.max(m, rows[i].amount / Math.max(1, rows[i].count))
                        for (var t = 1; t < yTicks.length; t++) {
                            if (m <= yTicks[t])
                                return yTicks[t]
                        }
                        return report.niceCeiling(m)
                    }
                    function py(avg) {
                        var f = Math.sqrt(Math.max(0, avg) / yTop)
                        return padT + (1 - Math.max(0, Math.min(1, f))) * (height - padT - padB)
                    }
                    /*
                        Area, not radius, carries the total — so the radius goes
                        as its square root. The floor is kept small on purpose:
                        a larger one flattens the whole range (a 69x spread in
                        kakera was arriving as a 2.2x spread in radius).
                    */
                    function radius(total) {
                        return 4 + 22 * Math.sqrt(total / maxTotal)
                    }
                    /*
                        Colours cluster tightly in value, so a label placed to the
                        right can land inside the next bubble along. Try the right,
                        and fall back to the left when the tile edge or another
                        bubble is in the way.
                    */
                    function labelGoesLeft(index, labelWidth) {
                        var row = rows[index]
                        var cx = px(row.count)
                        var cy = py(row.amount / Math.max(1, row.count))
                        var r = radius(row.amount)
                        var start = cx + r + 7
                        // Only go left if there is actually room left of the
                        // axis gutter; otherwise the label lands on the ticks.
                        var roomLeft = cx - r - 7 - labelWidth >= padL
                        if (start + labelWidth > width - 2)
                            return roomLeft
                        for (var i = 0; i < rows.length; i++) {
                            if (i === index) continue
                            var ox = px(rows[i].count)
                            var oy = py(rows[i].amount / Math.max(1, rows[i].count))
                            var orad = radius(rows[i].amount)
                            if (Math.abs(cy - oy) > orad + 6) continue
                            if (ox + orad > start && ox - orad < start + labelWidth)
                                return roomLeft
                        }
                        return false
                    }

                    Canvas {
                        id: scatterCanvas
                        anchors.fill: parent
                        onWidthChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            var rows = scatterBox.rows
                            ctx.font = "9px '" + Theme.monoFamily + "'"
                            var ticks = scatterBox.yTicks
                            for (var t = 0; t < ticks.length; t++) {
                                var value = ticks[t]
                                if (value > scatterBox.yTop) continue
                                var y = scatterBox.py(value)
                                ctx.strokeStyle = Theme.line
                                ctx.lineWidth = 1
                                ctx.beginPath()
                                ctx.moveTo(scatterBox.padL, y + 0.5)
                                ctx.lineTo(scatterBox.width - scatterBox.padR, y + 0.5)
                                ctx.stroke()
                                ctx.fillStyle = Theme.mute
                                ctx.textAlign = "right"
                                ctx.fillText(value >= 1000 ? (value / 1000) + "k" : "0",
                                             scatterBox.padL - 6, y + 3)
                            }
                            // x axis: click counts, on the same round steps
                            var xTop = scatterBox.xTop
                            ctx.textAlign = "center"
                            for (var xi = 0; xi <= 4; xi++) {
                                var cvalue = xTop * xi / 4
                                ctx.fillStyle = Theme.mute
                                ctx.fillText(String(Math.round(cvalue)),
                                             scatterBox.px(cvalue),
                                             scatterBox.height - scatterBox.padB + 13)
                            }
                            for (var i = 0; i < rows.length; i++) {
                                var avg = rows[i].amount / Math.max(1, rows[i].count)
                                var cx = scatterBox.px(rows[i].count)
                                var cy = scatterBox.py(avg)
                                var R = scatterBox.radius(rows[i].amount)
                                var hue = report.kakeraColour[rows[i].id] || Theme.mute
                                ctx.beginPath()
                                ctx.arc(cx, cy, R, 0, Math.PI * 2)
                                ctx.fillStyle = Qt.rgba(Qt.color(hue).r, Qt.color(hue).g,
                                                        Qt.color(hue).b, 0.17)
                                ctx.fill()
                                ctx.strokeStyle = hue
                                ctx.lineWidth = 1.5
                                ctx.stroke()
                            }
                            ctx.fillStyle = Theme.dim
                            ctx.textAlign = "center"
                            ctx.fillText("CLICKS", scatterBox.width / 2,
                                         scatterBox.height - 2)
                        }
                    }

                    // Real kakera art on each bubble, positioned by the same scale.
                    Repeater {
                        model: scatterBox.rows
                        Item {
                            required property var modelData
                            required property int index
                            readonly property real avg: modelData.amount / Math.max(1, modelData.count)
                            readonly property real cx: scatterBox.px(modelData.count)
                            readonly property real cy: scatterBox.py(avg)
                            readonly property real rad: scatterBox.radius(modelData.amount)

                            Image {
                                x: parent.cx - parent.rad * 0.45
                                y: parent.cy - parent.rad * 0.45
                                width: parent.rad * 0.9
                                height: parent.rad * 0.9
                                source: MudaeEmoji.kakeraUrl(modelData.id)
                                fillMode: Image.PreserveAspectFit
                                smooth: true
                            }
                            // Beside the bubble, never above or below it: the
                            // colours cluster tightly in value, so stacked labels
                            // collide with each other and with the axis.
                            Column {
                                id: bubbleLabel
                                readonly property bool toLeft:
                                    scatterBox.labelGoesLeft(index, width)
                                x: toLeft ? parent.cx - parent.rad - width - 7
                                          : parent.cx + parent.rad + 7
                                y: parent.cy - height / 2
                                spacing: 0
                                Label {
                                    text: modelData.label
                                    color: Theme.fg
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeSmall
                                }
                                Label {
                                    text: report.fmt(modelData.amount)
                                    color: Theme.mute
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeMicro
                                }
                            }
                        }
                    }
                }
            }

            // ================= kakera source =================
            Tile {
                Layout.columnSpan: page.span(3, 6)
                Layout.preferredWidth: page.colWidth(page.span(3, 6))
                Layout.maximumWidth: page.colWidth(page.span(3, 6))
                title: "source"

                // Clicks and $bku resets are the two that move the day; roll
                // gain and $dk are rounding on top of them.
                Repeater {
                    model: (report.breakdowns.kakera || {}).by_method || []
                    BarRow {
                        required property var modelData
                        required property int index
                        // Not `top`: that name is FINAL on the base type and the
                        // override is silently discarded.
                        readonly property int peak: {
                            var rows = (report.breakdowns.kakera || {}).by_method || []
                            return rows.length ? rows[0].amount : 1
                        }
                        label: modelData.label
                        value: report.fmt(modelData.amount)
                        suffix: Math.round(modelData.amount
                                           / Math.max(1, report.kind("kakera").total) * 100) + "%"
                        extra: report.sourceHasCount(modelData.id)
                               ? modelData.count + "×" : ""
                        fraction: modelData.amount / Math.max(1, peak)
                        barColour: report.seriesColour(index)
                        big: true
                    }
                }

            }

            // ================= daily click budgets =================
            Tile {
                Layout.columnSpan: page.span(3, 6)
                Layout.preferredWidth: page.colWidth(page.span(3, 6))
                Layout.maximumWidth: page.colWidth(page.span(3, 6))
                title: "daily click budgets"
                subtitle: report.scoped ? "in the order they were clicked" : ""

                // Not a tile that hides itself: an empty budgets panel that says
                // why it is empty is the whole point, because otherwise a general
                // report looks like a day where nothing was clicked.
                Label {
                    Layout.fillWidth: true
                    visible: !report.scoped
                    text: (report.tapes.perk8 || {}).note
                          || "Pick one account and one server above."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                    lineHeight: 1.3
                }

                Repeater {
                    model: report.scoped ? [
                        { key: "perk8", name: "Perk 8", kakera: true },
                        { key: "perk9", name: "Perk 9", kakera: false }
                    ] : []
                    ColumnLayout {
                        required property var modelData
                        readonly property var tape: report.tapes[modelData.key] || { slots: [] }
                        readonly property int cap: tape.cap === null || tape.cap === undefined
                                                   ? (tape.slots || []).length : tape.cap
                        Layout.fillWidth: true
                        spacing: 7

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Label {
                                text: Theme.sectionLabel(modelData.name)
                                color: Theme.fg
                                font.pixelSize: Theme.sizeMicro
                                font.weight: Font.DemiBold
                                font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                            }
                            Label {
                                Layout.fillWidth: true
                                text: (tape.slots || []).length + " of " + cap
                                color: Theme.mute
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeMicro
                            }
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 5
                            Repeater {
                                model: Math.max(cap, (tape.slots || []).length)
                                Rectangle {
                                    required property int index
                                    readonly property var slot: (tape.slots || [])[index]
                                    width: 21; height: 21
                                    radius: Theme.radiusPill > 20 ? 11 : Theme.radiusXs
                                    color: slot ? Qt.darker(Theme.surface, 1.1) : "transparent"
                                    border.width: slot ? 0 : 1
                                    border.color: Theme.line
                                    Image {
                                        anchors.fill: parent
                                        anchors.margins: 1
                                        visible: !!parent.slot
                                        source: !parent.slot ? ""
                                                : (modelData.kakera
                                                   ? MudaeEmoji.kakeraUrl(parent.slot.id)
                                                   : MudaeEmoji.sphereUrl(parent.slot.id))
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                    }
                                    ToolTip {
                                        id: slotTip
                                        visible: slotMouse.containsMouse && !!slot
                                        delay: 250
                                        readonly property var into: slot ? (slot.resolved || []) : []
                                        background: Rectangle {
                                            color: Theme.raised
                                            border.width: Theme.borderWidth
                                            border.color: Theme.line
                                            radius: Theme.radiusSm
                                        }
                                        // A transform is worth seeing as spheres,
                                        // not as a list of colour names.
                                        contentItem: RowLayout {
                                            spacing: 5
                                            Image {
                                                source: slot
                                                        ? (modelData.kakera
                                                           ? MudaeEmoji.kakeraUrl(slot.id)
                                                           : MudaeEmoji.sphereUrl(slot.id))
                                                        : ""
                                                sourceSize.width: 18
                                                sourceSize.height: 18
                                                Layout.preferredWidth: 18
                                                Layout.preferredHeight: 18
                                                fillMode: Image.PreserveAspectFit
                                            }
                                            Label {
                                                visible: slotTip.into.length > 0
                                                text: "→"
                                                color: Theme.mute
                                                font.pixelSize: Theme.sizeSmall
                                            }
                                            Repeater {
                                                model: slotTip.into
                                                Image {
                                                    required property var modelData
                                                    source: MudaeEmoji.sphereUrl(modelData)
                                                    sourceSize.width: 18
                                                    sourceSize.height: 18
                                                    Layout.preferredWidth: 18
                                                    Layout.preferredHeight: 18
                                                    fillMode: Image.PreserveAspectFit
                                                }
                                            }
                                            Label {
                                                text: slot ? report.fmt(slot.amount)
                                                             + (modelData.kakera ? "" : " SP") : ""
                                                color: Theme.fg
                                                font.family: Theme.monoFamily
                                                font.pixelSize: Theme.sizeSmall
                                                leftPadding: 3
                                            }
                                        }
                                    }
                                    MouseArea {
                                        id: slotMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ================= spheres — treemap =================
            Tile {
                Layout.columnSpan: page.span(5, 6)
                Layout.preferredWidth: page.colWidth(page.span(5, 6))
                Layout.maximumWidth: page.colWidth(page.span(5, 6))
                title: "spheres"
                subtitle: "by method"
                total: report.fmt(report.kind("sphere").total)
                totalUnit: "SP"

                Item {
                    id: treeBox
                    Layout.fillWidth: true
                    Layout.preferredHeight: 186

                    readonly property var tiles: {
                        var rows = (report.breakdowns.sphere || {}).by_method || []
                        if (rows.length === 0 || width <= 0) return []
                        var items = []
                        for (var i = 0; i < rows.length; i++)
                            items.push({ label: rows[i].label, value: rows[i].amount,
                                         colour: report.seriesColour(i) })
                        return report.squarify(items, width, height)
                    }

                    Repeater {
                        model: treeBox.tiles
                        Rectangle {
                            required property var modelData
                            x: modelData.x + 1
                            y: modelData.y + 1
                            width: Math.max(0, modelData.w - 2)
                            height: Math.max(0, modelData.h - 2)
                            radius: Theme.radiusXs
                            color: modelData.colour
                            opacity: 0.9
                            Label {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.margins: 7
                                // Draw the name only where it fits; the legend
                                // below names every tile, so the smallest one is
                                // never relying on text it cannot hold.
                                visible: parent.width > implicitWidth + 14 && parent.height > 24
                                text: modelData.label
                                color: Theme.bg
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeSmall
                                font.weight: Font.DemiBold
                            }
                            Label {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.margins: 7
                                anchors.topMargin: 23
                                visible: parent.height > 46 && parent.width > 76
                                text: report.fmt(modelData.value) + " SP"
                                color: Qt.rgba(0, 0, 0, 0.62)
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeMicro
                            }
                        }
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 14
                    rowSpacing: 3
                    Repeater {
                        model: (report.breakdowns.sphere || {}).by_method || []
                        RowLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: 7
                            Rectangle {
                                width: 10; height: 10
                                radius: Theme.radiusPill > 20 ? 5 : 2
                                color: report.seriesColour(index)
                            }
                            Label {
                                Layout.fillWidth: true
                                text: modelData.label
                                color: Theme.dim
                                font.pixelSize: Theme.sizeMicro
                                elide: Text.ElideRight
                            }
                            Label {
                                text: report.fmt(modelData.amount)
                                color: Theme.fg
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeMicro
                            }
                        }
                    }
                }
            }

            // ================= minigames — dumbbell =================
            Tile {
                Layout.columnSpan: page.span(7, 12)
                Layout.preferredWidth: page.colWidth(page.span(7, 12))
                Layout.maximumWidth: page.colWidth(page.span(7, 12))
                title: "minigames"
                subtitle: {
                    var b = report.minigames.benchmark || {}
                    // No window yet means no day has had every board record the
                    // uses it spent, so a per-use rate cannot be formed at all
                    // — say that rather than leave the marks silently missing.
                    return b.from ? "SP per use vs the " + b.from + " – " + b.to
                                    + " average"
                                  : "SP per use — waiting on a full day of use counts"
                }
                total: String((report.minigames.boards) || 0)
                totalUnit: "played"

                Label {
                    Layout.fillWidth: true
                    visible: (report.minigames.games || []).length === 0
                    text: "No boards played on this day."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: (report.minigames.games || []).length > 0
                    spacing: 10
                    Item { Layout.preferredWidth: 44 }
                    Label {
                        Layout.fillWidth: true
                        text: Theme.sectionLabel("SP per use")
                        color: Theme.dim
                        font.pixelSize: Theme.sizeMicro
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }
                    Label {
                        Layout.preferredWidth: 46
                        horizontalAlignment: Text.AlignRight
                        text: Theme.sectionLabel("boards")
                        color: Theme.dim
                        font.pixelSize: Theme.sizeMicro
                    }
                    Label {
                        Layout.preferredWidth: 42
                        horizontalAlignment: Text.AlignRight
                        text: Theme.sectionLabel("uses")
                        color: Theme.dim
                        font.pixelSize: Theme.sizeMicro
                    }
                    Label {
                        Layout.preferredWidth: 68
                        horizontalAlignment: Text.AlignRight
                        text: Theme.sectionLabel("earned")
                        color: Theme.dim
                        font.pixelSize: Theme.sizeMicro
                    }
                    Label {
                        Layout.preferredWidth: 52
                        horizontalAlignment: Text.AlignHCenter
                        text: Theme.sectionLabel("won")
                        color: Theme.dim
                        font.pixelSize: Theme.sizeMicro
                    }
                }

                Repeater {
                    model: report.minigames.games || []
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 10

                        Label {
                            Layout.preferredWidth: 44
                            text: modelData.label
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeMedium
                            font.weight: Font.DemiBold
                        }

                        Item {
                            id: track
                            Layout.fillWidth: true
                            Layout.preferredHeight: 30

                            readonly property real scaleTop: report.minigameScaleTop()
                            function at(value) { return (value / scaleTop) * width }

                            readonly property bool better:
                                (modelData.sp_per_use || 0) >= (modelData.benchmark_sp_per_use || 0)
                            readonly property color hue:
                                modelData.delta_pct === null ? Theme.mute
                                : (better ? Theme.good : Theme.bad)

                            Repeater {
                                model: 4
                                Rectangle {
                                    required property int index
                                    x: track.width * index / 4
                                    width: 1
                                    height: track.height
                                    color: Theme.line
                                }
                            }

                            Rectangle {
                                visible: modelData.benchmark_sp_per_use !== null
                                         && modelData.sp_per_use !== null
                                x: Math.min(track.at(modelData.benchmark_sp_per_use || 0),
                                            track.at(modelData.sp_per_use || 0))
                                width: Math.abs(track.at(modelData.sp_per_use || 0)
                                                - track.at(modelData.benchmark_sp_per_use || 0))
                                height: 3
                                radius: 2
                                anchors.verticalCenter: parent.verticalCenter
                                color: track.hue
                            }
                            Rectangle {
                                visible: modelData.benchmark_sp_per_use !== null
                                x: track.at(modelData.benchmark_sp_per_use || 0) - 6
                                width: 12; height: 12; radius: 6
                                anchors.verticalCenter: parent.verticalCenter
                                color: Theme.surface
                                border.width: 2
                                border.color: Theme.mute
                            }
                            Rectangle {
                                visible: modelData.sp_per_use !== null
                                x: track.at(modelData.sp_per_use || 0) - 8
                                width: 16; height: 16; radius: 8
                                anchors.verticalCenter: parent.verticalCenter
                                color: track.hue
                                border.width: 2
                                border.color: Theme.surface
                            }
                            Label {
                                visible: modelData.delta_pct !== null
                                x: track.better
                                   ? Math.min(track.width - width,
                                              track.at(modelData.sp_per_use || 0) + 13)
                                   : Math.max(0, track.at(modelData.sp_per_use || 0) - width - 13)
                                anchors.verticalCenter: parent.verticalCenter
                                text: report.deltaText(modelData.delta_pct)
                                color: track.hue
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeMicro
                                font.weight: Font.DemiBold
                            }
                        }

                        Label {
                            Layout.preferredWidth: 46
                            horizontalAlignment: Text.AlignRight
                            text: String(modelData.boards)
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                        }
                        Label {
                            // A board is one command; a use is one of the day's
                            // allowance it spent. `$ot 5` is one board, five uses.
                            Layout.preferredWidth: 42
                            horizontalAlignment: Text.AlignRight
                            // Null means the rows predate the `uses` field, which
                            // is unknown — not the same as "one per board".
                            text: modelData.uses === null || modelData.uses === undefined
                                  ? "–" : String(modelData.uses)
                            color: Theme.dim
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                        }
                        Label {
                            Layout.preferredWidth: 68
                            horizontalAlignment: Text.AlignRight
                            text: report.fmt(modelData.sp)
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                        }
                        Label {
                            Layout.preferredWidth: 52
                            horizontalAlignment: Text.AlignHCenter
                            // $ot and $oh have no win condition, so a rate for
                            // them would be an invented statistic — left blank
                            // rather than explained on every row.
                            text: modelData.has_win_state
                                  ? modelData.won + "/" + modelData.boards
                                  : "–"
                            color: modelData.has_win_state ? Theme.good : Theme.mute
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: (report.minigames.games || []).length > 0
                             && report.minigamesHaveRate()
                    spacing: 10
                    Item { Layout.preferredWidth: 44 }
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 13
                        Repeater {
                            model: 5
                            Label {
                                required property int index
                                readonly property real value:
                                    report.minigameScaleTop() * index / 4
                                x: parent.width * index / 4
                                   - (index === 0 ? 0 : (index === 4 ? width : width / 2))
                                text: value >= 1000
                                      ? (value / 1000).toFixed(1) + "k"
                                      : String(Math.round(value))
                                color: Theme.mute
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeMicro
                            }
                        }
                    }
                    Item { Layout.preferredWidth: 46 }
                    Item { Layout.preferredWidth: 42 }
                    Item { Layout.preferredWidth: 68 }
                    Item { Layout.preferredWidth: 52 }
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: (report.minigames.games || []).length > 0
                             && report.minigamesHaveRate()
                    spacing: 7
                    Item { Layout.preferredWidth: 44 }
                    Rectangle {
                        width: 11; height: 11; radius: 6
                        color: Theme.surface
                        border.width: 2
                        border.color: Theme.mute
                    }
                    Label {
                        text: "window average"
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                    }
                    Rectangle {
                        width: 12; height: 12; radius: 6
                        color: Theme.mute
                    }
                    Label {
                        text: "this day"
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                    }
                    Item { Layout.fillWidth: true }
                }
            }
        }
    }

    /*
        Squarified treemap. Rectangles keep an aspect ratio close to 1, which is
        what makes the areas comparable by eye; a naive slice-and-dice makes the
        small entries into slivers nobody can judge.
    */
    function squarify(items, boxW, boxH) {
        var out = []
        var rest = items.slice().sort(function (a, b) { return b.value - a.value })
        var rx = 0, ry = 0, rw = boxW, rh = boxH, i = 0

        function sumFrom(k) {
            var total = 0
            for (var n = k; n < rest.length; n++) total += rest[n].value
            return total
        }
        function worst(row, len, scale) {
            var sum = 0, mx = 0, mn = Infinity
            for (var n = 0; n < row.length; n++) {
                sum += row[n].value
                mx = Math.max(mx, row[n].value)
                mn = Math.min(mn, row[n].value)
            }
            sum *= scale; mx *= scale; mn *= scale
            if (sum <= 0 || mn <= 0) return Infinity
            return Math.max(len * len * mx / (sum * sum), sum * sum / (len * len * mn))
        }

        while (i < rest.length && rw > 0.5 && rh > 0.5) {
            var vertical = rw >= rh
            var len = vertical ? rh : rw
            var remaining = sumFrom(i)
            if (remaining <= 0) break
            var scale = (rw * rh) / remaining
            var row = [], best = Infinity, j = i
            while (j < rest.length) {
                var candidate = row.concat([rest[j]])
                var score = worst(candidate, len, scale)
                if (row.length === 0 || score <= best) { row = candidate; best = score; j++ }
                else break
            }
            var rowSum = 0
            for (var n = 0; n < row.length; n++) rowSum += row[n].value
            var thick = (rowSum * scale) / len
            var cursor = vertical ? ry : rx
            for (n = 0; n < row.length; n++) {
                var seg = (row[n].value * scale) / thick
                out.push({
                    label: row[n].label, value: row[n].value, colour: row[n].colour,
                    x: vertical ? rx : cursor,
                    y: vertical ? cursor : ry,
                    w: vertical ? thick : seg,
                    h: vertical ? seg : thick
                })
                cursor += seg
            }
            if (vertical) { rx += thick; rw -= thick } else { ry += thick; rh -= thick }
            i = j
        }
        return out
    }
}
