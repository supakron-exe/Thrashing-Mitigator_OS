import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import FluentUI 1.0

FocusScope {
    id: toast
    objectName: "resultToast"
    signal viewResults()
    property bool overviewPage: true
    property Item fallbackFocusItem
    property var previousFocusItem: null
    property var outcome: ({})
    property int lastOperationId: -1
    property bool opened: false
    property bool pending: false
    property int displayDuration: 6000
    property int remainingMs: displayDuration
    property real deadline: 0
    property real slide: 8
    readonly property var ownerWindow: Window.window
    readonly property bool foreground: ownerWindow && ownerWindow.active && ownerWindow.visibility !== Window.Minimized
    readonly property bool held: pointer.hovered || activeFocus
    readonly property string tone: outcome.tone || "success"
    readonly property var displayOutcome: Presenter.result(outcome, Language.revision)
    readonly property string message: (displayOutcome.title || qsTr("Optimization finished")) + ". " + (tone === "error" ? (overviewPage ? qsTr("Details are ready below.") : qsTr("Details are ready on Overview.")) : (overviewPage ? qsTr("Results are ready below.") : qsTr("Results are ready on Overview.")))

    implicitWidth: statusText.implicitWidth + 16 + 44 + 28 + 24 + 16
    implicitHeight: 44
    height: implicitHeight
    opacity: 0
    visible: opacity > 0
    enabled: opened
    transform: Translate { y: toast.slide }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: message
    Keys.onEscapePressed: dismiss(true)

    function pauseCountdown() {
        if (expiry.running) remainingMs = Math.max(0, deadline - Date.now())
        expiry.stop()
    }
    function resumeCountdown() {
        if (!opened || !foreground || held) return
        if (remainingMs <= 0) { dismiss(false); return }
        deadline = Date.now() + remainingMs
        expiry.interval = Math.max(1, remainingMs)
        expiry.start()
    }
    function settle() {
        reveal.stop()
        opacity = opened ? 1 : 0
        slide = opened ? 0 : 8
    }
    function animateVisibility() {
        reveal.stop()
        if (Theme.motion && foreground) reveal.start()
        else settle()
    }
    function present() {
        if (!pending || !foreground) return
        pending = false
        var item = ownerWindow.activeFocusItem
        if (item && !activeFocus) previousFocusItem = item
        opened = true
        animateVisibility()
        resumeCountdown()
    }
    function offer(result) {
        var id = Number(result.operationId || 0)
        if (!id || id === lastOperationId) return
        dismiss(false)
        lastOperationId = id
        outcome = result
        remainingMs = displayDuration
        pending = true
        present()
    }
    function dismiss(restoreFocus) {
        expiry.stop()
        pending = false
        var ownedFocus = activeFocus
        opened = false
        animateVisibility()
        if (restoreFocus && ownedFocus) {
            var item = previousFocusItem && previousFocusItem.visible && previousFocusItem.enabled ? previousFocusItem : fallbackFocusItem
            if (item) item.forceActiveFocus(Qt.OtherFocusReason)
        }
    }
    onHeldChanged: { if (held) pauseCountdown(); else resumeCountdown() }
    onForegroundChanged: {
        if (!foreground && opened) {
            pauseCountdown()
            opened = false
            pending = remainingMs > 0
            settle()
        } else if (foreground) present()
    }
    Connections { target: Preferences; function onChanged() { if (!Theme.motion) toast.settle() } }
    Timer { id: expiry; repeat: false; onTriggered: toast.dismiss(false) }
    ParallelAnimation {
        id: reveal
        NumberAnimation { target: toast; property: "opacity"; to: toast.opened ? 1 : 0; duration: 180; easing.type: Easing.OutCubic }
        NumberAnimation { target: toast; property: "slide"; to: toast.opened ? 0 : 8; duration: 180; easing.type: Easing.OutCubic }
    }
    HoverHandler { id: pointer; objectName: "toastHover" }
    Rectangle {
        anchors.fill: parent
        radius: 10
        color: Theme.toneSurface(toast.tone)
        border.color: Qt.rgba(Theme.tone(toast.tone).r, Theme.tone(toast.tone).g, Theme.tone(toast.tone).b, 0.3)
        FluShadow { radius: 10; elevation: 2 }
        // Shield only the popup's rectangle; the rest of the app stays usable.
        MouseArea { objectName: "toastShield"; anchors.fill: parent; acceptedButtons: Qt.AllButtons }
    }
    RowLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 8
        spacing: 8
        FluIcon { iconSource: toast.tone === "error" ? FluentIcons.ErrorBadge : toast.tone === "warning" ? FluentIcons.Info : FluentIcons.CheckMark; iconSize: 16; iconColor: Theme.tone(toast.tone); Accessible.ignored: true }
        BodyText {
            id: statusText
            objectName: "resultToastMessage"
            text: toast.displayOutcome.title || qsTr("Results ready")
            font.pixelSize: 13
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
            color: Theme.tone(toast.tone)
            Layout.fillWidth: true
            Accessible.ignored: true
        }
        OutlineButton {
            objectName: "toastViewResults"
            id: viewButton
            text: qsTr("View")
            Accessible.name: qsTr("View optimization results")
            font.pixelSize: 13
            implicitWidth: 44
            implicitHeight: 28
            horizontalPadding: 6
            textColor: Theme.tone(toast.tone)
            background: Rectangle { radius: 6; color: viewButton.hovered || viewButton.pressed ? Theme.surface : "transparent"; border.width: viewButton.visualFocus ? 2 : 0; border.color: Theme.accent }
            onClicked: { toast.dismiss(false); toast.viewResults() }
        }
        OutlineButton {
            objectName: "toastClose"
            id: closeButton
            implicitWidth: 28
            implicitHeight: 28
            horizontalPadding: 8
            Accessible.name: qsTr("Dismiss result notification")
            contentItem: FluIcon { iconSource: FluentIcons.ChromeClose; iconSize: 12; iconColor: Theme.tone(toast.tone); Accessible.ignored: true }
            background: Rectangle { radius: 6; color: closeButton.hovered || closeButton.pressed ? Theme.surface : "transparent"; border.width: closeButton.visualFocus ? 2 : 0; border.color: Theme.accent }
            onClicked: toast.dismiss(true)
        }
    }
    ToolTip.visible: statusText.truncated && (pointer.hovered || toast.activeFocus)
    ToolTip.delay: 400
    ToolTip.text: toast.message
}
