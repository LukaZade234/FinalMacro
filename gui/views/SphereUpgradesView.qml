import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Spheres › Upgrades — which ouroperk level to buy next.

    Deliberately not the full spcalc ladder (`docs/TODO.md` rules that out as a
    multi-day transcription). It answers one question, and **abstains** on every
    perk it cannot price from data the app actually holds rather than filling
    the column with a plausible-looking number that would make the ranking look
    authoritative.

    Only perk 9 is priced today: its sphere-value step against the account's own
    logged perk-9 income, and its extra click through the perk-9 DP.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""

    property var economy: ({ available: false, upgrades: [], stock: {} })

    readonly property var upgrades: economy.upgrades || []
    readonly property int priced: {
        var n = 0
        for (var i = 0; i < upgrades.length; i++)
            if (upgrades[i].payback_days !== null) n++
        return n
    }

    function refresh() {
        if (!channelProfileId) {
            economy = { available: false, upgrades: [], stock: {} }
            return
        }
        try {
            economy = JSON.parse(App.sphereEconomyJson(channelProfileId, accountId))
        } catch (e) {
            economy = { available: false, upgrades: [], stock: {} }
        }
    }

    function fmt(n) {
        if (n === null || n === undefined)
            return "—"
        return Number(n).toLocaleString(Qt.locale(), "f", 0)
    }

    function affordable(cost) {
        var have = (economy.stock || {}).shop_spheres
        return have !== null && have !== undefined && cost <= have
    }

    function confidenceColor(c) {
        if (c === "measured") return Theme.good
        if (c === "modelled") return Theme.warn
        return Theme.mute
    }

    onChannelProfileIdChanged: refresh()
    onAccountIdChanged: refresh()
    Component.onCompleted: refresh()

    Connections {
        target: App
        function onServersChanged() { root.refresh() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "What to buy next"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: root.upgrades.length === 0
                          ? "No $shop yet, or every perk is maxed."
                          : (root.priced === 0
                             ? "Nothing here can be priced from data the app holds — see the reasons below."
                             : root.priced + " of " + root.upgrades.length
                               + " perks can be priced. Payback is cost ÷ SP added per day.")
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ColumnLayout {
                        width: parent.width
                        spacing: 6

                        Repeater {
                            model: root.upgrades

                            delegate: Rectangle {
                                required property var modelData

                                Layout.fillWidth: true
                                implicitHeight: rowBody.implicitHeight + 18
                                color: modelData.payback_days !== null
                                       ? Theme.fade(Theme.accent, 0.07) : "transparent"
                                border.width: Theme.borderWidth
                                border.color: Theme.line
                                radius: Theme.radiusSm

                                ColumnLayout {
                                    id: rowBody
                                    anchors.fill: parent
                                    anchors.margins: 9
                                    spacing: 5

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 10

                                        Label {
                                            Layout.preferredWidth: 46
                                            text: modelData.id
                                            color: Theme.accent2
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.sizeSmall
                                            font.weight: Font.DemiBold
                                        }

                                        Label {
                                            Layout.preferredWidth: 66
                                            text: "lv " + modelData.level + "→" + modelData.next_level
                                            color: Theme.dim
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.sizeSmall
                                        }

                                        Label {
                                            Layout.preferredWidth: 86
                                            text: root.fmt(modelData.cost) + " SP"
                                            color: root.affordable(modelData.cost)
                                                   ? Theme.good : Theme.warn
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.sizeSmall
                                            horizontalAlignment: Text.AlignRight
                                        }

                                        Label {
                                            Layout.preferredWidth: 96
                                            text: modelData.sp_per_day !== null
                                                  ? "+" + root.fmt(modelData.sp_per_day) + " SP/day"
                                                  : "not priced"
                                            color: modelData.sp_per_day !== null
                                                   ? Theme.fg : Theme.mute
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.sizeSmall
                                            horizontalAlignment: Text.AlignRight
                                        }

                                        Label {
                                            Layout.preferredWidth: 80
                                            text: modelData.payback_days !== null
                                                  ? modelData.payback_days + " d" : "—"
                                            color: modelData.payback_days !== null
                                                   ? Theme.fg : Theme.mute
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.sizeSmall
                                            font.weight: Font.DemiBold
                                            horizontalAlignment: Text.AlignRight
                                        }

                                        Item { Layout.fillWidth: true }

                                        Label {
                                            text: Theme.sectionLabel(modelData.confidence)
                                            color: root.confidenceColor(modelData.confidence)
                                            font.pixelSize: Theme.sizeMicro
                                            font.weight: Font.DemiBold
                                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                                        }
                                    }

                                    Repeater {
                                        model: modelData.notes || []

                                        delegate: Label {
                                            required property string modelData

                                            Layout.fillWidth: true
                                            text: "· " + modelData
                                            color: Theme.mute
                                            font.pixelSize: Theme.sizeMicro
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: "Cost is derived from the sheet's \"cost increased by +N per level\" "
                          + "line — Mudae never prints the figure for a specific level."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
