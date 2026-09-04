import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Advisor › Wishlist — an app-side list the macro claims from, separate from
    Mudae's own `$wish`.

    A hit is treated exactly like a wish ping: the roll loop stops and claims
    immediately, spending `$rt` if the slot is on cooldown (`macro/wishlist.py`
    → `macro/roll_interrupts.py`). Two lists, because Mudae gives a roll two
    names worth matching — the character and the series it comes from.

    The **Global** toggle decides what the macro matches against: one list
    everywhere, or a separate list per (account, server). Both are kept, so
    flipping back does not lose the other side.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""

    property var wishlistData: ({ characters: [], series: [], global: true, scoped_ready: true })

    readonly property bool isGlobal: !!wishlistData.global
    readonly property bool scopedReady: !!wishlistData.scoped_ready

    function refresh() {
        try {
            wishlistData = JSON.parse(App.wishlistFor(root.accountId, root.channelProfileId))
        } catch (e) {
            wishlistData = ({ characters: [], series: [], global: true, scoped_ready: true })
        }
    }

    onAccountIdChanged: refresh()
    onChannelProfileIdChanged: refresh()
    Component.onCompleted: refresh()

    Connections {
        target: App
        function onWishlistChanged() { root.refresh() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        PanelCard {
            Layout.fillWidth: true
            title: "How a match is claimed"
            titleSize: Theme.sizeMedium

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "An unclaimed roll whose character or series is on a list below "
                          + "is claimed immediately — the same instant-claim path as a Mudae "
                          + "wish ping, spending $rt when the claim slot is on cooldown and "
                          + "Auto-use $rt is on in the preset. Names match exactly, ignoring "
                          + "case; \"Mari\" does not match \"Marin\"."
                    color: Theme.dim
                    font.pixelSize: Theme.sizeSmall
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: "Global"
                        color: Theme.fgPrimary
                        font.pixelSize: Theme.sizeSmall
                        font.weight: Font.DemiBold
                    }

                    ThemedSwitch {
                        checked: root.isGlobal
                        onToggled: App.setWishlistGlobal(checked)
                    }

                    Label {
                        Layout.fillWidth: true
                        text: root.isGlobal
                            ? "One list, used on every account and server."
                            : "A separate list per account and server — this page edits the pair picked above."
                        color: Theme.mute
                        font.pixelSize: Theme.sizeSmall
                        elide: Text.ElideRight
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap

            WishlistSection {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 420
                Layout.minimumWidth: 260

                title: "Wishes"
                subtitle: "Character names, as Mudae writes them on the roll."
                placeholder: "Rem$Alice$Audrey  ·  or  Rem, Alice"
                names: root.wishlistData.characters || []
                enabled: root.scopedReady
                onAddRequested: (text) => App.addWishlistCharacters(
                    text, root.accountId, root.channelProfileId)
                onRemoveRequested: (name) => App.removeWishlistCharacter(
                    name, root.accountId, root.channelProfileId)
            }

            WishlistSection {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 420
                Layout.minimumWidth: 260

                title: "Series wishes"
                subtitle: "Any character rolled from one of these claims, whatever their name."
                placeholder: "Re:Zero$Overlord  ·  or  Re:Zero, Overlord"
                names: root.wishlistData.series || []
                enabled: root.scopedReady
                onAddRequested: (text) => App.addWishlistSeries(
                    text, root.accountId, root.channelProfileId)
                onRemoveRequested: (name) => App.removeWishlistSeries(
                    name, root.accountId, root.channelProfileId)
            }
        }
    }
}
