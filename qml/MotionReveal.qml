import QtQuick
import QtQuick.Window
// Animates paint properties only; the target keeps its layout geometry.
Item {
    id: effect
    visible: false
    property Item targetItem
    property bool shown: true
    property int delay: 0
    property int duration: Theme.pageDuration
    property real offset: 12
    readonly property var ownerWindow: Window.window
    function settle() {
        wait.stop(); reveal.stop()
        if (!targetItem) return
        offset = shown ? 0 : 12
        targetItem.opacity = shown ? 1 : 0
        targetItem.visible = shown
    }
    function update() {
        wait.stop(); reveal.stop()
        if (!targetItem) return
        targetItem.enabled = shown
        if (!Theme.motion || !ownerWindow || !ownerWindow.active || ownerWindow.visibility === Window.Minimized) { settle(); return }
        if (shown) { targetItem.visible = true; offset = 12; targetItem.opacity = 0; wait.start() }
        else { offset = 0; reveal.start() }
    }
    onShownChanged: update()
    Component.onCompleted: Qt.callLater(update)
    Timer { id: wait; interval: effect.delay; onTriggered: reveal.start() }
    ParallelAnimation {
        id: reveal
        NumberAnimation { target: effect.targetItem; property: "opacity"; to: effect.shown ? 1 : 0; duration: effect.duration; easing.type: Easing.OutCubic }
        NumberAnimation { target: effect; property: "offset"; to: effect.shown ? 0 : 12; duration: effect.duration; easing.type: Easing.OutCubic }
        onFinished: { if (effect.targetItem && !effect.shown) effect.targetItem.visible = false }
    }
    Connections { target: Preferences; function onChanged() { if (!Theme.motion) effect.settle() } }
    Connections { target: effect.ownerWindow; function onActiveChanged() { if (!effect.ownerWindow.active) effect.settle() } function onVisibilityChanged() { if (effect.ownerWindow.visibility === Window.Minimized) effect.settle() } }
}
