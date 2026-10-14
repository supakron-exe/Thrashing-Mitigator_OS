import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Popup {
    id:popup
    objectName:"insightsDetails"
    property Item restoreFocusItem:null
    property string detailKind:"app"
    property bool processesExpanded:false
    readonly property var appData:detailKind==="app"?Insights.selectedApp:({})
    readonly property var eventData:detailKind==="event"?Insights.selectedEvent:({})
    parent:Overlay.overlay
    x:parent?parent.width-width-24:0;y:56
    width:parent?parent.width<1000?parent.width-48:440:440
    height:parent?parent.height-80:600
    padding:20;modal:true;focus:true;dim:true
    closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
    background:Card {}
    onOpened:processesExpanded=false
    onClosed:{if(detailKind==="event")Insights.closeEventInspection();if(restoreFocusItem)restoreFocusItem.forceActiveFocus()}
    contentItem:ScrollView {
        clip:true;contentWidth:availableWidth;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ColumnLayout {
            width:parent.width;spacing:18
            RowLayout {
                Layout.fillWidth:true
                BodyText {text:Object.keys(popup.appData).length?popup.appData.displayName||popup.appData.name:popup.eventData.title||qsTr("Details");font.pixelSize:22;font.weight:Font.DemiBold;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}
                OutlineButton {text:qsTr("Close");onClicked:popup.close()}
            }
            ColumnLayout {
                visible:Object.keys(popup.appData).length>0;Layout.fillWidth:true;spacing:16
                BodyText {text:popup.appData.nameDetail||"";visible:text.length>0;color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}
                BodyText {text:(popup.appData.beforeLabel||"—")+"  →  "+(popup.appData.ramLabel||"—");font.pixelSize:22;font.weight:Font.DemiBold;Layout.fillWidth:true}
                BodyText {text:qsTr("Change")+" · "+(popup.appData.deltaLabel||"—");font.pixelSize:24;font.weight:Font.DemiBold;Layout.fillWidth:true}
                BodyText {text:qsTr("Peak")+" · "+(popup.appData.peakLabel||"—");Layout.fillWidth:true}
                InsightsChart {Layout.fillWidth:true;Layout.preferredHeight:220;memoryScale:true;filled:true;scaleKey:popup.appData.id||"";points:popup.appData.series||[]}
                BodyText {text:popup.appData.stateLabel||"";color:Theme.muted;Layout.fillWidth:true}
                OutlineButton {text:qsTr("Processes at the range end")+"  "+(popup.processesExpanded?"▴":"▾");Layout.fillWidth:true;onClicked:popup.processesExpanded=!popup.processesExpanded}
                Repeater {model:popup.processesExpanded?(popup.appData.processes||[]):[];BodyText {required property var modelData;text:"PID "+modelData.pid+" · "+modelData.ramLabel;Layout.fillWidth:true}}
                BodyText {visible:!(popup.appData.processes||[]).length;text:qsTr("Process details are available for the latest 30 minutes of collected data.");color:Theme.muted;Layout.fillWidth:true}
            }
            ColumnLayout {
                visible:Object.keys(popup.eventData).length>0;Layout.fillWidth:true;spacing:14
                BodyText {text:popup.eventData.timeLabel||"";color:Theme.muted;Layout.fillWidth:true}
                BodyText {text:popup.eventData.detail||"";font.pixelSize:22;Layout.fillWidth:true}
                BodyText {text:qsTr("Apps that increased in this window");font.weight:Font.DemiBold;Layout.fillWidth:true}
                Repeater {
                    model:popup.eventData.contributors||[]
                    AbstractButton {
                        id:contributor
                        required property var modelData
                        Layout.fillWidth:true;implicitHeight:contentItem.implicitHeight+24;padding:12;hoverEnabled:true
                        Accessible.name:(modelData.displayName||modelData.name)+" · "+modelData.deltaLabel
                        onClicked:{Insights.selectApp(modelData.id);popup.close()}
                        background:Card {color:contributor.hovered?Theme.inset:Theme.surface;border.color:contributor.visualFocus?Theme.accent:Theme.border;border.width:contributor.visualFocus?2:1}
                        contentItem:ColumnLayout {spacing:4;BodyText {text:contributor.modelData.displayName||contributor.modelData.name;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere} BodyText {text:contributor.modelData.deltaLabel;color:Theme.accent;font.weight:Font.DemiBold;Layout.fillWidth:true}}
                    }
                }
                BodyText {visible:!(popup.eventData.contributors||[]).length;text:qsTr("No comparable app readings for this event.");color:Theme.muted;Layout.fillWidth:true}
                OutlineButton {objectName:"insightsJumpToEvent";text:qsTr("View this time window");Layout.fillWidth:true;onClicked:{Insights.jumpToInspectedEvent();popup.close()}}
            }
            BodyText {text:qsTr("App readings include shared memory and do not add up to system RAM usage.");color:Theme.muted;Layout.fillWidth:true}
            OutlineButton {text:qsTr("Open Task Manager");Layout.fillWidth:true;onClicked:Insights.openTaskManager()}
        }
    }
}
