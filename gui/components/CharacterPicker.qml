import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0

/*
    Pick one wishlist character, by typing.

    A wishlist runs to a couple of hundred names, which is well past what a
    plain dropdown can be scrolled through usefully — so this filters as you
    type and shows each candidate's own numbers beside its name. Those numbers
    are the reason you are choosing at all: a starwish, a perk-1 neighbour bonus
    and a perk-4 level are exactly what move a character's own `$bw` optimum
    away from the wishlist's, so picking blind from a list of names hides the
    thing being picked on.

    Selection is committed only on click or Enter. Typing filters and previews;
    leaving the field without committing restores the current selection, so a
    half-typed name never silently changes the page underneath.
*/
Item {
    id: root

    // Rows straight off the `$wl` capture: name, starwish, sphere_percent
    // (the perk-1 bonus), upgrades, spheres.
    property var entries: []
    property string selectedName: ""
    property string placeholder: "Whole wishlist"

    signal picked(string name)

    implicitHeight: 32

    // What has actually been typed as a search, held explicitly rather than
    // inferred from the field's focus: focus moves to the popup's scrollbar on
    // a drag, and a filter that resets itself mid-scroll is worse than none.
    property string searchText: ""

    readonly property var filtered: {
        var needle = searchText.trim().toLowerCase()
        var rows = entries || []
        var out = []
        for (var i = 0; i < rows.length; i++) {
            var name = String(rows[i].name || "")
            if (needle === "" || name.toLowerCase().indexOf(needle) >= 0)
                out.push(rows[i])
        }
        return out
    }

    function perk(row, number) {
        if (row.upgrades_full)
            return number <= 5 ? 6 : 1
        var ups = row.upgrades || {}
        return Number(ups[String(number)] || 0)
    }

    // The badges that explain why one character differs from another.
    function badgeText(row) {
        var bits = []
        var p1 = Number(row.sphere_percent || 0)
        if (p1 > 0)
            bits.push("perk 1 +" + p1 + "%")
        var p4 = perk(row, 4)
        if (p4 > 0)
            bits.push("perk 4 lv" + p4)
        if (row.upgrades_full)
            bits.push("full")
        return bits.join(" · ")
    }

    function commit(name) {
        root.selectedName = name
        root.searchText = ""
        field.text = name
        popup.close()
        field.focus = false
        root.picked(name)
    }

    // Abandon a half-typed search without changing the selection.
    function revert() {
        root.searchText = ""
        field.text = root.selectedName
        popup.close()
    }

    function open() {
        if (!popup.opened) {
            list.currentIndex = 0
            popup.open()
        }
    }

    ThemedTextField {
        id: field
        anchors.fill: parent
        text: root.selectedName
        placeholderText: root.placeholder
        selectByMouse: true
        font.pixelSize: 12
        leftPadding: 10
        rightPadding: clearButton.visible ? 46 : 26

        onActiveFocusChanged: {
            if (activeFocus) {
                selectAll()
                root.searchText = ""
                root.open()
            } else if (!popup.activeFocus) {
                // Never leave a half-typed name standing in for a selection.
                root.revert()
            }
        }

        onTextEdited: {
            root.searchText = text
            list.currentIndex = 0
            root.open()
        }

        Keys.onDownPressed: {
            root.open()
            list.currentIndex = Math.min(list.currentIndex + 1, list.count - 1)
        }
        Keys.onUpPressed: list.currentIndex = Math.max(list.currentIndex - 1, 0)
        Keys.onEscapePressed: {
            root.revert()
            focus = false
        }
        Keys.onReturnPressed: {
            if (list.currentIndex >= 0 && list.currentIndex < root.filtered.length)
                root.commit(root.filtered[list.currentIndex].name)
            else if (root.filtered.length === 1)
                root.commit(root.filtered[0].name)
            else if (text.trim() === "")
                root.commit("")
        }
        Keys.onTabPressed: function (event) {
            if (list.currentIndex >= 0 && list.currentIndex < root.filtered.length)
                root.commit(root.filtered[list.currentIndex].name)
            event.accepted = false
        }
    }

    // Clears back to the whole wishlist without hunting for an entry to pick.
    Label {
        id: clearButton
        anchors.right: chevron.left
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        visible: root.selectedName !== ""
        text: "✕"
        color: clearArea.containsMouse ? Theme.fg : Theme.mute
        font.pixelSize: Theme.sizeSmall

        MouseArea {
            id: clearArea
            anchors.fill: parent
            anchors.margins: -6
            hoverEnabled: true
            onClicked: root.commit("")
        }
    }

    Label {
        id: chevron
        anchors.right: parent.right
        anchors.rightMargin: 9
        anchors.verticalCenter: parent.verticalCenter
        text: "▾"
        color: Theme.mute
        font.pixelSize: Theme.sizeSmall

        MouseArea {
            anchors.fill: parent
            anchors.margins: -6
            onClicked: {
                if (popup.opened) {
                    popup.close()
                } else {
                    field.forceActiveFocus()
                    root.open()
                }
            }
        }
    }

    Popup {
        id: popup
        y: root.height + 4
        width: root.width
        // Tall enough to scan, short enough to leave the page visible behind
        // it, and never so short that the "no match" line has nowhere to sit.
        height: Math.max(Math.min(list.count * 40 + 10, 260), 44)
        padding: 5
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        background: Rectangle {
            color: Theme.raised
            border.color: Theme.border
            border.width: 1
            radius: Theme.radiusSm
        }

        ListView {
            id: list
            anchors.fill: parent
            clip: true
            model: root.filtered
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            highlightMoveDuration: 0
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            // Keyboard walking has to bring the row into view, or "scrolling
            // through them" shows the wrong thing.
            onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(
                currentIndex, ListView.Contain)

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: list.width
                height: 40
                radius: Theme.radiusXs
                color: index === list.currentIndex
                       ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18)
                       : (hover.containsMouse
                          ? Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.06)
                          : "transparent")

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: list.currentIndex = index
                    onClicked: root.commit(modelData.name)
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    anchors.topMargin: 4
                    anchors.bottomMargin: 4
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 5

                        // Mudae's own starwish mark rather than a ★ glyph, so a
                        // row here looks like the `$wl` line it came from.
                        Image {
                            visible: !!modelData.starwish
                            source: MudaeEmoji.urlFor("starwish")
                            sourceSize.width: 13
                            sourceSize.height: 13
                            Layout.preferredWidth: 13
                            Layout.preferredHeight: 13
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            mipmap: true
                        }

                        Label {
                            Layout.fillWidth: true
                            text: modelData.name
                            color: Theme.fg
                            font.pixelSize: Theme.sizeSmall
                            elide: Text.ElideRight
                        }

                        Label {
                            text: Number(modelData.spheres || 0).toLocaleString(
                                      Qt.locale(), "f", 0) + " sp"
                            color: Theme.mute
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.sizeMicro
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        text: root.badgeText(modelData) || "no upgrades"
                        color: Theme.dim
                        font.pixelSize: Theme.sizeMicro
                        elide: Text.ElideRight
                    }
                }
            }
        }

        // Sibling of the list, not a child: an extra item declared inside a
        // ListView lands in its content and scrolls away with the rows.
        Label {
            anchors.centerIn: parent
            visible: list.count === 0
            text: (root.entries || []).length === 0
                  ? "No $wl capture yet" : "No character matches"
            color: Theme.mute
            font.pixelSize: Theme.sizeSmall
        }
    }
}
