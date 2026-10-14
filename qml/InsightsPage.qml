import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI 1.0
ColumnLayout {
    id: page
    property Item lastFocusItem: null
    signal detailsRequested(string kind, var focusItem)
    spacing: 16
    Flow {
        Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; spacing: 8
        Repeater {
            model: [{label:qsTr("15 min"),value:900},{label:qsTr("1 hour"),value:3600},{label:qsTr("24 hours"),value:86400}]
            OutlineButton {
                required property var modelData
                text: modelData.label
                textColor: Insights.selectedRange === modelData.value ? Theme.accent : Theme.text
                Accessible.checkable: true; Accessible.checked: Insights.selectedRange === modelData.value
                onClicked: Insights.setRange(modelData.value)
            }
        }
        OutlineButton {
            id: moreButton; objectName: "insightsMore"; text: qsTr("More") + "  ▾"
            onClicked: moreMenu.open()
            FluMenu {
                id: moreMenu; y: moreButton.height + 4
                FluMenuItem {text:qsTr("5 min");font.family:Language.fontFamily;onTriggered:Insights.setRange(300)}
                FluMenuItem {text:qsTr("30 min");font.family:Language.fontFamily;onTriggered:Insights.setRange(1800)}
                FluMenuItem {text:qsTr("6 hours");font.family:Language.fontFamily;onTriggered:Insights.setRange(21600)}
                FluMenuSeparator {}
                FluMenuItem {text:qsTr("Earlier");font.family:Language.fontFamily;onTriggered:Insights.previousRange()}
                FluMenuItem {text:qsTr("Later");font.family:Language.fontFamily;enabled:!Insights.followLive;onTriggered:Insights.nextRange()}
                FluMenuSeparator {}
                FluMenuItem {text:Insights.tracking?qsTr("Pause tracking"):qsTr("Resume tracking");font.family:Language.fontFamily;onTriggered:Insights.tracking?Insights.pauseTracking():Insights.resumeTracking()}
            }
        }
        OutlineButton {visible:!Insights.followLive;text:qsTr("Back to latest");onClicked:Insights.returnToLive()}
        OutlineButton {visible:!Insights.tracking;text:qsTr("Resume tracking");textColor:Theme.accent;onClicked:Insights.resumeTracking()}
    }
    GridLayout {
        objectName: "insightsVisualGrid"; Layout.fillWidth: true
        columns: page.width >= 900 ? 2 : 1; columnSpacing: 16; rowSpacing: 16
        InsightsRanking {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.preferredWidth: page.width >= 900 ? (page.width-16)*0.4 : page.width
            onAppChosen: function(appId, focusItem) {page.lastFocusItem=focusItem;Insights.selectApp(appId)}
            onBrowseRequested: function(focusItem) {browser.kind="apps";browser.restoreFocusItem=focusItem;browser.open()}
        }
        InsightsTrend {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.preferredWidth: page.width >= 900 ? (page.width-16)*0.6 : page.width
            onDetailsRequested: function(focusItem) {page.lastFocusItem=focusItem;page.detailsRequested("app",focusItem)}
            onEventChosen: function(eventId, focusItem) {page.lastFocusItem=focusItem;Insights.inspectEvent(eventId);page.detailsRequested("event",focusItem)}
        }
    }
    InsightsEventPreview {
        Layout.fillWidth: true
        onEventChosen: function(eventId, focusItem) {page.lastFocusItem=focusItem;Insights.inspectEvent(eventId);page.detailsRequested("event",focusItem)}
        onBrowseRequested: function(focusItem) {browser.kind="events";browser.restoreFocusItem=focusItem;browser.open()}
    }
    BodyText {
        Layout.fillWidth:true
        text:(Insights.storageState.temporary?qsTr("Temporary live history"):qsTr("24-hour local history"))+" · "+qsTr("Updated %1").arg(Insights.lastSampleAt)
        color:Theme.muted;font.pixelSize:Language.code==="th"?13:12
    }
    BodyText {visible:Insights.coverage.denied>0;text:qsTr("Some processes could not be read. %1 readable, %2 unavailable.").arg(Insights.coverage.readable||0).arg(Insights.coverage.denied||0);color:Theme.warning;Layout.fillWidth:true}
    BodyText {visible:!!Insights.storageState.error;text:qsTr("History could not be saved. Live tracking continues. %1").arg(Insights.storageState.error||"");color:Theme.warning;Layout.fillWidth:true}
    InsightsBrowser {
        id: browser
        onAppChosen: function(appId) {Insights.selectApp(appId)}
        onEventChosen: function(eventId) {Insights.inspectEvent(eventId);page.lastFocusItem=browser.restoreFocusItem;page.detailsRequested("event",browser.restoreFocusItem)}
    }
}
