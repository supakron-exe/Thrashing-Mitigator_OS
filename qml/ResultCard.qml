import QtQuick
import QtQuick.Layouts
import FluentUI 1.0
Card {
    id: card
    objectName: "resultCard"
    property var result: Presenter.lastResult
    property bool expanded: false
    border.color: activeFocus ? Theme.accent : Theme.border
    border.width: activeFocus ? 2 : 1
    Accessible.role: Accessible.Pane
    Accessible.name: (result.title || qsTr("Optimization result")) + ". " + (result.message || "")
    implicitHeight: content.implicitHeight + 48
    Connections { target: Memory; function onResultChanged() { card.expanded = false } }
    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 24
        spacing: 20
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Rectangle {
                width: 40; height: 40; radius: 12; color: Theme.toneSurface(card.result.tone || "success")
                FluIcon { anchors.centerIn: parent; iconSource: card.result.tone === "error" ? FluentIcons.ErrorBadge : card.result.tone === "warning" ? FluentIcons.Info : FluentIcons.CheckMark; iconSize: 18; iconColor: Theme.tone(card.result.tone || "success"); Accessible.ignored: true }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                BodyText { text: card.result.title || ""; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.fillWidth: true }
                BodyText { text: card.result.message || ""; color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
                BodyText { visible: card.result.source === "auto"; text: qsTr("Auto Optimize") + " · " + (card.result.reason || ""); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
            }
            StatusBadge { label: card.result.mode || ""; tone: card.result.tone || "success" }
        }
        RowLayout {
            visible: !!card.result.hasMeasurements
            Layout.fillWidth: true
            spacing: 24
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                BodyText { text: qsTr("AVAILABLE CHANGE"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; font.weight: Font.DemiBold }
                BodyText { text: card.result.gain || ""; font.pixelSize: 32; font.weight: Font.DemiBold; color: Theme.tone(card.result.tone || "success") }
                BodyText { text: card.result.measurementLabel || ""; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
            }
            ColumnLayout { Layout.fillWidth: true; spacing: 6; BodyText { text: qsTr("Before"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12 } BodyText { text: card.result.before || ""; font.pixelSize: 20; font.weight: Font.DemiBold } }
            ColumnLayout { Layout.fillWidth: true; spacing: 6; BodyText { text: qsTr("After"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12 } BodyText { text: card.result.after || ""; font.pixelSize: 20; font.weight: Font.DemiBold } }
            ColumnLayout { Layout.fillWidth: true; spacing: 6; BodyText { text: qsTr("Duration"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12 } BodyText { text: card.result.duration || ""; font.pixelSize: 20; font.weight: Font.DemiBold } }
        }
        ColumnLayout {
            visible: !!card.result.hasMeasurements && Number(card.result.totalMb) > 0
            Layout.fillWidth: true
            spacing: 12
            Repeater {
                model: [{label: qsTr("Before"), mb: card.result.beforeMb, display: card.result.before}, {after: true, label: qsTr("After"), mb: card.result.afterMb, display: card.result.after}]
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 12
                    BodyText { text: modelData.label; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.preferredWidth: Math.max(44, implicitWidth) }
                    Rectangle {
                        Layout.fillWidth: true; height: 10; radius: 5; color: Theme.inset
                        Rectangle { width: parent.width * Math.max(0, Math.min(1, Number(modelData.mb || 0) / Math.max(1, Number(card.result.totalMb)))); height: parent.height; radius: 5; color: modelData.after ? Theme.accent : Theme.muted }
                        Accessible.ignored: true
                    }
                    BodyText { text: modelData.display || ""; font.pixelSize: Language.code === "th" ? 13 : 12; font.weight: Font.DemiBold; Layout.preferredWidth: 96; horizontalAlignment: Text.AlignRight }
                }
            }
            BodyText { text: qsTr("Available memory · Same total RAM scale · %1").arg(card.result.measurementLabel || ""); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
        }
        RowLayout {
            Layout.fillWidth: true
            BodyText { text: qsTr("%1 apps trimmed · %2 skipped with errors").arg(card.result.trimmed || 0).arg(card.result.failed || 0); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
            OutlineButton {
                id: detailsButton
                objectName: "detailsButton"
                text: card.expanded ? qsTr("Hide details") : qsTr("View details")
                implicitWidth: Math.max(138, contentItem.implicitWidth + 24)
                Accessible.name: text
                Accessible.checkable: true
                Accessible.checked: card.expanded
                contentItem: RowLayout {
                    spacing: 8
                    BodyText { text: detailsButton.text; color: detailsButton.textColor; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                    FluIcon {
                        iconSource: FluentIcons.ChevronDown; iconSize: 12; iconColor: Theme.muted; rotation: card.expanded ? 180 : 0
                        Behavior on rotation { enabled: Theme.motion; NumberAnimation { duration: Theme.detailsDuration; easing.type: Easing.OutCubic } }
                        Accessible.ignored: true
                    }
                }
                onClicked: card.expanded = !card.expanded
            }
        }
        ColumnLayout {
            id: detailsContent
            visible: false
            opacity: 0
            Layout.fillWidth: true
            spacing: 12
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            BodyText { text: qsTr("Operation sequence"); font.weight: Font.DemiBold; Layout.fillWidth: true }
            Repeater {
                model: Presenter.operation.stages || []
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 12
                    Rectangle { width: 7; height: 7; radius: 4; color: modelData.state === "success" ? Theme.success : modelData.state === "failed" ? Theme.error : modelData.state === "partial" || modelData.state === "skipped" ? Theme.warning : Theme.muted; Accessible.ignored: true }
                    BodyText { text: modelData.label; Layout.fillWidth: true; font.pixelSize: Language.code === "th" ? 13 : 12 }
                    BodyText { text: modelData.state === "pending" ? qsTr("Not reached") : modelData.state === "success" ? qsTr("Completed") : modelData.state === "partial" ? qsTr("Partial") : modelData.state === "skipped" ? qsTr("Skipped") : modelData.state === "failed" ? qsTr("Failed") : qsTr("Finished"); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12 }
                }
            }
            BodyText { visible: !!card.result.hasFree; text: qsTr("System steps: %1 completed · Free memory change: %2").arg(card.result.stepSummary || "").arg(card.result.freeChange || ""); color: Theme.muted; Layout.fillWidth: true }
            BodyText { visible: !!card.result.maximum && !!card.result.hasMeasurements; text: qsTr("Available at completion: %1").arg(card.result.completionChange || "") + (card.result.hasSettled ? qsTr(" · After settling: %1").arg(card.result.settledChange || "") : ""); color: Theme.muted; Layout.fillWidth: true }
            BodyText { visible: !!card.result.hasFree; text: qsTr("Free and Available are separate measurements; their changes are not added together."); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
            Repeater {
                model: card.expanded ? (card.result.steps || []).concat(card.result.targets || []) : []
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: detail.implicitHeight + 24
                    color: Theme.inset
                    radius: 10
                    RowLayout {
                        id: detail
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                        spacing: 12
                        FluIcon { iconSource: modelData.ok ? FluentIcons.CheckMark : FluentIcons.Info; iconSize: 16; iconColor: modelData.ok ? Theme.success : Theme.warning; Accessible.ignored: true }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            BodyText { text: modelData.name; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            BodyText { text: (modelData.ok ? qsTr("Completed · ") : qsTr("Skipped · ")) + modelData.detail; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                        }
                    }
                }
            }
        }
    }
    MotionReveal { targetItem: detailsContent; shown: card.expanded; duration: Theme.detailsDuration }
}
