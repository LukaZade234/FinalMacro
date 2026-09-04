import QtQuick
import QtQuick.Controls
import gui 1.0

/*
    Fetch one Mudae sheet for the scope the bar is pointed at.

    Lives in the scope bar rather than in the page body because that is where
    the pair it acts on is chosen: the button and the account/server pickers
    beside it are one control, and a fetch fired from here always means "for
    *this* pair" — never "for wherever the macro happens to be connected".

    It does not require a connection. The bridge takes the temporary route when
    it has to (`gui/scope_fetch.py`), so the only thing that disables the button
    is the macro being busy with something a sheet is not worth interrupting —
    and it says which, rather than going grey with no explanation.
*/
ThemedButton {
    id: control

    // One of the commands in `gui/scope_fetch.py`'s allowlist.
    property string command: ""
    property string accountId: ""
    property string channelProfileId: ""
    // What the button calls the command; `$wl` is not `$wishlist`.
    property string commandLabel: "$" + command

    // `state` is taken by Item, hence the longer name.
    property var fetchState: ({ command: "", busy: false, blocked_by: "" })

    // Half a scope is not a scope: a sheet fetched without both halves has
    // nowhere honest to be filed.
    readonly property bool scoped: accountId !== "" && channelProfileId !== ""
    readonly property bool running: fetchState.command === command
    readonly property string blockedBy: !scoped
        ? "Pick an account and a server first"
        : String(fetchState.blocked_by || "")

    function refresh() {
        try {
            fetchState = JSON.parse(App.scopeFetchJson)
        } catch (e) {
            fetchState = { command: "", busy: false, blocked_by: "" }
        }
    }

    Connections {
        target: App
        function onScopeFetchChanged() { control.refresh() }
    }

    Component.onCompleted: refresh()

    text: running ? "Fetching…" : ("Fetch " + commandLabel)
    loading: running
    implicitHeight: 26
    enabled: scoped && blockedBy === ""

    hoverEnabled: true
    ToolTip.visible: hovered && blockedBy !== ""
    ToolTip.text: blockedBy
    ToolTip.delay: 300

    onClicked: App.fetchForScope(command, accountId, channelProfileId)
}
