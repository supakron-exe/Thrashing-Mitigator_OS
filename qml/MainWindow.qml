import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI 1.0
FluWindow {
    id: window
    objectName: "mainWindow"
    title: "Thrashing Mitigator"
    width: 1180
    // FluFrameless adds the 40px app bar to the initial window/minimum height.
    height: 700
    minimumWidth: 900
    minimumHeight: 600
    backgroundColor: Theme.background
    property int page: 0
    onPageChanged: { Insights.setActive(page === 3); if (page !== 3) Insights.closeDetails(); Qt.callLater(function(){scroll.contentItem.contentY=0}) }
    property bool wide: scroll.availableWidth >= 900
    function viewResult() {
        if (!Object.keys(Memory.lastResult).length) return
        window.page = 0
        Qt.callLater(function() {
            // A previously hidden page needs a layout pass before its result y
            // and the ScrollView's maximum scroll position can be trusted.
            scroll.ensurePolished()
            dashboard.ensurePolished()
            var flick = scroll.contentItem
            flick.contentY = Math.max(0, Math.min(resultPanel.y, flick.contentHeight - flick.height))
            resultPanel.forceActiveFocus(Qt.OtherFocusReason)
        })
    }
    closeListener: function(event) {
        if (Memory.closing && Memory.safeToClose && Insights.safeToClose) {
            event.accepted = true
        } else {
            event.accepted = false
            Lifecycle.closeWindow(window)
        }
    }
    appBar: FluAppBar {
        height: 40
        minimizeText: qsTr("Minimize")
        restoreText: qsTr("Restore")
        maximizeText: qsTr("Maximize")
        closeText: qsTr("Close")
        titleVisible: false
        showDark: false
        showStayTop: false
        RowLayout {
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Image { source: "qrc:/redesign/assets/logo.png"; sourceClipRect: Qt.rect(880, 256, 1058, 935); fillMode: Image.PreserveAspectFit; Layout.preferredWidth: 22; Layout.preferredHeight: 22; Accessible.ignored: true }
            BodyText { text: window.title; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
        }
    }
    Component.onCompleted: Qt.callLater(function() {
        var area = FluTools.desktopAvailableGeometry(window)
        window.width = Math.max(window.minimumWidth, Math.min(window.width, area.width - 16))
        window.height = Math.max(window.minimumHeight, Math.min(window.height, area.height - 16))
        window.moveWindowToDesktopCenter()
        Lifecycle.windowReady(window)
    })
    RowLayout {
        objectName: "shell"
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 80
            Layout.fillHeight: true
            color: Theme.surface
            Rectangle { width: 1; height: parent.height; anchors.right: parent.right; color: Theme.border }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 16
                Image { source: "qrc:/redesign/assets/logo.png"; sourceClipRect: Qt.rect(880, 256, 1058, 935); fillMode: Image.PreserveAspectFit; Layout.preferredWidth: 40; Layout.preferredHeight: 40; Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 12; Accessible.name: qsTr("Thrashing Mitigator logo") }
                Rectangle { height: 1; color: Theme.border; Layout.fillWidth: true; Layout.topMargin: 8; Layout.bottomMargin: 8 }
                NavButton { objectName: "overviewNav"; text: qsTr("Overview"); selected: window.page === 0; onClicked: window.page = 0 }
                NavButton { objectName: "autoNav"; text: qsTr("Auto Optimize"); symbol: FluentIcons.Sync; selected: window.page === 2; onClicked: window.page = 2 }
                NavButton { objectName: "insightsNav"; text: qsTr("Insights"); symbol: FluentIcons.AreaChart; unreadCount: Insights.unreadCount; selected: window.page === 3; onClicked: window.page = 3 }
                Item { Layout.fillHeight: true }
                NavButton { objectName: "settingsNav"; text: qsTr("Settings"); symbol: FluentIcons.Settings; selected: window.page === 1; onClicked: window.page = 1 }
            }
        }
        Item {
            objectName: "mainContent"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 24
            RowLayout {
                id: header
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: Math.max(64, implicitHeight)
                spacing: 16
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    BodyText { text: window.page === 0 ? qsTr("Memory overview") : window.page === 2 ? qsTr("Auto Optimize") : window.page === 3 ? qsTr("Insights") : qsTr("Settings"); font.pixelSize: 28; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    BodyText { text: window.page === 0 ? qsTr("A clear view of your memory. A focused way to optimize it.") : window.page === 2 ? qsTr("Choose when memory optimization runs for you.") : window.page === 3 ? qsTr("Understand when memory grows and which apps change.") : qsTr("Make this workspace feel right for you."); color: Theme.muted; Layout.fillWidth: true }
                }
                StatusBadge { objectName: "liveBadge"; liveFeedback: window.page !== 3; label: window.page === 3 ? Insights.followLive ? Insights.status : qsTr("Historical") : Memory.live ? qsTr("LIVE") : qsTr("READING PAUSED"); tone: Memory.live ? "success" : "warning" }
                OutlineButton { id: themeButton; objectName: "themeToggle"; text: Theme.dark ? qsTr("Light theme") : qsTr("Dark theme"); implicitWidth: Math.max(112, contentItem.implicitWidth + 24); onClicked: Preferences.setTheme(Theme.dark ? "light" : "dark") }
            }
            ScrollView {
                id: scroll
                objectName: "mainScroll"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: header.bottom
                anchors.topMargin: 20
                anchors.bottom: parent.bottom
                clip: true
                rightPadding: 12
                contentWidth: availableWidth
                contentHeight: window.page === 0 ? dashboard.implicitHeight : window.page === 2 ? automaticPage.implicitHeight : window.page === 3 ? insightsPage.implicitHeight : settings.implicitHeight
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    id: dashboard
                    objectName: "dashboard"
                    opacity: 0
                    transform: Translate { y: overviewReveal.offset }
                    width: scroll.availableWidth
                    spacing: 16
                    RowLayout {
                        id: metrics
                        opacity: 0
                        transform: Translate { y: metricsReveal.offset }
                        Layout.fillWidth: true
                        spacing: 12
                        MetricCard { Layout.fillWidth: true; label: qsTr("TOTAL RAM"); bytes: Memory.snapshot.total; hint: qsTr("Installed physical memory") }
                        MetricCard { Layout.fillWidth: true; label: qsTr("IN USE"); bytes: Memory.snapshot.used; hint: qsTr("%1 of total memory").arg(Number(Memory.snapshot.percent).toFixed(1) + "%") }
                        MetricCard { Layout.fillWidth: true; label: qsTr("AVAILABLE"); bytes: Memory.snapshot.available; hint: qsTr("Ready for your applications"); emphasis: true }
                    }
                    Rectangle {
                        visible: !Memory.live
                        Layout.fillWidth: true
                        implicitHeight: readingError.implicitHeight + 32
                        color: Theme.warningSoft
                        radius: 12
                        BodyText { id: readingError; anchors.fill: parent; anchors.margins: 16; text: qsTr("Unable to update memory readings. Last reading: %1. Retrying every 2 seconds. %2").arg(Memory.snapshot.time).arg(Memory.monitorError); color: Theme.warning }
                    }
                    GridLayout {
                        id: charts
                        readonly property real historyWidth: window.wide ? Math.floor(Math.max(0, scroll.availableWidth - columnSpacing) * 0.64) : scroll.availableWidth
                        readonly property real panelWidth: window.wide ? scroll.availableWidth - columnSpacing - historyWidth : scroll.availableWidth
                        opacity: 0
                        transform: Translate { y: chartsReveal.offset }
                        Layout.fillWidth: true
                        columns: window.wide ? 2 : 1
                        columnSpacing: 20
                        rowSpacing: 16
                        HistoryCard {
                            Layout.fillWidth: true
                            Layout.fillHeight: false
                            Layout.alignment: Qt.AlignTop
                            Layout.minimumWidth: charts.historyWidth
                            Layout.preferredWidth: charts.historyWidth
                            Layout.maximumWidth: charts.historyWidth
                            Layout.minimumHeight: implicitHeight
                            Layout.preferredHeight: implicitHeight
                            Layout.maximumHeight: implicitHeight
                            plotHeight: Math.max(168, Math.min(360, Math.round((168 + (window.height - 740) * 0.4) / 8) * 8))
                            onViewResult: window.viewResult()
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            Layout.minimumWidth: charts.panelWidth
                            Layout.preferredWidth: charts.panelWidth
                            Layout.maximumWidth: charts.panelWidth
                            spacing: 16
                            DistributionCard { Layout.fillWidth: true }
                            OptimizeCard { Layout.fillWidth: true; onViewResult: window.viewResult() }
                        }
                    }
                    ResultCard { id: resultPanel; Layout.fillWidth: true; opacity: 0; visible: false; transform: Translate { y: resultReveal.offset } }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 8
                        BodyText { text: qsTr("LIVE MEMORY MONITOR"); font.pixelSize: Language.code === "th" ? 13 : 12; font.weight: Font.DemiBold; color: Theme.muted }
                        Item { Layout.fillWidth: true }
                        BodyText { text: qsTr("Updated %1 · Every 2 seconds").arg(Memory.snapshot.time); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
                    }
                }
                SettingsPage {
                    id: settings
                    opacity: 0
                    width: scroll.availableWidth
                    transform: Translate { y: settingsReveal.offset }
                }
                AutoOptimizePage {
                    id: automaticPage
                    opacity: 0
                    width: scroll.availableWidth
                    transform: Translate { y: autoReveal.offset }
                }
                InsightsPage { id: insightsPage; objectName: "insightsPage"; width: scroll.availableWidth; opacity: 0; transform: Translate { y: insightsReveal.offset } onDetailsRequested: function(kind, focusItem) { insightsDetails.detailKind=kind;insightsDetails.restoreFocusItem=focusItem;insightsDetails.open() } }
            }
            InsightsAppDetails { id: insightsDetails }
            ResultToast {
                id: resultToast
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                width: Math.min(resultToast.implicitWidth, 340, parent.width - 32)
                z: 900
                overviewPage: window.page === 0
                fallbackFocusItem: themeButton
                onViewResults: window.viewResult()
            }
        }
    }
    Rectangle {
        anchors.fill: parent
        color: Theme.background
        opacity: 0.97
        visible: Memory.closing
        z: 1000
        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(500, parent.width - 80)
            spacing: 20
            BusyIndicator { Layout.alignment: Qt.AlignHCenter; visible: Memory.running; Layout.preferredWidth: 32; Layout.preferredHeight: 32 }
            BodyText { text: qsTr("Finishing the current operation"); font.pixelSize: 24; font.weight: Font.DemiBold; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
            BodyText { text: qsTr("This window will close when the memory operation finishes."); color: Theme.muted; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
        }
        MouseArea { anchors.fill: parent }
    }
    MotionReveal { id: overviewReveal; targetItem: dashboard; shown: window.page === 0 }
    MotionReveal { id: settingsReveal; targetItem: settings; shown: window.page === 1 }
    MotionReveal { id: autoReveal; targetItem: automaticPage; shown: window.page === 2 }
    MotionReveal { id: insightsReveal; targetItem: insightsPage; shown: window.page === 3 }
    MotionReveal { id: metricsReveal; targetItem: metrics; shown: window.page === 0 }
    MotionReveal { id: chartsReveal; targetItem: charts; shown: window.page === 0; delay: 60 }
    MotionReveal { id: resultReveal; targetItem: resultPanel; shown: Object.keys(Memory.lastResult).length > 0; duration: Theme.resultDuration }
    Connections {
        target: Memory
        function onResultChanged() {
            if (!Object.keys(Memory.lastResult).length || Memory.closing) resultToast.dismiss(false)
            else resultToast.offer(Memory.lastResult)
        }
        function onClosingChanged() { if (Memory.closing) resultToast.dismiss(false) }
    }
}
