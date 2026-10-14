import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI 1.0
Card {
    id: card
    objectName: "insightsRankingCard"
    implicitHeight: Math.max(396,content.implicitHeight+32)
    signal appChosen(string appId, var focusItem)
    signal browseRequested(var focusItem)
    ColumnLayout {
        id:content
        anchors.fill:parent;anchors.margins:16;spacing:8
        RowLayout {
            Layout.fillWidth:true
            BodyText {text:qsTr("Apps gaining RAM");font.pixelSize:18;font.weight:Font.DemiBold;Layout.fillWidth:true}
            BodyText {text:qsTr("Top 5");color:Theme.muted;font.pixelSize:Language.code==="th"?13:12}
        }
        BodyText {
            text:qsTr("Increase over observed readings");color:Theme.muted
            font.pixelSize:Language.code==="th"?13:12;Layout.fillWidth:true
        }
        ListView {
            id:list
            objectName:"insightsRankingList"
            Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:296;Layout.preferredHeight:296
            model:Insights.visualRanking;spacing:4;interactive:false;clip:true
            delegate:AbstractButton {
                id:appRow
                required property var row
                objectName:"insightsRankingRow_"+row.id
                width:list.width;height:56;hoverEnabled:true;padding:8
                readonly property bool selected:Insights.selectedApp.id===row.id
                Accessible.name:(row.displayName||row.name)+" · "+qsTr("Increase")+" "+row.deltaLabel
                Accessible.checkable:true;Accessible.checked:selected
                ToolTip.visible:hovered;ToolTip.delay:450
                ToolTip.text:(row.displayName||row.name)+" · "+row.deltaLabel+"\n"+(row.nameDetail?row.nameDetail+"\n":"")+
                    (row.new?qsTr("Since first observed"):qsTr("Increase over observed readings"))+"\n"+
                    qsTr("Bars compare RAM increases across apps.")
                onClicked:card.appChosen(row.id,appRow)
                background:Rectangle {radius:10;color:appRow.selected?Theme.accentSoft:appRow.hovered?Theme.inset:"transparent";border.width:appRow.visualFocus?2:0;border.color:Theme.accent;Behavior on color {ColorAnimation {duration:Theme.hoverDuration}}}
                contentItem:RowLayout {
                    spacing:10
                    Rectangle {Layout.preferredWidth:28;Layout.preferredHeight:28;radius:8;color:Theme.inset;BodyText {anchors.centerIn:parent;text:(appRow.row.displayName||appRow.row.name).charAt(0).toUpperCase();font.weight:Font.DemiBold;color:Theme.accent}}
                    ColumnLayout {
                        Layout.fillWidth:true;spacing:4
                        RowLayout {
                            Layout.fillWidth:true;spacing:8
                            Text {objectName:"insightsRankingName_"+appRow.row.id;text:appRow.row.displayName||appRow.row.name;Layout.fillWidth:true;Layout.preferredHeight:28;verticalAlignment:Text.AlignVCenter;font.family:Language.fontFamily;font.pixelSize:14;color:Theme.text;wrapMode:Text.WrapAnywhere;maximumLineCount:2;elide:Text.ElideRight}
                            BodyText {objectName:"insightsRankingDelta_"+appRow.row.id;text:appRow.row.deltaLabel;font.weight:Font.DemiBold;color:Theme.accent;wrapMode:Text.NoWrap}
                        }
                        Rectangle {
                            Layout.fillWidth:true;Layout.preferredHeight:5;radius:3;color:Theme.border
                            Rectangle {width:parent.width*appRow.row.barRatio;height:parent.height;radius:3;color:Theme.accent;opacity:appRow.selected?1:0.65;Behavior on width {enabled:Theme.motion;NumberAnimation {duration:160;easing.type:Easing.OutCubic}}}
                        }
                    }
                }
            }
            ColumnLayout {
                anchors.centerIn:parent;width:parent.width-24;spacing:12;visible:list.count===0
                FluIcon {Layout.alignment:Qt.AlignHCenter;iconSource:FluentIcons.AreaChart;iconSize:40;iconColor:Theme.muted;Accessible.ignored:true}
                BodyText {text:Insights.visualSummary.appCount?qsTr("No comparable increase yet"):qsTr("Waiting for app readings");font.weight:Font.DemiBold;horizontalAlignment:Text.AlignHCenter;Layout.fillWidth:true}
                BodyText {text:Insights.visualSummary.appCount?qsTr("Apps may be steady, decreasing, or missing a baseline."):qsTr("Live readings will appear here as they arrive.");color:Theme.muted;horizontalAlignment:Text.AlignHCenter;Layout.fillWidth:true}
            }
        }
        OutlineButton {id:browse;objectName:"insightsBrowseApps";text:qsTr("View all apps");Layout.fillWidth:true;onClicked:card.browseRequested(browse)}
    }
}
