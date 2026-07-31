import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

// Six-step linear wizard overlay for editing one preset.
// Reads current values from App.getPresetRulesJson and saves one patch on Finish.
Item {
    id: wizard
    visible: open

    property string presetId: ""
    property var kakeraOptions: []
    property var sphereOptions: []
    property bool open: false
    property int activeStep: 0
    property bool showAdvancedKakera: false

    // Working draft (initialised from the current preset on open).
    property var draft: ({
        character_claim: { enabled: true, claim_on_wish_ping: true, only_final_hour: true,
                           min_kakera: null, max_claim_rank: null },
        kakera_reaction: { enabled: false, types_allowed: [], require_chaos_key: false,
                           require_chaos_key_bypass_types: ["kakeraP"],
                           require_perk_8: false, min_spheres: null, low_power: null,
                           perk_8_budget_mode: false,
                           perk_8_budget_bypass_types: ["kakeraP"],
                           perk_8_types_allowed: [], auto_use_dk: false },
        us_roll_kakera: { override: false, skip_kakera: false, types_allowed: [] },
        sphere_reaction: { enabled: false, types_allowed: [] }
    })

    signal finished()

    function loadFromPreset() {
        activeStep = 0
        if (!presetId) {
            return
        }
        try {
            var d = JSON.parse(App.getPresetRulesJson(presetId)) || {}
            draft = {
                character_claim: Object.assign({}, draft.character_claim, d.character_claim || {}),
                kakera_reaction: Object.assign({}, draft.kakera_reaction, d.kakera_reaction || {}),
                us_roll_kakera: Object.assign({}, draft.us_roll_kakera, d.us_roll_kakera || {}),
                sphere_reaction: Object.assign({}, draft.sphere_reaction, d.sphere_reaction || {})
            }
            // Legacy ``mode`` field from older presets.
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
        var u = draft.us_roll_kakera || {}
        if (k.require_perk_8)
            return true
        if (k.min_spheres !== null && k.min_spheres !== undefined)
            return true
        if (k.perk_8_budget_mode)
            return true
        if (k.low_power !== null && k.low_power !== undefined)
            return true
        if (u.override)
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

    function saveAndClose() {
        if (!presetId) {
            open = false
            return
        }
        var patch = {
            character_claim: draft.character_claim,
            kakera_reaction: draft.kakera_reaction,
            us_roll_kakera: draft.us_roll_kakera,
            sphere_reaction: draft.sphere_reaction
        }
        App.updatePresetRules(presetId, JSON.stringify(patch))
        open = false
        finished()
    }

    onOpenChanged: {
        if (open) {
            loadFromPreset()
        }
    }

    // Backdrop
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
        height: Math.min(parent.height - 60, 600)
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
                    text: "Step " + (activeStep + 1) + " / 4"
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

            // Body — StackLayout switches between steps.
            StackLayout {
                id: stepStack
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: wizard.activeStep

                // ---- Step 1: Character claim ----
                ColumnLayout {
                    spacing: 8
                    Label {
                        text: "1 · Character claim"
                        color: Theme.fgPrimary
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: "Decide whether the macro claims characters at all and how it picks them. Wish pings are honored separately so you can leave the main block off and still catch wishlist drops."
                        color: Theme.fgMuted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
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
                        text: "Only claim during the final roll hour"
                        checked: draft.character_claim.only_final_hour
                        onToggled: setDraftField("character_claim", "only_final_hour", checked)
                    }
                    Label {
                        text: "Example: \"enabled + only final hour\" reproduces the current 'best claim at reset' behaviour."
                        color: Theme.fgMuted
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                // ---- Step 2: Claim triggers ----
                ColumnLayout {
                    spacing: 8
                    Label { text: "2 · Claim triggers"; color: Theme.fgPrimary; font.pixelSize: 14; font.weight: Font.DemiBold }
                    Label {
                        text: "Leave fields blank to keep them off. Any non-blank trigger causes an instant claim mid-batch when it fires."
                        color: Theme.fgMuted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true
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

                        Label {
                            text: "Instant claim at claim rank ≤"
                            color: Theme.fgSecondary
                            font.pixelSize: 11
                            Layout.preferredWidth: 200
                            wrapMode: Text.WordWrap
                        }
                        ThemedTextField {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            placeholderText: "e.g. 200 = ranks 1–200"
                            text: draft.character_claim.max_claim_rank === null ? "" : draft.character_claim.max_claim_rank.toString()
                            onEditingFinished: setDraftField("character_claim", "max_claim_rank", parseIntOrNull(text))
                        }
                    }
                }

                // ---- Step 3: Kakera reaction ----
                ScrollView {
                    id: kakeraStepScroll
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: kakeraStepScroll.availableWidth
                        spacing: 8
                        Label { text: "3 · Kakera reaction"; color: Theme.fgPrimary; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Label {
                            text: "Pick which kakera colors the macro should click. Leave all unselected to allow every color."
                            color: Theme.fgMuted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true
                        }
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
                            text: "Use $dk when reaction power runs out (refills power to max)"
                            checked: !!draft.kakera_reaction.auto_use_dk
                            onToggled: setDraftField("kakera_reaction", "auto_use_dk", checked)
                        }
                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Require chaos key"
                            checked: !!draft.kakera_reaction.require_chaos_key
                            onToggled: setDraftField("kakera_reaction", "require_chaos_key", checked)
                        }
                        ColorChipPicker {
                            Layout.fillWidth: true
                            visible: !!draft.kakera_reaction.require_chaos_key
                            title: "Ignore chaos key requirement for"
                            options: kakeraOptions
                            selected: draft.kakera_reaction.require_chaos_key_bypass_types || ["kakeraP"]
                            onSelectionChanged: function(ids) {
                                setDraftField("kakera_reaction", "require_chaos_key_bypass_types", ids)
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Label {
                                text: "Advanced kakera options"
                                color: Theme.fgSecondary
                                font.pixelSize: 11
                                Layout.fillWidth: true
                            }
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
                            onPatch: function(block, key, value) {
                                setDraftField(block, key, value)
                            }
                            onPatchLowPower: function(key, value) {
                                setLowPowerField(key, value)
                            }
                            onSetLowPowerEnabled: function(on) {
                                setLowPowerEnabled(on)
                            }
                        }
                    }
                }

                // ---- Step 4: Sphere reaction ----
                ColumnLayout {
                    spacing: 8
                    Label { text: "4 · Sphere reaction"; color: Theme.fgPrimary; font.pixelSize: 14; font.weight: Font.DemiBold }
                    Label {
                        text: "Perk 9 lets you grab spheres on roll. Pick which colors to click — leaving all unselected accepts any color."
                        color: Theme.fgMuted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
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

            // Footer
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
                    visible: activeStep < 3
                    onClicked: activeStep = Math.min(3, activeStep + 1)
                }

                ThemedButton {
                    text: activeStep < 3 ? "Next" : "Save preset"
                    accent: true
                    onClicked: {
                        if (activeStep < 3) {
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
