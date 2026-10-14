import QtQuick
import QtQuick.Window
import FluentUI 1.0
Item {
    id: control
    implicitWidth: 20
    implicitHeight: 20
    readonly property bool animate: Theme.motion && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized
    Accessible.name: "Operation in progress"
    FluProgressRing { anchors.fill: parent; visible: control.animate; strokeWidth: 2; color: Theme.accent }
    FluIcon { anchors.centerIn: parent; visible: !control.animate; iconSource: FluentIcons.Info; iconSize: Math.min(control.width, 20); iconColor: Theme.accent; Accessible.ignored: true }
}
