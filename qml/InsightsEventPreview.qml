import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI 1.0
ColumnLayout {
    id:section
    signal eventChosen(string eventId, var focusItem)
    signal browseRequested(var focusItem)
    spacing:10
    RowLayout {
        Layout.fillWidth:true
        BodyText {text:qsTr("Recent events");font.pixelSize:18;font.weight:Font.DemiBold}
        StatusBadge {label:String(Insights.eventTotal);tone:"neutral"}
        Item {Layout.fillWidth:true}
        OutlineButton {id:allEvents;objectName:"insightsBrowseEvents";text:qsTr("View all");enabled:Insights.eventTotal>0;onClicked:section.browseRequested(allEvents)}
    }
    GridLayout {
        Layout.fillWidth:true;columns:section.width>=900?3:1;columnSpacing:12;rowSpacing:8
        Repeater {
            id:events
            model:Insights.recentEventModel
            AbstractButton {
                id:entry
                required property var row
                readonly property var modelData:row
                objectName:"insightsRecentEvent_"+row.id
                Layout.fillWidth:true;Layout.preferredHeight:100;hoverEnabled:true;padding:16
                Accessible.name:modelData.timeLabel+" · "+modelData.title+" · "+modelData.detail
                onClicked:section.eventChosen(modelData.id,entry)
                background:Card {color:entry.hovered?Theme.inset:Theme.surface;border.color:entry.visualFocus?Theme.accent:Theme.border;border.width:entry.visualFocus?2:1}
                contentItem:RowLayout {
                    spacing:12
                    FluIcon {Layout.alignment:Qt.AlignVCenter;iconSource:entry.modelData.kind==="optimize"?FluentIcons.Sync:entry.modelData.kind==="high"?FluentIcons.Info:FluentIcons.AreaChart;iconSize:22;iconColor:entry.modelData.kind==="optimize"?Theme.accent:Theme.warning;Accessible.ignored:true}
                    ColumnLayout {
                        Layout.fillWidth:true;spacing:3
                        RowLayout {Layout.fillWidth:true;BodyText {text:entry.modelData.timeLabel;color:Theme.muted;font.pixelSize:Language.code==="th"?13:12;Layout.fillWidth:true} Rectangle {width:6;height:6;radius:3;color:Theme.warning;visible:entry.modelData.unread}}
                        Text {text:entry.modelData.title;Layout.fillWidth:true;font.family:Language.fontFamily;font.pixelSize:14;font.weight:Font.DemiBold;color:Theme.text;wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight}
                        BodyText {text:entry.modelData.detail;color:Theme.muted;font.pixelSize:Language.code==="th"?13:12;Layout.fillWidth:true}
                    }
                }
                ToolTip.visible:hovered;ToolTip.text:modelData.title+" · "+modelData.detail
            }
        }
    }
    BodyText {visible:events.count===0;text:qsTr("No notable events in this range");color:Theme.muted;Layout.fillWidth:true}
}
