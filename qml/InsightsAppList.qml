import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI 1.0
Card {
    id: card
    property Item lastFocusItem: null
    property alias searchField: search
    signal appChosen(string appId, var focusItem)
    implicitHeight: content.implicitHeight+40
    ColumnLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 20
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            BodyText { text: qsTr("Apps in this range"); font.pixelSize:18; font.weight:Font.DemiBold; Layout.fillWidth:true }
            OutlineButton { text: qsTr("Refresh ranking"); onClicked:Insights.refreshRanking() }
        }
        RowLayout {
            Layout.fillWidth:true
            FluTextBox { id:search; objectName:"insightsSearch"; Layout.fillWidth:true; placeholderText:qsTr("Search apps"); font.family:Language.fontFamily; font.pixelSize:14; onTextChanged:Insights.setSearch(text); Accessible.name:qsTr("Search apps") }
            FluComboBox { objectName:"insightsSort"; Layout.preferredWidth:144; model:[qsTr("Increase"),qsTr("RAM usage"),qsTr("Name")]; font.family:Language.fontFamily; font.pixelSize:14; onActivated:Insights.setSort(["growth","ram","name"][currentIndex]); Accessible.name:qsTr("Sort apps") }
        }
        RowLayout {
            Layout.fillWidth:true
            BodyText { text:qsTr("Application"); color:Theme.muted; Layout.fillWidth:true }
            BodyText { text:qsTr("At range end"); color:Theme.muted; Layout.preferredWidth:100; horizontalAlignment:Text.AlignRight }
            BodyText { text:qsTr("Change"); color:Theme.muted; Layout.preferredWidth:104; horizontalAlignment:Text.AlignRight }
        }
        ListView {
            id: list
            objectName:"insightsAppList"
            Layout.fillWidth:true; Layout.preferredHeight:Math.max(80,Math.min(336,count*64))
            model:Insights.appModel; clip:true; spacing:4
            ScrollBar.vertical:ScrollBar {}
            delegate: AbstractButton {
                id: appRow
                required property var row
                width:list.width-12; height:60; hoverEnabled:true
                Accessible.name:(row.displayName||row.name)+" · "+row.ramLabel+" · "+row.deltaLabel
                ToolTip.visible:hovered; ToolTip.text:(row.displayName||row.name)+" · "+row.stateLabel+(row.nameDetail?"\n"+row.nameDetail:"")
                onClicked: { card.lastFocusItem=appRow;card.appChosen(row.id,appRow) }
                background:Rectangle { radius:10; color:appRow.hovered || appRow.visualFocus ? Theme.inset : "transparent"; border.width:appRow.visualFocus?2:0; border.color:Theme.accent }
                contentItem:RowLayout {
                    spacing:12
                    Rectangle { Layout.preferredWidth:32; Layout.preferredHeight:32;radius:8;color:Theme.accentSoft; BodyText { anchors.centerIn:parent;text:(appRow.row.displayName||appRow.row.name).charAt(0).toUpperCase();color:Theme.accent;font.weight:Font.DemiBold } }
                    ColumnLayout {
                        Layout.fillWidth:true;spacing:2
                        Text { text:appRow.row.displayName||appRow.row.name; font.family:Language.fontFamily;font.pixelSize:14; color:Theme.text; elide:Text.ElideRight; Layout.fillWidth:true }
                        Text { text:(appRow.row.nameDetail&&!appRow.row.nameUnavailable?appRow.row.processName+" · ":"")+appRow.row.count+" · "+appRow.row.stateLabel;font.family:Language.fontFamily;font.pixelSize:Language.code==="th"?13:12;color:Theme.muted;Layout.fillWidth:true;elide:Text.ElideRight }
                    }
                    InsightsSparkline {Layout.preferredWidth:56;Layout.preferredHeight:24;points:appRow.row.sparkline||[]}
                    BodyText { text:appRow.row.ramLabel;Layout.preferredWidth:100;horizontalAlignment:Text.AlignRight }
                    BodyText { text:appRow.row.deltaLabel;Layout.preferredWidth:104;horizontalAlignment:Text.AlignRight;color:appRow.row.delta>0?Theme.warning:Theme.muted }
                }
            }
            BodyText { anchors.centerIn:parent; width:parent.width-24;horizontalAlignment:Text.AlignHCenter;visible:list.count===0;text:qsTr("No app readings in this range.");color:Theme.muted }
        }
        BodyText { text:qsTr("App readings include shared memory and do not add up to system RAM usage.");font.pixelSize:Language.code==="th"?13:12;color:Theme.muted;Layout.fillWidth:true }
    }
}
