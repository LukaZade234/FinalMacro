import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Alts — accounts that supplement the main.

    **Setup**: the alts in turn order on the left (drag to reorder; the order
    decides which alt takes a trigger first, the same for every account), and
    the selected alt's tier and three parts on the right. Picking a tier fills
    all three parts; changing any part afterwards makes it Custom. The tier is
    worked out from the parts (`macro/alt_rules.py`), never stored on its own.

    **Ledger**: Pass to main — fetch an alt's kakera, spheres and top
    characters, then give what is above each keep amount (or picked
    characters) to the main — and this session's transfers.

    An account becomes an alt by setting its type to Alt on the Accounts page.
*/
Item {
    id: root
    clip: true

    property int section: 0
    property var altsData: ({ main: {}, alts: [], presets: [], alts_on: false, running: false })
    property string selectedId: ""
    property int dragFrom: -1
    property int dragTo: -1

    readonly property var selected: {
        for (var i = 0; i < altsData.alts.length; i++)
            if (altsData.alts[i].id === selectedId) return altsData.alts[i]
        return altsData.alts.length ? altsData.alts[0] : null
    }
    readonly property var rules: selected ? selected.rules : null

    // ---- Ledger › Pass to main ----
    property var passData: ({ connected: false, alts: [], transfers: [], ledger: { day: "", rows: [] } })
    readonly property var ledgerRows: passData.ledger ? passData.ledger.rows : []

    // Sum one ledger counter over every alt, for "today" or "week".
    function ledgerTotal(span, key) {
        var n = 0
        for (var i = 0; i < ledgerRows.length; i++)
            n += Number((ledgerRows[i][span] || {})[key] || 0)
        return n
    }
    function ledgerPending() {
        var n = 0
        for (var i = 0; i < ledgerRows.length; i++) n += ledgerRows[i].pending.length
        return n
    }
    property string passAltId: ""
    property var keepEdits: ({})     // "<alt id>:kakera" → keep typed this visit
    property var picks: ({})         // "<alt id>" → { name: true }
    readonly property var passAlt: {
        var list = passData.alts
        for (var i = 0; i < list.length; i++)
            if (list[i].id === passAltId) return list[i]
        return list.length ? list[0] : null
    }
    readonly property string passBusy: passAlt ? passAlt.busy : ""

    function ovValue(v) {
        if (v === true) return "on"
        if (v === false) return "off"
        if (Array.isArray(v)) return v.join(" ")
        return String(v)
    }
    function timeOf(iso) {
        if (!iso) return ""
        var t = String(iso).indexOf("T")
        return t >= 0 ? String(iso).substr(t + 1, 5) + " UTC" : String(iso)
    }
    // One row per sheet for the selected alt's Sheets card.
    function sheetRows(sh) {
        if (!sh) return []
        var b = sh.bonus || {}, at = sh.read_at || {}
        var bonusOk = sh.ready
        var rows = [{
            cmd: "$bonus", required: true, ok: bonusOk,
            text: bonusOk
                ? "read " + timeOf(at.bonus) + " · click " + (b.power_cost !== null && b.power_cost !== undefined ? b.power_cost + "%" : "30% (default)")
                  + " · max power " + (b.power_max || "—") + "%" + " · $dk every " + (b.dk_cooldown || "—")
                  + (b.rt_cooldown ? " · $rt every " + b.rt_cooldown : "")
                : "not read — the alt takes no trigger until it is (passing by hand still works)"
        }]
        var shopOk = !!at.shop
        rows.push({ cmd: "$shop", required: false, ok: shopOk,
            text: shopOk ? "read " + timeOf(at.shop) + (sh.shop && sh.shop.perk9_click_max ? " · perk-9 cap " + sh.shop.perk9_click_max : "")
                         : "not read — needed once the alt rolls for sphere buttons" })
        var ovOk = !!at.ov
        var diffs = sh.ov_diffs ? sh.ov_diffs.length : 0
        rows.push({ cmd: "$ov", required: false, ok: ovOk && diffs === 0 && !!sh.main_ov_read,
            text: !ovOk ? "not read — can't check the alt's roll display settings"
                : (!sh.main_ov_read ? "read " + timeOf(at.ov) + " · the main's $ov isn't read (Mudae page), nothing to compare with"
                : diffs ? "read " + timeOf(at.ov) + " · " + diffs + " roll display setting" + (diffs > 1 ? "s differ" : " differs") + " from the main:"
                         : "read " + timeOf(at.ov) + " · roll display matches the main") })
        return rows
    }

    function reloadPass() {
        try { passData = JSON.parse(App.altPassJson()) } catch (e) { }
    }
    function fmt(n) { return Number(n).toLocaleString(Qt.locale("en_US"), "f", 0) }
    function keepFor(kind) {
        if (!passAlt) return 0
        var k = passAlt.id + ":" + kind
        if (keepEdits[k] !== undefined) return keepEdits[k]
        return kind === "kakera" ? passAlt.kakera_keep : passAlt.spheres_keep
    }
    function setKeep(kind, v) {
        var e = Object.assign({}, keepEdits)
        e[passAlt.id + ":" + kind] = Math.max(0, v)
        keepEdits = e
    }
    function toSend(kind) {
        if (!passAlt) return 0
        var stock = kind === "kakera" ? passAlt.kakera_stock : passAlt.sphere_stock
        if (stock === null || stock === undefined) return 0
        return Math.max(0, stock - keepFor(kind))
    }
    function isPicked(name) { return !!(passAlt && picks[passAlt.id] && picks[passAlt.id][name]) }
    function togglePick(name) {
        var all = Object.assign({}, picks)
        var mine = Object.assign({}, all[passAlt.id] || {})
        if (mine[name]) delete mine[name]; else mine[name] = true
        all[passAlt.id] = mine
        picks = all
    }
    function pickAll() {
        var all = Object.assign({}, picks)
        var mine = {}
        for (var i = 0; i < passAlt.harem.length; i++) mine[passAlt.harem[i].name] = true
        all[passAlt.id] = mine
        picks = all
    }
    // Only names still in the alt's list: a character given away drops out.
    function pickedNames() {
        if (!passAlt || !picks[passAlt.id]) return []
        var out = []
        for (var i = 0; i < passAlt.harem.length; i++)
            if (picks[passAlt.id][passAlt.harem[i].name]) out.push(passAlt.harem[i].name)
        return out
    }

    function reload() {
        try { altsData = JSON.parse(App.altsJson()) } catch (e) { }
        if (!selected && altsData.alts.length) selectedId = altsData.alts[0].id
    }

    // Change one field of one part and save the whole rule set.
    function setPart(part, key, value) {
        if (!selected) return
        var r = JSON.parse(JSON.stringify(selected.rules))
        r[part][key] = value
        App.setAltRules(selected.id, JSON.stringify(r))
    }

    function toggleIn(part, key, value) {
        if (!rules) return
        var list = rules[part][key].slice()
        var i = list.indexOf(value)
        if (i >= 0) list.splice(i, 1); else list.push(value)
        setPart(part, key, list)
    }

    readonly property var tierCards: [
        { id: "support", name: "Support", note: "bank",
          text: "Doesn't roll. Spare claims and spare power on the main's rolls; passes everything to the main." },
        { id: "shared", name: "Shared", note: "mostly main",
          text: "Helps the main first, then rolls after the main's batch and keeps its own claims. Kakera and spheres go to the main." },
        { id: "independent", name: "Independent", note: "own",
          text: "Rolls with its own preset and keeps what it earns. Helps the main only when it has nothing of its own to do." }
    ]

    readonly property var passModes: [
        { v: "never", t: "never" }, { v: "session", t: "end of session" },
        { v: "daily", t: "once a day" }, { v: "above", t: "above reserve" }
    ]

    // Same artwork and order as Presets › Kakera. Purple is left out: it costs
    // no power, so the main takes it itself and an alt never needs to.
    readonly property var kakeraTypes: [
        { id: "kakera",  label: "Blue",    color: "#7aa2f7", icon: "../assets/kakera/Kakera.png"   },
        { id: "kakeraT", label: "Teal",    color: "#2ac3de", icon: "../assets/kakera/KakeraT.png"  },
        { id: "kakeraG", label: "Green",   color: "#9ece6a", icon: "../assets/kakera/KakeraG.png"  },
        { id: "kakeraY", label: "Yellow",  color: "#e0af68", icon: "../assets/kakera/KakeraY.png"  },
        { id: "kakeraO", label: "Orange",  color: "#ff9e64", icon: "../assets/kakera/KakeraO.png"  },
        { id: "kakeraR", label: "Red",     color: "#f7768e", icon: "../assets/kakera/KakeraR.png"  },
        { id: "kakeraW", label: "Rainbow", color: "#c0caf5", icon: "../assets/kakera/KakeraW.png"  },
        { id: "kakeraL", label: "Light",   color: "#bb9af7", icon: "../assets/kakera/KakeraL.png"  },
        { id: "kakeraD", label: "Dark",    color: "#3b4252", icon: "../assets/kakera/KakeraD.webp" },
        { id: "kakeraC", label: "Chaos",   color: "#ff5fa2", icon: "../assets/kakera/KakeraC.webp" }
    ]

    Connections {
        target: App
        function onAltsChanged() { root.reload() }
        function onConfigChanged() { root.reload() }
        function onAltsLiveChanged() { root.reloadPass(); root.reload() }
        function onConnectedChanged() { root.reloadPass() }
    }
    Component.onCompleted: { reload(); reloadPass() }

    // ---- small building blocks -------------------------------------------

    component Label: Text {
        color: Theme.fg
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeSmall
        wrapMode: Text.WordWrap
    }

    component Hint: Text {
        Layout.fillWidth: true
        color: Theme.mute
        font.family: Theme.fontFamily
        font.pixelSize: Theme.sizeTiny
        wrapMode: Text.WordWrap
        lineHeight: 1.15
    }

    // One choice out of a few, as a joined row of buttons.
    component Seg: Flow {
        id: seg
        property var options: []
        property string value: ""
        signal picked(string v)
        Layout.fillWidth: true
        spacing: 0
        Repeater {
            model: seg.options
            delegate: Rectangle {
                required property var modelData
                readonly property bool on: seg.value === modelData.v
                width: segText.implicitWidth + 18
                height: 24
                color: on ? Theme.raised : (segMouse.containsMouse ? Theme.hover : Theme.bg)
                border.color: Theme.line
                border.width: Theme.borderWidth
                Rectangle {
                    visible: parent.on
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    height: 2
                    color: Theme.accent2
                }
                Text {
                    id: segText
                    anchors.centerIn: parent
                    text: modelData.t
                    color: parent.on ? Theme.fg : Theme.dim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.sizeTiny
                    font.weight: parent.on ? Font.DemiBold : Font.Normal
                }
                MouseArea {
                    id: segMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: seg.picked(modelData.v)
                }
            }
        }
    }

    // A labelled on/off line.
    component SwitchRow: RowLayout {
        id: sw
        property string text: ""
        property bool checked: false
        signal toggled(bool on)
        Layout.fillWidth: true
        Label { text: sw.text; Layout.fillWidth: true }
        ThemedSwitch {
            showLabel: false
            checked: sw.checked
            onToggled: sw.toggled(checked)
        }
    }

    // Toggle chips (kakera colours, minigames).
    component Chips: Flow {
        id: chips
        property var options: []
        property var values: []
        signal flipped(string v)
        Layout.fillWidth: true
        spacing: 4
        Repeater {
            model: chips.options
            delegate: Rectangle {
                required property var modelData
                readonly property bool on: chips.values.indexOf(modelData.v) >= 0
                readonly property color tone: modelData.c ? modelData.c : Theme.good
                width: chipText.implicitWidth + 12
                height: 20
                radius: Theme.radiusSm
                color: on ? Qt.rgba(tone.r, tone.g, tone.b, 0.16) : "transparent"
                border.color: on ? tone : Theme.line
                border.width: 1
                Text {
                    id: chipText
                    anchors.centerIn: parent
                    text: modelData.t
                    color: parent.on ? Theme.fg : Theme.mute
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.sizeTiny
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: chips.flipped(modelData.v)
                }
            }
        }
    }

    component Divider: Rectangle {
        Layout.fillWidth: true
        Layout.topMargin: 2
        Layout.bottomMargin: 2
        height: 1
        color: Theme.line
    }

    component ReserveField: RowLayout {
        id: rf
        property string unit: ""
        property int value: 0
        property string command: ""
        signal changed(int v)
        Layout.fillWidth: true
        spacing: 6
        Hint { text: "keep"; Layout.fillWidth: false }
        ThemedTextField {
            Layout.preferredWidth: 96
            text: String(rf.value)
            validator: IntValidator { bottom: 0 }
            horizontalAlignment: Text.AlignRight
            onEditingFinished: rf.changed(parseInt(text || "0"))
        }
        Hint { text: rf.unit + " · " + rf.command }
    }

    // One currency in Pass to main: stock, keep, what goes out, and the button.
    component StockColumn: Rectangle {
        id: sc
        property string title: ""
        property string icon: ""
        property string unit: ""
        property string command: ""
        property var stock: null
        property int keep: 0
        readonly property bool known: stock !== null && stock !== undefined
        readonly property int sends: known ? Math.max(0, stock - keep) : 0
        signal keepEdited(int v)
        signal give()
        Layout.fillWidth: true
        Layout.preferredWidth: 3
        Layout.alignment: Qt.AlignTop
        implicitHeight: scCol.implicitHeight + 20
        radius: Theme.radiusSm
        color: Theme.bg
        border.color: Theme.line
        border.width: Theme.borderWidth

        ColumnLayout {
            id: scCol
            anchors.fill: parent
            anchors.margins: 10
            spacing: 8
            RowLayout {
                spacing: 6
                Image { source: sc.icon; sourceSize: Qt.size(16, 16); Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
                Label { text: sc.title; font.weight: Font.DemiBold; Layout.fillWidth: true }
                Hint { Layout.fillWidth: false; text: "from :" + (sc.unit === "ka" ? "kakera" : "sp") + ": stock" }
            }
            Text {
                text: sc.known ? root.fmt(sc.stock) + " " + sc.unit : "—"
                color: Theme.fg
                font.family: Theme.fontFamily
                font.pixelSize: Theme.sizeXLarge
                font.weight: Font.DemiBold
            }
            RowLayout {
                spacing: 6
                Hint { text: "keep"; Layout.fillWidth: false; Layout.alignment: Qt.AlignVCenter }
                ThemedTextField {
                    id: keepField
                    Layout.preferredWidth: 110
                    text: String(sc.keep)
                    validator: IntValidator { bottom: 0 }
                    horizontalAlignment: Text.AlignRight
                    onEditingFinished: sc.keepEdited(parseInt(text || "0"))
                }
                ThemedButton {
                    text: "give all"
                    onClicked: { keepField.text = "0"; sc.keepEdited(0) }
                }
            }
            Hint {
                text: !sc.known ? "Fetch to read the stock."
                    : (sc.sends > 0 ? "sends " + root.fmt(sc.sends) + " " + sc.unit : "nothing (stock ≤ keep)")
                color: sc.sends > 0 ? Theme.fg : Theme.mute
            }
            Text {
                Layout.fillWidth: true
                visible: sc.sends > 0
                text: "$" + sc.command + " <@" + (root.passData.main_id || "main") + "> " + sc.sends
                color: Theme.dim
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeTiny
                wrapMode: Text.WrapAnywhere
            }
            ThemedButton {
                Layout.fillWidth: true
                text: "Give " + sc.title.toLowerCase()
                enabled: root.passBusy === "" && sc.sends > 0
                onClicked: sc.give()
            }
        }
    }

    // ---- page ------------------------------------------------------------

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: ["Setup", "Ledger"]
                delegate: PresetSectionTab {
                    required property string modelData
                    required property int index
                    text: modelData
                    stretch: false
                    tabActive: root.section === index
                    onClicked: root.section = index
                }
            }

            Item { Layout.fillWidth: true }

            Hint {
                Layout.fillWidth: false
                text: root.altsData.main.name
                    ? "alts serve " + root.altsData.main.name + " in the Run channel"
                    : "pick the main on the Run page"
            }
            Label { text: "Alts"; color: Theme.dim }
            ThemedSwitch {
                showLabel: true
                checked: root.altsData.alts_on
                onToggled: App.setAltsOn(checked)
            }
        }

        // ================= Setup =================
        RowLayout {
            visible: root.section === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap

            PanelCard {
                title: "Turn order"
                Layout.preferredWidth: 250
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop

                Hint {
                    visible: root.altsData.alts.length === 0
                    text: "No alts yet. Set an account's type to Alt on the Accounts page and it appears here."
                }

                Repeater {
                    id: altList
                    model: root.altsData.alts
                    delegate: Rectangle {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool current: root.selected && root.selected.id === modelData.id
                        Layout.fillWidth: true
                        implicitHeight: 46
                        radius: Theme.radiusSm
                        color: current ? Theme.raised : (rowMouse.containsMouse ? Theme.hover : "transparent")

                        Rectangle {
                            visible: root.dragFrom >= 0 && root.dragTo === row.index && root.dragFrom !== row.index
                            anchors.left: parent.left; anchors.right: parent.right
                            y: root.dragTo < root.dragFrom ? 0 : parent.height - 2
                            height: 2
                            color: Theme.accent2
                        }
                        Rectangle {
                            visible: row.current
                            width: 2; height: parent.height
                            color: Theme.accent2
                        }

                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: root.selectedId = row.modelData.id
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 6
                            anchors.rightMargin: 6
                            spacing: 7

                            // Grip — drag to change the turn order.
                            Item {
                                Layout.preferredWidth: 12
                                Layout.fillHeight: true
                                Column {
                                    anchors.centerIn: parent
                                    spacing: 2
                                    Repeater {
                                        model: 3
                                        Rectangle { width: 10; height: 2; radius: 1; color: Theme.mute }
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.SizeVerCursor
                                    preventStealing: true
                                    onPressed: { root.dragFrom = row.index; root.dragTo = row.index }
                                    onPositionChanged: function(mouse) {
                                        var y = mapToItem(row.parent, mouse.x, mouse.y).y
                                        var step = row.height + 4
                                        root.dragTo = Math.max(0, Math.min(root.altsData.alts.length - 1,
                                                                           Math.floor((y - altList.itemAt(0).y) / step)))
                                    }
                                    onReleased: {
                                        if (root.dragTo !== root.dragFrom && root.dragFrom >= 0)
                                            App.moveAlt(root.altsData.alts[root.dragFrom].id, root.dragTo)
                                        root.dragFrom = -1
                                        root.dragTo = -1
                                    }
                                }
                            }

                            Rectangle {
                                Layout.preferredWidth: 17
                                Layout.preferredHeight: 17
                                radius: 3
                                color: Theme.bg
                                border.color: Theme.line
                                Text {
                                    anchors.centerIn: parent
                                    text: row.modelData.turn
                                    color: Theme.dim
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeMicro
                                    font.weight: Font.DemiBold
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Label {
                                    Layout.fillWidth: true
                                    text: row.modelData.name
                                    elide: Text.ElideRight
                                    wrapMode: Text.NoWrap
                                    font.weight: Font.DemiBold
                                }
                                Hint {
                                    text: row.modelData.is_main ? "is the Run account — acts as the main"
                                        : !row.modelData.has_token ? "no token — can't connect"
                                        : row.modelData.tier + (row.modelData.rules.enabled ? "" : " · off")
                                    color: (row.modelData.is_main || !row.modelData.has_token) ? Theme.warn : Theme.mute
                                    elide: Text.ElideRight
                                    wrapMode: Text.NoWrap
                                }
                            }

                            ThemedSwitch {
                                showLabel: false
                                checked: row.modelData.rules.enabled
                                onToggled: App.setAltEnabled(row.modelData.id, checked)
                            }
                        }
                    }
                }

                Divider { Layout.topMargin: 8 }
                Hint {
                    text: "When a trigger can go to an alt — a spare claim, a kakera button, a force-divorce claim — the first eligible alt in this order takes it, and no other alt acts on it. Only the main ever rolls $us."
                }
            }

            ScrollablePage {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: root.selected !== null
                contentSpacing: Theme.gap

                // ---- Sheets: the gate before any automatic use ----
                PanelCard {
                    id: sheetsCard
                    Layout.fillWidth: true
                    readonly property var sh: root.selected ? root.selected.sheets : null
                    readonly property string busy: root.selected ? root.selected.busy : ""
                    title: root.selected ? "Sheets · " + root.selected.name : "Sheets"
                    headerAccessory: ThemedButton {
                        text: sheetsCard.busy === "sheets" ? "Fetching…" : "Fetch $bonus · $shop · $ov"
                        loading: sheetsCard.busy === "sheets"
                        enabled: root.selected !== null && sheetsCard.busy === "" && root.selected.has_token
                        onClicked: App.fetchAltSheets(root.selected.id)
                    }

                    Repeater {
                        model: root.sheetRows(sheetsCard.sh)
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 10
                            Text {
                                Layout.preferredWidth: 58
                                text: modelData.cmd
                                color: Theme.fg
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeSmall
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.preferredWidth: 14
                                text: modelData.ok ? "✓" : (modelData.required ? "✕" : "·")
                                color: modelData.ok ? Theme.good : (modelData.required ? Theme.warn : Theme.mute)
                                font.pixelSize: Theme.sizeSmall
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.text
                                color: modelData.ok ? Theme.dim : (modelData.required ? Theme.warn : Theme.mute)
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.sizeTiny
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    Repeater {
                        model: sheetsCard.sh ? sheetsCard.sh.ov_diffs : []
                        delegate: Hint {
                            required property var modelData
                            Layout.leftMargin: 82
                            text: "· " + modelData.label + ": main " + root.ovValue(modelData.main)
                                  + ", alt " + root.ovValue(modelData.alt) + " — " + modelData.why
                            color: Theme.warn
                        }
                    }

                    Hint {
                        text: root.selected && root.selected.note ? root.selected.note
                            : (sheetsCard.sh && sheetsCard.sh.channel
                               ? "For " + sheetsCard.sh.channel + ". Read on the alt's own connection while it runs, or a short one of its own otherwise. On the main's rolls an alt pays its full click cost: the keys there aren't its soulkeys."
                               : "Pick the Run channel first: sheets are per server.")
                    }
                }

                PanelCard {
                    Layout.fillWidth: true
                    title: root.selected ? "Tier · " + root.selected.name : "Tier"

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width > 760 ? 4 : 2
                        columnSpacing: 8
                        rowSpacing: 8

                        Repeater {
                            model: root.tierCards
                            delegate: Rectangle {
                                required property var modelData
                                readonly property bool on: root.selected && root.selected.tier === modelData.id
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: tierCol.implicitHeight + 20
                                radius: Theme.radiusMd
                                color: tierMouse.containsMouse && !on ? Theme.hover : Theme.bg
                                border.color: on ? Theme.accent2 : Theme.line
                                border.width: on ? 2 : 1
                                ColumnLayout {
                                    id: tierCol
                                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                    anchors.margins: 10
                                    spacing: 4
                                    RowLayout {
                                        Label { text: modelData.name; font.weight: Font.DemiBold }
                                        Item { Layout.fillWidth: true }
                                        Hint { text: modelData.note; Layout.fillWidth: false }
                                    }
                                    Hint { text: modelData.text; color: Theme.dim }
                                }
                                MouseArea {
                                    id: tierMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: App.setAltTier(root.selected.id, modelData.id)
                                }
                            }
                        }

                        Rectangle {
                            readonly property bool on: root.selected && root.selected.tier === "custom"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.preferredHeight: customCol.implicitHeight + 20
                            radius: Theme.radiusMd
                            color: Theme.bg
                            opacity: on ? 1 : 0.55
                            border.color: on ? Theme.accent2 : Theme.line
                            border.width: on ? 2 : 1
                            ColumnLayout {
                                id: customCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 10
                                spacing: 4
                                Label { text: "Custom"; font.weight: Font.DemiBold }
                                Hint { text: "Any part changed after picking a tier. Pick a tier again to reset all three parts."; color: Theme.dim }
                            }
                        }
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: width > 1050 ? 3 : 1
                    columnSpacing: Theme.gap
                    rowSpacing: Theme.gap
                    visible: root.rules !== null

                    // ---- Claims ----
                    PanelCard {
                        title: "Claims"
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop

                        Label { text: "Whose rolls" }
                        Seg {
                            options: [{ v: "main", t: "main's only" }, { v: "both", t: "main's, then own" }, { v: "own", t: "own, help when idle" }]
                            value: root.rules ? root.rules.claims.source : ""
                            onPicked: function(v) { root.setPart("claims", "source", v) }
                        }
                        Hint { text: "On the main's rolls the alt claims only what the main's preset would claim but has no slot for, and always gives it to the main. The main gets first pick." }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            enabled: root.rules && root.rules.claims.source !== "main"
                            opacity: enabled ? 1 : 0.4
                            Divider {}
                            Label { text: "On its own rolls" }
                            Seg {
                                options: [{ v: "preset", t: "follow a preset" }, { v: "first", t: "first unclaimed" }]
                                value: root.rules ? root.rules.claims.own_policy : ""
                                onPicked: function(v) { root.setPart("claims", "own_policy", v) }
                            }
                            ThemedComboBox {
                                Layout.fillWidth: true
                                visible: root.rules && root.rules.claims.own_policy === "preset"
                                model: ["(main's preset)"].concat(root.altsData.presets)
                                currentIndex: root.rules ? Math.max(0, root.altsData.presets.indexOf(root.rules.claims.own_preset_id) + 1) : 0
                                onActivated: function(i) { root.setPart("claims", "own_preset_id", i === 0 ? "" : root.altsData.presets[i - 1]) }
                            }
                            Label { text: "Then" }
                            Seg {
                                options: [{ v: "give", t: "give to main" }, { v: "keep", t: "keep" }]
                                value: root.rules ? root.rules.claims.own_after : ""
                                onPicked: function(v) { root.setPart("claims", "own_after", v) }
                            }
                        }

                        Divider {}
                        SwitchRow {
                            text: "Extra force-divorce cycle"
                            checked: root.rules ? root.rules.claims.force_divorce : false
                            onToggled: function(on) { root.setPart("claims", "force_divorce", on) }
                        }
                        Hint { text: "Main divorces → this alt claims (Emerald IV payout; the keys stay on the character) → gives it back → the main's own cycle. Alts take this in turn order; the character always ends with the main." }
                        SwitchRow {
                            text: "Spend the alt's $rt too"
                            checked: root.rules ? root.rules.claims.spend_rt : false
                            onToggled: function(on) { root.setPart("claims", "spend_rt", on) }
                        }
                        Divider {}
                        SwitchRow {
                            text: "Snipe guard"
                            checked: root.rules ? root.rules.claims.snipe_guard : false
                            onToggled: function(on) { root.setPart("claims", "snipe_guard", on) }
                        }
                        Hint { text: "Also claim the main's wishes on other players' rolls while the main has no claim." }
                    }

                    // ---- Kakera ----
                    PanelCard {
                        title: "Kakera"
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop

                        SwitchRow {
                            text: "On the main's rolls"
                            checked: root.rules ? root.rules.kakera.on_main_rolls : false
                            onToggled: function(on) { root.setPart("kakera", "on_main_rolls", on) }
                        }
                        Hint { text: "Only after the main is out of power. Never perk-8 kakera (they pay the roller) and no sphere buttons." }
                        ColorChipPicker {
                            enabled: root.rules && root.rules.kakera.on_main_rolls
                            opacity: enabled ? 1 : 0.4
                            title: "Colours worth the alt's power"
                            controlled: true
                            options: root.kakeraTypes
                            selected: root.rules ? root.rules.kakera.main_roll_types : []
                            onSelectionChanged: function(ids) { root.setPart("kakera", "main_roll_types", ids) }
                        }
                        Divider {}
                        SwitchRow {
                            text: "On its own rolls"
                            checked: root.rules ? root.rules.kakera.on_own_rolls : false
                            onToggled: function(on) { root.setPart("kakera", "on_own_rolls", on) }
                        }
                        Hint { text: "Uses the kakera rules in the alt's own preset." }
                        Divider {}
                        SwitchRow {
                            text: "$dk when power runs out"
                            checked: root.rules ? root.rules.kakera.use_dk : false
                            onToggled: function(on) { root.setPart("kakera", "use_dk", on) }
                        }
                        Label { text: "Auto $kl" }
                        Seg {
                            options: [{ v: "off", t: "off" }, { v: "daily", t: "once a day" }, { v: "hourly", t: "every hour" }]
                            value: root.rules ? root.rules.kakera.auto_kl : ""
                            onPicked: function(v) { root.setPart("kakera", "auto_kl", v) }
                        }
                        Divider {}
                        Label { text: "Pass kakera to main" }
                        Seg {
                            options: root.passModes
                            value: root.rules ? root.rules.kakera.pass_mode : ""
                            onPicked: function(v) { root.setPart("kakera", "pass_mode", v) }
                        }
                        ReserveField {
                            enabled: root.rules && root.rules.kakera.pass_mode !== "never"
                            opacity: enabled ? 1 : 0.4
                            unit: "ka"
                            command: "$givek @main N, alt types y"
                            value: root.rules ? root.rules.kakera.keep : 0
                            onChanged: function(v) { root.setPart("kakera", "keep", v) }
                        }
                    }

                    // ---- Spheres ----
                    PanelCard {
                        title: "Spheres"
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop

                        SwitchRow {
                            text: "Daily minigames at the reset"
                            checked: root.rules ? root.rules.spheres.minigames : false
                            onToggled: function(on) { root.setPart("spheres", "minigames", on) }
                        }
                        Chips {
                            enabled: root.rules && root.rules.spheres.minigames
                            opacity: enabled ? 1 : 0.4
                            options: [{ v: "oh", t: "$oh" }, { v: "oc", t: "$oc" }, { v: "oq", t: "$oq" }, { v: "ot", t: "$ot" }]
                            values: root.rules ? root.rules.spheres.games : []
                            onFlipped: function(v) { root.toggleIn("spheres", "games", v) }
                        }
                        Hint { text: "Same solvers as the main, on the alt's own connection, one account at a time." }
                        Divider {}
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            enabled: root.rules && root.rules.claims.source !== "main"
                            opacity: enabled ? 1 : 0.4
                            Label { text: "Sphere buttons on its own rolls" }
                            Seg {
                                options: [{ v: "off", t: "off" }, { v: "perk9", t: "perk-9 budget" }, { v: "twenty", t: "20 clicks, then stop" }]
                                value: root.rules ? root.rules.spheres.buttons : ""
                                onPicked: function(v) { root.setPart("spheres", "buttons", v) }
                            }
                            Hint { text: "“20 clicks, then stop” rolls only until the day's 20 sphere clicks are spent, then stops rolling until the reset." }
                        }
                        Divider {}
                        Label { text: "Pass spheres to main" }
                        Seg {
                            options: root.passModes
                            value: root.rules ? root.rules.spheres.pass_mode : ""
                            onPicked: function(v) { root.setPart("spheres", "pass_mode", v) }
                        }
                        ReserveField {
                            enabled: root.rules && root.rules.spheres.pass_mode !== "never"
                            opacity: enabled ? 1 : 0.4
                            unit: "sp"
                            command: "$givesp @main N, alt types y"
                            value: root.rules ? root.rules.spheres.keep : 0
                            onChanged: function(v) { root.setPart("spheres", "keep", v) }
                        }
                    }
                }
            }

            Item {
                visible: root.selected === null
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        // ================= Ledger =================
        ScrollablePage {
            visible: root.section === 1
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentSpacing: Theme.gap

            PanelCard {
                Layout.fillWidth: true
                title: "Pass to main"
                headerAccessory: Hint {
                    Layout.fillWidth: false
                    text: "by hand, one exchange at a time"
                }

                Hint {
                    visible: root.passAlt === null
                    text: root.passData.connected
                        ? "No alt is connected. An alt that failed to connect shows on the Run page."
                        : "Connect with Alts on to pass kakera, spheres or characters from an alt to the main."
                }

                RowLayout {
                    visible: root.passAlt !== null
                    Layout.fillWidth: true
                    spacing: 8
                    Seg {
                        Layout.fillWidth: false
                        options: root.passData.alts.map(function(a) { return { v: a.id, t: a.name } })
                        value: root.passAlt ? root.passAlt.id : ""
                        onPicked: function(v) { root.passAltId = v }
                    }
                    ThemedButton {
                        text: root.passBusy === "fetching" ? "Fetching…" : "Fetch"
                        loading: root.passBusy === "fetching"
                        enabled: root.passBusy === ""
                        onClicked: App.fetchAltBalances(root.passAlt.id)
                    }
                    Hint {
                        text: !root.passAlt ? ""
                            : (root.passAlt.fetched_at
                               ? "✓ " + root.passAlt.fetched_at + " UTC · read " + root.passAlt.fetched_from.join(", ")
                               : "Not fetched yet. Fetch reads $tu, then $ku / $ohu only for a stock $tu lacks, then $mmk= for the characters.")
                    }
                }

                RowLayout {
                    visible: root.passAlt !== null
                    Layout.fillWidth: true
                    spacing: Theme.gap

                    StockColumn {
                        title: "Kakera"
                        icon: "../assets/kakera/Kakera.png"
                        unit: "ka"
                        command: "givek"
                        stock: root.passAlt ? root.passAlt.kakera_stock : null
                        keep: root.keepFor("kakera")
                        onKeepEdited: function(v) { root.setKeep("kakera", v) }
                        onGive: App.passAltToMain(root.passAlt.id, root.keepFor("kakera"), -1, "[]")
                    }
                    StockColumn {
                        title: "Spheres"
                        icon: "../assets/kakera/SpR.webp"
                        unit: "sp"
                        command: "givesp"
                        stock: root.passAlt ? root.passAlt.sphere_stock : null
                        keep: root.keepFor("spheres")
                        onKeepEdited: function(v) { root.setKeep("spheres", v) }
                        onGive: App.passAltToMain(root.passAlt.id, -1, root.keepFor("spheres"), "[]")
                    }

                    // Characters
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 4
                        Layout.alignment: Qt.AlignTop
                        implicitHeight: charCol.implicitHeight + 20
                        radius: Theme.radiusSm
                        color: Theme.bg
                        border.color: Theme.line
                        border.width: Theme.borderWidth

                        ColumnLayout {
                            id: charCol
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "Characters"; font.weight: Font.DemiBold; Layout.fillWidth: false }
                                Item { Layout.fillWidth: true }
                                Hint {
                                    Layout.fillWidth: false
                                    text: root.passAlt && root.passAlt.harem_pages
                                        ? "$mmk= page 1 of " + root.passAlt.harem_pages + " · most valuable first" : ""
                                }
                            }
                            Hint {
                                visible: !root.passAlt || root.passAlt.harem.length === 0
                                text: !root.passAlt || !root.passAlt.fetched_at ? "Fetch to list them."
                                    : (root.passAlt.harem_pages === 0 ? "The harem is empty." : "No characters read.")
                            }
                            Rectangle {
                                visible: root.passAlt !== null && root.passAlt.harem.length > 0
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(196, charList.contentHeight + 2)
                                color: "transparent"
                                border.color: Theme.line
                                border.width: Theme.borderWidth
                                radius: Theme.radiusSm
                                ListView {
                                    id: charList
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    clip: true
                                    boundsBehavior: Flickable.StopAtBounds
                                    model: root.passAlt ? root.passAlt.harem : []
                                    delegate: Rectangle {
                                        required property var modelData
                                        required property int index
                                        readonly property bool picked: root.isPicked(modelData.name)
                                        width: charList.width
                                        height: 28
                                        color: charMouse.containsMouse ? Theme.hover : "transparent"
                                        Rectangle {
                                            visible: index > 0
                                            width: parent.width; height: 1; color: Theme.line
                                        }
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 8
                                            anchors.rightMargin: 8
                                            spacing: 8
                                            // Shows the pick; the row's MouseArea above does the toggling.
                                            ThemedCheckBox {
                                                checked: parent.parent.picked
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: modelData.name
                                                elide: Text.ElideRight
                                                wrapMode: Text.NoWrap
                                            }
                                            Hint {
                                                Layout.fillWidth: false
                                                text: modelData.kakera !== null && modelData.kakera !== undefined
                                                    ? root.fmt(modelData.kakera) + " ka" : ""
                                            }
                                        }
                                        MouseArea {
                                            id: charMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.togglePick(modelData.name)
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Hint {
                                    text: root.pickedNames().length
                                        ? root.pickedNames().length + " selected → " + root.pickedNames().length + " × $give (the main types y)"
                                        : "none selected"
                                }
                                ThemedButton {
                                    text: "select all"
                                    enabled: root.passAlt !== null && root.passAlt.harem.length > 0
                                    onClicked: root.pickAll()
                                }
                            }
                            ThemedButton {
                                Layout.fillWidth: true
                                text: "Give selected"
                                enabled: root.passBusy === "" && root.pickedNames().length > 0
                                onClicked: App.passAltToMain(root.passAlt.id, -1, -1, JSON.stringify(root.pickedNames()))
                            }
                        }
                    }
                }

                Divider { visible: root.passAlt !== null }

                RowLayout {
                    visible: root.passAlt !== null
                    Layout.fillWidth: true
                    spacing: 10
                    Hint {
                        text: root.passBusy === "passing" ? "Passing… one exchange at a time, through the channel's command lane."
                            : (root.passAlt && root.passAlt.note ? root.passAlt.note
                            : "Kakera and spheres: the alt types y. Characters: the main types y. A y only goes out when Mudae's question names exactly that amount or character; anything else is answered n. Keep starts at the reserve set in Setup.")
                        color: root.passAlt && root.passAlt.note && root.passBusy === "" ? Theme.warn : Theme.mute
                    }
                    ThemedButton {
                        accent: true
                        text: "Give everything above keep"
                        loading: root.passBusy === "passing"
                        enabled: root.passBusy === "" && root.passAlt !== null
                            && (root.toSend("kakera") > 0 || root.toSend("spheres") > 0 || root.pickedNames().length > 0)
                        onClicked: App.passAltToMain(root.passAlt.id, root.keepFor("kakera"), root.keepFor("spheres"),
                                                     JSON.stringify(root.pickedNames()))
                    }
                }
            }

            // ---- What the alts did for the main (alt_ledger.json) ----
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap
                Repeater {
                    model: [
                        { lbl: "claims for main", v: root.ledgerTotal("today", "claims"),
                          s: root.ledgerTotal("today", "characters_given") + " given · " + root.ledgerPending() + " waiting", c: Theme.accent },
                        { lbl: "kakera on main's rolls", v: root.ledgerTotal("today", "kakera_earned"), s: "earned by the alts", c: Theme.accent2 },
                        { lbl: "kakera to main", v: root.ledgerTotal("today", "kakera_passed"), s: "$givek", c: Theme.good },
                        { lbl: "spheres to main", v: root.ledgerTotal("today", "spheres_passed"), s: "$givesp", c: Theme.good }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: kpiCol.implicitHeight + 20
                        radius: Theme.radiusMd
                        color: Theme.bgDark
                        border.color: Theme.border
                        Column {
                            id: kpiCol
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 2
                            Hint { width: parent.width; text: modelData.lbl }
                            Text {
                                text: root.fmt(modelData.v)
                                color: modelData.c
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeLarge
                                font.weight: Font.DemiBold
                            }
                            Hint { width: parent.width; text: modelData.s; elide: Text.ElideRight }
                        }
                    }
                }
            }

            PanelCard {
                Layout.fillWidth: true
                title: "Per alt"
                headerAccessory: Hint {
                    Layout.fillWidth: false
                    text: "today (since 00:00 UTC) · last 7 days"
                }

                Hint {
                    visible: root.ledgerRows.length === 0
                    text: "No alts yet. Set an account's type to Alt on the Accounts page."
                }

                // Header
                RowLayout {
                    visible: root.ledgerRows.length > 0
                    Layout.fillWidth: true
                    spacing: 10
                    Hint { Layout.fillWidth: true; text: "alt" }
                    Repeater {
                        model: ["claims", "FD cycles", "ka earned", "sp games", "ka passed", "sp passed", "waiting"]
                        delegate: Hint {
                            required property var modelData
                            Layout.fillWidth: false
                            Layout.preferredWidth: 96
                            horizontalAlignment: Text.AlignRight
                            text: modelData
                        }
                    }
                }
                Repeater {
                    model: root.ledgerRows
                    delegate: RowLayout {
                        id: lrow
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle {
                                width: 7; height: 7; radius: 4
                                color: lrow.modelData.connected ? Theme.good : Theme.mute
                            }
                            Label { text: lrow.modelData.name; elide: Text.ElideRight; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                        }
                        Repeater {
                            model: ["claims", "fd_cycles", "kakera_earned", "spheres_earned", "kakera_passed", "spheres_passed"]
                            delegate: Column {
                                required property var modelData
                                Layout.preferredWidth: 96
                                Text {
                                    width: parent.width
                                    horizontalAlignment: Text.AlignRight
                                    text: root.fmt((lrow.modelData.today || {})[parent.modelData] || 0)
                                    color: Theme.fg
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeSmall
                                }
                                Hint {
                                    width: parent.width
                                    horizontalAlignment: Text.AlignRight
                                    text: "7d " + root.fmt((lrow.modelData.week || {})[parent.modelData] || 0)
                                }
                            }
                        }
                        Text {
                            Layout.preferredWidth: 96
                            horizontalAlignment: Text.AlignRight
                            text: lrow.modelData.pending.length ? lrow.modelData.pending.join(", ") : "—"
                            color: lrow.modelData.pending.length ? Theme.warn : Theme.mute
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeTiny
                            elide: Text.ElideRight
                        }
                    }
                }
                Hint {
                    visible: root.ledgerRows.length > 0
                    text: "Top: today. Below: the last 7 days. sp games: spheres from the alt's own daily minigames (once a day, at its first session). Waiting: claimed for the main, given at the next batch end. Automatic passing follows each alt's Kakera and Spheres › Pass to main."
                }
            }

            PanelCard {
                Layout.fillWidth: true
                title: "Transfers"
                headerAccessory: Hint { Layout.fillWidth: false; text: "newest first · kept across restarts" }

                Hint {
                    visible: root.passData.transfers.length === 0
                    text: "Nothing given to the main yet."
                }
                Repeater {
                    model: root.passData.transfers
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 12
                        Hint {
                            Layout.fillWidth: false
                            Layout.preferredWidth: 64
                            text: modelData.time
                        }
                        Label { Layout.fillWidth: false; Layout.preferredWidth: 110; text: modelData.alt; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                        Label {
                            Layout.fillWidth: true
                            text: (modelData.transfer === "character" ? "$give " : (modelData.transfer === "kakera" ? "$givek " : "$givesp "))
                                + modelData.what
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }
                        Hint {
                            Layout.fillWidth: false
                            Layout.preferredWidth: 160
                            text: modelData.why || ""
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }
                        Text {
                            text: modelData.ok ? "sent" : (modelData.confirmed ? "unconfirmed · " + modelData.reason : "failed · " + modelData.reason)
                            color: modelData.ok ? Theme.good : Theme.warn
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeTiny
                        }
                    }
                }
            }
        }
    }
}
