import QtQuick
import QtQuick.Window
import FluentUI 1.0
FluFilledButton {
    id: control
    implicitHeight: 44
    font.family: Language.fontFamily
    font.pixelSize: 14
    font.weight: Font.DemiBold
    scale: pressed && Theme.motion && Window.window && Window.window.active ? 0.98 : 1
    Behavior on scale { enabled: Theme.motion; NumberAnimation { duration: Theme.pressDuration; easing.type: Easing.OutCubic } }
    normalColor: Theme.accent
    textColor: disabled ? Theme.muted : Theme.accentText
    contentItem: BodyText {
        text: control.text
        font: control.font
        color: control.disabled ? Theme.muted : Theme.accentText
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 10
        color: control.disabled ? Theme.inset : control.pressed ? Qt.darker(Theme.accent, 1.16) : control.hovered ? Qt.lighter(Theme.accent, 1.08) : Theme.accent
        Behavior on color { ColorAnimation { duration: Theme.hoverDuration } }
        Rectangle { anchors.fill: parent; anchors.margins: -3; color: "transparent"; radius: 12; border.color: Theme.accent; border.width: 2; visible: control.visualFocus }
    }
}
