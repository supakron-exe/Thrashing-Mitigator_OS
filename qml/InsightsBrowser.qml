import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Popup {
    id:popup
    objectName:"insightsBrowser"
    property string kind:"apps"
    property Item restoreFocusItem:null
    signal appChosen(string appId)
    signal eventChosen(string eventId)
    parent:Overlay.overlay
    width:parent?Math.min(940,parent.width-48):880
    height:parent?Math.min(620,parent.height-80):580
    x:parent?(parent.width-width)/2:0;y:56
    padding:20;modal:true;focus:true;dim:true
    closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
    background:Card {}
    onOpened:{if(kind==="events")Insights.changeEventPage(-Insights.eventPage)}
    onClosed:{if(restoreFocusItem)restoreFocusItem.forceActiveFocus()}
    contentItem:ColumnLayout {
        spacing:12
        RowLayout {
            Layout.fillWidth:true
            BodyText {text:popup.kind==="apps"?qsTr("All apps"):qsTr("Event timeline");font.pixelSize:22;font.weight:Font.DemiBold;Layout.fillWidth:true}
            OutlineButton {objectName:"insightsBrowserClose";text:qsTr("Close");onClicked:popup.close()}
        }
        ScrollView {
            Layout.fillWidth:true;Layout.fillHeight:true;clip:true;contentWidth:availableWidth
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            Loader {width:parent.width;active:popup.opened;sourceComponent:popup.kind==="apps"?appsComponent:eventsComponent}
        }
    }
    Component {id:appsComponent;InsightsAppList {onAppChosen:function(appId,focusItem){popup.close();popup.appChosen(appId)}}}
    Component {id:eventsComponent;InsightsEventList {onEventChosen:function(eventId,focusItem){popup.close();popup.eventChosen(eventId)}}}
}
