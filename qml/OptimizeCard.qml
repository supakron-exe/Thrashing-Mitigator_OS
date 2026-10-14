import QtQuick
import QtQuick.Layouts
import FluentUI 1.0
Card {
    id: card
    signal viewResult()
    property var operation: Presenter.operation
    readonly property var stages: operation.stages || []
    readonly property int stageIndex: {
        for (var i = 0; i < stages.length; i++) if (stages[i].id === operation.stageId) return i
        return 0
    }
    implicitHeight: content.implicitHeight + 40
    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 20
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            BodyText { text: qsTr("Optimize memory"); font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
            FluIcon { iconSource: FluentIcons.LightningBolt; iconSize: 20; iconColor: Theme.accent; Accessible.ignored: true }
        }
        Item {
            Layout.fillWidth: true
            implicitHeight: Math.max(idleMode.implicitHeight, runningStage.implicitHeight)
            ColumnLayout {
                id: idleMode
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                visible: !Memory.running
                spacing: 12
                FluComboBox {
                    id: modes
                    objectName: "modeSelector"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    model: ["Standard", "Deep", "Maximum"]
                    currentIndex: model.indexOf(Memory.selectedMode)
                    disabled: Memory.busy
                    normalColor: Theme.inset
                    hoverColor: Theme.surface
                    disableColor: Theme.inset
                    font.family: Language.fontFamily
                    font.pixelSize: 14
                    Accessible.name: qsTr("Optimization mode")
                    Accessible.description: modeHint.text
                    onActivated: Memory.setMode(currentText)
                }
                BodyText {
                    id: modeHint
                    Layout.fillWidth: true
                    color: Theme.muted
                    font.pixelSize: Language.code === "th" ? 13 : 12
                    text: Memory.selectedMode === "Standard" ? qsTr("Trims eligible idle background apps. Active apps stay untouched.") : Memory.selectedMode === "Deep" ? qsTr("Trims idle apps, then cleans system memory. Administrator access enables all system steps.") : qsTr("Includes active apps and system memory. Administrator access enables all system steps.")
                }
            }
            ColumnLayout {
                id: runningStage
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                visible: Memory.running
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    BusyIndicator { objectName: "operationSpinner"; Layout.preferredWidth: 18; Layout.preferredHeight: 18 }
                    BodyText { text: (card.operation.source === "auto" ? qsTr("Auto · ") + card.operation.mode + " · " : "") + qsTr("Step %1 of %2").arg(card.stageIndex + 1).arg(card.stages.length); color: Theme.accent; font.pixelSize: Language.code === "th" ? 13 : 12; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    BodyText { text: qsTr("%1 s elapsed").arg(card.operation.elapsedSeconds || 0); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Repeater {
                        model: card.stages
                        Rectangle {
                            required property var modelData
                            Layout.fillWidth: true; height: 4; radius: 2
                            color: modelData.state === "active" ? Theme.accent : modelData.state === "pending" ? Theme.border : Theme.muted
                            Behavior on color { ColorAnimation { duration: Theme.hoverDuration } }
                            Accessible.ignored: true
                        }
                    }
                }
                BodyText { text: card.stages[card.stageIndex] ? card.stages[card.stageIndex].label : qsTr("Preparing"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                BodyText { text: Presenter.progress; Layout.fillWidth: true; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
            }
        }
        ActionButton { objectName: "optimizeButton"; Layout.fillWidth: true; text: Memory.running ? qsTr("Optimizing…") : Memory.busy ? qsTr("Please wait…") : qsTr("Optimize now"); disabled: Memory.busy || Memory.closing; onClicked: Memory.startOptimization() }
        ColumnLayout {
            visible: !Memory.running && Object.keys(Memory.lastResult).length > 0
            Layout.fillWidth: true
            spacing: 8
            BodyText { text: Presenter.lastResult.title || ""; color: Theme.tone(Memory.lastResult.tone || "warning"); font.weight: Font.DemiBold; Layout.fillWidth: true }
            OutlineButton { objectName: "viewResultButton"; text: qsTr("View result"); Layout.fillWidth: true; onClicked: card.viewResult() }
        }
        BodyText { visible: Memory.busy && !Memory.running; text: Presenter.progress; color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
        BodyText { visible: !Memory.busy && !Object.keys(Memory.lastResult).length; text: qsTr("Runs only when you choose to optimize."); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
    }
}
