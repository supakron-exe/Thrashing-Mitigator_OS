import QtQuick
import QtQuick.Controls
import FluentUI 1.0
OutlineButton {
    id: control
    property int symbol: FluentIcons.ViewDashboard
    property bool selected: false
    property int unreadCount: 0
    width: 48
    height: 48
    Accessible.name: text
    Accessible.description: (selected ? qsTr("Current page") : qsTr("Open %1").arg(text)) + (unreadCount > 0 ? " · " + qsTr("New events") : "")
    Accessible.checkable: true
    Accessible.checked: selected
    contentItem: FluIcon { iconSource: control.symbol; iconSize: 22; iconColor: control.selected ? Theme.accent : Theme.muted; Accessible.ignored: true }
    background: Rectangle {
        radius: 12
        color: control.selected || control.pressed ? Theme.accentSoft : control.hovered ? Theme.inset : "transparent"
        border.width: control.visualFocus ? 2 : 0
        border.color: Theme.accent
        Behavior on color { ColorAnimation { duration: Theme.hoverDuration } }
        Rectangle { width: 3; height: 20; radius: 2; color: Theme.accent; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; visible: control.selected }
    }
    Rectangle { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 7; width: 7; height: 7; radius: 4; color: Theme.warning; visible: control.unreadCount > 0; Accessible.ignored: true }
    ToolTip.visible: hovered
    ToolTip.delay: 500
    ToolTip.text: text
}
