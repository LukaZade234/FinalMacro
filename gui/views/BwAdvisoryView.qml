import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import gui 1.0
import "../components"

/*
    Advisor › $bw — the rolls-versus-wishes trade.

    Deliberately blank: the previous draft was cleared so this page can be
    designed from scratch. It keeps its scope properties because `AdvisorView`
    binds them, so whatever is built here already knows which account on which
    server it is advising.
*/
Item {
    id: root
    clip: true

    property string channelProfileId: ""
    property string accountId: ""
}
