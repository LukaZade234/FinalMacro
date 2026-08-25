import QtQuick
import QtQuick.Layouts

import gui 1.0
import "../emptyStates.js" as Empty

/*
    Boxed — Run page.

    Design G: Target and Controls stacked at the top, then the live feed beside
    a Resources / Session column. Every group is a captioned double-ruled box.
*/
Item {
    id: page

    RunModel { id: run }
    TargetModel { id: targets }

    ColumnLayout {
        anchors.fill: parent
        // Captions straddle the top rule of their box, so the first row needs
        // headroom or half the text is clipped away.
        anchors.topMargin: 7
        spacing: 11

        // ---- target --------------------------------------------------------

        BoxedBox {
            Layout.fillWidth: true
            Layout.preferredHeight: 92
            caption: "Target"

            ColumnLayout {
                anchors.fill: parent
                spacing: 9

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 9

                    BoxedCombo {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 100
                        label: "Account"
                        value: targets.accountLabel
                        options: targets.accountNames
                        currentIndex: targets.accountIndex
                        onPicked: function(index) { targets.selectAccount(index) }
                    }

                    BoxedCombo {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 140
                        label: "Channel"
                        value: targets.channelLabel
                        options: targets.channelLabels
                        currentIndex: targets.channelIndex
                        onPicked: function(index) { targets.selectChannel(index) }
                    }

                    BoxedCombo {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 120
                        label: "Preset"
                        value: targets.presetLabel
                        options: targets.presetNames
                        currentIndex: targets.presetIndex
                        onPicked: function(index) { targets.selectPreset(index) }
                    }
                }

                Row {
                    Layout.fillWidth: true
                    spacing: 6

                    Repeater {
                        model: [
                            { label: "Claim", on: run.claimRuleOn },
                            { label: "Kakera", on: run.kakeraRuleOn },
                            { label: "Spheres", on: run.sphereRuleOn }
                        ]

                        delegate: Rectangle {
                            required property var modelData

                            width: ruleText.implicitWidth + 20
                            height: 22
                            color: modelData.on ? Theme.fade(Theme.good, 0.10) : Theme.raised
                            opacity: modelData.on ? 1 : 0.45
                            border.width: 1
                            border.color: modelData.on ? Theme.fade(Theme.good, 0.45) : Theme.line

                            Text {
                                id: ruleText
                                anchors.centerIn: parent
                                text: modelData.label
                                color: modelData.on ? Theme.good : Theme.mute
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeMicro
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }

        // ---- controls ------------------------------------------------------

        BoxedBox {
            Layout.fillWidth: true
            Layout.preferredHeight: controlPad.implicitHeight + 26
            caption: "Controls"

            Flow {
                id: controlPad
                width: parent.width
                spacing: 7

                BoxedButton {
                    text: "Stop"
                    variant: "kill"
                    enabled: run.macroRunning || run.engineRunning
                    onClicked: App.stopMacro()
                }
                BoxedButton {
                    text: run.connectLabel
                    enabled: !run.connecting && !run.disconnecting
                    onClicked: run.connected ? App.disconnect() : App.connect()
                }
                BoxedButton {
                    text: "Start hourly"
                    variant: "hourly"
                    enabled: run.canStartHourly
                    onClicked: App.startMacro()
                }
                BoxedButton {
                    text: "Roll $us"
                    enabled: run.canStartUs
                    onClicked: App.startUsMode()
                }
                BoxedButton {
                    text: "$tu"
                    enabled: run.canCheck
                    onClicked: App.runTu()
                }
                BoxedButton {
                    text: "$us"
                    enabled: run.canCheck
                    onClicked: App.runUsCheck()
                }
                BoxedButton {
                    text: "$oh"
                    enabled: run.canPlayMinigame
                    onClicked: App.playOhSphere()
                }
                BoxedButton {
                    text: "$oc"
                    enabled: run.canPlayMinigame
                    onClicked: App.playOcSphere()
                }
                BoxedButton {
                    text: "$oq"
                    enabled: run.canPlayMinigame
                    onClicked: App.playOqSphere()
                }
                BoxedButton {
                    text: "Play all"
                    variant: "go"
                    enabled: run.canPlayMinigame
                    onClicked: App.playAllMinigames()
                }
            }
        }

        // ---- feed + side ---------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 11

            BoxedBox {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 300
                caption: "Live feed"
                hot: true

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

                        readonly property bool hit: modelData.kind === "claim"

                        width: ListView.view.width
                        height: 24

                        Rectangle {
                            anchors.fill: parent
                            color: parent.hit ? Theme.accent : "transparent"
                        }

                        Text {
                            id: stamp
                            anchors.left: parent.left
                            anchors.leftMargin: 2
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.time
                            color: parent.hit ? Theme.bg : Theme.mute
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeBody
                        }

                        Text {
                            anchors.left: stamp.right
                            anchors.leftMargin: 11
                            anchors.right: parent.right
                            anchors.rightMargin: 2
                            anchors.verticalCenter: parent.verticalCenter
                            text: MudaeEmoji.feedHtml(modelData.text, 16, !parent.hit)
                            textFormat: Text.RichText
                            wrapMode: Text.NoWrap
                            clip: true
                            color: parent.hit ? Theme.bg
                                : (modelData.kind === "kakera" ? Theme.accent
                                : (modelData.kind === "error" ? Theme.bad
                                : (modelData.kind === "skip" ? Theme.mute : Theme.dim)))
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeBody
                        }
                    }
                }

                // An empty box would read as a rendering fault, so the reason
                // there is nothing to show is spelled out instead.
                Text {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    height: 24
                    verticalAlignment: Text.AlignVCenter
                    visible: feed.count === 0
                    text: Empty.runFeedEmpty(run.connected)
                    color: Theme.mute
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.sizeBody
                }
            }

            ColumnLayout {
                Layout.preferredWidth: 290
                Layout.maximumWidth: 290
                Layout.fillHeight: true
                spacing: 11

                BoxedBox {
                    Layout.fillWidth: true
                    Layout.preferredHeight: resources.implicitHeight + 28
                    caption: "Resources"

                    Column {
                        id: resources
                        width: parent.width
                        spacing: 0

                        BoxedStatRow {
                            width: parent.width
                            label: "Rolls"
                            value: run.rollsText
                            tone: "accent"
                            fraction: run.rollsFraction
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Rolls reset"
                            value: run.resetText
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Claim"
                            value: run.claimReady ? "Ready now" : run.claimText
                            tone: run.claimReady ? "good" : ""
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Next claim"
                            value: run.nextClaimText
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Power"
                            value: run.powerText
                            fraction: run.powerFraction
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "DK stock"
                            value: run.dkText
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "$us bonus"
                            value: run.usText
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Perk 8"
                            value: run.perk8Text
                            tone: "accent"
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Perk 9 today"
                            value: run.perk9Text
                        }
                    }
                }

                BoxedBox {
                    Layout.fillWidth: true
                    visible: run.powerSaveOn
                    Layout.preferredHeight: run.powerSaveOn ? (saverCol.implicitHeight + 28) : 0
                    Layout.maximumHeight: run.powerSaveOn ? 400 : 0
                    caption: "Smart saver"

                    Column {
                        id: saverCol
                        width: parent.width
                        spacing: 0

                        Repeater {
                            model: run.powerSaveRows
                            BoxedStatRow {
                                width: saverCol.width
                                label: modelData.label
                                value: modelData.value
                                tone: modelData.tone || ""
                            }
                        }
                    }
                }

                BoxedBox {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 120
                    caption: "Session"

                    Column {
                        width: parent.width
                        spacing: 0

                        BoxedStatRow {
                            width: parent.width
                            label: "Last claim"
                            value: run.lastClaimName !== "" ? run.lastClaimName : "—"
                            tone: run.lastClaimName !== "" ? "good" : ""
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Kakera"
                            value: run.compact(run.sessionKakera) + " ka"
                            tone: "accent"
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Spheres / keys"
                            value: run.sessionSpheres + " / " + run.sessionKeys
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Claims"
                            value: String(run.sessionClaims)
                            tone: "good"
                        }
                        BoxedStatRow {
                            width: parent.width
                            label: "Elapsed"
                            value: run.sessionElapsedText !== "" ? run.sessionElapsedText : "—"
                        }
                    }
                }
            }
        }
    }
}
