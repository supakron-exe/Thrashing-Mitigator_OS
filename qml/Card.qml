import QtQuick
Rectangle {
    color: Theme.surface
    radius: 16
    border.color: Theme.border
    border.width: 1
    Behavior on color { ColorAnimation { duration: Theme.motion ? 180 : 0 } }
}
