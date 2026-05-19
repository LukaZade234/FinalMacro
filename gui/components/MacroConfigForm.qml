import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

GridLayout {
    id: form
    columns: 4
    columnSpacing: 12
    rowSpacing: 10
    Layout.fillWidth: true

    property bool _ready: false
    property string presetId: ""

    function fieldValue(key) {
        if (presetId)
            return App.presetConfigField(presetId, key)
        return App.macroConfigField(key)
    }

    function setField(key, value) {
        if (presetId)
            App.setPresetConfigField(presetId, key, value)
        else
            App.setMacroConfigField(key, value)
    }

    Label { text: "Prefix"; color: Theme.fgSecondary; font.pixelSize: 11 }
    TextField {
        id: prefixField
        text: form.fieldValue("prefix")
        color: Theme.fgPrimary
        Layout.columnSpan: 1
        Layout.fillWidth: true
        maximumLength: 4
        background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
        onEditingFinished: form.setField("prefix", text)
    }
    Label { text: "Roll cmd"; color: Theme.fgSecondary; font.pixelSize: 11 }
    TextField {
        id: rollCmdField
        text: form.fieldValue("roll_command")
        color: Theme.fgPrimary
        Layout.fillWidth: true
        background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
        onEditingFinished: form.setField("roll_command", text)
    }

    Label { text: "Delay (s)"; color: Theme.fgSecondary; font.pixelSize: 11 }
    TextField {
        id: delayField
        text: form.fieldValue("roll_delay_sec")
        color: Theme.fgPrimary
        Layout.fillWidth: true
        background: Rectangle { radius: 6; color: Theme.inputBg; border.color: Theme.border }
        onEditingFinished: form.setField("roll_delay_sec", text)
    }
    Label { text: "On N left, roll N more"; color: Theme.fgSecondary; font.pixelSize: 11 }
    SpinBox {
        id: stopSpin
        from: 0
        to: 20
        value: parseInt(form.fieldValue("rolls_left_stop")) || 2
        editable: true
        Layout.fillWidth: true
        onValueModified: if (form._ready) form.setField("rolls_left_stop", value.toString())
    }

    CheckBox {
        id: wishClaimBox
        text: "Claim wish when you are pinged"
        checked: form.fieldValue("auto_claim_wish") === "true"
        Layout.columnSpan: 4
        contentItem: Text {
            text: parent.text
            color: Theme.fgPrimary
            font.pixelSize: 12
            leftPadding: parent.indicator.width + parent.spacing
            verticalAlignment: Text.AlignVCenter
        }
        onToggled: if (form._ready) form.setField("auto_claim_wish", checked ? "true" : "false")
    }

    CheckBox {
        id: claimResetBox
        text: "Claim best this batch on final roll hour (≤45s buttons)"
        checked: form.fieldValue("claim_best_at_claim_reset") === "true"
        Layout.columnSpan: 4
        contentItem: Text {
            text: parent.text
            color: Theme.fgPrimary
            font.pixelSize: 12
            leftPadding: parent.indicator.width + parent.spacing
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
        }
        onToggled: if (form._ready) form.setField("claim_best_at_claim_reset", checked ? "true" : "false")
    }

    function reloadFromApp() {
        form._ready = false
        prefixField.text = fieldValue("prefix")
        rollCmdField.text = fieldValue("roll_command")
        delayField.text = fieldValue("roll_delay_sec")
        stopSpin.value = parseInt(fieldValue("rolls_left_stop")) || 2
        wishClaimBox.checked = fieldValue("auto_claim_wish") === "true"
        claimResetBox.checked = fieldValue("claim_best_at_claim_reset") === "true"
        form._ready = true
    }

    Component.onCompleted: {
        reloadFromApp()
        form._ready = true
    }
}
