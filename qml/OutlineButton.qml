import QtQuick
import QtQuick.Window
import FluentUI 1.0
FluButton {
    id: control
    implicitHeight: 40
    textColor: Theme.text
    font.family: Language.fontFamily
    font.pixelSize: 14
    scale: pressed && Theme.motion && Window.window && Window.window.active ? 0.98 : 1
    Behavior on scale { enabled: Theme.motion; NumberAnimation { duration: Theme.pressDuration; easing.type: Easing.OutCubic } }
    background: Rectangle {
        radius: 10
        color: control.pressed ? Theme.accentSoft : control.hovered ? Theme.inset : Theme.surface
        border.color: control.visualFocus ? Theme.accent : Theme.border
        border.width: control.visualFocus ? 2 : 1
        Behavior on color { ColorAnimation { duration: Theme.hoverDuration } }
    }
}
