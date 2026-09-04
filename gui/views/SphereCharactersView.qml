import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Spheres › Characters — which characters carry which ouroperk.

    Captured from Mudae's own `$wl` listing (`macro/wishlist_capture.py`),
    which is the only place the roster appears: `$shop` reports a perk's
    *level*, never how many characters are assigned to it, and that count is
    what turns OP1 and OP9 from a level into a rate.

    The sphere cost of each roster is **derived** from the published ladder
    rather than read back, and shown against Mudae's own figure — they agree on
    every real row so far, and a disagreement is worth seeing rather than
    hiding, since it would mean the ladder moved or the row was misread.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""

    property var listing: ({ entries: [], captured: false, fetching: false })

    readonly property bool captured: !!listing.captured
    readonly property bool fetching: !!listing.fetching
    readonly property bool scopedReady: !!listing.scoped_ready

    function refresh() {
        try {
            listing = JSON.parse(
                App.mudaeWishlistFor(root.accountId, root.channelProfileId))
        } catch (e) {
            listing = ({ entries: [], captured: false, fetching: false })
        }
    }

    onAccountIdChanged: refresh()
    onChannelProfileIdChanged: refresh()
    Component.onCompleted: refresh()

    Connections {
        target: App
        function onMudaeWishlistChanged() { root.refresh() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.fillWidth: true
            title: "Ouroperk roster"
            titleSize: Theme.sizeMedium

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        Layout.fillWidth: true
                        text: root.captured
                            ? "Captured from $wl — every character on the wishlist, the "
                              + "spheres invested in it, and which ouroperks it carries."
                            : root.scopedReady
                            ? "Nothing captured for this account on this server yet. $shop "
                              + "reports each perk's level, never how many characters carry "
                              + "it — that roster is what turns OP1 and OP9 into a rate."
                            : "Pick an account and a server above — a capture belongs to one "
                              + "pair."
                        color: Theme.dim
                        font.pixelSize: Theme.sizeSmall
                        wrapMode: Text.WordWrap
                    }

                    ActionButton {
                        text: root.fetching ? "Fetching…" : "Fetch $wl"
                        buttonHeight: 32
                        Layout.preferredWidth: 116
                        enabled: !root.fetching
                        loading: root.fetching
                        fillColor: Theme.accentPrimary
                        textColor: Theme.bgDark
                        labelWeight: Font.DemiBold
                        onClicked: App.fetchMudaeWishlist()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: root.captured
                    spacing: 8

                    StatusChip {
                        label: "Wishes"
                        value: (root.listing.wl_used === null ? "—" : root.listing.wl_used)
                               + " / " + (root.listing.wl_max === null ? "—" : root.listing.wl_max)
                    }
                    StatusChip {
                        label: "Starwishes"
                        value: (root.listing.sw_used === null ? "—" : root.listing.sw_used)
                               + " / " + (root.listing.sw_max === null ? "—" : root.listing.sw_max)
                    }
                    StatusChip {
                        label: "Invested"
                        value: (root.listing.total_spheres || 0).toLocaleString(
                            Qt.locale(), "f", 0) + " sp"
                    }
                    StatusChip {
                        label: "Via"
                        value: root.listing.route === "dm" ? "DM" : "pages"
                    }
                    StatusChip {
                        label: "Complete"
                        value: root.listing.complete ? "yes" : "partial"
                        tone: root.listing.complete ? "active" : "warn"
                    }

                    Item { Layout.fillWidth: true }
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.captured && !root.listing.complete
                    text: "Some rows did not arrive, so counts here are a floor, not a total. "
                          + "Fetching again is safe — a partial capture replaces cleanly."
                    color: Theme.warn
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    visible: !root.captured
                    text: root.listing.allow_dms
                        ? "Mudae will DM the whole list in one go ($wlsz+z!)."
                        : "Mudae direct messages are off, so the macro will page through the "
                          + "channel reply instead ($wlz+z!) — slower, and a slow page can "
                          + "cut a long list short. Settings can change that."
                    color: Theme.mute
                    font.pixelSize: Theme.sizeMicro
                    wrapMode: Text.WordWrap
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.captured
            title: "Characters"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        Layout.preferredWidth: 220
                        text: Theme.sectionLabel("character")
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }
                    Label {
                        Layout.preferredWidth: 90
                        text: Theme.sectionLabel("spheres")
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                        horizontalAlignment: Text.AlignRight
                    }
                    Label {
                        Layout.fillWidth: true
                        text: Theme.sectionLabel("ouroperks")
                        color: Theme.mute
                        font.pixelSize: Theme.sizeMicro
                        font.letterSpacing: Theme.tracking(Theme.sizeMicro)
                    }
                }

                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: root.listing.entries || []
                    clip: true
                    spacing: 2
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: Rectangle {
                        required property var modelData

                        width: ListView.view.width
                        height: 28
                        radius: Theme.radiusXs
                        color: index % 2 === 0 ? "transparent" : Theme.fade(Theme.bgLight, 0.5)

                        required property int index

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 6
                            anchors.rightMargin: 6
                            spacing: 10

                            RowLayout {
                                // Pinned at both ends, not just preferred: a
                                // nested layout hands its implicit width up as
                                // a *minimum*, which beats a preferred width
                                // and would push the column off its header.
                                Layout.preferredWidth: 214
                                Layout.minimumWidth: 214
                                Layout.maximumWidth: 214
                                spacing: 5

                                Image {
                                    visible: modelData.starwish
                                    source: MudaeEmoji.urlFor("starwish")
                                    Layout.preferredWidth: 13
                                    Layout.preferredHeight: 13
                                    sourceSize.width: 13
                                    sourceSize.height: 13
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.name
                                    color: Theme.fgPrimary
                                    font.pixelSize: Theme.sizeSmall
                                    elide: Text.ElideRight
                                }

                                Label {
                                    visible: modelData.sphere_percent !== null
                                    text: "+" + modelData.sphere_percent + "%"
                                    color: Theme.accentSecondary
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.sizeMicro
                                }
                            }

                            Label {
                                Layout.preferredWidth: 90
                                text: (modelData.spheres || 0).toLocaleString(
                                    Qt.locale(), "f", 0)
                                // Mudae's figure and the ladder disagree: worth
                                // seeing, since one of the two is wrong.
                                color: modelData.cost_matches ? Theme.dim : Theme.warn
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.sizeMicro
                                horizontalAlignment: Text.AlignRight
                            }

                            Label {
                                Layout.fillWidth: true
                                text: modelData.upgrades_full
                                    ? "Full — every perk maxed"
                                    : root.perkSummary(modelData.upgrades)
                                color: modelData.upgrades_full ? Theme.good : Theme.dim
                                font.pixelSize: Theme.sizeMicro
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }

        PanelCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.captured
            title: "What this unlocks"
            titleSize: Theme.sizeMedium
            fillContentVertically: true

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                Label {
                    Layout.fillWidth: true
                    text: "With the roster captured, OP1's spawn share becomes priceable and "
                          + "the Upgrades ranking can cover more of the ladder than the one "
                          + "perk it can defend today."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }
            }
        }
    }

    function perkSummary(upgrades) {
        if (!upgrades)
            return "—"
        var keys = Object.keys(upgrades).sort(function (a, b) { return a - b })
        if (keys.length === 0)
            return "—"
        var parts = []
        for (var i = 0; i < keys.length; i++) {
            var count = upgrades[keys[i]]
            parts.push(count > 1 ? ("OP" + keys[i] + " ×" + count) : ("OP" + keys[i]))
        }
        return parts.join("  ")
    }
}
