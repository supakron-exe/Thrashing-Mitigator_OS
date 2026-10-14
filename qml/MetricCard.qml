import QtQuick
import QtQuick.Layouts
import FluentUI 1.0
Card {
    id: card
    property string label
    property real bytes: 0
    property string hint
    property bool emphasis: false
    implicitHeight: Math.max(128, content.implicitHeight + 40)
    ColumnLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 20
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            BodyText { text: card.label; font.pixelSize: Language.code === "th" ? 13 : 12; font.weight: Font.DemiBold; color: Theme.muted; Layout.fillWidth: true }
            FluIcon { iconSource: card.emphasis ? FluentIcons.LightningBolt : FluentIcons.System; iconSize: 16; iconColor: card.emphasis ? Theme.accent : Theme.muted; Accessible.ignored: true }
        }
        RowLayout {
            spacing: 6
            BodyText { text: Theme.gb(card.bytes); font.pixelSize: 32; font.weight: Font.DemiBold; color: card.emphasis ? Theme.accent : Theme.text }
            BodyText { text: "GB"; color: Theme.muted; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 6 }
            Item { Layout.fillWidth: true }
        }
        BodyText { text: card.hint; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
    }
}
