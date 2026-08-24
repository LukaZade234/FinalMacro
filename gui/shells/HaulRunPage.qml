import QtQuick
import QtQuick.Layouts
import Qt5Compat.GraphicalEffects

import gui 1.0
import "../components"

/*
    Haul — Run page.

    Layout C from the mockups: selector bar, control bar, five vitals, then the
    live feed with a session-haul column beside it.
*/
Item {
    id: page

    RunModel { id: run }
    TargetModel { id: targets }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // ---- selectors -----------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TargetSelector {
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                label: "Account"
                iconName: "accounts"
                value: targets.accountLabel
                options: targets.accountNames
                currentIndex: targets.accountIndex
                onPicked: function(index) { targets.selectAccount(index) }
            }

            TargetSelector {
                Layout.fillWidth: true
                Layout.preferredWidth: 130
                label: "Channel"
                iconName: "servers"
                value: targets.channelLabel
                options: targets.channelLabels
                currentIndex: targets.channelIndex
                onPicked: function(index) { targets.selectChannel(index) }
            }

            TargetSelector {
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                label: "Preset"
                iconName: "presets"
                value: targets.presetLabel
                options: targets.presetNames
                currentIndex: targets.presetIndex
                highlight: true
                onPicked: function(index) { targets.selectPreset(index) }
            }
        }

        // ---- controls ------------------------------------------------------

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: controlFlow.implicitHeight + 20
            radius: Theme.radiusLg
            color: Theme.surface
            border.width: 1
            border.color: Theme.line

            Flow {
                id: controlFlow
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                HaulButton {
                    text: "Stop"
                    variant: "stop"
                    enabled: run.macroRunning || run.engineRunning
                    onClicked: App.stopMacro()
                }

                HaulButton {
                    text: run.connectLabel
                    variant: "ghost"
                    enabled: !run.connecting && !run.disconnecting
                    onClicked: run.connected ? App.disconnect() : App.connect()
                }

                ControlDivider {}

                HaulButton {
                    text: "Start hourly"
                    variant: "hourly"
                    enabled: run.connected && !run.macroRunning
                    onClicked: App.startMacro()
                }

                HaulButton {
                    text: "Roll $us"
                    enabled: run.connected && !run.macroRunning
                    onClicked: App.startUsMode()
                }

                ControlDivider {}

                ControlGroupLabel { text: "Checks" }

                HaulButton {
                    text: "$tu"
                    enabled: run.connected
                    onClicked: App.runTu()
                }

                HaulButton {
                    text: "$us"
                    enabled: run.connected
                    onClicked: App.runUsCheck()
                }

                ControlDivider {}

                ControlGroupLabel { text: "Minigames" }

                HaulButton {
                    text: "$oh"
                    enabled: run.connected
                    onClicked: App.playOhSphere()
                }
                HaulButton {
                    text: "$oc"
                    enabled: run.connected
                    onClicked: App.playOcSphere()
                }
                HaulButton {
                    text: "$oq"
                    enabled: run.connected
                    onClicked: App.playOqSphere()
                }
                HaulButton {
                    text: "Play all"
                    variant: "go"
                    enabled: run.connected
                    onClicked: App.playAllMinigames()
                }
            }
        }

        // ---- vitals --------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            HaulVital {
                Layout.fillWidth: true
                Layout.preferredWidth: 140
                label: "Phase"
                phase: true
                pulsing: run.macroRunning
                value: run.phase
                caption: run.statusLine
            }

            HaulVital {
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                label: "Rolls"
                tone: "accent"
                value: run.rollsLeft >= 0 ? String(run.rollsLeft) : "—"
                suffix: (run.rollsLeft >= 0 && run.rollsMax > 0) ? "/" + run.rollsMax : ""
                fraction: run.rollsFraction
                caption: run.usText !== "—" ? run.usText : "no $us stack"
            }

            HaulVital {
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                label: "Refill"
                value: run.resetMinutes >= 0 ? String(run.resetMinutes) : "—"
                suffix: run.resetMinutes >= 0 ? "m" : ""
                fraction: run.resetFraction
                caption: "waiting for $tu"
            }

            HaulVital {
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                label: "Claim"
                tone: run.claimReady ? "good" : "neutral"
                value: run.claimText
                fraction: run.claimReady ? 1 : -1
                caption: run.nextClaimText !== "—" ? "next " + run.nextClaimText : ""
            }

            HaulVital {
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                label: "Power"
                tone: run.powerTone === "warn" ? "warn" : "neutral"
                value: run.powerPercent >= 0 ? String(run.powerPercent) : "—"
                suffix: run.powerPercent >= 0 ? "%" : ""
                fraction: run.powerFraction
                caption: run.dkText !== "—" ? "dk " + run.dkText : ""
            }
        }

        // ---- feed + haul column --------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 260
                radius: Theme.radiusLg
                color: Theme.surface
                border.width: 1
                border.color: Theme.line
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // feed header
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 15
                            text: "Live feed"
                            color: Theme.fg
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeMedium
                            font.weight: Font.DemiBold
                        }

                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: parent.right
                            anchors.rightMargin: 15
                            spacing: 4

                            Repeater {
                                model: [
                                    { key: "all", label: "All" },
                                    { key: "claim", label: "Claims" },
                                    { key: "kakera", label: "Kakera" },
                                    { key: "error", label: "Errors" }
                                ]

                                delegate: Rectangle {
                                    required property var modelData

                                    readonly property bool active: run.filterKind === modelData.key

                                    width: pillText.implicitWidth + 20
                                    height: 22
                                    radius: 11
                                    color: active ? Theme.raised : "transparent"

                                    Text {
                                        id: pillText
                                        anchors.centerIn: parent
                                        text: modelData.label + " " + (run.counts[modelData.key] || 0)
                                        color: parent.active ? Theme.fg : Theme.mute
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.sizeTiny
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: run.filterKind = modelData.key
                                    }
                                }
                            }
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
                        Layout.topMargin: 6
                        Layout.bottomMargin: 6

                        // An empty card would read as a rendering fault, so the
                        // reason there is nothing to show is spelled out instead.
                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: 33
                            anchors.top: parent.top
                            height: 28
                            verticalAlignment: Text.AlignVCenter
                            visible: feed.count === 0
                            text: run.connected ? "No activity yet" : "Not connected — no activity"
                            color: Theme.mute
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeBody
                        }

                    ListView {
                        id: feed
                        anchors.fill: parent
                        clip: true
                        model: run.visibleFeed
                        boundsBehavior: Flickable.StopAtBounds

                        // Newest entries are appended, so follow the tail unless
                        // the user has scrolled away from it.
                        property bool atTail: true
                        onContentYChanged: atTail = (contentY + height) >= (contentHeight - 24)
                        onCountChanged: if (atTail) positionViewAtEnd()

                        delegate: Item {
                            required property var modelData

                            width: ListView.view.width
                            height: 28

                            Rectangle {
                                anchors.fill: parent
                                color: modelData.kind === "claim"
                                    ? Theme.fade(Theme.good, 0.08)
                                    : "transparent"
                            }

                            Rectangle {
                                id: dot
                                anchors.left: parent.left
                                anchors.leftMargin: 15
                                anchors.verticalCenter: parent.verticalCenter
                                width: 7
                                height: 7
                                rotation: 45
                                color: {
                                    switch (modelData.kind) {
                                    case "claim": return Theme.good
                                    case "kakera": return Theme.accent
                                    case "error": return Theme.bad
                                    case "cmd": return Theme.accent2
                                    default: return Theme.raised
                                    }
                                }
                            }

                            Text {
                                anchors.left: dot.right
                                anchors.leftMargin: 11
                                anchors.right: stamp.left
                                anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.text
                                color: modelData.kind === "error" ? Theme.bad
                                    : (modelData.kind === "skip" ? Theme.mute : Theme.dim)
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.sizeBody
                                elide: Text.ElideRight
                            }

                            Text {
                                id: stamp
                                anchors.right: parent.right
                                anchors.rightMargin: 15
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.time
                                color: Theme.mute
                                font.family: Theme.monoFamily
                                font.pixelSize: 10
                            }
                        }
                    }
                    }
                }
            }

            // ---- side column ------------------------------------------------

            ColumnLayout {
                Layout.preferredWidth: 286
                Layout.maximumWidth: 286
                Layout.fillHeight: true
                spacing: 10

                // session haul
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 132

                    GradientPanel {
                        anchors.fill: parent
                        radius: Theme.radiusLg
                        colorFrom: Theme.blend(Theme.accent2, Theme.surface, 0.20)
                        colorTo: Theme.surface
                        stopTo: 0.65
                        borderColor: Theme.line
                        borderWidth: 1
                    }

                    Column {
                        anchors.fill: parent
                        anchors.leftMargin: 15
                        anchors.rightMargin: 15
                        anchors.topMargin: 13
                        spacing: 0

                        Text {
                            text: Theme.sectionLabel("This session")
                            color: Theme.mute
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                            bottomPadding: 10
                        }

                        Text {
                            id: haulNumber
                            text: run.compact(run.sessionKakera)
                            color: Theme.fg
                            font.family: Theme.fontFamily
                            font.pixelSize: 30
                            font.weight: Font.Bold
                            font.letterSpacing: -0.03 * 30

                            // The mockup fills this number with a fg→accent
                            // gradient, which needs a shader. The software
                            // renderer has none, so it keeps the solid colour.
                            layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
                            layer.effect: LinearGradient {
                                start: Qt.point(0, 0)
                                end: Qt.point(haulNumber.width, haulNumber.height * 0.4)
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: Theme.fg }
                                    GradientStop { position: 0.7; color: Theme.accent }
                                    GradientStop { position: 1.0; color: Theme.accent }
                                }
                            }
                        }

                        Item { width: 1; height: 10 }

                        Row {
                            id: haulTally
                            width: parent.width
                            spacing: 7

                            Repeater {
                                model: [
                                    { label: "Claims", value: run.sessionClaims, tone: "good" },
                                    { label: "Spheres", value: run.sessionSpheres, tone: "" },
                                    { label: "Keys", value: run.sessionKeys, tone: "" }
                                ]

                                delegate: Column {
                                    required property var modelData
                                    width: (haulTally.width - 14) / 3
                                    spacing: 1

                                    Text {
                                        text: modelData.label
                                        color: Theme.mute
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.sizeSmall
                                    }
                                    Text {
                                        text: run.compact(modelData.value)
                                        color: modelData.tone === "good" ? Theme.good : Theme.fg
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.sizeLarge
                                        font.weight: Font.Bold
                                    }
                                }
                            }
                        }
                    }
                }

                // last claim
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 122

                    GradientPanel {
                        anchors.fill: parent
                        radius: Theme.radiusLg
                        colorFrom: Theme.blend(Theme.good, Theme.surface, 0.11)
                        colorTo: Theme.surface
                        stopTo: 0.8
                        borderColor: Theme.fade(Theme.good, 0.34)
                        borderWidth: 1
                    }

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.leftMargin: 15
                        anchors.rightMargin: 15
                        anchors.topMargin: 13
                        spacing: 3

                        Text {
                            text: Theme.sectionLabel("Last claim")
                            color: Theme.mute
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                            bottomPadding: 7
                        }

                        Text {
                            width: parent.width
                            text: run.lastClaimName !== "" ? run.lastClaimName : "Nothing yet"
                            color: run.lastClaimName !== "" ? Theme.fg : Theme.mute
                            font.family: Theme.fontFamily
                            font.pixelSize: 17
                            font.weight: Font.Bold
                            font.letterSpacing: -0.02 * 17
                            elide: Text.ElideRight
                        }

                        Text {
                            width: parent.width
                            text: run.lastClaimDetail !== "" ? run.lastClaimDetail : "no claims this session"
                            color: Theme.dim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeSmall
                            elide: Text.ElideRight
                        }
                    }

                    Rectangle {
                        id: claimRule
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: 15
                        anchors.rightMargin: 15
                        anchors.bottomMargin: 36
                        height: 1
                        color: Theme.line
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 15
                        anchors.top: claimRule.bottom
                        anchors.topMargin: 9
                        text: run.sessionClaims + (run.sessionClaims === 1 ? " claim" : " claims")
                        color: Theme.good
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.sizeLarge
                        font.weight: Font.Bold
                    }

                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 15
                        anchors.top: claimRule.bottom
                        anchors.topMargin: 11
                        text: run.lastClaimTime
                        color: Theme.mute
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.sizeSmall
                    }
                }

                // perks
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 130
                    radius: Theme.radiusLg
                    color: Theme.surface
                    border.width: 1
                    border.color: Theme.line

                    Column {
                        anchors.fill: parent
                        anchors.leftMargin: 15
                        anchors.rightMargin: 15
                        anchors.topMargin: 13
                        spacing: 7

                        Text {
                            text: Theme.sectionLabel("Perks today")
                            color: Theme.mute
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.sizeMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                            bottomPadding: 3
                        }

                        Item {
                            width: parent.width
                            height: 16

                            Text {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Perk 8"
                                color: Theme.dim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.sizeBody
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: run.perk8Text
                                color: Theme.accent
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeBody
                                font.weight: Font.DemiBold
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 4
                            radius: 2
                            color: Theme.raised
                            visible: run.perk8Fraction >= 0

                            Rectangle {
                                width: parent.width * Math.min(1, Math.max(0, run.perk8Fraction))
                                height: parent.height
                                radius: parent.radius
                                color: Theme.accent
                            }
                        }

                        Item {
                            width: parent.width
                            height: 16

                            Text {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Perk 9"
                                color: Theme.dim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.sizeBody
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: run.perk9Text
                                color: Theme.fg
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeBody
                                font.weight: Font.DemiBold
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 4
                            radius: 2
                            color: Theme.raised
                            visible: run.perk9Fraction >= 0

                            Rectangle {
                                width: parent.width * Math.min(1, Math.max(0, run.perk9Fraction))
                                height: parent.height
                                radius: parent.radius
                                color: Theme.accent2
                            }
                        }

                        Item { width: 1; height: 3 }

                        Repeater {
                            model: [
                                { label: "Rolls reset", value: run.resetText, accent: true },
                                { label: "Next claim", value: run.nextClaimText, accent: false }
                            ]

                            delegate: Item {
                                required property var modelData
                                width: parent.width
                                height: 22

                                Rectangle {
                                    id: bullet
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 5
                                    height: 5
                                    radius: 2.5
                                    color: modelData.accent ? Theme.accent : Theme.line
                                }

                                Text {
                                    anchors.left: bullet.right
                                    anchors.leftMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.label
                                    color: Theme.dim
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.sizeBody
                                }

                                Text {
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.value
                                    color: modelData.accent ? Theme.accent : Theme.fg
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeBody
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
