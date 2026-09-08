import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import gui 1.0
import "../components"
import "../emptyStates.js" as Empty

/*
    Quiet — Run page.

    The one page in this design with a dominant number, because it is the one
    page that has a single question: how many rolls are left this hour. Claim,
    power and the two daily budgets sit beside it as small figures; everything
    else is a hairline apart rather than a card apart.

    The side column carries the two smart functions in a **condensed** form.
    The full strips (`components/Perk8PowerSaveStatus.qml`,
    `Perk9AdaptiveStatus.qml`) list five and four chips plus three follow-up
    sections; here each is cut to what you would act on:

      Smart saver   is it holding normal clicks, and how much bar will it spend
      Adaptive p9   the live threshold, which spheres it admits, what moves it

    Everything dropped is still on Presets and in the full strips on the other
    shells — this is a summary, not a replacement.
*/
Item {
    id: page

    RunModel { id: run }
    TargetModel { id: targets }

    readonly property var saver: run.powerSave
    readonly property var adaptive: run.perk9Adaptive

    function spendText() {
        if (!saver || saver.spendable_percent === null || saver.spendable_percent === undefined)
            return "—"
        var n = Number(saver.spendable_percent)
        var bar = Number(saver.power_percent)
        if (isFinite(bar) && n >= bar - 0.5)
            return "all of the bar"
        return Math.round(n) + "% of the bar"
    }

    function saverLead() {
        if (!saver)
            return ""
        if (saver.power_blocked)
            return "Saving power — reacts held"
        return saver.normal_clicks ? "Normal clicks allowed" : "Holding normal clicks"
    }

    function perk8Left() {
        if (run.perk8Max <= 0)
            return ""
        var left = Math.max(0, run.perk8Max - run.perk8Used)
        if (left === 0)
            return "All 40 spent — chaos kakera still click."
        return left + " left before they expire at 00:00 UTC."
    }

    function thresholdText() {
        if (!adaptive)
            return "—"
        if (adaptive.spend_down)
            return "spending down"
        if (adaptive.threshold === null || adaptive.threshold === undefined)
            return "—"
        return "≥ " + adaptive.threshold + " SP"
    }

    function spawnsLeftText() {
        if (!adaptive || adaptive.spawns_left === null || adaptive.spawns_left === undefined)
            return "spawns left unknown"
        return adaptive.spawns_left + " spawns left"
    }

    function nextMoveText() {
        if (!adaptive)
            return ""
        if (run.perk9LooserText)
            return "Opens up " + run.perk9LooserText + "."
        if (run.perk9StricterText)
            return "Tightens " + run.perk9StricterText + "."
        return "No further change today."
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- targets -------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 34

            QuietTarget {
                Layout.preferredWidth: 150
                label: "Account"
                value: targets.accountLabel
                options: targets.accountNames
                currentIndex: targets.accountIndex
                onPicked: function(index) { targets.selectAccount(index) }
            }

            QuietTarget {
                Layout.fillWidth: true
                Layout.preferredWidth: 260
                label: "Channel"
                value: targets.channelLabel
                options: targets.channelLabels
                currentIndex: targets.channelIndex
                onPicked: function(index) { targets.selectChannel(index) }
            }

            QuietTarget {
                Layout.preferredWidth: 190
                label: "Preset"
                value: targets.presetLabel
                options: targets.presetNames
                currentIndex: targets.presetIndex
                highlight: true
                onPicked: function(index) { targets.selectPreset(index) }
            }
        }

        // ---- the dominant number, and the figures beside it -----------------

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 22
            Layout.bottomMargin: 16
            spacing: 36

            ColumnLayout {
                spacing: 0

                Label {
                    text: run.rollsText
                    color: Theme.fg
                    font.family: Theme.monoFamily
                    font.pixelSize: 52
                    font.weight: Font.Medium
                    font.letterSpacing: -2
                }

                Label {
                    Layout.topMargin: 9
                    text: {
                        var bits = ["rolls this hour"]
                        if (run.resetText !== "—")
                            bits.push("refills in " + run.resetText)
                        if (run.usBonus > 0)
                            bits.push(run.usBonus + " from $us")
                        return bits.join(" · ")
                    }
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                }
            }

            Repeater {
                model: [
                    { key: "Claim", value: run.claimText, tone: run.claimTone },
                    { key: "Power", value: run.powerText, tone: run.powerTone },
                    { key: "Perk 8", value: run.perk8Text, tone: "" },
                    { key: "Perk 9", value: run.perk9Text, tone: "" }
                ]

                delegate: ColumnLayout {
                    required property var modelData

                    Layout.alignment: Qt.AlignBottom
                    Layout.bottomMargin: 4
                    spacing: 6

                    Label {
                        text: Theme.sectionLabel(modelData.key)
                        color: Theme.mute
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeMicro
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }

                    Label {
                        text: modelData.value
                        color: modelData.tone === "good" ? Theme.good
                             : modelData.tone === "warn" ? Theme.warn : Theme.fg
                        font.pixelSize: Theme.sizeXLarge
                        font.weight: Font.Medium
                    }
                }
            }

            Item { Layout.fillWidth: true }

            RowLayout {
                Layout.alignment: Qt.AlignBottom
                Layout.bottomMargin: 6
                spacing: 9

                Rectangle {
                    Layout.preferredWidth: 5
                    Layout.preferredHeight: 5
                    radius: 2.5
                    visible: run.macroRunning
                    color: Theme.accent

                    SequentialAnimation on opacity {
                        running: run.macroRunning
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.28; duration: 1100 }
                        NumberAnimation { to: 1.0; duration: 1100 }
                    }
                }

                Label {
                    text: run.statusLine
                    color: Theme.dim
                    font.pixelSize: Theme.sizeBody
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        // ---- actions --------------------------------------------------------

        Flow {
            Layout.fillWidth: true
            Layout.topMargin: 14
            Layout.bottomMargin: 14
            spacing: 9

            QuietAction {
                text: "Stop"
                tone: "stop"
                enabled: run.engineRunning
                onClicked: App.stopMacro()
            }
            QuietAction {
                text: run.connectLabel
                enabled: !run.connecting && !run.disconnecting
                onClicked: run.connected ? App.disconnect() : App.connect()
            }
            QuietAction {
                text: "Start hourly"
                tone: "go"
                enabled: run.canStartHourly
                onClicked: App.startMacro()
            }
            QuietAction {
                text: "Roll $us"
                enabled: run.canStartUs
                onClicked: App.startUsMode()
            }
            QuietAction {
                text: "$forcedivorce"
                enabled: run.canForceDivorce
                onClicked: App.startForceDivorce()
            }

            QuietGroupLabel { text: "Checks" }
            QuietAction { text: "$tu"; enabled: run.canCheck; onClicked: App.runTu() }
            QuietAction { text: "$us"; enabled: run.canCheck; onClicked: App.runUsCheck() }

            QuietGroupLabel { text: "Minigames" }
            QuietAction { text: "$oh"; enabled: run.canPlayMinigame; onClicked: App.playOhSphere() }
            QuietAction { text: "$oc"; enabled: run.canPlayMinigame; onClicked: App.playOcSphere() }
            QuietAction { text: "$oq"; enabled: run.canPlayMinigame; onClicked: App.playOqSphere() }
            QuietAction { text: "$ot"; enabled: run.canPlayMinigame; onClicked: App.playOtSphere() }
            QuietAction {
                text: "Play all"
                tone: "accent"
                enabled: run.canPlayMinigame
                onClicked: App.playAllMinigames()
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        // ---- feed, and the side column --------------------------------------

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 16
            spacing: 40

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                ListView {
                    id: feedView
                    anchors.fill: parent
                    clip: true
                    model: run.visibleFeed
                    spacing: 3
                    boundsBehavior: Flickable.StopAtBounds

                    // Newest lines are the ones worth reading, so the feed rests
                    // at the bottom until the reader scrolls up to look back.
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

                    delegate: RowLayout {
                        required property var modelData
                        width: feedView.width
                        spacing: 20

                        Label {
                            Layout.preferredWidth: 56
                            Layout.alignment: Qt.AlignTop
                            text: modelData.time
                            color: Theme.mute
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                        }

                        // Rich text so Mudae's emoji resolve to images and the
                        // per-token tinting matches the other shells; the kind
                        // colour stays as the base for everything untinted.
                        Label {
                            Layout.fillWidth: true
                            text: MudaeEmoji.feedHtml(modelData.text, 16)
                            textFormat: Text.RichText
                            color: run.colorFor(modelData.kind)
                            font.pixelSize: Theme.sizeBody
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                        }
                    }
                }

                Label {
                    anchors.centerIn: parent
                    visible: feedView.count === 0
                    width: parent.width * 0.7
                    horizontalAlignment: Text.AlignHCenter
                    text: Empty.runFeedEmpty(run.connected)
                    color: Theme.mute
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }
            }

            ColumnLayout {
                Layout.preferredWidth: 244
                Layout.maximumWidth: 244
                Layout.fillHeight: true
                spacing: Theme.gap

                // -- last claim ------------------------------------------------
                QuietSection {
                    title: "Last claim"
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            Layout.fillWidth: true
                            text: run.lastClaimName || "none yet"
                            color: run.lastClaimName ? Theme.fg : Theme.mute
                            font.pixelSize: Theme.sizeLarge
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: run.lastClaimDetail !== ""
                            Layout.topMargin: 5
                            text: run.lastClaimDetail
                            color: Theme.accent
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeSmall
                            elide: Text.ElideRight
                        }
                    }
                }

                // -- force divorce farm -----------------------------------------
                QuietSection {
                    title: "Force divorce"
                    visible: run.forceDivorceOn
                    status: run.forceDivorceTarget
                    statusGood: run.forceDivorceOn
                    Layout.fillWidth: true

                    Repeater {
                        model: run.forceDivorceRows
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 12

                            Label {
                                text: modelData.label
                                color: Theme.dim
                                font.pixelSize: Theme.sizeSmall
                            }
                            Item { Layout.fillWidth: true }
                            Label {
                                text: modelData.value
                                color: modelData.tone === "good" ? Theme.good
                                    : (modelData.tone === "bad" ? Theme.bad
                                    : (modelData.tone === "accent" ? Theme.accent : Theme.fg))
                                font.pixelSize: Theme.sizeSmall
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                // -- perk 8, condensed ------------------------------------------
                QuietSection {
                    title: "Smart saver"
                    status: page.saver ? (run.powerSaveOn ? "on" : "off") : ""
                    statusGood: run.powerSaveOn
                    Layout.fillWidth: true

                    QuietMeter {
                        Layout.fillWidth: true
                        label: "Perk 8 today"
                        value: run.perk8Text
                        fraction: run.perk8Fraction
                        accentValue: true
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: run.powerSaveOn
                        text: page.saverLead() + " · can spend " + page.spendText()
                        color: Theme.dim
                        font.pixelSize: Theme.sizeSmall
                        wrapMode: Text.WordWrap
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: run.powerSaveOn && page.perk8Left() !== ""
                        text: page.perk8Left()
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        wrapMode: Text.WordWrap
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: !run.powerSaveOn
                        text: "Off — clicks and $dk follow the ordinary rules."
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        wrapMode: Text.WordWrap
                    }
                }

                // -- perk 9, condensed ------------------------------------------
                QuietSection {
                    title: "Adaptive perk 9"
                    status: run.perk9AdaptiveOn ? "on" : "off"
                    statusGood: run.perk9AdaptiveOn
                    Layout.fillWidth: true

                    QuietMeter {
                        Layout.fillWidth: true
                        label: "Clicks today"
                        value: run.perk9Text
                        fraction: run.perk9Fraction
                        accentValue: true
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: run.perk9AdaptiveOn
                        text: "Taking " + page.thresholdText() + " · " + page.spawnsLeftText()
                        color: Theme.dim
                        font.pixelSize: Theme.sizeSmall
                        wrapMode: Text.WordWrap
                    }

                    // Which spheres that threshold actually admits, as the
                    // artwork rather than a list of colour names — the point is
                    // to be checkable at a glance.
                    Flow {
                        Layout.fillWidth: true
                        visible: run.perk9AdaptiveOn && run.perk9Allowed.length > 0
                        spacing: 4

                        Repeater {
                            model: run.perk9Allowed
                            delegate: SphereTypeBadge {
                                required property string modelData
                                sphereId: modelData
                            }
                        }

                        // What the next tightening would drop, shown faint: the
                        // threshold's direction of travel, without a second row.
                        Repeater {
                            model: run.perk9StricterDrops
                            delegate: SphereTypeBadge {
                                required property string modelData
                                sphereId: modelData
                                opacity: 0.3
                            }
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: run.perk9AdaptiveOn && page.nextMoveText() !== ""
                        text: page.nextMoveText()
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        wrapMode: Text.WordWrap
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: !run.perk9AdaptiveOn
                        text: "Off — perk 9 uses the preset's fixed colour list."
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        wrapMode: Text.WordWrap
                    }
                }

                // -- session haul ------------------------------------------------
                QuietSection {
                    title: "This session"
                    Layout.fillWidth: true

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Label {
                            text: run.compact(run.sessionKakera)
                            color: Theme.fg
                            font.family: Theme.monoFamily
                            font.pixelSize: 26
                            font.weight: Font.Medium
                        }

                        Label {
                            Layout.alignment: Qt.AlignBottom
                            Layout.bottomMargin: 4
                            text: "ka"
                            color: Theme.mute
                            font.pixelSize: Theme.sizeSmall
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        spacing: 18

                        Repeater {
                            model: [
                                { key: "Claims", value: run.sessionClaims },
                                { key: "Spheres", value: run.sessionSpheres },
                                { key: "Keys", value: run.sessionKeys }
                            ]

                            delegate: ColumnLayout {
                                required property var modelData
                                spacing: 3

                                Label {
                                    text: modelData.key
                                    color: Theme.mute
                                    font.pixelSize: Theme.sizeMicro
                                }

                                Label {
                                    text: String(modelData.value)
                                    color: Theme.fg
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeLarge
                                    font.weight: Font.Medium
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
