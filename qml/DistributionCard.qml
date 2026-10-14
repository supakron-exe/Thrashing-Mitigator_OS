import QtQuick
import QtQuick.Layouts
Card {
    implicitHeight: Math.max(200, content.implicitHeight + 40)
    Connections { target: Memory; function onSampleChanged() { donut.requestPaint() } }
    Connections { target: Preferences; function onChanged() { donut.requestPaint() } }
    ColumnLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 20
        spacing: 12
        BodyText { text: qsTr("Memory distribution"); font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            spacing: 20
            Item {
                Layout.preferredWidth: 126
                Layout.preferredHeight: 126
                Canvas {
                    id: donut
                    anchors.fill: parent
                    onPaint: {
                        var ctx = getContext("2d"); ctx.reset()
                        var cx = width / 2, cy = height / 2, r = Math.min(width, height) / 2 - 8
                        ctx.lineWidth = 9; ctx.lineCap = "round"
                        ctx.strokeStyle = Theme.border; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke()
                        var percentage = Number(Memory.snapshot.percent) / 100
                        if (percentage > 0) { ctx.strokeStyle = Theme.accent; ctx.beginPath(); ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + percentage * Math.PI * 2); ctx.stroke() }
                    }
                }
                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 2
                    BodyText { text: Math.round(Memory.snapshot.percent) + "%"; font.pixelSize: 28; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignHCenter }
                    BodyText { text: qsTr("in use"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.alignment: Qt.AlignHCenter }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 20
                ColumnLayout {
                    spacing: 6
                    RowLayout { spacing: 8; Rectangle { width: 7; height: 7; radius: 3; color: Theme.accent } BodyText { text: qsTr("In use"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12 } }
                    BodyText { text: Theme.gb(Memory.snapshot.used) + " GB"; font.pixelSize: 18; font.weight: Font.DemiBold }
                }
                ColumnLayout {
                    spacing: 6
                    RowLayout { spacing: 8; Rectangle { width: 7; height: 7; radius: 3; color: Theme.muted } BodyText { text: qsTr("Available"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12 } }
                    BodyText { text: Theme.gb(Memory.snapshot.available) + " GB"; font.pixelSize: 18; font.weight: Font.DemiBold }
                }
            }
        }
    }
}
