import QtQuick
import QtQuick.Layouts

import gui 1.0
import "../components"
import "../emptyStates.js" as Empty

/*
    Console — Run page.

    Design B: target line, a single-row status line with the run state pinned to
    the right, a monospace log beside a narrow rail, and a command bar of keys
    along the bottom. Everything is full-bleed and divided by hairlines.
*/
Item {
    id: page

    RunModel { id: run }
    TargetModel { id: targets }

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- target line ---------------------------------------------------

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 54

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 9

                TargetSelector {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 100
                    Layout.preferredHeight: 36
                    implicitHeight: 36
                    showIcon: false
                    label: "account"
                    value: targets.accountLabel
                    options: targets.accountNames
                    currentIndex: targets.accountIndex
                    onPicked: function(index) { targets.selectAccount(index) }
                }

                TargetSelector {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 140
                    Layout.preferredHeight: 36
                    implicitHeight: 36
                    showIcon: false
                    label: "channel"
                    value: targets.channelLabel
                    options: targets.channelLabels
                    currentIndex: targets.channelIndex
                    onPicked: function(index) { targets.selectChannel(index) }
                }

                TargetSelector {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 120
                    Layout.preferredHeight: 36
                    implicitHeight: 36
                    showIcon: false
                    highlight: true
                    label: "preset"
                    value: targets.presetLabel
                    options: targets.presetNames
                    currentIndex: targets.presetIndex
                    onPicked: function(index) { targets.selectPreset(index) }
                }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.line
            }
        }

        // ---- status line ---------------------------------------------------

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            // The mockup darkens the page background rather than using a token.
            color: Theme.blend("#000000", Theme.bg, 0.3)
            clip: true

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.line
            }

            Row {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom

                ConsoleStatCell {
                    firstCell: true
                    key: "rolls"
                    value: run.rollsText
                    tone: "accent"
                    fraction: run.rollsFraction
                }
                ConsoleStatCell {
                    key: "reset"
                    value: run.resetText
                }
                ConsoleStatCell {
                    key: "claim"
                    value: run.claimReady ? "ready" : run.claimText.toLowerCase()
                    tone: run.claimReady ? "good" : "neutral"
                }
                ConsoleStatCell {
                    key: "power"
                    value: run.powerText
                    tone: run.powerTone === "warn" ? "neutral" : "accent"
                    fraction: run.powerFraction
                }
                ConsoleStatCell {
                    key: "dk"
                    value: run.dkText
                }
                ConsoleStatCell {
                    key: "us"
                    value: run.usText
                    tone: "violet"
                }
            }

            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: phaseRow.implicitWidth + 32
                color: Theme.accent

                Row {
                    id: phaseRow
                    anchors.centerIn: parent
                    spacing: 9

                    ThemeSphere {
                        id: phaseMark
                        anchors.verticalCenter: parent.verticalCenter
                        size: 16
                        opacity: run.macroRunning && !phaseMark.blinkOn ? 0 : 1
                        property bool blinkOn: true

                        // Hard steps, matching the mockup's blink — not a fade.
                        Timer {
                            interval: 500
                            running: run.macroRunning
                            repeat: true
                            onTriggered: phaseMark.blinkOn = !phaseMark.blinkOn
                            onRunningChanged: if (!running) phaseMark.blinkOn = true
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: run.phase.toUpperCase()
                        color: Theme.bg
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeSmall
                        font.weight: Font.DemiBold
                    }
                }
            }
        }

        // ---- log + rail ----------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // ---- log -------------------------------------------------------

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 300
                spacing: 0

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 31

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 15
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 14

                        Repeater {
                            model: [
                                { key: "all", label: "all" },
                                { key: "claim", label: "claim" },
                                { key: "kakera", label: "kakera" },
                                { key: "skip", label: "skip" },
                                { key: "error", label: "error" }
                            ]

                            delegate: Item {
                                required property var modelData

                                readonly property bool active: run.filterKind === modelData.key

                                width: filterText.implicitWidth
                                height: 18

                                Text {
                                    id: filterText
                                    anchors.top: parent.top
                                    text: modelData.label + " " + (run.counts[modelData.key] || 0)
                                    color: parent.active ? Theme.accent
                                        : (filterMouse.containsMouse ? Theme.dim : Theme.mute)
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeMicro
                                }

                                Rectangle {
                                    visible: parent.active
                                    anchors.top: filterText.bottom
                                    anchors.topMargin: 2
                                    width: parent.width
                                    height: 1
                                    color: Theme.accent
                                }

                                MouseArea {
                                    id: filterMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: run.filterKind = modelData.key
                                }
                            }
                        }
                    }

                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 15
                        anchors.verticalCenter: parent.verticalCenter
                        text: run.visibleFeed.length + " lines"
                        color: Theme.mute
                        opacity: 0.6
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeMicro
                    }

                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: Theme.line
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.topMargin: 8
                    Layout.bottomMargin: 8

                    // An empty log would read as a rendering fault, so the
                    // reason there is nothing to show is spelled out instead.
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 15
                        anchors.top: parent.top
                        height: 25
                        verticalAlignment: Text.AlignVCenter
                        visible: feed.count === 0
                        text: Empty.runFeedEmpty(run.connected)
                        color: Theme.mute
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeBody
                    }

                ListView {
                    id: feed
                    anchors.fill: parent
                    clip: true
                    model: run.visibleFeed
                    boundsBehavior: Flickable.StopAtBounds

                    property bool stickToBottom: true

                    function updateStickToBottom() {
                        if (!moving && !flicking)
                            return
                        var maxY = Math.max(0, contentHeight - height)
                        stickToBottom = (contentY + height) >= (maxY - 24)
                    }

                    onMovingChanged: updateStickToBottom()
                    onFlickingChanged: updateStickToBottom()
                    onCountChanged: if (stickToBottom) Qt.callLater(positionViewAtEnd)
                    Component.onCompleted: Qt.callLater(positionViewAtEnd)

                    delegate: Item {
                        required property var modelData

                        readonly property color kindColor: run.colorFor(modelData.kind)

                        width: ListView.view.width
                        height: 25

                        Rectangle {
                            anchors.fill: parent
                            color: modelData.kind === "claim"
                                ? Theme.fade(Theme.good, 0.09)
                                : "transparent"
                        }

                        Text {
                            id: stamp
                            anchors.left: parent.left
                            anchors.leftMargin: 15
                            anchors.verticalCenter: parent.verticalCenter
                            width: 74
                            text: modelData.time
                            color: Theme.mute
                            opacity: 0.75
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeBody
                        }

                        Text {
                            id: glyph
                            anchors.left: stamp.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 20
                            text: modelData.glyph
                            color: parent.kindColor
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeBody
                            font.weight: Font.DemiBold
                        }

                        Text {
                            anchors.left: glyph.right
                            anchors.right: parent.right
                            anchors.rightMargin: 15
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.text
                            color: modelData.kind === "claim" ? Theme.good
                                : (modelData.kind === "error" ? Theme.bad
                                : (modelData.kind === "skip" ? Theme.mute : Theme.dim))
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeBody
                            elide: Text.ElideRight
                        }
                    }
                }
                }
            }

            // ---- rail ------------------------------------------------------

            Item {
                Layout.preferredWidth: 266
                Layout.maximumWidth: 266
                Layout.fillHeight: true

                Rectangle {
                    anchors.left: parent.left
                    width: 1
                    height: parent.height
                    color: Theme.line
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 13
                    anchors.topMargin: 11
                    anchors.bottomMargin: 11
                    spacing: 11

                    // last claim
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: claimColumn.implicitHeight + 20
                        color: Theme.fade(Theme.good, 0.08)
                        border.width: 1
                        border.color: Theme.fade(Theme.good, 0.4)

                        Column {
                            id: claimColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: 11
                            anchors.rightMargin: 11
                            anchors.topMargin: 10
                            spacing: 2

                            Text {
                                width: parent.width
                                text: run.lastClaimName !== "" ? run.lastClaimName : "no claim yet"
                                color: run.lastClaimName !== "" ? Theme.good : Theme.mute
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeLarge
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                text: run.lastClaimDetail
                                visible: text !== ""
                                color: Theme.dim
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeSmall
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                topPadding: 5
                                text: run.lastClaimTime !== ""
                                    ? "claimed " + run.lastClaimTime + " · next in " + run.nextClaimText
                                    : "next claim " + run.nextClaimText
                                color: Theme.mute
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeSmall
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    ConsoleRailBlock {
                        Layout.fillWidth: true
                        title: "perks"
                        rows: [
                            { label: "perk 8", value: run.perk8Text, tone: "accent" },
                            { label: "perk 9 today", value: run.perk9Text, tone: "" },
                            { label: "rolls reset", value: run.resetText, tone: "" },
                            { label: "next claim", value: run.nextClaimText, tone: "" }
                        ]
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.line
                    }

                    ConsoleRailBlock {
                        Layout.fillWidth: true
                        title: "session"
                        rows: [
                            { label: "kakera", value: run.compact(run.sessionKakera), tone: "accent" },
                            { label: "spheres", value: String(run.sessionSpheres), tone: "" },
                            { label: "keys", value: String(run.sessionKeys), tone: "" },
                            { label: "claims", value: String(run.sessionClaims), tone: "good" }
                        ]
                    }

                    Item { Layout.fillHeight: true }
                }
            }
        }

        // ---- command bar ---------------------------------------------------

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: commandFlow.implicitHeight + 20
            color: Theme.surface

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: Theme.line
            }

            Flow {
                id: commandFlow
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.topMargin: 10
                anchors.bottomMargin: 10
                spacing: 7

                ConsoleButton {
                    text: "Stop"
                    variant: "kill"
                    enabled: run.macroRunning || run.engineRunning
                    onClicked: App.stopMacro()
                }

                ConsoleButton {
                    text: run.connectLabel
                    enabled: !run.connecting && !run.disconnecting
                    onClicked: run.connected ? App.disconnect() : App.connect()
                }

                ConsoleButton {
                    text: "Start hourly"
                    variant: "go"
                    enabled: run.connected && !run.macroRunning
                    onClicked: App.startMacro()
                }

                ConsoleButton {
                    text: "Roll $us"
                    enabled: run.connected && !run.macroRunning
                    onClicked: App.startUsMode()
                }

                ConsoleButton {
                    text: "$tu"
                    enabled: run.connected
                    onClicked: App.runTu()
                }

                ConsoleButton {
                    text: "$us"
                    enabled: run.connected
                    onClicked: App.runUsCheck()
                }

                ConsoleButton {
                    text: "$oh"
                    enabled: run.connected
                    onClicked: App.playOhSphere()
                }

                ConsoleButton {
                    text: "$oc"
                    enabled: run.connected
                    onClicked: App.playOcSphere()
                }

                ConsoleButton {
                    text: "$oq"
                    enabled: run.connected
                    onClicked: App.playOqSphere()
                }

                ConsoleButton {
                    text: "Play all"
                    variant: "go"
                    enabled: run.connected
                    onClicked: App.playAllMinigames()
                }
            }
        }
    }
}
