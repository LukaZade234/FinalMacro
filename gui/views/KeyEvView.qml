import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Advisor › Key EV — how many keys arrive, and what one is worth.

    The two halves are answerable to different degrees, and the page keeps them
    apart rather than blending them into one confident-looking number.

    **Production** is now real. `1` key is guaranteed on a wish spawn, `$bonus`
    gives the account-wide extra-key chance, and the `$wlsz+z!` capture gives
    each character's own perk 4. All three are independent, so the expectations
    add. `Advisor › $bw` multiplies this by spawn chance to get keys an hour;
    here it is per spawn, which is the part that does not depend on `$bw`.

    **Value** is not. A chaos key is priced because it halves the reaction-power
    cost of a kakera click, so its worth is the power saved at the account's own
    kakera-per-click — arithmetic that does not care what character it is on.
    Claim keys unlock a character, and nothing in the app models what a
    character returns, so they report their rate and abstain.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""

    readonly property var emptyPayload: ({
        keys: { available: false, rows: [], production: { available: false } },
        bw: {}
    })

    property var payload: emptyPayload

    readonly property var keys: payload.keys || {}
    readonly property var production: keys.production || { available: false }
    readonly property var rows: keys.rows || []

    readonly property real keysPerDay: {
        var total = 0
        for (var i = 0; i < rows.length; i++)
            total += Number(rows[i].per_day || 0)
        return total
    }

    readonly property var chaosRow: {
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].key_type === "chaos")
                return rows[i]
        }
        return null
    }

    // What perk 4 contributes on average, as the difference between the mean and
    // the two terms that apply to every character. Derived rather than sent so
    // the four figures on screen are guaranteed to add up.
    readonly property real meanPerk4: {
        if (!production.available)
            return 0
        return Number(production.mean_keys_per_spawn)
               - 1 - Number(production.global_extra_key_pct || 0) / 100
    }

    // Perk-4 levels present on the wishlist, biggest first — "who carries it"
    // is the useful shape, not a row per level including the empty ones.
    readonly property var perkLevels: {
        var out = []
        var byLevel = production.by_level || {}
        for (var key in byLevel) {
            var level = parseInt(key)
            if (level > 0)
                out.push({ level: level, count: byLevel[key] })
        }
        out.sort(function (a, b) { return b.level - a.level })
        return out
    }

    function refresh() {
        if (!channelProfileId || !accountId) {
            payload = emptyPayload
            return
        }
        try {
            payload = JSON.parse(App.advisorJson(channelProfileId, accountId))
        } catch (e) {
            payload = emptyPayload
        }
    }

    function pct(n) {
        return (n === null || n === undefined) ? "—" : Number(n).toFixed(0) + "%"
    }

    onChannelProfileIdChanged: refresh()
    onAccountIdChanged: refresh()
    Component.onCompleted: refresh()

    Connections {
        target: App
        function onServersChanged() { root.refresh() }
        function onMudaeWishlistChanged() { root.refresh() }
        function onKeysChanged() { root.refresh() }
        function onScopeFetchChanged() { root.refresh() }
    }

    ScrollablePage {
        anchors.fill: parent
        contentSpacing: Theme.gap

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap

            Repeater {
                model: [
                    {
                        label: "keys a day",
                        value: root.keys.available ? root.keysPerDay.toFixed(1) : "—",
                        note: root.keys.available ? "logged, last 14 days" : "no key log yet"
                    },
                    {
                        label: "keys per wish spawn",
                        value: root.production.available
                               ? Number(root.production.mean_keys_per_spawn).toFixed(2) : "—",
                        note: root.production.available
                              ? "up to " + Number(root.production.best_keys_per_spawn).toFixed(2)
                                + " on a maxed character"
                              : "needs $wl"
                    },
                    {
                        label: "chaos key",
                        value: root.chaosRow && root.chaosRow.priced
                               ? Number(root.chaosRow.value_kakera).toLocaleString(
                                     Qt.locale(), "f", 0)
                               : "—",
                        note: root.chaosRow && root.chaosRow.priced
                              ? "kakera per use" : "no logged clicks yet"
                    },
                    {
                        label: "carrying perk 4",
                        value: root.production.available
                               ? String(root.production.with_perk4) : "—",
                        note: root.production.available
                              ? "of " + root.production.characters + " wishlist characters"
                              : ""
                    }
                ]

                delegate: Rectangle {
                    required property var modelData

                    Layout.fillWidth: true
                    implicitHeight: 78
                    color: Theme.surface
                    border.width: Theme.borderWidth
                    border.color: Theme.line
                    radius: Theme.radiusMd

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.cardPadding
                        spacing: 3

                        Label {
                            text: Theme.sectionLabel(modelData.label)
                            color: Theme.mute
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                        }

                        Label {
                            text: modelData.value
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeTitle
                            font.weight: Font.Medium
                        }

                        Label {
                            Layout.fillWidth: true
                            text: modelData.note
                            color: Theme.mute
                            font.pixelSize: Theme.sizeMicro
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        // --- What arrives ----------------------------------------------------

        PanelCard {
            Layout.fillWidth: true
            title: "Keys per wish spawn"
            titleSize: Theme.sizeMedium

            Label {
                Layout.fillWidth: true
                visible: !root.production.available
                text: root.production.why
                      || "Fetch $wl for this account and server to model key production."
                color: Theme.mute
                font.pixelSize: Theme.sizeSmall
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                visible: root.production.available
                spacing: 10

                Repeater {
                    // Written as the sum it is, so the terms visibly reach the
                    // mean rather than being three unrelated figures.
                    model: [
                        { term: "1.00", label: "guaranteed on a wish spawn", colour: Theme.fg },
                        { term: "+ " + (root.production.global_extra_key_pct / 100).toFixed(2),
                          label: "$bonus extra-key chance ("
                                 + root.pct(root.production.global_extra_key_pct) + ")",
                          colour: Theme.accent },
                        { term: "+ " + root.meanPerk4.toFixed(2),
                          label: "the character's own perk 4 (0 to 0.30)",
                          colour: Theme.accent2 },
                        { term: "= " + Number(root.production.mean_keys_per_spawn).toFixed(2),
                          label: "averaged over the wishlist", colour: Theme.good }
                    ]

                    delegate: ColumnLayout {
                        required property var modelData

                        Layout.fillWidth: true
                        spacing: 2

                        Label {
                            text: modelData.term
                            color: modelData.colour
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeLarge
                        }

                        Label {
                            Layout.fillWidth: true
                            text: modelData.label
                            color: Theme.mute
                            font.pixelSize: Theme.sizeMicro
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                Layout.topMargin: 6
                visible: root.production.available
                text: "The three are independent, so their expectations add. Multiply by a "
                      + "character's spawn chance for keys an hour — that is the $bw page."
                color: Theme.dim
                font.pixelSize: Theme.sizeMicro
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 6
                visible: root.production.available && root.perkLevels.length > 0
                spacing: 8

                Label {
                    text: Theme.sectionLabel("perk 4 roster")
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    font.weight: Font.DemiBold
                    font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                }

                Repeater {
                    model: root.perkLevels

                    delegate: Rectangle {
                        required property var modelData

                        implicitWidth: levelLabel.implicitWidth + 16
                        implicitHeight: 22
                        radius: Theme.radiusPill
                        color: Theme.raised
                        border.width: Theme.borderWidth
                        border.color: Theme.line

                        Label {
                            id: levelLabel
                            anchors.centerIn: parent
                            text: "lv " + modelData.level + " × " + modelData.count
                                  + "  (+" + (root.production.perk4_pct_by_level || [])[modelData.level]
                                  + "%)"
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeMicro
                        }
                    }
                }

                Item { Layout.fillWidth: true }
            }
        }

        // --- What one is worth ------------------------------------------------

        PanelCard {
            Layout.fillWidth: true
            title: "Per key type"
            titleSize: Theme.sizeMedium

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Repeater {
                    model: [
                        { text: "type", width: 110, align: Text.AlignLeft },
                        { text: "a day", width: 70, align: Text.AlignRight },
                        { text: "worth", width: 110, align: Text.AlignRight },
                        { text: "why", width: 0, align: Text.AlignLeft }
                    ]

                    delegate: Label {
                        required property var modelData

                        Layout.preferredWidth: modelData.width
                        Layout.fillWidth: modelData.width === 0
                        horizontalAlignment: modelData.align
                        text: Theme.sectionLabel(modelData.text)
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }
                }
            }

            Repeater {
                model: root.rows

                delegate: RowLayout {
                    required property var modelData

                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    spacing: 10

                    RowLayout {
                        Layout.preferredWidth: 110
                        // A nested layout fills by default, which would take the
                        // whole row and pull the numeric columns off the header.
                        Layout.fillWidth: false
                        spacing: 6

                        KeyTypeBadge {
                            keyType: modelData.key_type
                            size: 16
                        }

                        Label {
                            Layout.fillWidth: true
                            text: modelData.key_type
                            color: Theme.fg
                            font.pixelSize: Theme.sizeSmall
                        }
                    }

                    Label {
                        Layout.preferredWidth: 70
                        horizontalAlignment: Text.AlignRight
                        text: Number(modelData.per_day).toFixed(2)
                        color: Number(modelData.per_day) > 0 ? Theme.fg : Theme.mute
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeSmall
                    }

                    Label {
                        Layout.preferredWidth: 110
                        horizontalAlignment: Text.AlignRight
                        text: modelData.priced
                              ? Number(modelData.value_kakera).toLocaleString(Qt.locale(), "f", 0)
                                + " k"
                              : "not priced"
                        color: modelData.priced ? Theme.good : Theme.mute
                        font.family: modelData.priced ? Theme.monoFamily : Theme.fontFamily
                        font.pixelSize: Theme.sizeSmall
                    }

                    Label {
                        Layout.fillWidth: true
                        // Chaos carries its own arithmetic, which is worth
                        // reading. The four claim keys share one reason, so it
                        // is stated once under the table instead of four times.
                        text: modelData.key_type === "chaos"
                              ? modelData.note
                              : "claim key — worth whatever it unlocks"
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        elide: Text.ElideRight
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                Layout.topMargin: 4
                visible: !root.keys.available
                text: "No keys logged in the last 14 days for this account, so the rates are "
                      + "all zero. The production model above does not depend on them."
                color: Theme.mute
                font.pixelSize: Theme.sizeMicro
                wrapMode: Text.WordWrap
            }
        }

        // --- Evidence ---------------------------------------------------------

        PanelCard {
            Layout.fillWidth: true
            title: "Evidence"
            titleSize: Theme.sizeMedium

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "Rates are this account's own key log over the last 14 days. The "
                          + "chaos price uses its measured kakera per click ("
                          + (root.keys.kakera_per_click
                             ? Number(root.keys.kakera_per_click).toLocaleString(Qt.locale(), "f", 0)
                             : "not yet measured")
                          + ") against a "
                          + Number(root.keys.kakera_base_cost || 30).toFixed(0)
                          + "% click cost; the cost cancels out, so the figure is robust to it."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }

                ScopeFetchButton {
                    command: "wishlist"
                    commandLabel: "$wl"
                    accountId: root.accountId
                    channelProfileId: root.channelProfileId
                }

                ScopeFetchButton {
                    command: "bonus"
                    commandLabel: "$bonus"
                    accountId: root.accountId
                    channelProfileId: root.channelProfileId
                }
            }

            Label {
                Layout.fillWidth: true
                text: "Claim keys are not priced, and more capture will not change that: a "
                      + "bronze, silver, gold or omega key is worth whatever the character "
                      + "you spend it on returns, and nothing here models a character's "
                      + "return. Perk 4 tells us how many arrive, not what one buys."
                color: Theme.dim
                font.pixelSize: Theme.sizeMicro
                wrapMode: Text.WordWrap
            }
        }
    }
}
