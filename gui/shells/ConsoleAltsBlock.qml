import QtQuick
import QtQuick.Layouts

import gui 1.0

/*
    The alts at the top of the Console Run rail.

    The on/off switch sits first: the alts start and stop with the main. Below
    it, one row per alt in turn order — the order that decides which alt takes
    a trigger first — with its claim, power, $dk and $rt, and what it is doing.
*/
Item {
    id: block

    property var runModel

    readonly property var alts: runModel ? runModel.alts : []
    readonly property int upCount: {
        var n = 0
        for (var i = 0; i < alts.length; i++) if (alts[i].connected) n++
        return n
    }

    implicitHeight: column.implicitHeight

    function minutesText(m) {
        if (m === null || m === undefined || m < 0) return "—"
        if (m < 60) return m + "m"
        var h = Math.floor(m / 60), r = m % 60
        return r > 0 ? h + "h " + r + "m" : h + "h"
    }

    // 6,337,375 → "6.34M"; 589 → "589". "—" until a full $tu was read.
    function stockText(n) {
        if (n === null || n === undefined) return "—"
        if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 1 : 2) + "M"
        if (n >= 1e4) return Math.round(n / 1e3) + "k"
        return Number(n).toLocaleString(Qt.locale("en_US"), "f", 0)
    }

    function gamesText(g) {
        if (!g) return ""
        var parts = []
        var ids = ["oh", "oc", "oq", "ot"]
        for (var i = 0; i < ids.length; i++)
            if (g[ids[i]] > 0) parts.push("$" + ids[i] + " " + g[ids[i]])
        return parts.length ? parts.join(" · ") : "all played"
    }

    Column {
        id: column
        width: parent.width
        spacing: 6

        Item {
            width: column.width
            height: caption.implicitHeight + 2
            Text {
                id: caption
                text: Theme.sectionLabel("alts")
                color: Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeMicro
                font.letterSpacing: Theme.tracking(Theme.sizeMicro)
            }
            Text {
                anchors.right: parent.right
                anchors.verticalCenter: caption.verticalCenter
                text: block.alts.length ? "turn order ↓" : ""
                color: Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeMicro
            }
        }

        RowLayout {
            width: column.width
            spacing: 8
            ConsoleButton {
                text: !block.runModel.altsOn ? "Alts: off"
                    : (block.alts.length ? "Alts: on · " + block.upCount : "Alts: on")
                onClicked: App.setAltsOn(!block.runModel.altsOn)
            }
            Text {
                Layout.fillWidth: true
                text: !block.runModel.altsOn ? "alts stay offline"
                    : (block.runModel.connected ? (block.alts.length ? "start and stop with the main" : "no alts enabled")
                                           : "connect to start them")
                color: Theme.mute
                font.family: Theme.monoFamily
                font.pixelSize: Theme.sizeTiny
                elide: Text.ElideRight
            }
        }

        Repeater {
            model: block.alts
            delegate: Column {
                required property var modelData
                width: column.width
                spacing: 3
                topPadding: 5

                Rectangle { width: parent.width; height: 1; color: Theme.line }

                RowLayout {
                    width: parent.width
                    spacing: 6
                    Rectangle {
                        Layout.preferredWidth: 15
                        Layout.preferredHeight: 15
                        radius: 3
                        color: Theme.raised
                        Text {
                            anchors.centerIn: parent
                            text: modelData.turn > 0 ? modelData.turn : "–"
                            color: Theme.dim
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                        }
                    }
                    Rectangle {
                        Layout.preferredWidth: 7
                        Layout.preferredHeight: 7
                        radius: 4
                        color: modelData.connected ? Theme.good
                            : (modelData.status === "standby" ? Theme.warn : Theme.mute)
                    }
                    Text {
                        Layout.fillWidth: true
                        text: modelData.name
                        color: Theme.fg
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeSmall
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Text {
                        text: modelData.tier
                        color: Theme.accent2
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeTiny
                    }
                }

                Grid {
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 1
                    Repeater {
                        model: [
                            { k: "claim", v: modelData.claim_available === true ? "ready"
                                : block.minutesText(modelData.claim_cooldown_minutes), good: modelData.claim_available === true },
                            { k: "power", v: modelData.power_percent !== null && modelData.power_percent !== undefined
                                ? Math.round(modelData.power_percent) + "%" : "—", good: false },
                            { k: "dk", v: modelData.dk_stock > 0 ? "ready" : block.minutesText(modelData.dk_next_minutes),
                              good: modelData.dk_stock > 0 },
                            { k: "rt", v: modelData.rt_available === true ? "ready" : block.minutesText(modelData.rt_next_minutes),
                              good: modelData.rt_available === true },
                            { k: "ka", v: block.stockText(modelData.kakera_stock), good: false },
                            { k: "sp", v: block.stockText(modelData.sphere_stock), good: false }
                        ]
                        delegate: Row {
                            required property var modelData
                            spacing: 5
                            Text {
                                width: 36
                                text: modelData.k
                                color: Theme.mute
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeTiny
                            }
                            Text {
                                text: modelData.v
                                color: modelData.good ? Theme.good : Theme.fg
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeTiny
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    visible: modelData.kakera_from_main_rolls > 0
                    text: "from the main's rolls: +" + block.stockText(modelData.kakera_from_main_rolls) + " ka"
                    color: Theme.good
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeTiny
                    elide: Text.ElideRight
                }

                Text {
                    width: parent.width
                    visible: !!modelData.claimed_for_main && modelData.claimed_for_main.length > 0
                    text: "for the main (give at batch end): "
                          + (modelData.claimed_for_main || []).join(", ")
                    color: Theme.good
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeTiny
                    elide: Text.ElideRight
                }

                Text {
                    width: parent.width
                    visible: !!modelData.minigames_left
                    text: "games: " + block.gamesText(modelData.minigames_left)
                    color: Theme.dim
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeTiny
                    elide: Text.ElideRight
                }

                Text {
                    width: parent.width
                    text: "now: " + modelData.status
                          + (modelData.connected && modelData.ready === false ? " · needs $bonus (Alts › Setup)" : "")
                    color: modelData.connected && modelData.ready === false ? Theme.warn : Theme.dim
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeTiny
                    elide: Text.ElideRight
                }
            }
        }
    }
}
