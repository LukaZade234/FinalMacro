import QtQuick
import gui 1.0

// Soul-key icon for Statistics → Keys (summary cards and recent rows).
Item {
    id: root
    property string keyType: ""
    property int size: 20

    readonly property string iconSource: MudaeEmoji.keyUrl(keyType)

    implicitWidth: size
    implicitHeight: size

    Image {
        anchors.fill: parent
        visible: root.iconSource !== ""
        source: root.iconSource
        sourceSize.width: root.size
        sourceSize.height: root.size
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }
}
