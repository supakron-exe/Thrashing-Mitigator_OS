import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
Card {
    id: card
    property Item lastFocusItem:null
    signal eventChosen(string eventId, var focusItem)
    implicitHeight:content.implicitHeight+40
    ColumnLayout {
        id:content
        anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:20
        spacing:14
        BodyText { text:qsTr("Events");font.pixelSize:18;font.weight:Font.DemiBold;Layout.fillWidth:true }
        OutlineButton { text:qsTr("Mark all read");visible:Insights.unreadCount>0;onClicked:Insights.markAllRead() }
        ListView {
            id:list
            objectName:"insightsEventList"
            Layout.fillWidth:true;Layout.preferredHeight:Math.max(112,Math.min(368,count*108));model:Insights.eventModel;clip:true;spacing:8
            ScrollBar.vertical:ScrollBar {}
            delegate:AbstractButton {
                id:eventRow
                required property var row
                width:list.width-12;height:112;hoverEnabled:true
                Accessible.name:row.title+" · "+row.timeLabel+" · "+row.detail
                onClicked:{card.lastFocusItem=eventRow;card.eventChosen(row.id,eventRow)}
                background:Rectangle {color:eventRow.hovered||eventRow.visualFocus?Theme.accentSoft:Theme.inset;radius:10;border.width:eventRow.visualFocus?2:0;border.color:Theme.accent}
                contentItem:ColumnLayout {
                    spacing:4
                    RowLayout {
                        Layout.fillWidth:true
                        Rectangle {width:6;height:6;radius:3;color:Theme.warning;visible:eventRow.row.unread}
                        BodyText {text:eventRow.row.timeLabel;color:Theme.muted;font.pixelSize:Language.code==="th"?13:12;Layout.fillWidth:true}
                    }
                    BodyText {text:eventRow.row.title;font.weight:Font.DemiBold;Layout.fillWidth:true}
                    BodyText {text:eventRow.row.detail;color:Theme.muted;Layout.fillWidth:true}
                }
            }
            BodyText {anchors.centerIn:parent;width:parent.width-24;horizontalAlignment:Text.AlignHCenter;visible:list.count===0;text:qsTr("No events met the criteria in this range.");color:Theme.muted}
        }
        Flow {
            visible:Insights.eventTotal>200
            Layout.fillWidth:true;Layout.preferredHeight:implicitHeight;spacing:8
            OutlineButton {text:qsTr("Newer events");enabled:Insights.eventPage>0;onClicked:Insights.changeEventPage(-1)}
            OutlineButton {text:qsTr("Older events");enabled:(Insights.eventPage+1)*200<Insights.eventTotal;onClicked:Insights.changeEventPage(1)}
        }
        BodyText {visible:Insights.eventTotal>200;text:qsTr("Page %1 · %2 events").arg(Insights.eventPage+1).arg(Insights.eventTotal);color:Theme.muted;Layout.fillWidth:true}
    }
}
