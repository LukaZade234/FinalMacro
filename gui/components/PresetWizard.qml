import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Five-step wizard aligned with Presets tab sections.
Item {
    id: wizard
    visible: open

    property string presetId: ""
    property var kakeraOptions: []
    property var sphereOptions: []
    property bool open: false
    property int activeStep: 0
    property bool showAdvancedKakera: false

    readonly property var stepTitles: [
        "Rolling", "Claims", "Reactions", "$us", "Expert"
    ]

    property var draft: ({
        basic: { prefix: "$", roll_command: "wa", roll_delay_sec: 0.6,
                 humanize_roll_delay: false, roll_delay_jitter_sec: 0.4, notification_mode: false },
        character_claim: { enabled: true, claim_on_wish_ping: true, only_final_hour: true,
                           auto_use_rt: false, min_kakera: null, max_claim_rank: null },
        kakera_reaction: { enabled: false, types_allowed: [], require_chaos_key: false,
                           require_chaos_key_bypass_types: ["kakeraP"],
                           require_perk_8: false, min_spheres: null, low_power: null,
                           perk_8_budget_mode: false, perk_8_priority: true,
                           perk_8_budget_bypass_types: ["kakeraP"],
                           perk_8_types_allowed: [], auto_use_dk: false,
                           perk_8_power_save: true, perk_8_power_window_hours: 4 },
        us_roll_kakera: { override: false, skip_kakera: false, types_allowed: [] },
        us_mode: { us_batch_size: 20, us_reset_margin_minutes: 2,
                   us_keep_draining: false, us_stop_on_power_exhausted: false,
                   us_stop_after_rolls_enabled: false, us_stop_after_rolls: 100,
                   us_schedule_enabled: false, us_schedule_start: "04:00",
                   us_schedule_end: "06:00" },
        sphere_reaction: { enabled: false, types_allowed: [] },
        expert: { claim_expire_sec: 45,
                  us_read_before_add_delay_sec: 2, us_add_delay_sec: 5,
                  us_roll_timeout_retry_sec: 5 }
    })

    signal finished()

    function loadFromPreset() {
        activeStep = 0
        if (!presetId)
            return
        try {
            var d = JSON.parse(App.getPresetRulesJson(presetId)) || {}
            draft = {
                basic: Object.assign({}, draft.basic, d.basic || {}),
                character_claim: Object.assign({}, draft.character_claim, d.character_claim || {}),
                kakera_reaction: Object.assign({}, draft.kakera_reaction, d.kakera_reaction || {}),
                us_roll_kakera: Object.assign({}, draft.us_roll_kakera, d.us_roll_kakera || {}),
                us_mode: Object.assign({}, draft.us_mode, d.us_mode || {}),
                sphere_reaction: Object.assign({}, draft.sphere_reaction, d.sphere_reaction || {}),
                expert: Object.assign({}, draft.expert, d.expert || {})
            }
            var us = draft.us_roll_kakera
            if (us.mode !== undefined && us.override === undefined) {
                if (us.mode === "none") {
                    us.override = true
                    us.skip_kakera = true
                } else if (us.mode === "selected") {
                    us.override = true
                    us.skip_kakera = false
                } else {
                    us.override = false
                    us.skip_kakera = false
                }
                delete us.mode
                draft.us_roll_kakera = us
            }
            showAdvancedKakera = kakeraUsesAdvancedOptions()
        } catch (e) {
        }
    }

    function kakeraUsesAdvancedOptions() {
        var k = draft.kakera_reaction || {}
        if (k.require_perk_8)
            return true
        if (k.min_spheres !== null && k.min_spheres !== undefined)
            return true
        if (k.perk_8_budget_mode)
            return true
        if (k.low_power !== null && k.low_power !== undefined)
            return true
        return false
    }

    function setDraftField(block, key, value) {
        var d = JSON.parse(JSON.stringify(draft))
        d[block][key] = value
        draft = d
    }

    function setLowPowerEnabled(on) {
        var d = JSON.parse(JSON.stringify(draft))
        if (on) {
            d.kakera_reaction.low_power = d.kakera_reaction.low_power
                || { below_percent: 30, types_allowed: [] }
        } else {
            d.kakera_reaction.low_power = null
        }
        draft = d
    }

    function setLowPowerField(key, value) {
        var d = JSON.parse(JSON.stringify(draft))
        if (!d.kakera_reaction.low_power) {
            d.kakera_reaction.low_power = { below_percent: 30, types_allowed: [] }
        }
        d.kakera_reaction.low_power[key] = value
        draft = d
    }

    function parseIntOrNull(text) {
        if (!text || text.trim().length === 0)
            return null
        var n = parseInt(text)
        return isNaN(n) ? null : n
    }

    function parseFloatOrDefault(text, fallback) {
        if (!text || text.trim().length === 0)
            return fallback
        var n = parseFloat(text)
        return isNaN(n) ? fallback : n
    }

    function saveAndClose() {
        if (!presetId) {
            open = false
            return
        }
        var patch = {
            basic: draft.basic,
            character_claim: draft.character_claim,
            kakera_reaction: draft.kakera_reaction,
            us_roll_kakera: draft.us_roll_kakera,
            us_mode: draft.us_mode,
            sphere_reaction: draft.sphere_reaction,
            expert: draft.expert
        }
        App.updatePresetRules(presetId, JSON.stringify(patch))
        open = false
        finished()
    }

    onOpenChanged: {
        if (open)
            loadFromPreset()
    }

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: 0.55
        MouseArea {
            anchors.fill: parent
            onClicked: { /* swallow */ }
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - 60, 720)
        height: Math.min(parent.height - 60, 620)
        radius: 12
        color: Theme.bgMedium
        border.color: Theme.border

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: "Preset wizard · " + (presetId || "(no preset)")
                    color: Theme.fgPrimary
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Label {
                    text: "Step " + (activeStep + 1) + " / 5 · " + stepTitles[activeStep]
                    color: Theme.fgMuted
                    font.pixelSize: 11
                }
                ToolButton {
                    text: "×"
                    onClicked: wizard.open = false
                    contentItem: Text {
                        text: parent.text
                        color: Theme.fgSecondary
                        font.pixelSize: 18
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            StackLayout {
                id: stepStack
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: wizard.activeStep

                // ---- Rolling ----
                ColumnLayout {
                    spacing: 8
                    Label { text: "Rolling"; color: Theme.fgPrimary; font.pixelSize: 14; font.weight: Font.DemiBold }
                    Label {
                        text: "How the macro sends roll commands and paces each batch."
                        color: Theme.fgMuted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    GridLayout {
                        columns: 2
                        columnSpacing: 12
                        rowSpacing: 8
                        Layout.fillWidth: true

                        Label { text: "Prefix"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                        ThemedTextField {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            maximumLength: 4
                            text: draft.basic.prefix || "$"
                            onEditingFinished: setDraftField("basic", "prefix", text)
                        }

                        Label { text: "Roll command"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                        ThemedTextField {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            text: draft.basic.roll_command || "wa"
                            onEditingFinished: setDraftField("basic", "roll_command", text)
                        }

                        Label { text: "Delay between rolls (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                        ThemedTextField {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            text: draft.basic.roll_delay_sec !== undefined ? draft.basic.roll_delay_sec.toString() : "0.6"
                            onEditingFinished: setDraftField("basic", "roll_delay_sec", parseFloatOrDefault(text, 0.6))
                        }
                    }
                    ThemedCheckBox {
                        Layout.fillWidth: true
                        text: "Humanize delays (random extra wait between rolls)"
                        checked: !!draft.basic.humanize_roll_delay
                        onToggled: setDraftField("basic", "humanize_roll_delay", checked)
                    }
                    GridLayout {
                        columns: 2
                        columnSpacing: 12
                        rowSpacing: 8
                        Layout.fillWidth: true
                        visible: !!draft.basic.humanize_roll_delay

                        Label { text: "Extra jitter (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                        ThemedTextField {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            text: draft.basic.roll_delay_jitter_sec !== undefined ? draft.basic.roll_delay_jitter_sec.toString() : "0.4"
                            onEditingFinished: setDraftField("basic", "roll_delay_jitter_sec", parseFloatOrDefault(text, 0.4))
                        }
                    }
                    ThemedCheckBox {
                        Layout.fillWidth: true
                        text: "Notification mode (disconnect between hourly sessions)"
                        checked: !!draft.basic.notification_mode
                        onToggled: setDraftField("basic", "notification_mode", checked)
                    }
                }

                // ---- Claims ----
                ScrollView {
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 8
                        Label { text: "Claims"; color: Theme.fgPrimary; font.pixelSize: 14; font.weight: Font.DemiBold }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Claim characters (master switch)"
                            checked: draft.character_claim.enabled
                            onToggled: setDraftField("character_claim", "enabled", checked)
                        }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Always claim if a wish pings you"
                            checked: draft.character_claim.claim_on_wish_ping
                            onToggled: setDraftField("character_claim", "claim_on_wish_ping", checked)
                        }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Use $rt for wish pings when claim is on cooldown (Emerald badge)"
                            checked: !!draft.character_claim.auto_use_rt
                            onToggled: setDraftField("character_claim", "auto_use_rt", checked)
                        }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Only claim during the final roll hour (claim reset = roll reset on $tu)"
                            checked: draft.character_claim.only_final_hour
                            onToggled: setDraftField("character_claim", "only_final_hour", checked)
                        }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Remember $tu state between sessions"
                            checked: !!draft.character_claim.persist_tu_state
                            onToggled: setDraftField("character_claim", "persist_tu_state", checked)
                        }
                        GridLayout {
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 8
                            Layout.fillWidth: true

                            Label { text: "Instant claim min kakera"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 200 }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                placeholderText: "blank = off"
                                text: draft.character_claim.min_kakera === null ? "" : draft.character_claim.min_kakera.toString()
                                onEditingFinished: setDraftField("character_claim", "min_kakera", parseIntOrNull(text))
                            }

                            Label { text: "Instant claim at claim rank ≤"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 200; wrapMode: Text.WordWrap }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                placeholderText: "e.g. 200"
                                text: draft.character_claim.max_claim_rank === null ? "" : draft.character_claim.max_claim_rank.toString()
                                onEditingFinished: setDraftField("character_claim", "max_claim_rank", parseIntOrNull(text))
                            }
                        }
                    }
                }

                // ---- Reactions ----
                ScrollView {
                    id: kakeraStepScroll
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: kakeraStepScroll.availableWidth
                        spacing: 8
                        Label { text: "Reactions"; color: Theme.fgPrimary; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Label { text: "Kakera"; color: Theme.fgSecondary; font.pixelSize: 12; font.weight: Font.DemiBold }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Enable kakera reactions"
                            checked: draft.kakera_reaction.enabled
                            onToggled: setDraftField("kakera_reaction", "enabled", checked)
                        }
                        ColorChipPicker {
                            Layout.fillWidth: true
                            title: "Allowed kakera colors"
                            options: kakeraOptions
                            selected: draft.kakera_reaction.types_allowed || []
                            onSelectionChanged: function(ids) {
                                setDraftField("kakera_reaction", "types_allowed", ids)
                            }
                        }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Use $dk when reaction power runs out"
                            checked: !!draft.kakera_reaction.auto_use_dk
                            onToggled: setDraftField("kakera_reaction", "auto_use_dk", checked)
                        }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Require chaos key"
                            checked: !!draft.kakera_reaction.require_chaos_key
                            onToggled: setDraftField("kakera_reaction", "require_chaos_key", checked)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Advanced kakera options"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.fillWidth: true }
                            ThemedSwitch {
                                checked: wizard.showAdvancedKakera
                                onToggled: wizard.showAdvancedKakera = checked
                            }
                        }
                        KakeraAdvancedPanel {
                            Layout.fillWidth: true
                            visible: wizard.showAdvancedKakera
                            rules: wizard.draft
                            kakeraOptions: wizard.kakeraOptions
                            onPatch: function(block, key, value) { setDraftField(block, key, value) }
                            onPatchLowPower: function(key, value) { setLowPowerField(key, value) }
                            onSetLowPowerEnabled: function(on) { setLowPowerEnabled(on) }
                        }
                        Label { text: "Spheres"; color: Theme.fgSecondary; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.topMargin: 8 }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Enable sphere reactions"
                            checked: draft.sphere_reaction.enabled
                            onToggled: setDraftField("sphere_reaction", "enabled", checked)
                        }
                        ColorChipPicker {
                            Layout.fillWidth: true
                            title: "Allowed sphere colors"
                            options: sphereOptions
                            selected: draft.sphere_reaction.types_allowed || []
                            onSelectionChanged: function(ids) {
                                setDraftField("sphere_reaction", "types_allowed", ids)
                            }
                        }
                    }
                }

                // ---- $us ----
                ScrollView {
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    contentWidth: availableWidth
                    UsRollPanel {
                        width: parent.width
                        rules: wizard.draft
                        kakeraOptions: wizard.kakeraOptions
                        onPatch: function(block, key, value) { setDraftField(block, key, value) }
                        onPatchUsMode: function(key, value) { setDraftField("us_mode", key, value) }
                    }
                }

                // ---- Expert ----
                ColumnLayout {
                    spacing: 8
                    Label { text: "Expert"; color: Theme.fgPrimary; font.pixelSize: 14; font.weight: Font.DemiBold }
                    Label {
                        text: "Optional fine-tuning. Defaults work for most setups — skip if unsure."
                        color: Theme.fgMuted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    GridLayout {
                        columns: 2
                        columnSpacing: 12
                        rowSpacing: 8
                        Layout.fillWidth: true

                        Label { text: "Claim timeout (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 180 }
                        ThemedTextField {
                            Layout.fillWidth: true
                            text: draft.expert.claim_expire_sec !== undefined ? draft.expert.claim_expire_sec.toString() : "45"
                            onEditingFinished: setDraftField("expert", "claim_expire_sec", parseInt(text) || 45)
                        }

                        Label { text: "Rolls per $us"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 180 }
                        ThemedTextField {
                            Layout.fillWidth: true
                            text: draft.us_mode.us_batch_size !== undefined ? draft.us_mode.us_batch_size.toString() : "20"
                            onEditingFinished: setDraftField("us_mode", "us_batch_size", parseInt(text) || 20)
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                ThemedButton {
                    text: "Back"
                    enabled: activeStep > 0
                    onClicked: activeStep = Math.max(0, activeStep - 1)
                }

                Item { Layout.fillWidth: true }

                ThemedButton {
                    text: "Skip"
                    visible: activeStep < 4
                    onClicked: activeStep = Math.min(4, activeStep + 1)
                }

                ThemedButton {
                    text: activeStep < 4 ? "Next" : "Save preset"
                    accent: true
                    onClicked: {
                        if (activeStep < 4) {
                            activeStep += 1
                        } else {
                            saveAndClose()
                        }
                    }
                }
            }
        }
    }
}
