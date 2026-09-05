import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Advisor › $bw — rolls spent against wish spawns bought.

    `$bw N` locks N of the hour's rolls in exchange for a spawn bonus on
    wishlist characters, so it is a straight trade with a peak somewhere in the
    middle. The sweep is `macro/bw_calc.py`; this page is its inputs, its curve
    and its evidence.

    Laid out around the one thing anyone opens it for: **where the peaks are**.
    There are three, because a starwish's bonus grows faster than a plain wish's
    and a single character's faster still, so they stop wanting more `$bw` at
    different points — and which of the three you care about depends on what you
    are trying to farm. They lead the page; the sweep that produced them sits
    below as a table beside its curve; the inputs that shift them sit at the
    bottom, because they are set once and then left alone.

    The character picker is at the top rather than among the inputs: it changes
    the third headline answer, so it belongs with the answers.

    It reads four sheets, each fetched separately, so the evidence row lists them
    with a fetch beside any that is missing. That is also why this page's fetch
    buttons are in the body rather than in the scope bar like Mudae's and
    Spheres': those hubs own one sheet per pill, and this one consumes four.

    Nothing here sends `$bw`. It is advisory — the command is shown to copy.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""

    readonly property var emptyPayload: ({
        bw: { available: false, sweep: { available: false, points: [] },
              inputs: {}, options: {}, notes: [], perk1_check: {} },
        keys: {}
    })

    property var payload: emptyPayload
    property var wishlist: ({ entries: [] })

    readonly property var bw: payload.bw || {}
    readonly property var sweep: bw.sweep || { available: false, points: [] }
    readonly property var options: bw.options || {}
    readonly property var sheets: bw.inputs || {}

    readonly property var entries: wishlist.entries || []

    readonly property var focusRow: {
        var wanted = root.options.focus_name || ""
        if (!wanted)
            return null
        for (var i = 0; i < entries.length; i++) {
            if (entries[i].name === wanted)
                return entries[i]
        }
        return null
    }

    // The columns `bwcalc` prints, in its order. "sel" is the selected
    // character; its two columns show a dash until one is picked.
    // Every column is sized to its own widest value rather than sharing the
    // panel's slack: six numbers spread across a half-page leaves the eye
    // travelling between them, and the width saved goes to the curve, which
    // actually uses it. Sized for the uppercase headers, which are wider than
    // the figures under them in every shell that capitalises them.
    // The panel title carries the "keys/hr" unit, so the two keys columns drop
    // it — Console tracks its uppercase labels wide enough that the full names
    // ran into each other.
    readonly property var tableColumns: [
        { label: "$bw", width: 36 },
        { label: "rolls/hr", width: 62 },
        { label: "wl/hr", width: 58 },
        { label: "sel/hr", width: 58 },
        { label: "wl keys", width: 68 },
        { label: "sel keys", width: 74 }
    ]
    readonly property int tableWidth: 386

    function refresh() {
        if (!channelProfileId || !accountId) {
            payload = emptyPayload
            wishlist = { entries: [] }
            return
        }
        try {
            payload = JSON.parse(App.advisorJson(channelProfileId, accountId))
        } catch (e) {
            payload = emptyPayload
        }
        try {
            wishlist = JSON.parse(App.mudaeWishlistFor(accountId, channelProfileId))
        } catch (e2) {
            wishlist = { entries: [] }
        }
    }

    function setOption(key, value) {
        var patch = {}
        patch[key] = value
        App.setBwOptions(channelProfileId, accountId, JSON.stringify(patch))
    }

    function fmt(n, places) {
        if (n === null || n === undefined)
            return "—"
        return Number(n).toLocaleString(Qt.locale(), "f", places === undefined ? 0 : places)
    }

    // "on it" / "-4 from here" — how far the current setting is from a peak.
    function distanceFrom(bwValue) {
        if (!root.sweep.available || bwValue === null || bwValue === undefined)
            return ""
        var delta = bwValue - root.sweep.current_bw
        if (delta === 0)
            return "you are on it"
        return (delta > 0 ? "+" : "") + delta + " from your $bw"
    }

    onChannelProfileIdChanged: refresh()
    onAccountIdChanged: refresh()
    Component.onCompleted: refresh()

    Connections {
        target: App
        function onServersChanged() { root.refresh() }
        function onMudaeWishlistChanged() { root.refresh() }
        function onBwOptionsChanged() { root.refresh() }
        function onScopeFetchChanged() { root.refresh() }
    }

    ScrollablePage {
        anchors.fill: parent
        contentSpacing: Theme.gap

        // --- Focus character, and the run's own numbers in passing ------------

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 46
            // Matches `components/PanelCard.qml` so it sits level with every
            // other panel on the page in all four shells.
            color: Theme.bgMedium
            border.width: 1
            border.color: Theme.border
            radius: Theme.radiusLg

            Rectangle {
                visible: Theme.doubleBorder
                anchors.fill: parent
                anchors.margins: 2
                radius: Theme.radiusLg
                color: "transparent"
                border.width: 1
                border.color: Theme.border
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.cardPadding
                anchors.rightMargin: Theme.cardPadding
                spacing: 10

                Label {
                    text: Theme.sectionLabel("character")
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    font.weight: Font.DemiBold
                    font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                }

                CharacterPicker {
                    Layout.preferredWidth: 260
                    Layout.fillWidth: false
                    entries: root.entries
                    selectedName: root.options.focus_name || ""
                    onPicked: function (name) { root.setOption("focus_name", name) }
                }

                // Mudae's own starwish mark, drawn rather than spelled, so it
                // reads the same here as on the `$wl` row it came from.
                Image {
                    visible: !!(root.focusRow && root.focusRow.starwish)
                    source: MudaeEmoji.urlFor("starwish")
                    sourceSize.width: 14
                    sourceSize.height: 14
                    Layout.preferredWidth: 14
                    Layout.preferredHeight: 14
                    Layout.leftMargin: 2
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }

                // What the selection actually is, so the third peak card's
                // number has a visible reason beside it.
                Label {
                    Layout.fillWidth: true
                    text: {
                        if (!root.focusRow)
                            return root.entries.length > 0
                                   ? "all " + root.entries.length + " wishlist characters"
                                   : ""
                        var bits = []
                        if (root.focusRow.starwish)
                            bits.push("starwish")
                        var p1 = Number(root.focusRow.sphere_percent || 0)
                        if (p1 > 0)
                            bits.push("perk 1 +" + p1 + "%")
                        var ups = root.focusRow.upgrades || {}
                        var p4 = root.focusRow.upgrades_full
                                 ? 6 : Number(ups["4"] || 0)
                        if (p4 > 0)
                            bits.push("perk 4 lv" + p4)
                        bits.push(root.fmt(root.focusRow.spheres) + " sp")
                        return bits.join(" · ")
                    }
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    elide: Text.ElideRight
                }

                // The old headline tiles, reduced to a strip: they are context
                // for the peaks above, not answers in their own right.
                Label {
                    visible: root.bw.available
                    text: "$bw " + root.bw.bw_penalty + "  ·  " + root.bw.net
                          + " net rolls/hr  ·  " + root.fmt(root.bw.rolls_lost_per_day)
                          + " rolls/day spent"
                    color: Theme.mute
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeMicro
                }
            }
        }

        // --- The three peaks --------------------------------------------------

        Label {
            Layout.fillWidth: true
            visible: !root.sweep.available
            text: root.sweep.blocked_by
                  || "Fetch $bonus and $wl for this account and server to find the peaks."
            color: Theme.mute
            font.pixelSize: Theme.sizeSmall
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.sweep.available
            spacing: Theme.gap

            Repeater {
                model: {
                    if (!root.sweep.available)
                        return []
                    var rows = [{
                        heading: "whole wishlist",
                        accent: Theme.good,
                        bw: root.sweep.best_total_bw,
                        keys: root.sweep.best_total.total_keys_per_hour,
                        places: 3,
                        lines: [
                            Number(root.sweep.best_total.wl_spawns_per_hour).toFixed(2)
                            + " wishlist spawns/hr",
                            (100 * root.sweep.best_total.wl_share_of_rolls).toFixed(1)
                            + "% of net rolls land on one"
                        ]
                    }]
                    if (root.sweep.best_starwish)
                        rows.push({
                            heading: "starwishes",
                            accent: Theme.warn,
                            bw: root.sweep.best_starwish_bw,
                            keys: root.sweep.best_starwish.sw_keys_per_hour,
                            places: 3,
                            lines: [
                                Number(root.sweep.best_starwish.sw_spawns_per_hour).toFixed(2)
                                + " starwish spawns/hr",
                                (100 * root.sweep.best_starwish.sw_share_of_rolls).toFixed(1)
                                + "% of net rolls land on one"
                            ]
                        })
                    if (root.sweep.best_focus && root.sweep.focus_name)
                        rows.push({
                            heading: root.sweep.focus_name,
                            accent: Theme.accent2,
                            bw: root.sweep.best_focus_bw,
                            keys: root.sweep.best_focus.focus_keys_per_hour,
                            places: 3,
                            lines: [
                                Number(root.sweep.best_focus.focus_spawns_per_hour).toFixed(3)
                                + " spawns/hr",
                                "spawns 1 in "
                                + Math.round(root.sweep.best_focus.focus_one_in_rolls)
                                + " rolls"
                            ]
                        })
                    else
                        rows.push({ heading: "one character", accent: Theme.line,
                                    bw: null, keys: null, places: 3, lines: [] })
                    return rows
                }

                delegate: Rectangle {
                    required property var modelData

                    readonly property bool pending: modelData.bw === null
                    readonly property bool onIt: !pending
                                                 && modelData.bw === root.sweep.current_bw

                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    implicitHeight: 132
                    // Deliberately the same chrome as `components/PanelCard.qml`
                    // rather than a shape of its own: a fixed `Theme.borderWidth`
                    // is 3px in Boxed, and against panels that rule themselves at
                    // 1px these read as a heavier, misaligned box. Only the border
                    // *colour* carries the card's identity.
                    color: Theme.bgMedium
                    radius: Theme.radiusLg
                    border.width: 1
                    border.color: pending ? Theme.border : modelData.accent

                    // Boxed rules its panels twice; a single stroke here would
                    // sit a rule short of everything around it.
                    Rectangle {
                        visible: Theme.doubleBorder
                        anchors.fill: parent
                        anchors.margins: 2
                        radius: Theme.radiusLg
                        color: "transparent"
                        border.width: 1
                        border.color: parent.pending ? Theme.border : modelData.accent
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.cardPadding
                        spacing: 2

                        Label {
                            Layout.fillWidth: true
                            text: Theme.sectionLabel("optimal $bw · " + modelData.heading)
                            color: parent.parent.pending ? Theme.mute : modelData.accent
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: parent.parent.parent.pending
                                      ? "—" : String(modelData.bw)
                                color: parent.parent.parent.pending ? Theme.mute : Theme.fg
                                font.family: Theme.monoFamily
                                font.pixelSize: 34
                                font.weight: Font.Medium
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignBottom
                                Layout.bottomMargin: 5
                                spacing: 0

                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.keys === null
                                          ? "" : Number(modelData.keys).toFixed(modelData.places)
                                    color: Theme.fg
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeLarge
                                    elide: Text.ElideRight
                                }

                                Label {
                                    text: modelData.keys === null ? "" : "keys / hour"
                                    color: Theme.mute
                                    font.pixelSize: Theme.sizeMicro
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }

                        Label {
                            Layout.fillWidth: true
                            visible: parent.parent.pending
                            text: "Pick a character above to see where its own EV peaks — "
                                  + "it is usually lower than the wishlist's."
                            color: Theme.mute
                            font.pixelSize: Theme.sizeMicro
                            wrapMode: Text.WordWrap
                        }

                        Repeater {
                            model: modelData.lines
                            delegate: Label {
                                required property var modelData

                                Layout.fillWidth: true
                                text: modelData
                                color: Theme.mute
                                font.pixelSize: Theme.sizeMicro
                                elide: Text.ElideRight
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.topMargin: 3
                            visible: !parent.parent.pending
                            text: parent.parent.onIt
                                  ? "✓ " + root.distanceFrom(modelData.bw)
                                  : root.distanceFrom(modelData.bw)
                            color: parent.parent.onIt ? Theme.good : Theme.dim
                            font.pixelSize: Theme.sizeMicro
                        }
                    }
                }
            }
        }

        // --- The sweep: table beside its curve --------------------------------

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 470
            visible: root.sweep.available
            spacing: Theme.gap

            PanelCard {
                // Sized to its own columns rather than to a share of the row,
                // so everything left over goes to the chart.
                Layout.preferredWidth: root.tableWidth + Theme.cardPadding * 2 + 14
                Layout.fillWidth: false
                Layout.fillHeight: true
                title: "EV keys/hr vs $bw"
                titleSize: Theme.sizeMedium
                fillContentVertically: true

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Repeater {
                        model: root.tableColumns
                        delegate: Label {
                            required property var modelData

                            Layout.preferredWidth: modelData.width
                            Layout.fillWidth: false
                            horizontalAlignment: Text.AlignRight
                            text: Theme.sectionLabel(modelData.label)
                            color: Theme.mute
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                            elide: Text.ElideRight
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.line
                }

                // Every `$bw` the pool allows, with the rows worth looking at
                // tinted. Opens on the current setting rather than at 0, which
                // is fifteen rows away from anything anyone came here to read.
                ListView {
                    id: sweepTable
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: root.sweep.points || []
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    function showCurrent() {
                        if (count > 0)
                            positionViewAtIndex(
                                Math.max(0, (root.sweep.current_bw || 0) - 6),
                                ListView.Beginning)
                    }

                    onCountChanged: showCurrent()
                    Component.onCompleted: showCurrent()

                    delegate: Rectangle {
                        required property var modelData

                        readonly property bool isCurrent:
                            modelData.bw === root.sweep.current_bw
                        readonly property bool isBestTotal:
                            modelData.bw === root.sweep.best_total_bw
                        readonly property bool isBestStarwish:
                            modelData.bw === root.sweep.best_starwish_bw
                        readonly property bool isBestFocus:
                            root.sweep.focus_name !== ""
                            && modelData.bw === root.sweep.best_focus_bw

                        width: sweepTable.width
                        height: 23
                        color: isBestTotal
                               ? Qt.rgba(Theme.good.r, Theme.good.g, Theme.good.b, 0.15)
                               : isBestFocus
                                 ? Qt.rgba(Theme.accent2.r, Theme.accent2.g,
                                           Theme.accent2.b, 0.15)
                                 : isBestStarwish
                                   ? Qt.rgba(Theme.warn.r, Theme.warn.g, Theme.warn.b, 0.13)
                                   : isCurrent
                                     ? Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.07)
                                     : "transparent"

                        // Marks the row you are actually on, which can coincide
                        // with a peak and would otherwise be invisible under it.
                        Rectangle {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            width: 2
                            visible: parent.isCurrent
                            color: Theme.fg
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 4
                            spacing: 6

                            Repeater {
                                model: [
                                    String(modelData.bw),
                                    String(modelData.net_rolls),
                                    Number(modelData.wl_spawns_per_hour).toFixed(3),
                                    modelData.focus_spawns_per_hour === null
                                        ? "—"
                                        : Number(modelData.focus_spawns_per_hour).toFixed(3),
                                    Number(modelData.total_keys_per_hour).toFixed(3),
                                    modelData.focus_keys_per_hour === null
                                        ? "—"
                                        : Number(modelData.focus_keys_per_hour).toFixed(3)
                                ]

                                delegate: Label {
                                    required property var modelData
                                    required property int index

                                    Layout.preferredWidth: root.tableColumns[index].width
                                    Layout.fillWidth: false
                                    horizontalAlignment: Text.AlignRight
                                    verticalAlignment: Text.AlignVCenter
                                    text: modelData
                                    color: index === 0 ? Theme.accent2 : Theme.fg
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeSmall
                                }
                            }

                            Item { Layout.fillWidth: true }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Repeater {
                        model: {
                            if (!root.sweep.available)
                                return []
                            var keys = [{ label: "your $bw", colour: Theme.fg },
                                        { label: "wishlist", colour: Theme.good }]
                            if (root.sweep.best_starwish_bw !== null
                                    && root.sweep.best_starwish_bw !== undefined)
                                keys.push({ label: "starwishes", colour: Theme.warn })
                            if (root.sweep.focus_name)
                                keys.push({ label: root.sweep.focus_name,
                                            colour: Theme.accent2 })
                            return keys
                        }

                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: false
                            spacing: 4

                            Rectangle {
                                implicitWidth: 8
                                implicitHeight: 8
                                radius: 2
                                color: Qt.rgba(modelData.colour.r, modelData.colour.g,
                                               modelData.colour.b, 0.4)
                                border.width: 1
                                border.color: modelData.colour
                            }

                            Label {
                                text: modelData.label
                                color: Theme.mute
                                font.pixelSize: Theme.sizeMicro
                                elide: Text.ElideRight
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }
                }
            }

            PanelCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: "The curve"
                titleSize: Theme.sizeMedium
                fillContentVertically: true

                BwSweepChart {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    points: root.sweep.points || []
                    currentBw: root.sweep.available ? root.sweep.current_bw : -1
                    bestTotalBw: root.sweep.available ? root.sweep.best_total_bw : -1
                    bestStarwishBw: root.sweep.best_starwish_bw === null
                                    || root.sweep.best_starwish_bw === undefined
                                    ? -1 : root.sweep.best_starwish_bw
                    bestFocusBw: root.sweep.best_focus_bw === null
                                 || root.sweep.best_focus_bw === undefined
                                 ? -1 : root.sweep.best_focus_bw
                    focusName: root.sweep.focus_name || ""
                }

                Label {
                    Layout.fillWidth: true
                    text: "Advisory only — nothing here sends $bw. Set it yourself with  $bw "
                          + (root.sweep.available ? root.sweep.best_total_bw : 0)
                    color: Theme.dim
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }
        }

        // --- Inputs and evidence, both set-once ------------------------------

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap

            PanelCard {
                Layout.fillWidth: true
                Layout.preferredWidth: 4
                Layout.alignment: Qt.AlignTop
                title: "Inputs no sheet answers"
                titleSize: Theme.sizeMedium

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 10
                    rowSpacing: 8

                    Label {
                        text: "Base pool"
                        color: Theme.fg
                        font.pixelSize: Theme.sizeSmall
                    }

                    ThemedSpinBox {
                        Layout.fillWidth: true
                        from: 1
                        to: 200000
                        stepSize: 100
                        editable: true
                        value: root.options.base_pool || 2000
                        onValueModified: root.setOption("base_pool", value)
                    }

                    Label {
                        text: "$persrare rerolls"
                        color: Theme.fg
                        font.pixelSize: Theme.sizeSmall
                    }

                    ThemedSpinBox {
                        Layout.fillWidth: true
                        from: 1
                        to: 20
                        value: root.options.persrare_n || 1
                        onValueModified: root.setOption("persrare_n", value)
                    }

                    Label {
                        text: "Claimed in pool"
                        color: Theme.fg
                        font.pixelSize: Theme.sizeSmall
                    }

                    ThemedSpinBox {
                        Layout.fillWidth: true
                        from: 0
                        to: 200000
                        stepSize: 100
                        value: root.options.claimed_pool || 0
                        onValueModified: root.setOption("claimed_pool", value)
                    }
                }

                ThemedCheckBox {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    text: "Rolls use slash commands"
                    textSize: Theme.sizeSmall
                    checked: !!root.options.uses_slash
                    onToggled: root.setOption("uses_slash", checked)
                }

                Label {
                    Layout.fillWidth: true
                    text: "Base pool is every rollable character outside your wishlist. It "
                          + "follows the server's game mode and disable lists, and nothing "
                          + "derives it yet — 2,000 is a placeholder, and it is what decides "
                          + "which $bw wins. $persrare comes from $ov, which has no parser; "
                          + "at 1 reroll the model is unchanged."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }

            PanelCard {
                Layout.fillWidth: true
                Layout.preferredWidth: 6
                Layout.alignment: Qt.AlignTop
                title: "Evidence"
                titleSize: Theme.sizeMedium

                Repeater {
                    model: [
                        { key: "bonus", label: "$bonus", command: "bonus",
                          commandLabel: "$bonus" },
                        { key: "wishlist", label: "$wl", command: "wishlist",
                          commandLabel: "$wl" },
                        { key: "shop", label: "$shop", command: "shop",
                          commandLabel: "$shop" },
                        { key: "settings", label: "$settings", command: "settings",
                          commandLabel: "$settings" }
                    ]

                    delegate: RowLayout {
                        required property var modelData

                        readonly property var sheet: root.sheets[modelData.key] || {}

                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        spacing: 8

                        Label {
                            Layout.preferredWidth: 62
                            text: modelData.label
                            color: Theme.accent2
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                        }

                        Label {
                            Layout.preferredWidth: 14
                            text: sheet.ready ? "✓" : (sheet.required ? "✕" : "–")
                            color: sheet.ready
                                   ? Theme.good
                                   : (sheet.required ? Theme.bad : Theme.mute)
                            font.pixelSize: Theme.sizeSmall
                        }

                        Label {
                            Layout.fillWidth: true
                            text: {
                                if (!sheet.ready)
                                    return sheet.why || ""
                                if (sheet.inferred)
                                    return "saved before sheets were per-account — re-fetch"
                                return sheet.read_at
                                       ? "read " + String(sheet.read_at).substring(0, 16)
                                         .replace("T", " ") + " UTC"
                                       : "stored"
                            }
                            color: sheet.inferred ? Theme.warn : Theme.mute
                            font.pixelSize: Theme.sizeMicro
                            elide: Text.ElideRight
                        }

                        ScopeFetchButton {
                            command: modelData.command
                            commandLabel: modelData.commandLabel
                            accountId: root.accountId
                            channelProfileId: root.channelProfileId
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    visible: (root.bw.perk1_check || {}).available === true
                    text: {
                        var check = root.bw.perk1_check || {}
                        if (check.agrees)
                            return "Perk 1: all " + check.total + " wishlist rows still match "
                                   + "what $shop OP1 (" + check.share_pct + "% shared) implies, "
                                   + "so the captured spawn bonuses are current."
                        return "Perk 1: only " + check.matches + " of " + check.total
                               + " rows match what $shop OP1 (" + check.share_pct
                               + "% shared) implies — the $wl capture predates a shop "
                               + "upgrade. Re-fetch $wl."
                    }
                    color: (root.bw.perk1_check || {}).agrees ? Theme.mute : Theme.warn
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }

                Repeater {
                    model: root.bw.notes || []

                    delegate: Label {
                        required property var modelData

                        Layout.fillWidth: true
                        text: "· " + modelData
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        wrapMode: Text.WordWrap
                    }
                }

                Label {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    text: "Spawn chance is a character's weight over the whole pool's, so read "
                          + "these as a comparison rather than a rate. The peak is flat: on a "
                          + "wishlist this size several $bw values sit within a percent of "
                          + "each other, and the base pool is what decides which one wins. "
                          + "Slash commands are not modelled — the macro rolls with $."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
