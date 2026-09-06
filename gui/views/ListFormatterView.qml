import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Advisor › Formatter — the list formatter, moved from the Utilities page when
    that page was absorbed into this hub. `mudae/list_formatter.py` is behind it.

    It takes two shapes of input: a Mudae listing, whose ranks and series get
    stripped, and a plain list of names, which is taken as written. The copy says
    both, because the page used to promise only the first and silently returned
    nothing for the second.
*/
Item {
    id: formatterRoot
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
            text: "Paste Mudae list output — wishlists, $top, kakera rankings — or just type names one per line, and get them back joined with $ for commands like $tt."
            color: Theme.fgMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(420, formatterRoot.height - 80)
            title: "List formatter"
            titleSize: 14
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                Label {
                    Layout.fillWidth: true
                    text: "Paste Mudae list output (wishlists, $top, kakera rankings) and the ranks, series and stats are stripped off. A plain list of names — one per line, or separated by $ or commas — is taken as-is, which is what you want when you are building a list rather than pasting one back. Either way the names come out joined with $ for commands like $tt."
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
                        onClicked: formatterRoot.refreshListOutput()
                    }

                    ThemedButton {
                        text: "Clear"
                        onClicked: {
                            inputArea.text = ""
                            outputArea.text = ""
                            listFormatterResult = { names: [], count: 0, formatted: "" }
                            statusLabel.text = "Paste a list above, then Format."
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
                            : "Paste a list above, then Format."
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

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                            TextArea {
                                id: inputArea
                                width: parent.width
                                wrapMode: TextArea.Wrap
                                placeholderText: "#1 - Hatsune Miku 💞 - VOCALOID\n#2 - Zero Two 💞 - …\n\n…or just:\nHatsune Miku\nZero Two"
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
                                        statusLabel.text = "Paste a list above, then Format."
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

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

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
