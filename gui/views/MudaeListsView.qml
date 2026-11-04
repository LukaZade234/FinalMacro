import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Advisor › Lists — Mudae's `$dl`, `$adl` and `$wl`, read back and saved.

    Three tabs, one per list. Each shows the scoped pair's latest capture as
    **Current on Mudae**, beside named presets saved from earlier captures
    (global per list type, so the editing step can send one to any server).

    Fetching clicks through every page (`macro/listing_capture.py`); `$wl` goes
    through the existing wishlist capture, so the same fetch also refreshes
    `$bw` and Spheres › Characters. A listing that lost a page is shown as
    *partial*, never as a shorter list.

    Presets can also be made by hand: **Add new** gives a blank one, and
    **Edit** on any saved preset adds names (`A$B$C`, as Mudae takes them),
    renames, reorders and removes rows, and sets each wish's type (starwish,
    locked, kakera wish). "Current on Mudae" is never edited — it is what
    Mudae printed. Saved wishlist presets drop the ✅: claimed-ness is a fact
    about today, not part of the list.

    **Send to Mudae** is drawn but disabled: it will clear the list and send
    one bulk add, and that needs the edit commands captured.
*/
Item {
    id: root
    clip: true

    // Mudae's emoji marks. Qt's own font fallback finds no emoji glyphs under
    // the bundled Plex faces, so each mark names Twemoji outright; where that
    // is missing Qt falls back as before.
    component Mark: Label {
        font.family: "Twemoji"
        font.pixelSize: Theme.sizeSmall
    }

    property string channelProfileId: ""
    property string accountId: ""

    property string kind: "dl"
    // Selected preset per tab; "live" is the current capture.
    property var selected: ({ dl: "live", adl: "live", sdl: "live", wl: "live" })
    property var listsData: ({ current: {}, presets: { dl: [], adl: [], sdl: [], wl: [] }, scoped_ready: false })
    property bool naming: false
    property string namingMode: "save"   // save | new | rename
    property string copiedNote: ""
    property bool editing: false
    property int renamingIndex: -1
    property string addNote: ""
    // Drag and drop: the row being dragged and where it would land.
    property int dragFrom: -1
    property int dragTo: -1
    property real dragPointerY: 0

    // Drop target from the pointer's y in the list's own coordinates; past
    // either end it clamps to the first or last row.
    function updateDropTarget(y) {
        var target = rows.indexAt(10, y + rows.contentY)
        if (target < 0)
            target = y < 0 ? 0 : rows.count - 1
        dragTo = target
    }

    function finishDrag() {
        var from = dragFrom
        var to = dragTo
        dragFrom = -1
        dragTo = -1
        if (from >= 0 && to >= 0 && from !== to)
            App.moveMudaeListEntryTo(kind, selectedId, from, to)
    }

    // Scroll while a row is held near the top or bottom edge of the list.
    Timer {
        interval: 30
        repeat: true
        running: root.dragFrom >= 0
        onTriggered: {
            var edge = 28
            var step = 0
            if (root.dragPointerY < edge)
                step = -8
            else if (root.dragPointerY > rows.height - edge)
                step = 8
            if (step === 0)
                return
            rows.contentY = Math.max(0, Math.min(rows.contentHeight - rows.height, rows.contentY + step))
            root.updateDropTarget(root.dragPointerY)
        }
    }

    readonly property var knownToggles: [
        { command: "$togglewestern", label: "Western animanga" },
        { command: "$toggleirl", label: "IRL" }
    ]
    readonly property bool dlHasTotals: {
        var v = view
        if (v.total !== null && v.total !== undefined)
            return true
        var pools = v.pools || {}
        return pools.wa !== undefined || pools.ha !== undefined || pools.wg !== undefined || pools.hg !== undefined
    }

    function hasToggle(command) {
        var toggles = view.toggles || []
        for (var i = 0; i < toggles.length; i++)
            if (toggles[i].command === command)
                return true
        return false
    }

    // One figure: a tile when reading, a field when editing a preset (if
    // `field` names something the user may type). Blank is allowed.
    component CountTile: Rectangle {
        id: tile
        property string label: ""
        property string field: ""
        property var value: null
        property var maxValue: null
        property bool total: false
        property string sub: ""
        property string placeholder: "blank"
        readonly property bool editable: root.editing && field !== ""

        implicitHeight: tileCol.implicitHeight + 16
        color: Theme.bg
        border.color: Theme.line
        border.width: 1
        radius: Theme.radiusSm

        function shown(v) { return v === null || v === undefined ? "" : String(v) }
        onValueChanged: if (!countField.activeFocus) countField.text = shown(value)

        ColumnLayout {
            id: tileCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 2
            Label { text: Theme.sectionLabel(tile.label); color: Theme.mute; font.pixelSize: Theme.sizeMicro }
            Label {
                visible: !tile.editable
                text: root.fmt(tile.value) + (tile.maxValue !== null && tile.maxValue !== undefined ? " / " + root.fmt(tile.maxValue) : "")
                color: tile.total ? Theme.accent : Theme.fg
                font.pixelSize: Theme.sizeXLarge
                font.weight: Font.DemiBold
            }
            ThemedTextField {
                id: countField
                visible: tile.editable
                Layout.fillWidth: true
                implicitHeight: 28
                placeholderText: tile.placeholder
                font.pixelSize: Theme.sizeMedium
                validator: RegularExpressionValidator { regularExpression: /[0-9,]*/ }
                Component.onCompleted: text = tile.shown(tile.value)
                onEditingFinished: {
                    if (text.replace(/,/g, "") !== tile.shown(tile.value))
                        App.setMudaeListCount(root.kind, root.selectedId, tile.field, text)
                }
            }
            Label {
                visible: tile.sub !== ""
                text: tile.sub
                color: Theme.mute
                font.pixelSize: Theme.sizeTiny
            }
        }
    }

    // A small text button for a row's edit actions.
    component RowAction: Label {
        id: action
        signal clicked()
        property string tip: ""
        color: actionMouse.containsMouse ? Theme.accent : Theme.dim
        font.pixelSize: Theme.sizeSmall
        ToolTip.visible: tip !== "" && actionMouse.containsMouse
        ToolTip.text: tip
        ToolTip.delay: 400
        MouseArea {
            id: actionMouse
            anchors.fill: parent
            anchors.margins: -3
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: action.clicked()
        }
    }

    // A wish-type flag in edit mode: shown full when set, faint when not;
    // clicking flips it.
    component FlagToggle: Item {
        id: flag
        signal toggled()
        property bool on: false
        property string glyph: ""
        property bool kakera: false
        property string tip: ""
        implicitWidth: 18
        implicitHeight: 18
        opacity: on ? 1 : (flagMouse.containsMouse ? 0.6 : 0.22)
        Mark {
            visible: !flag.kakera
            anchors.centerIn: parent
            text: flag.glyph
        }
        Image {
            visible: flag.kakera
            anchors.centerIn: parent
            source: MudaeEmoji.assetBase + "Kakera.png"
            sourceSize.width: 16
            sourceSize.height: 16
            width: 14
            height: 14
            fillMode: Image.PreserveAspectFit
        }
        ToolTip.visible: flagMouse.containsMouse
        ToolTip.text: tip + (on ? " — click to clear" : " — click to set")
        ToolTip.delay: 400
        MouseArea {
            id: flagMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: flag.toggled()
        }
    }

    readonly property var kinds: [
        { id: "dl", label: "$dl · disablelist", command: "disablelist", fetchLabel: "$dld" },
        { id: "adl", label: "$adl · antidisablelist", command: "antidisablelist", fetchLabel: "$adl" },
        { id: "sdl", label: "$sdl · server disablelist", command: "serverdisablelist", fetchLabel: "$sdl" },
        { id: "wl", label: "$wl · wishlist", command: "wishlist", fetchLabel: "$wl" }
    ]
    readonly property var kindInfo: {
        for (var i = 0; i < kinds.length; i++)
            if (kinds[i].id === kind)
                return kinds[i]
        return kinds[0]
    }
    // What a list's rows are, for labels.
    readonly property string rowNoun: kind === "dl" ? "Disabled"
        : (kind === "adl" ? "Series" : (kind === "sdl" ? "Characters" : "Wishes"))
    // The server disablelist holds at most this many characters.
    readonly property int sdlCap: 1000

    readonly property var current: (listsData.current || {})[kind] || ({})
    readonly property var savedPresets: (listsData.presets || {})[kind] || []
    readonly property string selectedId: selected[kind] || "live"
    readonly property var selectedPreset: {
        if (selectedId === "live")
            return null
        for (var i = 0; i < savedPresets.length; i++)
            if (savedPresets[i].id === selectedId)
                return savedPresets[i]
        return null
    }
    readonly property bool showingLive: selectedPreset === null
    readonly property var view: showingLive ? current : (selectedPreset.data || {})
    readonly property bool hasData: showingLive ? !!current.captured : true
    readonly property var entries: view.entries || []

    function refresh() {
        // Every edit rebuilds the model, which puts a ListView back at the
        // top; hold the scroll position across it.
        var keepY = rows.contentY
        try {
            listsData = JSON.parse(App.mudaeListsFor(root.accountId, root.channelProfileId))
        } catch (e) {
            listsData = ({ current: {}, presets: { dl: [], adl: [], sdl: [], wl: [] }, scoped_ready: false })
        }
        rows.contentY = keepY
        Qt.callLater(function () {
            rows.contentY = Math.max(0, Math.min(keepY, rows.contentHeight - rows.height))
        })
        // A deleted preset falls back to the live capture.
        if (selectedId !== "live" && selectedPreset === null)
            select("live")
    }

    function select(id) {
        var next = Object.assign({}, selected)
        next[kind] = id
        selected = next
        naming = false
        stopEditing()
    }

    function stopEditing() {
        dragFrom = -1
        dragTo = -1
        editing = false
        renamingIndex = -1
        addNote = ""
    }

    function fmt(n) {
        return (n === null || n === undefined) ? "—" : Number(n).toLocaleString(Qt.locale("en_US"), "f", 0)
    }

    function when(iso) {
        if (!iso)
            return ""
        var d = new Date(iso)
        if (isNaN(d.getTime()))
            return ""
        return Qt.formatDateTime(d, "d MMM HH:mm")
    }

    function entryName(e) {
        return (typeof e === "string") ? e : String(e.name || "")
    }

    function copyText() {
        var names = []
        for (var i = 0; i < entries.length; i++)
            names.push(entryName(entries[i]))
        return names.join("$")
    }

    // Header chips for the list on screen: slot counts, then completeness.
    function chips() {
        var out = []
        var v = view
        // "N/max" when Mudae said the max; a hand-made list just counts.
        function count(used, max, unit) {
            if (used === null || used === undefined)
                return
            var has = max !== null && max !== undefined
            out.push({ text: fmt(used) + (has ? "/" + fmt(max) : "") + " " + unit, tone: "accent" })
        }
        // A saved preset shows only its own counts, from its own rows: the slot
        // maximum is the server's (a preset can be sent to any server), and the
        // header it was saved from may describe a list it only partly holds.
        var maxOf = function (m) { return showingLive ? m : null }
        var rows = v.entries || []
        if (kind === "wl") {
            var stars = 0
            for (var i = 0; i < rows.length; i++)
                if (rows[i].starwish)
                    stars++
            count(showingLive ? v.wl_used : rows.length, maxOf(v.wl_max), "$wl")
            count(showingLive ? v.sw_used : stars, maxOf(v.sw_max), "$sw")
        } else {
            count(showingLive ? v.used : rows.length, maxOf(v.max),
                  kind === "adl" ? "series" : (kind === "sdl" ? "characters" : (showingLive ? "slots" : "entries")))
        }
        if (kind === "sdl" && !showingLive && (v.entries || []).length > sdlCap)
            out.push({ text: "over the " + fmt(sdlCap) + " cap", tone: "warn" })
        if (showingLive && hasData) {
            if (v.complete) {
                var pages = v.pages || 1
                out.push({ text: "complete" + (kind === "wl" ? "" : " · " + pages + " page" + (pages > 1 ? "s" : "")), tone: "good" })
            } else {
                var seen = (v.seen_pages || []).join(",")
                out.push({ text: "partial" + (v.pages ? " · read page " + (seen || "?") + " of " + v.pages : ""), tone: "warn" })
            }
        }
        return out
    }

    onAccountIdChanged: refresh()
    onChannelProfileIdChanged: refresh()
    onKindChanged: { naming = false; copiedNote = ""; stopEditing() }
    Component.onCompleted: { refresh(); refreshSend() }

    Connections {
        target: App
        function onMudaeListsChanged() { root.refresh() }
        function onMudaeWishlistChanged() { root.refresh() }
    }

    property var commandPlan: ({ regular: [], nitro: [], split: false, notes: [] })
    property string copiedCommand: ""

    property var sendState: ({ running: false })
    readonly property bool sendingThis: !!sendState.running && sendState.kind === kind
                                        && sendState.preset_id === selectedId

    function refreshSend() {
        try {
            sendState = JSON.parse(App.listSendJson)
        } catch (e) {
            sendState = ({ running: false })
        }
    }

    // Gamemode 2 changes what $disable / $antidisable do, so a $dl / $adl send
    // to a server known to run it asks first. Unknown gamemode: no question.
    readonly property bool gamemode2Warning: (kind === "dl" || kind === "adl") && listsData.gamemode === 2

    function requestSend() {
        if (gamemode2Warning)
            gamemodePopup.open()
        else
            openSendConfirm()
    }

    function openSendConfirm() {
        try {
            sendPlan = JSON.parse(App.mudaeListCommands(root.kind, root.selectedId, root.accountId, root.channelProfileId))
        } catch (e) {
            sendPlan = ({ error: "Could not build the commands.", regular: [], nitro: [] })
        }
        sendNitro.checked = false
        sendPopup.open()
    }

    property var sendPlan: ({ regular: [], nitro: [], toggles: [] })

    // What the send will do if the preset has more starwishes than the server's
    // starwish limit (Mudae then offers to trade wishlist slots for more).
    function starwishTradeNote() {
        var want = Number(view.sw_used || 0)
        var limit = current.sw_max
        var size = current.wl_max
        var rows = (view.entries || []).length
        var rule = "If Mudae offers to trade wishlist slots for more $starwish slots, the macro accepts "
                 + "only if the wishlist still has room for all " + rows + " wishes afterwards; otherwise it answers n and stops."
        if (limit === null || limit === undefined || want <= limit)
            return rule
        return "This preset has " + want + " starwishes and this server allows " + limit
             + (size ? " (wishlist size " + Number(size).toLocaleString(Qt.locale("en_US"), "f", 0) + ")" : "")
             + ", so Mudae will offer a trade. " + rule
    }

    Connections {
        target: App
        function onListSendChanged() { root.refreshSend() }
    }

    function openCommands() {
        try {
            commandPlan = JSON.parse(App.mudaeListCommands(root.kind, root.selectedId, root.accountId, root.channelProfileId))
        } catch (e) {
            commandPlan = ({ error: "Could not build the commands.", regular: [], nitro: [] })
        }
        copiedCommand = ""
        commandPopup.open()
    }

    // A list of commands to send one by one, each with its own copy button.
    component CommandColumn: Rectangle {
        id: column
        property string title: ""
        property string limitLabel: ""
        property var commands: []
        property string tag: ""

        implicitHeight: colLayout.implicitHeight + 24
        radius: Theme.radiusMd
        color: Theme.bg
        border.color: Theme.line
        border.width: 1

        ColumnLayout {
            id: colLayout
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 12
            spacing: 8

            RowLayout {
                spacing: 8
                Label {
                    text: column.title
                    color: Theme.fg
                    font.pixelSize: Theme.sizeMedium
                    font.weight: Font.DemiBold
                }
                Rectangle {
                    visible: column.limitLabel !== ""
                    implicitWidth: limitText.implicitWidth + 14
                    implicitHeight: 20
                    radius: Theme.radiusSm
                    color: Theme.raised
                    Label {
                        id: limitText
                        anchors.centerIn: parent
                        text: column.limitLabel
                        color: Theme.dim
                        font.pixelSize: Theme.sizeTiny
                    }
                }
                Label {
                    text: column.commands.length + " message" + (column.commands.length === 1 ? "" : "s")
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                }
            }

            Repeater {
                model: column.commands

                delegate: RowLayout {
                    id: cmdRow
                    required property var modelData
                    required property int index
                    readonly property string key: column.tag + ":" + index
                    Layout.fillWidth: true
                    spacing: 10

                    ThemedButton {
                        Layout.preferredWidth: 170
                        implicitHeight: 28
                        text: root.copiedCommand === cmdRow.key
                            ? "Copied"
                            : "Copy command " + (cmdRow.index + 1) + "/" + column.commands.length
                        accent: root.copiedCommand === cmdRow.key
                        onClicked: {
                            App.copyToClipboard(cmdRow.modelData.text)
                            root.copiedCommand = cmdRow.key
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Label {
                            Layout.fillWidth: true
                            text: cmdRow.modelData.text
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                            elide: Text.ElideRight
                        }
                        Label {
                            Layout.fillWidth: true
                            text: cmdRow.modelData.note + " · " + Number(cmdRow.modelData.chars).toLocaleString(Qt.locale("en_US"), "f", 0) + " chars"
                            color: String(cmdRow.modelData.note).indexOf("only if") >= 0 ? Theme.warn : Theme.mute
                            font.pixelSize: Theme.sizeTiny
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    // One command outside the numbered list (the clear, a toggle).
    component SingleCommand: RowLayout {
        id: single
        property var command: ({ text: "", note: "", chars: 0 })
        property string key: ""
        property string buttonText: "Copy"
        property bool muted: false
        spacing: 10

        ThemedButton {
            Layout.preferredWidth: 170
            implicitHeight: 28
            text: root.copiedCommand === single.key ? "Copied" : single.buttonText
            accent: root.copiedCommand === single.key
            onClicked: {
                App.copyToClipboard(single.command.text)
                root.copiedCommand = single.key
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Label {
                Layout.fillWidth: true
                text: single.command.text
                color: single.muted ? Theme.dim : Theme.fg
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeSmall
                elide: Text.ElideRight
            }
            Label {
                Layout.fillWidth: true
                text: single.command.note || ""
                color: String(single.command.note || "").indexOf("only if") >= 0 ? Theme.warn : Theme.mute
                font.pixelSize: Theme.sizeTiny
                elide: Text.ElideRight
            }
        }
    }

    component StepLabel: Label {
        color: Theme.mute
        font.pixelSize: Theme.sizeMicro
        font.letterSpacing: 0.6
    }

    Popup {
        id: gamemodePopup
        parent: Overlay.overlay
        modal: true
        focus: true
        anchors.centerIn: parent
        width: Math.min(parent ? parent.width - 80 : 600, 580)
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radiusLg
            color: Theme.surface
            border.color: Theme.warn
            border.width: 1
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: "⚠  This server runs gamemode 2"
                color: Theme.warn
                font.pixelSize: Theme.sizeXLarge
                font.weight: Font.DemiBold
            }
            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.fg
                font.pixelSize: Theme.sizeSmall
                textFormat: Text.StyledText
                text: root.kind === "dl"
                    ? "In gamemode 2, <b>$disable</b> works differently: every series you disable "
                      + "<b>enables</b> the same number of disabled characters, and the list cannot go "
                      + "below the limits <b>$limroul</b> shows. Clearing and rebuilding the disablelist "
                      + "here will not give the same result as on a gamemode 1 server."
                    : "In gamemode 2, the disable lists work differently: disabling enables the same "
                      + "number of characters, within the limits <b>$limroul</b> shows, so the "
                      + "antidisablelist may not have the effect it would on a gamemode 1 server."
            }
            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.dim
                font.pixelSize: Theme.sizeSmall
                text: "Are you sure you want to send this " + root.kindInfo.fetchLabel.replace("$dld", "$dl") + " anyway?"
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemedButton {
                    text: "Cancel"
                    implicitHeight: 30
                    onClicked: gamemodePopup.close()
                }
                ThemedButton {
                    text: "Proceed anyway"
                    danger: true
                    implicitHeight: 30
                    onClicked: {
                        gamemodePopup.close()
                        root.openSendConfirm()
                    }
                }
            }
        }
    }

    // Confirm before a send: it clears the list on a live server.
    Popup {
        id: sendPopup
        parent: Overlay.overlay
        modal: true
        focus: true
        anchors.centerIn: parent
        width: Math.min(parent ? parent.width - 80 : 640, 620)
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radiusLg
            color: Theme.surface
            border.color: Theme.line
            border.width: 1
        }

        readonly property int addCount: (sendNitro.checked ? root.sendPlan.nitro : root.sendPlan.regular || []).length

        ColumnLayout {
            anchors.fill: parent
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: "Send “" + (root.selectedPreset ? root.selectedPreset.name : "") + "” to Mudae?"
                color: Theme.fg
                font.pixelSize: Theme.sizeXLarge
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.fg
                font.pixelSize: Theme.sizeSmall
                textFormat: Text.StyledText
                text: root.kind === "sdl"
                    ? "This <b>replaces</b> the <b>server's</b> $sdl on the server picked above — "
                      + "it is one list for everyone there. The macro will:"
                    : "This <b>replaces</b> your " + root.kindInfo.fetchLabel.replace("$dld", "$dl")
                      + " on the account and server picked above. The macro will:"
            }

            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.dim
                font.pixelSize: Theme.sizeSmall
                text: (root.kind === "dl" ? "· read the current $dld, to see which toggles are on\n" : "")
                      + (root.kind === "sdl"
                         ? "· send $sdl to see whether the list is empty; if not, clear it with $serverenableall and type confirm\n"
                         : "· clear the list with " + ((root.sendPlan.clear || {}).text || "") + " and type confirm\n")
                      + "· send " + sendPopup.addCount + " add command" + (sendPopup.addCount === 1 ? "" : "s") + ", waiting for Mudae's tick on each\n"
                      + (root.kind === "dl" ? "· flip only the toggles that differ from the preset\n" : "")
                      + "· read the list back and check it matches the preset"
                      + (root.kind === "wl" ? "\n\n" + root.starwishTradeNote() : "")
            }

            Label {
                Layout.fillWidth: true
                visible: !!root.sendPlan.error
                text: root.sendPlan.error || ""
                color: Theme.bad
                font.pixelSize: Theme.sizeSmall
                wrapMode: Text.WordWrap
            }

            ThemedCheckBox {
                id: sendNitro
                visible: !!root.sendPlan.split
                text: "My account has Nitro — use 4,000-character messages ("
                      + (root.sendPlan.nitro || []).length + " instead of " + (root.sendPlan.regular || []).length + ")"
                textSize: Theme.sizeSmall
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemedButton {
                    text: "Cancel"
                    implicitHeight: 30
                    onClicked: sendPopup.close()
                }
                ThemedButton {
                    text: "Clear and send"
                    accent: true
                    implicitHeight: 30
                    enabled: !root.sendPlan.error
                    onClicked: {
                        App.sendMudaeListPreset(root.kind, root.selectedId, root.accountId,
                                                root.channelProfileId, sendNitro.checked)
                        sendPopup.close()
                    }
                }
            }
        }
    }

    Popup {
        id: commandPopup
        parent: Overlay.overlay
        modal: true
        focus: true
        anchors.centerIn: parent
        width: Math.min(parent ? parent.width - 80 : 900, root.commandPlan.split ? 1000 : 720)
        height: Math.min(parent ? parent.height - 80 : 700, popupLayout.implicitHeight + 40)
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radiusLg
            color: Theme.surface
            border.color: Theme.line
            border.width: 1
        }

        ColumnLayout {
            id: popupLayout
            anchors.fill: parent
            spacing: 14

            RowLayout {
                spacing: 10
                Label {
                    visible: !!root.commandPlan.split
                    text: "⚠"
                    color: Theme.warn
                    font.pixelSize: Theme.sizeXLarge
                }
                Label {
                    Layout.fillWidth: true
                    text: root.commandPlan.split
                        ? root.kindInfo.fetchLabel + " commands exceed Discord length"
                        : "Commands for " + (root.showingLive ? "Current on Mudae" : (root.selectedPreset ? root.selectedPreset.name : ""))
                    color: Theme.fg
                    font.pixelSize: Theme.sizeXLarge
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }

            Rectangle {
                Layout.fillWidth: true
                visible: !!root.commandPlan.split || !!root.commandPlan.error
                implicitHeight: bannerText.implicitHeight + 20
                radius: Theme.radiusMd
                color: "transparent"
                border.color: root.commandPlan.error ? Theme.bad : Theme.warn
                border.width: 1
                Label {
                    id: bannerText
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 12
                    wrapMode: Text.WordWrap
                    textFormat: Text.StyledText
                    color: Theme.fg
                    font.pixelSize: Theme.sizeSmall
                    text: root.commandPlan.error
                        ? root.commandPlan.error
                        : "<b>" + Number(root.commandPlan.total_chars || 0).toLocaleString(Qt.locale("en_US"), "f", 0)
                          + "</b> characters — Discord allows <b>2,000</b> per message (<b>4,000</b> with Nitro). "
                          + "Copy each block as a separate message."
                }
            }

            StepLabel {
                visible: !!root.commandPlan.clear
                text: Theme.sectionLabel("1 · Clear the list first")
            }
            SingleCommand {
                Layout.fillWidth: true
                visible: !!root.commandPlan.clear
                command: root.commandPlan.clear || ({ text: "", note: "" })
                key: "clear"
                buttonText: "Copy clear command"
            }
            StepLabel {
                text: Theme.sectionLabel((root.commandPlan.clear ? "2 · " : "") + "Add it back, in this order")
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: commandsRow.implicitHeight
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                contentWidth: availableWidth

                RowLayout {
                    id: commandsRow
                    width: parent.width
                    spacing: 14

                    CommandColumn {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        visible: (root.commandPlan.regular || []).length > 0
                        title: root.commandPlan.split ? "Regular" : "Add"
                        limitLabel: root.commandPlan.split ? "2,000 max" : ""
                        commands: root.commandPlan.regular || []
                        tag: "regular"
                    }

                    CommandColumn {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        visible: !!root.commandPlan.split
                        title: "Nitro"
                        limitLabel: "4,000 max"
                        commands: root.commandPlan.nitro || []
                        tag: "nitro"
                    }
                }
            }

            StepLabel {
                visible: (root.commandPlan.toggles || []).length > 0
                text: Theme.sectionLabel("3 · Toggles — each flips when sent")
            }
            Repeater {
                model: root.commandPlan.toggles || []
                delegate: SingleCommand {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    command: modelData
                    key: "toggle:" + index
                    buttonText: "Copy " + modelData.text
                    muted: !modelData.send
                }
            }

            Repeater {
                model: root.commandPlan.notes || []
                delegate: Label {
                    required property var modelData
                    Layout.fillWidth: true
                    text: "· " + modelData
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemedButton {
                    text: "Close"
                    implicitHeight: 30
                    onClicked: commandPopup.close()
                }
            }
        }
    }

    Timer {
        id: copiedTimer
        interval: 1600
        onTriggered: root.copiedNote = ""
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        // ---- list tabs + fetch ---------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: root.kinds

                delegate: PresetSectionTab {
                    required property var modelData
                    text: modelData.label
                    stretch: false
                    tabActive: root.kind === modelData.id
                    onClicked: root.kind = modelData.id
                }
            }

            Item { Layout.fillWidth: true }

            ScopeFetchButton {
                command: "lists"
                commandLabel: "all three"
                accountId: root.accountId
                channelProfileId: root.channelProfileId
            }

            ScopeFetchButton {
                command: root.kindInfo.command
                commandLabel: root.kindInfo.fetchLabel
                accountId: root.accountId
                channelProfileId: root.channelProfileId
                accent: true
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap

            // ---- presets rail ----------------------------------------------

            PanelCard {
                Layout.preferredWidth: 250
                Layout.minimumWidth: 210
                Layout.fillHeight: true
                fillContentVertically: true
                title: "Presets"
                titleSize: Theme.sizeMedium

                headerAccessory: Label {
                    text: root.savedPresets.length + " saved"
                    color: Theme.mute
                    font.pixelSize: Theme.sizeTiny
                }

                ListView {
                    id: presetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 3
                    boundsBehavior: Flickable.StopAtBounds
                    model: [{ id: "live", name: "Current on Mudae", live: true }].concat(root.savedPresets)

                    delegate: Rectangle {
                        id: presetRow
                        required property var modelData
                        readonly property bool active: root.selectedId === modelData.id
                        readonly property bool live: !!modelData.live

                        width: ListView.view.width
                        height: presetCol.implicitHeight + 12
                        radius: Theme.radiusSm
                        color: active ? Theme.raised : (presetMouse.containsMouse ? Theme.hover : "transparent")
                        opacity: presetMouse.containsMouse && !active ? 0.9 : 1

                        Rectangle {
                            visible: presetRow.active
                            width: 2
                            height: parent.height
                            color: Theme.accent
                        }

                        ColumnLayout {
                            id: presetCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 10
                            anchors.rightMargin: 8
                            spacing: 2

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 7

                                Rectangle {
                                    width: 7; height: 7; radius: 4
                                    color: presetRow.live
                                        ? (root.current.captured ? Theme.good : Theme.line)
                                        : Theme.line
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: presetRow.modelData.name
                                    color: Theme.fg
                                    font.pixelSize: Theme.sizeSmall
                                    font.weight: presetRow.active ? Font.DemiBold : Font.Normal
                                    elide: Text.ElideRight
                                }

                                Label {
                                    text: presetRow.live ? "live" : String((presetRow.modelData.data || {}).entries ? presetRow.modelData.data.entries.length : 0)
                                    color: Theme.mute
                                    font.pixelSize: Theme.sizeTiny
                                }
                            }

                            Label {
                                Layout.fillWidth: true
                                Layout.leftMargin: 14
                                text: presetRow.live
                                    ? (root.current.captured ? "fetched " + root.when(root.current.fetched_at) : "not fetched for this pair")
                                    : ("saved " + root.when(presetRow.modelData.saved_at)
                                       + (presetRow.modelData.source_label ? " · " + presetRow.modelData.source_label : ""))
                                color: Theme.mute
                                font.pixelSize: Theme.sizeTiny
                                elide: Text.ElideRight
                            }
                        }

                        MouseArea {
                            id: presetMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.select(presetRow.modelData.id)
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.line
                }

                // Save / rename, inline — the app has no modal for a name.
                RowLayout {
                    Layout.fillWidth: true
                    visible: root.naming
                    spacing: 6

                    ThemedTextField {
                        id: nameField
                        Layout.fillWidth: true
                        placeholderText: "Preset name"
                        font.pixelSize: Theme.sizeSmall
                        onAccepted: saveButton.clicked()
                    }

                    ThemedButton {
                        id: saveButton
                        text: root.namingMode === "rename" ? "Rename" : (root.namingMode === "new" ? "Create" : "Save")
                        accent: true
                        implicitHeight: 28
                        enabled: nameField.text.trim() !== ""
                        onClicked: {
                            var name = nameField.text.trim()
                            if (name === "")
                                return
                            if (root.namingMode === "rename") {
                                App.renameMudaeListPreset(root.kind, root.selectedId, name)
                                root.naming = false
                            } else if (root.namingMode === "new") {
                                var created = App.createMudaeListPreset(root.kind, name)
                                if (created !== "") {
                                    root.select(created)
                                    // A blank list is only useful once filled.
                                    root.editing = true
                                }
                            } else {
                                var id = App.saveMudaeListPreset(root.kind, name, root.accountId, root.channelProfileId)
                                if (id !== "")
                                    root.select(id)
                            }
                        }
                    }

                    ThemedButton {
                        text: "Cancel"
                        implicitHeight: 28
                        onClicked: root.naming = false
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    visible: !root.naming
                    spacing: 6

                    ThemedButton {
                        text: "Save current as…"
                        implicitHeight: 28
                        enabled: !!root.current.captured
                        hoverEnabled: true
                        ToolTip.visible: hovered && !enabled
                        ToolTip.text: "Fetch the list first"
                        onClicked: {
                            root.namingMode = "save"
                            nameField.text = ""
                            root.naming = true
                            nameField.forceActiveFocus()
                        }
                    }

                    ThemedButton {
                        text: "Add new"
                        implicitHeight: 28
                        hoverEnabled: true
                        ToolTip.visible: hovered
                        ToolTip.text: "A blank preset to fill by hand"
                        ToolTip.delay: 400
                        onClicked: {
                            root.namingMode = "new"
                            nameField.text = ""
                            root.naming = true
                            nameField.forceActiveFocus()
                        }
                    }

                    ThemedButton {
                        text: "Rename"
                        implicitHeight: 28
                        enabled: !root.showingLive
                        onClicked: {
                            root.namingMode = "rename"
                            nameField.text = root.selectedPreset ? root.selectedPreset.name : ""
                            root.naming = true
                            nameField.forceActiveFocus()
                        }
                    }

                    ThemedButton {
                        text: deleteArmed ? "Confirm delete" : "Delete"
                        implicitHeight: 28
                        danger: deleteArmed
                        enabled: !root.showingLive
                        property bool deleteArmed: false
                        onClicked: {
                            if (!deleteArmed) {
                                deleteArmed = true
                                disarm.restart()
                                return
                            }
                            deleteArmed = false
                            App.deleteMudaeListPreset(root.kind, root.selectedId)
                        }
                        Timer { id: disarm; interval: 3000; onTriggered: parent.deleteArmed = false }
                    }
                }
            }

            // ---- the list --------------------------------------------------

            PanelCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                fillContentVertically: true

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: root.showingLive ? "Current on Mudae" : root.selectedPreset.name
                        color: Theme.fg
                        font.pixelSize: Theme.sizeLarge
                        font.weight: Font.DemiBold
                    }

                    Repeater {
                        model: root.hasData ? root.chips() : []

                        delegate: Rectangle {
                            required property var modelData
                            implicitHeight: 20
                            implicitWidth: chipText.implicitWidth + 14
                            radius: Theme.radiusSm
                            color: "transparent"
                            border.width: 1
                            border.color: modelData.tone === "good" ? Theme.good
                                : (modelData.tone === "warn" ? Theme.warn : Theme.line)

                            Label {
                                id: chipText
                                anchors.centerIn: parent
                                text: parent.modelData.text
                                font.pixelSize: Theme.sizeTiny
                                color: parent.modelData.tone === "good" ? Theme.good
                                    : (parent.modelData.tone === "warn" ? Theme.warn : Theme.accent)
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        text: root.showingLive
                            ? (root.current.captured ? "fetched " + root.when(root.current.fetched_at) : "")
                            : ("saved " + root.when(root.selectedPreset.saved_at)
                               + (root.selectedPreset.source_label ? " · " + root.selectedPreset.source_label : ""))
                        color: Theme.mute
                        font.pixelSize: Theme.sizeSmall
                        elide: Text.ElideRight
                    }

                    ThemedButton {
                        text: root.editing ? "Done" : "Edit"
                        accent: root.editing
                        implicitHeight: 28
                        enabled: !root.showingLive
                        hoverEnabled: true
                        HoverHandler { id: editHover }
                        ToolTip.visible: editHover.hovered && root.showingLive
                        ToolTip.text: "Save it as a preset to edit it — the live capture stays as Mudae printed it"
                        onClicked: {
                            if (root.editing)
                                root.stopEditing()
                            else
                                root.editing = true
                        }
                    }
                }

                // ---- add (edit mode) ----
                RowLayout {
                    Layout.fillWidth: true
                    visible: root.editing
                    spacing: 6

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 62
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        TextArea {
                            id: addField
                            width: parent.width
                            wrapMode: TextArea.Wrap
                            selectByMouse: true
                            color: Theme.fg
                            font.pixelSize: Theme.sizeSmall
                            placeholderTextColor: Theme.mute
                            placeholderText: root.kind === "dl"
                                ? "Kadokawa Corporation$Shueisha$Kodansha\n$togglewestern   ·   one command or list per line"
                                : (root.kind === "adl"
                                   ? "Cyberpunk: Edgerunners$Lord of the Mysteries   ·   or one per line"
                                   : root.kind === "sdl"
                                   ? "Character names: Abra$Absol$Acerola   ·   or one per line (not series)"
                                   : "$swl Reze$Lucy   ·   $wishk Makima   ·   $wishli 4$Power\nor plain names: Power$Makima   ·   one command per line")
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.inputBg
                                border.color: addField.activeFocus ? Theme.accentPrimary : Theme.border
                                border.width: 1
                            }
                            // Enter adds; Shift+Enter starts a new line.
                            Keys.onReturnPressed: (event) => {
                                if (event.modifiers & Qt.ShiftModifier)
                                    event.accepted = false
                                else
                                    addButton.clicked()
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 4
                        Layout.alignment: Qt.AlignTop

                        ThemedButton {
                            id: addButton
                            text: "Add"
                            accent: true
                            implicitHeight: 28
                            enabled: addField.text.trim() !== ""
                            onClicked: {
                                var r = {}
                                try {
                                    r = JSON.parse(App.applyMudaeListInput(root.kind, root.selectedId, addField.text))
                                } catch (e) {
                                    r = { added: 0, updated: 0, toggles: 0, ignored: [] }
                                }
                                var bits = ["added " + r.added]
                                if (r.updated) bits.push(r.updated + " already listed — flags/position updated")
                                if (r.toggles) bits.push(r.toggles + " toggle" + (r.toggles > 1 ? "s" : ""))
                                if ((r.ignored || []).length) bits.push("not understood: " + r.ignored.join(", "))
                                root.addNote = bits.join(" · ")
                                if (r.added + r.updated + r.toggles > 0)
                                    addField.text = ""
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.editing && root.addNote !== ""
                    text: root.addNote
                    color: root.addNote.indexOf("not understood") >= 0 ? Theme.warn : Theme.good
                    font.pixelSize: Theme.sizeTiny
                    wrapMode: Text.WordWrap
                }

                // Not fetched yet for this pair.
                Label {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.hasData
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.WordWrap
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                    text: !root.listsData.scoped_ready
                        ? "Pick an account and a server above."
                        : ("Nothing fetched for this account and server yet. Fetch "
                           + root.kindInfo.fetchLabel + " reads every page of it"
                           + ((root.kind === "wl" || root.kind === "sdl")
                              ? (root.listsData.allow_dms
                                 ? " (by DM" + (root.kind === "sdl" ? ", $sdls — Mudae can pause while mailing a long list" : "") + ")."
                                 : " (page by page in the channel" + (root.kind === "sdl" ? " — up to 67 pages; turning on Mudae DMs in Settings is much quicker" : "") + ").")
                              : "."))
                }

                // ---- $dl summary ----
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.hasData && root.kind === "dl"
                    spacing: 6

                    // Totals. Limits are not shown: they differ per server and
                    // the list does not depend on them. On a preset they are
                    // the user's to type, or to leave blank.
                    GridLayout {
                        Layout.fillWidth: true
                        visible: root.editing || root.dlHasTotals
                        columns: 5
                        columnSpacing: 1
                        rowSpacing: 1

                        Repeater {
                            model: root.kind === "dl" ? [
                                { label: "disabled · all pools", field: "total", value: root.view.total, total: true },
                                { label: "$wa", field: "wa", value: (root.view.pools || {}).wa },
                                { label: "$ha", field: "ha", value: (root.view.pools || {}).ha },
                                { label: "$wg", field: "wg", value: (root.view.pools || {}).wg },
                                { label: "$hg", field: "hg", value: (root.view.pools || {}).hg }
                            ] : []

                            delegate: CountTile {
                                required property var modelData
                                Layout.fillWidth: true
                                label: modelData.label
                                field: modelData.field
                                value: modelData.value
                                total: !!modelData.total
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        spacing: 14

                        Label {
                            text: Theme.sectionLabel("Toggles · " + (root.view.toggles || []).length)
                            color: Theme.mute
                            font.pixelSize: Theme.sizeMicro
                        }

                        // The toggles Mudae is known to print, ticked on or off.
                        Repeater {
                            model: root.editing ? root.knownToggles : []
                            delegate: ThemedCheckBox {
                                required property var modelData
                                text: modelData.label + "  " + modelData.command
                                textSize: Theme.sizeSmall
                                checked: root.hasToggle(modelData.command)
                                onToggled: App.setMudaeListToggle(root.kind, root.selectedId, modelData.command, checked)
                            }
                        }
                    }

                    Label {
                        visible: !root.editing && (root.view.toggles || []).length === 0
                        text: "No whole-category toggles."
                        color: Theme.mute
                        font.pixelSize: Theme.sizeSmall
                    }

                    Repeater {
                        model: root.kind === "dl" ? (root.view.toggles || []) : []
                        delegate: Rectangle {
                            id: toggleRow
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            implicitHeight: 30
                            radius: Theme.radiusSm
                            color: "transparent"
                            border.width: 1
                            border.color: Theme.accent2

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 10
                                Label {
                                    Layout.fillWidth: true
                                    text: toggleRow.modelData.name + " are completely disabled"
                                    color: Theme.fg
                                    font.pixelSize: Theme.sizeSmall
                                    elide: Text.ElideRight
                                }
                                Label {
                                    text: toggleRow.modelData.command
                                    color: Theme.accent2
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeSmall
                                }
                                RowAction {
                                    visible: root.editing
                                    text: "×"
                                    tip: "Remove this toggle from the preset"
                                    onClicked: App.removeMudaeListToggle(root.kind, root.selectedId, toggleRow.index)
                                }
                            }
                        }
                    }
                }

                // ---- $adl summary ----
                RowLayout {
                    id: adlRow
                    Layout.fillWidth: true
                    // Never stretch: fillHeight on a child would propagate up
                    // and pull the tiles to the full panel height.
                    Layout.fillHeight: false
                    visible: root.hasData && root.kind === "adl"
                    spacing: 1
                    readonly property real tileHeight: Math.max(charTile.implicitHeight, slotTile.implicitHeight)

                    CountTile {
                        id: charTile
                        Layout.fillWidth: true
                        Layout.preferredHeight: adlRow.tileHeight
                        label: "antidisabled characters"
                        field: "characters"
                        value: root.view.characters
                        total: true
                        placeholder: "optional"
                    }

                    // Series slots are never typed: they are the rows below.
                    CountTile {
                        id: slotTile
                        Layout.fillWidth: true
                        Layout.preferredHeight: adlRow.tileHeight
                        label: "series slots"
                        field: ""
                        value: root.view.used
                        maxValue: root.showingLive ? root.view.max : null
                        sub: root.editing ? "counted from the list" : ""
                    }
                }

                // ---- rows ----
                RowLayout {
                    Layout.fillWidth: true
                    visible: root.hasData
                    Label {
                        text: Theme.sectionLabel(root.rowNoun)
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: root.kind === "dl"
                            ? root.entries.length + (root.view.used ? " of " + root.view.used : "") + " · names only"
                            : root.kind === "sdl"
                            ? root.entries.length + " · character names only"
                            : root.entries.length + " in Mudae's order" + (root.kind === "wl" ? " ·" : "")
                        color: Theme.mute
                        font.pixelSize: Theme.sizeTiny
                    }
                    Mark {
                        visible: root.kind === "wl"
                        text: "⭐"
                        font.pixelSize: Theme.sizeTiny
                    }
                    Label {
                        visible: root.kind === "wl"
                        text: "starwish  "
                        color: Theme.mute
                        font.pixelSize: Theme.sizeTiny
                    }
                    Mark {
                        visible: root.kind === "wl"
                        text: "🔐"
                        font.pixelSize: Theme.sizeTiny
                    }
                    Label {
                        visible: root.kind === "wl"
                        text: "locked"
                        color: Theme.mute
                        font.pixelSize: Theme.sizeTiny
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.hasData
                    color: "transparent"
                    border.color: Theme.line
                    border.width: 1
                    radius: Theme.radiusSm
                    clip: true

                    ListView {
                        id: rows
                        anchors.fill: parent
                        anchors.margins: 1
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        // The list must not flick while a row is being dragged.
                        interactive: root.dragFrom < 0
                        model: root.hasData ? root.entries : []
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        Label {
                            anchors.centerIn: parent
                            width: parent.width - 40
                            visible: root.hasData && rows.count === 0
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            color: Theme.mute
                            font.pixelSize: Theme.sizeSmall
                            text: root.editing
                                ? "Empty — paste names above, separated by $ or one per line."
                                : (root.showingLive ? "Mudae's list is empty." : "This preset is empty. Press Edit to add names.")
                        }

                        delegate: Rectangle {
                            id: row
                            required property var modelData
                            required property int index
                            readonly property bool isWish: root.kind === "wl" && typeof modelData !== "string"
                            readonly property bool renaming: root.editing && root.renamingIndex === index

                            width: ListView.view.width
                            height: renaming ? 32 : 26
                            color: root.dragFrom === index ? Theme.raised
                                : (index % 2 === 0 ? Theme.bg : Theme.surface)
                            opacity: root.dragFrom === index ? 0.6 : 1

                            // Where the dragged row would land: a line on the
                            // side of this row it would end up.
                            Rectangle {
                                visible: root.dragFrom >= 0 && root.dragTo === row.index && root.dragTo !== root.dragFrom
                                anchors.left: parent.left
                                anchors.right: parent.right
                                height: 2
                                y: root.dragTo > root.dragFrom ? parent.height - 2 : 0
                                color: Theme.accent
                                z: 2
                            }

                            function commitRename() {
                                if (App.renameMudaeListEntry(root.kind, root.selectedId, row.index, renameField.text))
                                    root.renamingIndex = -1
                                else
                                    renameField.selectAll()   // blank, or already listed
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8

                                // Drag handle (edit mode). The row is moved on
                                // release; while dragging, a line marks the drop.
                                Label {
                                    visible: root.editing
                                    text: "≡"
                                    color: gripMouse.containsMouse || root.dragFrom === row.index ? Theme.accent : Theme.mute
                                    font.pixelSize: Theme.sizeLarge
                                    Layout.preferredWidth: 14

                                    MouseArea {
                                        id: gripMouse
                                        anchors.fill: parent
                                        anchors.margins: -4
                                        hoverEnabled: true
                                        preventStealing: true
                                        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                        onPressed: {
                                            root.renamingIndex = -1
                                            root.dragFrom = row.index
                                            root.dragTo = row.index
                                        }
                                        onPositionChanged: (mouse) => {
                                            if (root.dragFrom < 0)
                                                return
                                            var p = mapToItem(rows, mouse.x, mouse.y)
                                            root.dragPointerY = p.y
                                            root.updateDropTarget(p.y)
                                        }
                                        onReleased: root.finishDrag()
                                        onCanceled: { root.dragFrom = -1; root.dragTo = -1 }
                                    }
                                }

                                Label {
                                    Layout.preferredWidth: 28
                                    text: String(row.index + 1)
                                    color: Theme.mute
                                    font.pixelSize: Theme.sizeTiny
                                    horizontalAlignment: Text.AlignRight
                                }

                                // Starwish mark sits before the name, so the
                                // starwishes read as a column without a split.
                                Mark {
                                    visible: root.kind === "wl" && !root.editing
                                    Layout.preferredWidth: 16
                                    text: row.isWish && row.modelData.starwish ? "⭐" : ""
                                }
                                FlagToggle {
                                    visible: root.kind === "wl" && root.editing
                                    on: row.isWish && !!row.modelData.starwish
                                    glyph: "⭐"
                                    tip: "Starwish"
                                    onToggled: App.setMudaeListEntryFlag(root.kind, root.selectedId, row.index, "starwish", !on)
                                }

                                Label {
                                    visible: !row.renaming
                                    Layout.fillWidth: true
                                    text: root.entryName(row.modelData)
                                    color: Theme.fg
                                    font.pixelSize: Theme.sizeSmall
                                    font.weight: row.isWish && row.modelData.starwish ? Font.DemiBold : Font.Normal
                                    elide: Text.ElideRight

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: root.editing
                                        onDoubleClicked: {
                                            root.renamingIndex = row.index
                                        }
                                    }
                                }

                                ThemedTextField {
                                    id: renameField
                                    visible: row.renaming
                                    Layout.fillWidth: true
                                    implicitHeight: 26
                                    font.pixelSize: Theme.sizeSmall
                                    onVisibleChanged: if (visible) {
                                        text = root.entryName(row.modelData)
                                        forceActiveFocus()
                                        selectAll()
                                    }
                                    onAccepted: row.commitRename()
                                    Keys.onEscapePressed: root.renamingIndex = -1
                                }

                                RowAction {
                                    visible: row.renaming
                                    text: "save"
                                    onClicked: row.commitRename()
                                }
                                RowAction {
                                    visible: row.renaming
                                    text: "cancel"
                                    onClicked: root.renamingIndex = -1
                                }

                                FlagToggle {
                                    visible: root.kind === "wl" && root.editing && !row.renaming
                                    on: row.isWish && !!row.modelData.locked
                                    glyph: "🔐"
                                    tip: "Locked wish ($wishl) — kept by $wp and $wpx"
                                    onToggled: App.setMudaeListEntryFlag(root.kind, root.selectedId, row.index, "locked", !on)
                                }
                                FlagToggle {
                                    visible: root.kind === "wl" && root.editing && !row.renaming
                                    on: row.isWish && !!row.modelData.kakera_wish
                                    kakera: true
                                    tip: "Kakera wish ($wishk)"
                                    onToggled: App.setMudaeListEntryFlag(root.kind, root.selectedId, row.index, "kakera_wish", !on)
                                }

                                RowLayout {
                                    visible: root.editing && !row.renaming
                                    spacing: 10
                                    Layout.leftMargin: 6
                                    RowAction {
                                        text: "rename"
                                        onClicked: root.renamingIndex = row.index
                                    }
                                    RowAction {
                                        text: "×"
                                        tip: "Remove"
                                        onClicked: {
                                            root.renamingIndex = -1
                                            App.removeMudaeListEntry(root.kind, root.selectedId, row.index)
                                        }
                                    }
                                }

                                Mark {
                                    visible: row.isWish && !!row.modelData.locked && !root.editing
                                    text: "🔐"
                                    ToolTip.visible: lockHover.hovered
                                    ToolTip.text: "Locked wish — kept by $wp and $wpx"
                                    HoverHandler { id: lockHover }
                                }

                                Image {
                                    visible: row.isWish && !!row.modelData.kakera_wish && !root.editing
                                    source: MudaeEmoji.assetBase + "Kakera.png"
                                    sourceSize.width: 16
                                    sourceSize.height: 16
                                    Layout.preferredWidth: 14
                                    Layout.preferredHeight: 14
                                    fillMode: Image.PreserveAspectFit
                                    ToolTip.visible: kakHover.hovered
                                    ToolTip.text: "Kakera wish ($wishk) — no ping, not a wish for wishprotect"
                                    HoverHandler { id: kakHover }
                                }

                                Mark {
                                    visible: row.isWish && !!row.modelData.owned
                                    text: "✅"
                                }

                                Mark {
                                    visible: row.isWish && !!row.modelData.server_disabled
                                    text: "🚫"
                                    ToolTip.visible: sdHover.hovered
                                    ToolTip.text: "Disabled on this server ($serverdisable)"
                                    HoverHandler { id: sdHover }
                                }

                                Label {
                                    visible: row.isWish && row.modelData.sphere_percent !== null && row.modelData.sphere_percent !== undefined
                                    text: row.isWish && row.modelData.sphere_percent ? "+" + row.modelData.sphere_percent + "%" : ""
                                    color: Theme.mute
                                    font.pixelSize: Theme.sizeTiny
                                    Layout.preferredWidth: 42
                                    horizontalAlignment: Text.AlignRight
                                }
                            }
                        }
                    }
                }

                // ---- send progress / result ----
                Label {
                    Layout.fillWidth: true
                    visible: root.sendState.kind === root.kind && (!!root.sendState.running || !!root.sendState.message)
                    wrapMode: Text.WordWrap
                    font.pixelSize: Theme.sizeSmall
                    color: root.sendState.running ? Theme.dim
                        : (root.sendState.ok ? Theme.good : Theme.warn)
                    text: root.sendState.running
                        ? "Sending to Mudae — " + (root.sendState.progress || "")
                        : (root.sendState.message || "")
                }

                // ---- actions ----
                RowLayout {
                    Layout.fillWidth: true
                    visible: root.hasData
                    spacing: 8

                    ThemedButton {
                        text: "Copy list"
                        implicitHeight: 28
                        enabled: root.entries.length > 0
                        onClicked: {
                            App.copyToClipboard(root.copyText())
                            root.copiedNote = "Copied " + root.entries.length + " names"
                            copiedTimer.restart()
                        }
                    }

                    ThemedButton {
                        text: "Copy command"
                        implicitHeight: 28
                        enabled: root.entries.length > 0 || (root.kind === "dl" && (root.view.toggles || []).length > 0)
                        hoverEnabled: true
                        ToolTip.visible: hovered
                        ToolTip.text: "The Mudae commands that rebuild this list, in order"
                        ToolTip.delay: 400
                        onClicked: root.openCommands()
                    }

                    Label {
                        text: root.copiedNote !== "" ? root.copiedNote : "list: names joined with $"
                        color: root.copiedNote !== "" ? Theme.good : Theme.mute
                        font.pixelSize: Theme.sizeTiny
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    ThemedButton {
                        text: root.sendingThis ? "Sending…" : "Send to Mudae"
                        loading: root.sendingThis
                        accent: !root.showingLive && !root.sendState.running
                        implicitHeight: 28
                        enabled: !root.showingLive && !root.sendState.running && !root.editing
                        hoverEnabled: true
                        // A disabled control gets no hover, so the tooltip
                        // hangs off a handler that does.
                        HoverHandler { id: sendHover }
                        ToolTip.visible: sendHover.hovered
                        ToolTip.text: root.showingLive
                            ? "Pick a saved preset — this is already what Mudae has"
                            : (root.editing ? "Press Done first" : "Clear this list on Mudae and add the preset back")
                        onClicked: root.requestSend()
                    }
                }
            }
        }
    }
}
