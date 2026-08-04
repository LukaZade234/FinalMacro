import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

Item {
    id: utilitiesRoot
    clip: true

    Rectangle {
        anchors.fill: parent
        color: Theme.bgDark
    }

    property var listFormatterResult: ({ names: [], count: 0, formatted: "" })

    function refreshListOutput() {
        try {
            listFormatterResult = JSON.parse(App.parseMudaeCharacterListJson(inputArea.text))
        } catch (e) {
            listFormatterResult = { names: [], count: 0, formatted: "" }
        }
    }

    ScrollablePage {
        anchors.fill: parent

        Label {
            Layout.fillWidth: true
            text: "Helper tools for Mudae workflows."
            color: Theme.fgMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(420, utilitiesRoot.height - 80)
            title: "List formatter"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                Label {
                    Layout.fillWidth: true
                    text: "Paste Mudae list output (wishlists, $top, kakera rankings, etc.). Character names are extracted and joined with $ for commands like $tt or custom searches."
                    color: Theme.fgMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    ThemedButton {
                        text: "Format"
                        accent: true
                        onClicked: utilitiesRoot.refreshListOutput()
                    }

                    ThemedButton {
                        text: "Clear"
                        onClicked: {
                            inputArea.text = ""
                            outputArea.text = ""
                            listFormatterResult = { names: [], count: 0, formatted: "" }
                            statusLabel.text = "Paste a Mudae list above, then Format."
                        }
                    }

                    ThemedButton {
                        text: "Copy output"
                        enabled: outputArea.text.length > 0
                        onClicked: App.copyToClipboard(outputArea.text)
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        id: statusLabel
                        text: listFormatterResult.count > 0
                            ? (listFormatterResult.count + " name" + (listFormatterResult.count === 1 ? "" : "s"))
                            : "Paste a Mudae list above, then Format."
                        color: listFormatterResult.count > 0 ? Theme.success : Theme.fgMuted
                        font.pixelSize: 11
                    }
                }

                SplitView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 280
                    orientation: Qt.Horizontal

                    handle: Rectangle {
                        implicitWidth: 6
                        color: SplitHandle.pressed ? Theme.bgHover
                             : SplitHandle.hovered ? Theme.bgLight
                             : "transparent"
                    }

                    PanelCard {
                        SplitView.preferredWidth: Math.floor(SplitView.view.width * 0.5)
                        SplitView.minimumWidth: 160
                        SplitView.fillHeight: true
                        title: "Input"
                        titleSize: 12
                        fillContentVertically: true

                        ThemedScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            TextArea {
                                id: inputArea
                                width: parent.width
                                wrapMode: TextArea.Wrap
                                placeholderText: "#1 - Hatsune Miku 💞 - VOCALOID\n#2 - Zero Two 💞 - …"
                                font.family: "Consolas, monospace"
                                font.pixelSize: 11
                                color: Theme.fgSecondary
                                selectByMouse: true
                                background: Rectangle {
                                    radius: 6
                                    color: Theme.inputBg
                                    border.color: inputArea.activeFocus ? Theme.accentPrimary : Theme.border
                                    border.width: 1
                                }
                                onTextChanged: {
                                    if (text.trim().length === 0)
                                        statusLabel.text = "Paste a Mudae list above, then Format."
                                }
                            }
                        }
                    }

                    PanelCard {
                        SplitView.fillWidth: true
                        SplitView.minimumWidth: 160
                        SplitView.fillHeight: true
                        title: "Output ($ separated)"
                        titleSize: 12
                        fillContentVertically: true

                        ThemedScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            TextArea {
                                id: outputArea
                                width: parent.width
                                readOnly: true
                                wrapMode: TextArea.Wrap
                                font.family: "Consolas, monospace"
                                font.pixelSize: 11
                                color: Theme.fgPrimary
                                selectByMouse: true
                                text: listFormatterResult.formatted || ""
                                background: Rectangle {
                                    radius: 6
                                    color: Theme.inputBg
                                    border.color: Theme.border
                                    border.width: 1
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
