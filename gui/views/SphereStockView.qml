import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Spheres › Stock & shop — what you hold and what the ladder costs.

    The two stock figures are shown as two readings rather than merged into a
    "liquid vs invested" split: `$ohu` prints a sphere stock line and `$shop`
    prints its own balance, they are read at different moments, and nothing in
    the app establishes that they mean different pools. Labelling them by source
    is the honest presentation.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""

    property var economy: ({ available: false, stock: {}, shop: {}, upgrades: [] })

    readonly property var perks: {
        var out = []
        var raw = (economy.shop || {}).perks || {}
        for (var key in raw) {
            var perk = raw[key]
            out.push({
                number: parseInt(key),
                level: perk.level,
                maxed: !!perk.maxed,
                detail: perkDetail(perk)
            })
        }
        out.sort(function (a, b) { return a.number - b.number })
        return out
    }

    function perkDetail(perk) {
        var bits = []
        for (var k in perk) {
            if (k === "level" || k === "maxed" || k.indexOf("next_") === 0)
                continue
            var label = k.replace(/_pct$/, " %").replace(/_/g, " ")
            var next = perk["next_" + k]
            bits.push(label + " " + perk[k] + (next !== undefined ? " → " + next : ""))
        }
        return bits.join(" · ")
    }

    function refresh() {
        if (!channelProfileId) {
            economy = { available: false, stock: {}, shop: {}, upgrades: [] }
            return
        }
        try {
            economy = JSON.parse(App.sphereEconomyJson(channelProfileId, accountId))
        } catch (e) {
            economy = { available: false, stock: {}, shop: {}, upgrades: [] }
        }
    }

    function fmt(n) {
        if (n === null || n === undefined)
            return "—"
        return Number(n).toLocaleString(Qt.locale(), "f", 0)
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

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap

            Repeater {
                model: [
                    { key: "ohu_stock", label: "Sphere stock", note: "from $ohu" },
                    { key: "shop_spheres", label: "Shop balance", note: "from $shop" }
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
                            text: root.fmt((root.economy.stock || {})[modelData.key])
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeTitle
                            font.weight: Font.Medium
                        }

                        Label {
                            text: modelData.note
                            color: Theme.mute
                            font.pixelSize: Theme.sizeMicro
                        }
                    }
                }
            }

            Rectangle {
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
                        text: Theme.sectionLabel("invest")
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }

                    Label {
                        Layout.fillWidth: true
                        text: "Not wired — the invest command's syntax and reply are "
                              + "undocumented, and no kakera balance is tracked."
                        color: Theme.dim
                        font.pixelSize: Theme.sizeSmall
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "$shop · ouroperk ladder"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    visible: root.economy.available

                    Label {
                        visible: !!root.economy.inferred
                        text: Theme.sectionLabel("inferred")
                        color: Theme.warn
                        font.pixelSize: Theme.sizeMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }

                    Label {
                        Layout.fillWidth: true
                        text: root.economy.inferred
                              ? "Saved before sheets were per-account — re-fetch to be sure."
                              : (root.economy.read_at
                                 ? "read " + String(root.economy.read_at).substring(0, 16).replace("T", " ") + " UTC"
                                 : "")
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        elide: Text.ElideRight
                    }

                    Label {
                        text: "levels cost " + root.fmt((root.economy.shop || {}).level_cost_step)
                              + " × level"
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                    }
                }

                Label {
                    visible: !root.economy.available
                    Layout.fillWidth: true
                    text: "No $shop yet — set this channel on Run, connect, then Fetch $shop."
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
                        spacing: 0

                        Repeater {
                            model: root.perks

                            delegate: RowLayout {
                                required property var modelData

                                Layout.fillWidth: true
                                Layout.preferredHeight: 30
                                spacing: 10

                                Label {
                                    Layout.preferredWidth: 44
                                    text: "OP" + modelData.number
                                    color: Theme.accent2
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeSmall
                                }

                                Label {
                                    Layout.preferredWidth: 56
                                    text: modelData.maxed
                                          ? "MAX" : "lv " + modelData.level
                                    color: modelData.maxed ? Theme.good : Theme.fg
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeSmall
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.detail
                                    color: Theme.dim
                                    font.pixelSize: Theme.sizeSmall
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
