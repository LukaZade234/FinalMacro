import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: presetsRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var presetData: ({ presets: [] })
    property int selectedIndex: 0
    property string editingPresetId: ""
    property var rules: ({})
    property bool _ready: false
    property bool showAdvancedKakera: false
    property int activeSection: 0

    readonly property var sectionLabels: [
        "Rolling", "Claims", "Reactions", "$us", "Expert"
    ]

    readonly property var kakeraOptions: [
        { id: "kakeraP", label: "Purple",  color: "#9d7cd8", icon: "../assets/kakera/KakeraP.png"  },
        { id: "kakera",  label: "Blue",    color: "#7aa2f7", icon: "../assets/kakera/Kakera.png"   },
        { id: "kakeraT", label: "Teal",    color: "#2ac3de", icon: "../assets/kakera/KakeraT.png"  },
        { id: "kakeraG", label: "Green",   color: "#9ece6a", icon: "../assets/kakera/KakeraG.png"  },
        { id: "kakeraY", label: "Yellow",  color: "#e0af68", icon: "../assets/kakera/KakeraY.png"  },
        { id: "kakeraO", label: "Orange",  color: "#ff9e64", icon: "../assets/kakera/KakeraO.png"  },
        { id: "kakeraR", label: "Red",     color: "#f7768e", icon: "../assets/kakera/KakeraR.png"  },
        { id: "kakeraW", label: "Rainbow", color: "#c0caf5", icon: "../assets/kakera/KakeraW.png"  },
        { id: "kakeraL", label: "Light",   color: "#bb9af7", icon: "../assets/kakera/KakeraL.png"  },
        { id: "kakeraD", label: "Dark",    color: "#3b4252", icon: "../assets/kakera/KakeraD.webp" },
        { id: "kakeraC", label: "Chaos",   color: "#ff5fa2", icon: "../assets/kakera/KakeraC.webp" }
    ]

    readonly property var sphereOptions: SphereAssets.options

    function reload() {
        _ready = false
        try {
            presetData = JSON.parse(App.presetsJson)
        } catch (e) {
            presetData = { presets: [] }
        }
        if (selectedIndex >= (presetData.presets || []).length)
            selectedIndex = Math.max(0, (presetData.presets || []).length - 1)
        if (presetList)
            presetList.currentIndex = selectedIndex
        var p = currentPreset()
        editingPresetId = p ? p.id : ""
        loadRules()
        _ready = true
    }

    function presets() {
        return presetData.presets || []
    }

    function currentPreset() {
        var list = presets()
        if (selectedIndex < 0 || selectedIndex >= list.length)
            return null
        return list[selectedIndex]
    }

    function loadRules() {
        if (!editingPresetId) {
            rules = {}
            showAdvancedKakera = false
            return
        }
        try {
            rules = JSON.parse(App.getPresetRulesJson(editingPresetId)) || {}
        } catch (e) {
            rules = {}
        }
        showAdvancedKakera = kakeraUsesAdvancedOptions()
    }

    function kakeraUsesAdvancedOptions() {
        var k = rules.kakera_reaction || {}
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

    function patch(block, key, value) {
        if (!_ready || !editingPresetId)
            return
        var patchObj = {}
        var blockObj = {}
        blockObj[key] = value
        patchObj[block] = blockObj
        App.updatePresetRules(editingPresetId, JSON.stringify(patchObj))
    }

    function patchLowPower(key, value) {
        if (!_ready || !editingPresetId)
            return
        var patchObj = { kakera_reaction: { low_power: {} } }
        patchObj.kakera_reaction.low_power[key] = value
        App.updatePresetRules(editingPresetId, JSON.stringify(patchObj))
    }

    function setLowPowerEnabled(on) {
        if (!_ready || !editingPresetId)
            return
        var payload = on
            ? { kakera_reaction: { low_power: { below_percent: 30, types_allowed: [] } } }
            : { kakera_reaction: { low_power: null } }
        App.updatePresetRules(editingPresetId, JSON.stringify(payload))
    }

    function getField(block, key) {
        if (!rules[block])
            return ""
        var v = rules[block][key]
        return (v === null || v === undefined) ? "" : v.toString()
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

    Connections {
        target: App
        function onConfigChanged() {
            presetsRoot.reload()
        }
    }

    ScrollablePage {
        anchors.fill: parent

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 640
            spacing: 12

        PanelCard {
            Layout.preferredWidth: 200
            Layout.maximumWidth: 240
            Layout.minimumHeight: 520
            Layout.alignment: Qt.AlignTop
            title: "Presets"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    ThemedTextField {
                        id: newPresetField
                        Layout.fillWidth: true
                        placeholderText: "Preset name"
                    }
                    ThemedButton {
                        text: "Add"
                        accent: true
                        enabled: newPresetField.text.trim().length > 0
                        onClicked: {
                            var newId = App.addPreset(newPresetField.text.trim())
                            newPresetField.text = ""
                            reload()
                            for (var i = 0; i < presets().length; i++) {
                                if (presets()[i].id === newId) {
                                    selectedIndex = i
                                    presetList.currentIndex = i
                                    editingPresetId = newId
                                    loadRules()
                                    break
                                }
                            }
                            wizardLoader.activeStep = 0
                            wizardLoader.open = true
                        }
                    }
                }

                ListView {
                    id: presetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: presets().length
                    currentIndex: selectedIndex
                    onCurrentIndexChanged: {
                        if (currentIndex === selectedIndex)
                            return
                        selectedIndex = currentIndex
                        var p = currentPreset()
                        editingPresetId = p ? p.id : ""
                        loadRules()
                    }
                    delegate: ThemedListDelegate {
                        width: presetList.width
                        text: presets()[index] ? presets()[index].id : ""
                        highlighted: presetList.currentIndex === index
                        onClicked: presetList.currentIndex = index
                    }
                }

                ThemedButton {
                    Layout.fillWidth: true
                    text: "Duplicate"
                    enabled: currentPreset() !== null
                    onClicked: {
                        var p = currentPreset()
                        if (!p)
                            return
                        App.duplicatePreset(p.id, p.id + "_copy")
                        reload()
                    }
                }

                ThemedButton {
                    Layout.fillWidth: true
                    text: "Remove"
                    danger: true
                    enabled: presets().length > 1 && currentPreset() !== null
                    onClicked: {
                        var p = currentPreset()
                        if (!p)
                            return
                        App.removePreset(p.id)
                        reload()
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: "Set the active preset on Run → Run target."
                    color: Theme.fgMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 520
            spacing: 10

            RowLayout {
                Layout.fillWidth: true

                Label {
                    text: editingPresetId ? "Preset: " + editingPresetId : "Select or add a preset"
                    color: Theme.fgPrimary
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                ThemedButton {
                    text: "Wizard"
                    enabled: editingPresetId.length > 0
                    onClicked: {
                        wizardLoader.activeStep = 0
                        wizardLoader.open = true
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Repeater {
                    model: presetsRoot.sectionLabels
                    PresetSectionTab {
                        Layout.fillWidth: true
                        text: modelData
                        tabActive: presetsRoot.activeSection === index
                        onClicked: presetsRoot.activeSection = index
                    }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.minimumHeight: 420
                currentIndex: presetsRoot.activeSection

                // ---- Rolling ----
                ScrollablePage {
                    PanelCard {
                        title: "Commands"
                        titleSize: 13
                        Layout.fillWidth: true

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
                                text: (rules.basic && rules.basic.prefix) ? rules.basic.prefix : "$"
                                onEditingFinished: patch("basic", "prefix", text)
                            }

                            Label { text: "Roll command"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                text: (rules.basic && rules.basic.roll_command) ? rules.basic.roll_command : "wa"
                                onEditingFinished: patch("basic", "roll_command", text)
                            }

                            Label { text: "Delay between rolls (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                text: (rules.basic && rules.basic.roll_delay_sec !== undefined) ? rules.basic.roll_delay_sec.toString() : "0.6"
                                onEditingFinished: patch("basic", "roll_delay_sec", parseFloatOrDefault(text, 0.6))
                            }
                        }
                    }

                    PanelCard {
                        title: "Session"
                        titleSize: 13
                        Layout.fillWidth: true

                        ThemedCheckBox {
                            Layout.fillWidth: true
                            text: "Disconnect between hourly roll sessions so phone notifications work"
                            checked: rules.basic ? !!rules.basic.notification_mode : false
                            onToggled: patch("basic", "notification_mode", checked)
                        }
                    }
                }

                // ---- Claims ----
                ScrollablePage {
                    RuleBlockCard {
                        Layout.fillWidth: true
                        title: "Character claim"
                        subtitle: (rules.character_claim && rules.character_claim.enabled)
                            ? "Claim characters that match these triggers."
                            : "All character claims disabled."
                        enabled_: rules.character_claim ? rules.character_claim.enabled : true
                        onEnabledToggled: function(value) { patch("character_claim", "enabled", value) }

                        PanelCard {
                            title: "Wish behavior"
                            titleSize: 12
                            Layout.fillWidth: true

                            ThemedCheckBox {
                                Layout.fillWidth: true
                                text: "Claim immediately when a wish pings you"
                                checked: rules.character_claim ? rules.character_claim.claim_on_wish_ping : true
                                onToggled: patch("character_claim", "claim_on_wish_ping", checked)
                            }

                            ThemedCheckBox {
                                Layout.fillWidth: true
                                text: "Use $rt for wish pings when claim is on cooldown (Emerald badge)"
                                checked: rules.character_claim ? !!rules.character_claim.auto_use_rt : false
                                onToggled: patch("character_claim", "auto_use_rt", checked)
                            }
                        }

                        PanelCard {
                            title: "Batch behavior"
                            titleSize: 12
                            Layout.fillWidth: true

                            ThemedCheckBox {
                                Layout.fillWidth: true
                                text: "Only claim during the final roll hour (claim reset = roll reset on $tu)"
                                checked: rules.character_claim ? rules.character_claim.only_final_hour : true
                                onToggled: patch("character_claim", "only_final_hour", checked)
                            }
                        }

                        PanelCard {
                            title: "Instant triggers"
                            titleSize: 12
                            Layout.fillWidth: true

                            Label {
                                Layout.fillWidth: true
                                text: "Leave blank to keep off. Any trigger causes an instant claim mid-batch."
                                color: Theme.fgMuted
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: 12
                                rowSpacing: 8

                                Label { text: "Instant claim min kakera"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 180 }
                                ThemedTextField {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 32
                                    placeholderText: "off (leave blank)"
                                    text: getField("character_claim", "min_kakera")
                                    onEditingFinished: patch("character_claim", "min_kakera", parseIntOrNull(text))
                                }

                                Label {
                                    text: "Instant claim at claim rank ≤"
                                    color: Theme.fgSecondary
                                    font.pixelSize: 11
                                    Layout.preferredWidth: 180
                                    wrapMode: Text.WordWrap
                                }
                                ThemedTextField {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 32
                                    placeholderText: "e.g. 200 = ranks 1–200"
                                    text: getField("character_claim", "max_claim_rank")
                                    onEditingFinished: patch("character_claim", "max_claim_rank", parseIntOrNull(text))
                                }
                            }
                        }
                    }
                }

                // ---- Reactions ----
                ScrollablePage {
                    id: reactionsPage

                    GridLayout {
                        Layout.fillWidth: true
                        columns: reactionsPage.contentWidth >= 900 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12

                        RuleBlockCard {
                            Layout.fillWidth: true
                            title: "Kakera reaction"
                            subtitle: (rules.kakera_reaction && rules.kakera_reaction.enabled)
                                ? "Click kakera buttons on rolls that pass these filters."
                                : "Kakera buttons will not be clicked."
                            enabled_: rules.kakera_reaction ? rules.kakera_reaction.enabled : false
                            onEnabledToggled: function(value) { patch("kakera_reaction", "enabled", value) }

                            ColorChipPicker {
                                Layout.fillWidth: true
                                title: "Kakera colors (none = any)"
                                options: kakeraOptions
                                selected: rules.kakera_reaction ? (rules.kakera_reaction.types_allowed || []) : []
                                onSelectionChanged: function(ids) {
                                    patch("kakera_reaction", "types_allowed", ids)
                                }
                            }

                            ThemedCheckBox {
                                Layout.fillWidth: true
                                text: "Use $dk when reaction power runs out"
                                checked: rules.kakera_reaction ? !!rules.kakera_reaction.auto_use_dk : false
                                onToggled: patch("kakera_reaction", "auto_use_dk", checked)
                            }

                            ThemedCheckBox {
                                Layout.fillWidth: true
                                text: "Require chaos key"
                                checked: rules.kakera_reaction ? !!rules.kakera_reaction.require_chaos_key : false
                                onToggled: patch("kakera_reaction", "require_chaos_key", checked)
                            }

                            ColorChipPicker {
                                Layout.fillWidth: true
                                visible: rules.kakera_reaction && !!rules.kakera_reaction.require_chaos_key
                                title: "Ignore chaos key requirement for"
                                options: kakeraOptions
                                selected: rules.kakera_reaction
                                    ? (rules.kakera_reaction.require_chaos_key_bypass_types || ["kakeraP"])
                                    : ["kakeraP"]
                                onSelectionChanged: function(ids) {
                                    patch("kakera_reaction", "require_chaos_key_bypass_types", ids)
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
                                    checked: presetsRoot.showAdvancedKakera
                                    onToggled: presetsRoot.showAdvancedKakera = checked
                                }
                            }

                            KakeraAdvancedPanel {
                                Layout.fillWidth: true
                                visible: presetsRoot.showAdvancedKakera
                                rules: presetsRoot.rules
                                kakeraOptions: presetsRoot.kakeraOptions
                                onPatch: function(block, key, value) {
                                    presetsRoot.patch(block, key, value)
                                }
                                onPatchLowPower: function(key, value) {
                                    presetsRoot.patchLowPower(key, value)
                                }
                                onSetLowPowerEnabled: function(on) {
                                    presetsRoot.setLowPowerEnabled(on)
                                }
                            }
                        }

                        RuleBlockCard {
                            Layout.fillWidth: true
                            title: "Sphere reaction"
                            subtitle: (rules.sphere_reaction && rules.sphere_reaction.enabled)
                                ? "Click sphere buttons matching the filter."
                                : "Sphere buttons will not be clicked."
                            enabled_: rules.sphere_reaction ? rules.sphere_reaction.enabled : false
                            onEnabledToggled: function(value) { patch("sphere_reaction", "enabled", value) }

                            ColorChipPicker {
                                Layout.fillWidth: true
                                title: "Sphere colors (none = any)"
                                options: sphereOptions
                                selected: rules.sphere_reaction ? (rules.sphere_reaction.types_allowed || []) : []
                                onSelectionChanged: function(ids) {
                                    patch("sphere_reaction", "types_allowed", ids)
                                }
                            }
                        }
                    }
                }

                // ---- $us ----
                ScrollablePage {
                    UsRollPanel {
                        Layout.fillWidth: true
                        rules: presetsRoot.rules
                        kakeraOptions: presetsRoot.kakeraOptions
                        onPatch: function(block, key, value) {
                            presetsRoot.patch(block, key, value)
                        }
                        onPatchUsMode: function(key, value) {
                            presetsRoot.patch("us_mode", key, value)
                        }
                    }
                }

                // ---- Expert ----
                ScrollablePage {
                    PanelCard {
                        title: "Claim timing"
                        titleSize: 13
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: "How long the macro waits for a claim button to appear before giving up."
                            color: Theme.fgMuted
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }

                        GridLayout {
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 8
                            Layout.fillWidth: true

                            Label { text: "Claim button timeout (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 200; wrapMode: Text.WordWrap }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                text: getField("expert", "claim_expire_sec") || "45"
                                onEditingFinished: patch("expert", "claim_expire_sec", parseInt(text) || 45)
                            }
                        }
                    }

                    PanelCard {
                        title: "$us timing"
                        titleSize: 13
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: "Fine-tune how long the macro waits for Mudae during $us commands. Defaults are safe for most servers."
                            color: Theme.fgMuted
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }

                        GridLayout {
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 8
                            Layout.fillWidth: true

                            Label { text: "Pause after reading $us stack (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 200; wrapMode: Text.WordWrap }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                text: getField("expert", "us_read_before_add_delay_sec") || "2"
                                onEditingFinished: patch("expert", "us_read_before_add_delay_sec", parseFloatOrDefault(text, 2))
                            }

                            Label { text: "Wait after sending $us N (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 200; wrapMode: Text.WordWrap }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                text: getField("expert", "us_add_delay_sec") || "5"
                                onEditingFinished: patch("expert", "us_add_delay_sec", parseFloatOrDefault(text, 5))
                            }

                            Label { text: "Retry delay after roll timeout (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 200; wrapMode: Text.WordWrap }
                            ThemedTextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                text: getField("expert", "us_roll_timeout_retry_sec") || "5"
                                onEditingFinished: patch("expert", "us_roll_timeout_retry_sec", parseFloatOrDefault(text, 5))
                            }
                        }
                    }
                }
            }
        }
    }
    }

    PresetWizard {
        id: wizardLoader
        anchors.fill: parent
        presetId: editingPresetId
        kakeraOptions: presetsRoot.kakeraOptions
        sphereOptions: presetsRoot.sphereOptions
        onFinished: presetsRoot.reload()
    }

    Component.onCompleted: reload()
}
