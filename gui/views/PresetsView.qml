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

    // Kakera buttons, listed in value order (cheapest first, chaos last). Purple
    // is shown first since it costs no reaction power. Icons resolve to PNG/WebP
    // assets under gui/assets/kakera/.
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

    // Spheres share the kakera palette minus chaos; icons fall back to color dots
    // since no sphere-specific PNGs are shipped.
    readonly property var sphereOptions: [
        { id: "spP", label: "Purple",  color: "#9d7cd8" },
        { id: "sp",  label: "Blue",    color: "#7aa2f7" },
        { id: "spT", label: "Teal",    color: "#2ac3de" },
        { id: "spG", label: "Green",   color: "#9ece6a" },
        { id: "spY", label: "Yellow",  color: "#e0af68" },
        { id: "spO", label: "Orange",  color: "#ff9e64" },
        { id: "spR", label: "Red",     color: "#f7768e" },
        { id: "spW", label: "Rainbow", color: "#c0caf5" },
        { id: "spL", label: "Light",   color: "#bb9af7" },
        { id: "spD", label: "Dark",    color: "#3b4252" }
    ]

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
            return
        }
        try {
            rules = JSON.parse(App.getPresetRulesJson(editingPresetId)) || {}
        } catch (e) {
            rules = {}
        }
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

    function patchBasic(key, value) {
        if (!_ready || !editingPresetId)
            return
        var patchObj = { basic: {} }
        patchObj.basic[key] = value
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

    function getInt(block, key) {
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

    Connections {
        target: App
        function onConfigChanged() {
            presetsRoot.reload()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 12

        // ----- Left sidebar: preset list -----
        PanelCard {
            Layout.preferredWidth: 200
            Layout.maximumWidth: 240
            Layout.fillHeight: true
            title: "Presets"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    TextField {
                        id: newPresetField
                        Layout.fillWidth: true
                        placeholderText: "Preset name"
                        color: Theme.fgPrimary
                        background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                    }
                    Button {
                        text: "Add"
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
                    delegate: ItemDelegate {
                        width: presetList.width
                        text: presets()[index] ? presets()[index].id : ""
                        highlighted: presetList.currentIndex === index
                        onClicked: presetList.currentIndex = index
                    }
                }

                Button {
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

                Button {
                    Layout.fillWidth: true
                    text: "Remove"
                    enabled: presets().length > 1 && currentPreset() !== null
                    onClicked: {
                        var p = currentPreset()
                        if (!p)
                            return
                        App.removePreset(p.id)
                        reload()
                    }
                }

                Button {
                    Layout.fillWidth: true
                    text: "Use on Run"
                    enabled: editingPresetId.length > 0
                    onClicked: App.setActivePreset(editingPresetId)
                }
            }
        }

        // ----- Right pane: details -----
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

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

                Button {
                    text: "Wizard"
                    enabled: editingPresetId.length > 0
                    onClicked: {
                        wizardLoader.activeStep = 0
                        wizardLoader.open = true
                    }
                }
            }

            ScrollView {
                id: scroller
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.vertical.policy: ScrollBar.AsNeeded
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                contentWidth: availableWidth

                ColumnLayout {
                    width: scroller.availableWidth
                    spacing: 12

                    // -- Basic settings --
                    PanelCard {
                        title: "Basic"
                        titleSize: 13
                        Layout.fillWidth: true

                        GridLayout {
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 8
                            Layout.fillWidth: true

                            Label { text: "Prefix"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                maximumLength: 4
                                color: Theme.fgPrimary
                                background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                                text: (rules.basic && rules.basic.prefix) ? rules.basic.prefix : "$"
                                onEditingFinished: patchBasic("prefix", text)
                            }

                            Label { text: "Roll command"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                color: Theme.fgPrimary
                                background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                                text: (rules.basic && rules.basic.roll_command) ? rules.basic.roll_command : "wa"
                                onEditingFinished: patchBasic("roll_command", text)
                            }

                            Label { text: "Delay between rolls (s)"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                color: Theme.fgPrimary
                                background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                                text: (rules.basic && rules.basic.roll_delay_sec !== undefined) ? rules.basic.roll_delay_sec.toString() : "0.6"
                                onEditingFinished: patchBasic("roll_delay_sec", parseFloat(text) || 0.6)
                            }

                            Label { text: "Stop at N rolls left"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                            SpinBox {
                                from: 0
                                to: 20
                                editable: true
                                Layout.fillWidth: true
                                value: (rules.basic && rules.basic.rolls_left_stop !== undefined) ? rules.basic.rolls_left_stop : 2
                                onValueModified: patchBasic("rolls_left_stop", value)
                            }
                        }
                    }

                    // -- Character claim --
                    RuleBlockCard {
                        id: charCard
                        Layout.fillWidth: true
                        title: "Character claim"
                        subtitle: (rules.character_claim && rules.character_claim.enabled)
                            ? "Claim characters that match these triggers."
                            : "All character claims disabled."
                        enabled_: rules.character_claim ? rules.character_claim.enabled : true
                        onEnabledToggled: function(value) { patch("character_claim", "enabled", value) }

                        CheckBox {
                            Layout.fillWidth: true
                            text: "Claim immediately when a wish pings you"
                            checked: rules.character_claim ? rules.character_claim.claim_on_wish_ping : true
                            contentItem: Text {
                                text: parent.text; color: Theme.fgPrimary; font.pixelSize: 12
                                leftPadding: parent.indicator.width + parent.spacing
                                verticalAlignment: Text.AlignVCenter; wrapMode: Text.WordWrap
                            }
                            onToggled: patch("character_claim", "claim_on_wish_ping", checked)
                        }

                        CheckBox {
                            Layout.fillWidth: true
                            text: "Only claim during the final roll hour"
                            checked: rules.character_claim ? rules.character_claim.only_final_hour : true
                            contentItem: Text {
                                text: parent.text; color: Theme.fgPrimary; font.pixelSize: 12
                                leftPadding: parent.indicator.width + parent.spacing
                                verticalAlignment: Text.AlignVCenter; wrapMode: Text.WordWrap
                            }
                            onToggled: patch("character_claim", "only_final_hour", checked)
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 8

                            Label { text: "Instant claim min kakera"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 180 }
                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                placeholderText: "off (leave blank)"
                                color: Theme.fgPrimary
                                background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                                text: getInt("character_claim", "min_kakera")
                                onEditingFinished: patch("character_claim", "min_kakera", parseIntOrNull(text))
                            }

                            Label {
                                text: "Instant claim at claim rank ≤"
                                color: Theme.fgSecondary
                                font.pixelSize: 11
                                Layout.preferredWidth: 180
                                wrapMode: Text.WordWrap
                            }
                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                placeholderText: "e.g. 200 = ranks 1–200"
                                color: Theme.fgPrimary
                                background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                                text: getInt("character_claim", "max_claim_rank")
                                onEditingFinished: patch("character_claim", "max_claim_rank", parseIntOrNull(text))
                            }
                        }
                    }

                    // -- Kakera reaction --
                    RuleBlockCard {
                        id: kakCard
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

                        Flow {
                            Layout.fillWidth: true
                            spacing: 12

                            CheckBox {
                                text: "Require chaos key"
                                checked: rules.kakera_reaction ? !!rules.kakera_reaction.require_chaos_key : false
                                contentItem: Text { text: parent.text; color: Theme.fgPrimary; font.pixelSize: 12; leftPadding: parent.indicator.width + parent.spacing; verticalAlignment: Text.AlignVCenter }
                                onToggled: patch("kakera_reaction", "require_chaos_key", checked)
                            }
                            CheckBox {
                                text: "Require perk 8 character"
                                checked: rules.kakera_reaction ? !!rules.kakera_reaction.require_perk_8 : false
                                contentItem: Text { text: parent.text; color: Theme.fgPrimary; font.pixelSize: 12; leftPadding: parent.indicator.width + parent.spacing; verticalAlignment: Text.AlignVCenter }
                                onToggled: patch("kakera_reaction", "require_perk_8", checked)
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 8

                            Label { text: "Min spheres on roll"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 180 }
                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                placeholderText: "off"
                                color: Theme.fgPrimary
                                background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
                                text: getInt("kakera_reaction", "min_spheres")
                                onEditingFinished: patch("kakera_reaction", "min_spheres", parseIntOrNull(text))
                            }

                            Label { text: "Daily click budget"; color: Theme.fgSecondary; font.pixelSize: 11; Layout.preferredWidth: 180 }
                            SpinBox {
                                from: 0
                                to: 500
                                editable: true
                                Layout.fillWidth: true
                                value: rules.kakera_reaction ? (rules.kakera_reaction.daily_click_budget || 40) : 40
                                onValueModified: patch("kakera_reaction", "daily_click_budget", value)
                            }
                        }

                        CheckBox {
                            Layout.fillWidth: true
                            text: "Perk-8 priority: skip non-perk-8 once the daily budget is hit"
                            checked: rules.kakera_reaction ? !!rules.kakera_reaction.perk_8_budget_mode : false
                            contentItem: Text {
                                text: parent.text; color: Theme.fgPrimary; font.pixelSize: 12
                                leftPadding: parent.indicator.width + parent.spacing
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.WordWrap
                            }
                            onToggled: patch("kakera_reaction", "perk_8_budget_mode", checked)
                        }

                        // Low-power sub-card
                        Rectangle {
                            Layout.fillWidth: true
                            radius: 8
                            color: Theme.bgDark
                            border.color: Theme.border
                            implicitHeight: lpLayout.implicitHeight + 16

                            ColumnLayout {
                                id: lpLayout
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 8
                                spacing: 6

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        text: "Low-power override"
                                        color: Theme.fgPrimary
                                        font.pixelSize: 12
                                        Layout.fillWidth: true
                                    }
                                    Switch {
                                        checked: rules.kakera_reaction && rules.kakera_reaction.low_power !== null && rules.kakera_reaction.low_power !== undefined
                                        onToggled: setLowPowerEnabled(checked)
                                    }
                                }
                                Label {
                                    visible: rules.kakera_reaction && rules.kakera_reaction.low_power
                                    text: "When power drops below the threshold, only these colors are clicked."
                                    color: Theme.fgMuted
                                    font.pixelSize: 10
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                RowLayout {
                                    visible: rules.kakera_reaction && rules.kakera_reaction.low_power
                                    Layout.fillWidth: true
                                    Label { text: "Below power %"; color: Theme.fgSecondary; font.pixelSize: 11 }
                                    SpinBox {
                                        from: 0
                                        to: 100
                                        editable: true
                                        value: (rules.kakera_reaction && rules.kakera_reaction.low_power) ? (rules.kakera_reaction.low_power.below_percent || 30) : 30
                                        onValueModified: patchLowPower("below_percent", value)
                                    }
                                    Item { Layout.fillWidth: true }
                                }
                                ColorChipPicker {
                                    Layout.fillWidth: true
                                    visible: rules.kakera_reaction && rules.kakera_reaction.low_power
                                    title: "Allowed colors when low power"
                                    options: kakeraOptions
                                    selected: (rules.kakera_reaction && rules.kakera_reaction.low_power)
                                        ? (rules.kakera_reaction.low_power.types_allowed || [])
                                        : []
                                    onSelectionChanged: function(ids) {
                                        patchLowPower("types_allowed", ids)
                                    }
                                }
                            }
                        }
                    }

                    // -- Sphere reaction --
                    RuleBlockCard {
                        id: sphCard
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
        }
    }

    // Wizard overlay
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
