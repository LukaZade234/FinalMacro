import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

Item {
    id: panel
    property string channelProfileId: ""
    property var displayData: ({ sections: [], field_count: 0 })

    function refresh() {
        if (!channelProfileId) {
            displayData = { sections: [], field_count: 0 }
            return
        }
        try {
            displayData = JSON.parse(App.formatChannelSettingsDisplayJson(channelProfileId))
        } catch (e) {
            displayData = { sections: [], field_count: 0 }
        }
    }

    Connections {
        target: App
        function onServersChanged() { panel.refresh() }
    }

    onChannelProfileIdChanged: refresh()
    Component.onCompleted: refresh()

    ScrollView {
        id: displayScroll
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: displayScroll.availableWidth
            spacing: 10

            Label {
                visible: !channelProfileId
                Layout.fillWidth: true
                text: "Select a channel to view parsed $settings."
                color: Theme.fgMuted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            Label {
                visible: channelProfileId && displayData.field_count === 0
                Layout.fillWidth: true
                text: "No $settings yet — set this channel on Run, connect, then Fetch $settings."
                color: Theme.fgMuted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: displayData.sections || []
                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Label {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        text: modelData.title
                        color: Theme.accentPrimary
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }

                    Repeater {
                        model: modelData.rows || []
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            Layout.preferredHeight: 30

                            Rectangle {
                                Layout.preferredWidth: 4
                                Layout.preferredHeight: 14
                                Layout.alignment: Qt.AlignVCenter
                                radius: 2
                                color: modelData.has_value ? Theme.success : Theme.fgMuted
                                opacity: modelData.has_value ? 0.85 : 0.35
                            }

                            Label {
                                Layout.preferredWidth: 118
                                Layout.maximumWidth: 140
                                Layout.alignment: Qt.AlignVCenter
                                text: modelData.label || modelData.field || ""
                                color: Theme.fgSecondary
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }

                            MudaeCommandChip {
                                Layout.alignment: Qt.AlignVCenter
                                visible: (modelData.command || "").length > 0
                                command: modelData.command
                            }

                            Item { Layout.fillWidth: true; Layout.minimumWidth: 4 }

                            Label {
                                Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                                text: modelData.display || "—"
                                color: modelData.has_value ? Theme.fgPrimary : Theme.fgMuted
                                font.pixelSize: 11
                                font.weight: Font.Medium
                                horizontalAlignment: Text.AlignRight
                                elide: Text.ElideLeft
                                Layout.maximumWidth: Math.max(120, displayScroll.availableWidth * 0.35)
                            }
                        }
                    }
                }
            }
        }
    }
}
