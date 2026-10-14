import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Card {
    id:card
    objectName:"insightsTrendCard"
    readonly property var appData:Insights.selectedApp
    readonly property var qualityHints: {
        var hints=[]
        if(appData.hasPartialReadings) hints.push(qsTr("Partial readings"))
        if(appData.hasGaps) hints.push(qsTr("Gaps in history"))
        return hints
    }
    readonly property bool minuteSummary:(appData.series||[]).some(function(point){return !!point.aggregated})
    signal detailsRequested(var focusItem)
    signal eventChosen(string eventId, var focusItem)
    implicitHeight:Math.max(396,content.implicitHeight+32)
    ColumnLayout {
        id:content
        anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:16;spacing:10
        RowLayout {
            Layout.fillWidth:true
            Text {objectName:"insightsTrendAppName";text:card.appData.displayName||card.appData.name||qsTr("App memory trend");Layout.fillWidth:true;elide:Text.ElideRight;font.family:Language.fontFamily;font.pixelSize:18;font.weight:Font.DemiBold;color:Theme.text;ToolTip.visible:nameHover.containsMouse;ToolTip.text:text;MouseArea {id:nameHover;anchors.fill:parent;hoverEnabled:true;acceptedButtons:Qt.NoButton}}
            OutlineButton {id:details;objectName:"insightsAppDetailsButton";text:qsTr("Details");enabled:!!card.appData.id;onClicked:card.detailsRequested(details)}
        }
        BodyText {objectName:"insightsTrendProcessName";text:card.appData.nameDetail||"";visible:text.length>0;color:Theme.muted;font.pixelSize:Language.code==="th"?13:12;Layout.fillWidth:true}
        RowLayout {
            Layout.fillWidth:true;spacing:12
            BodyText {text:(card.appData.beforeLabel||"—")+"  →  "+(card.appData.ramLabel||"—");font.pixelSize:20;font.weight:Font.DemiBold;Layout.fillWidth:true}
            BodyText {text:card.appData.deltaLabel||"—";font.pixelSize:22;font.weight:Font.DemiBold;color:card.appData.delta<0?Theme.success:Theme.accent}
        }
        BodyText {
            objectName:"insightsTrendBaseline"
            Layout.fillWidth:true;font.pixelSize:Language.code==="th"?13:12;color:Theme.muted
            text:card.appData.new?qsTr("Since first observed"):card.appData.closed||card.appData.comparable===false?card.appData.stateLabel||qsTr("No continuous baseline"):Insights.visualSummary.fallback&&card.appData.id===Insights.visualSummary.fallbackAppId?qsTr("Highest RAM usage · no comparable increase"):qsTr("First reading → last reading")
        }
        Item {
            Layout.fillWidth:true;Layout.preferredHeight:220;Layout.minimumHeight:220;Layout.maximumHeight:220
            InsightsChart {id:chart;objectName:"insightsChart";anchors.fill:parent;memoryScale:true;filled:true;scaleKey:(card.appData.id||"")+":"+Insights.selectedRange+":"+(Insights.followLive?"live":Insights.selectedEnd);points:card.appData.series||[];events:Insights.selectedAppMarkers;onEventSelected:card.eventChosen(eventId,chart)}
            BodyText {anchors.centerIn:parent;width:parent.width-96;horizontalAlignment:Text.AlignHCenter;visible:!(card.appData.series||[]).length;text:Insights.loading?qsTr("Loading app trend…"):qsTr("No app readings in this range.");color:Theme.muted}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:8
            BodyText {objectName:"insightsTrendObservedSpan";text:card.appData.observedSpanLabel||qsTr("Waiting for readings");color:Theme.muted;font.pixelSize:Language.code==="th"?13:12;Layout.fillWidth:true}
            BodyText {text:card.minuteSummary?qsTr("1-minute summary"):qsTr("Live readings");color:Theme.muted;font.pixelSize:Language.code==="th"?13:12}
        }
        BodyText {
            objectName:"insightsTrendReadingStatus"
            text:(card.appData.stale?qsTr("Last observed %1").arg(card.appData.lastLabel||"—")+" · ":"")+
                 (card.qualityHints.length?card.qualityHints.join(" · ")+" · ":"")+
                 qsTr("System RAM change")+"  "+(Insights.summary.changeLabel||"—")
            font.pixelSize:Language.code==="th"?13:12;color:Theme.muted;Layout.fillWidth:true
        }
    }
}
