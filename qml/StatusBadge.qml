import QtQuick
import QtQuick.Window
import QtQuick.Layouts
Rectangle {
    id: badge
    property string label: qsTr("Normal")
    property string tone: "success"
    property bool liveFeedback: false
    property real lastTimestamp: 0
    implicitWidth: row.implicitWidth + 24
    implicitHeight: 32
    radius: 16
    color: Theme.toneSurface(tone)
    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Item {
            width: 6; height: 6
            Rectangle { anchors.centerIn: parent; width: 16; height: 16; radius: 8; color: Theme.tone(badge.tone); opacity: 0; id: halo; objectName: badge.liveFeedback ? "liveHalo" : "statusHalo"; Accessible.ignored: true }
            Rectangle { anchors.fill: parent; radius: 3; color: Theme.tone(badge.tone); Accessible.ignored: true }
        }
        BodyText { text: badge.label; font.pixelSize: Language.code === "th" ? 13 : 12; font.weight: Font.DemiBold; color: Theme.tone(badge.tone) }
    }
    SequentialAnimation {
        id: samplePulse
        NumberAnimation { target: halo; property: "opacity"; to: 0.24; duration: 70 }
        NumberAnimation { target: halo; property: "opacity"; to: 0; duration: 150 }
    }
    Connections {
        target: Memory
        function onSampleChanged() {
            var timestamp = Number(Memory.snapshot.timestamp || 0)
            if (badge.liveFeedback && !Memory.live) { samplePulse.stop(); halo.opacity = 0 }
            if (badge.liveFeedback && Memory.live && timestamp !== badge.lastTimestamp && Theme.motion && badge.visible && badge.Window.window && badge.Window.window.active) samplePulse.restart()
            badge.lastTimestamp = timestamp
        }
    }
    Connections { target: Preferences; function onChanged() { if (!Theme.motion) { samplePulse.stop(); halo.opacity = 0 } } }
    Connections { target: badge.Window.window; function onActiveChanged() { if (!badge.Window.window.active) { samplePulse.stop(); halo.opacity = 0 } } }
}
