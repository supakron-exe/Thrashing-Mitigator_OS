import QtQuick
import QtQuick.Layouts
import FluentUI 1.0
ColumnLayout {
    id: field
    property string label
    property string hint
    property string controlName
    property int value: 3
    property int from: 1
    property int to: 1440
    signal edited(int value)
    spacing: 6
    RowLayout {
        Layout.fillWidth: true
        spacing: 16
        BodyText { text: field.label; Layout.fillWidth: true; font.weight: Font.DemiBold }
        FluSpinBox {
            id: number
            objectName: field.controlName
            Layout.preferredWidth: 136
            Layout.preferredHeight: 40
            from: field.from; to: field.to; value: field.value
            editable: true
            locale: Qt.locale("en_US")
            font.family: Language.fontFamily; font.pixelSize: 14
            normalColor: Theme.inset; hoverColor: Theme.accentSoft; pressedColor: Theme.accentSoft
            Accessible.name: field.label
            onValueModified: field.edited(value)
            contentItem: TextInput {
                text: number.displayText
                font: number.font
                color: Theme.text
                selectionColor: Theme.accent
                selectedTextColor: Theme.accentText
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                validator: number.validator
                readOnly: !number.editable
                inputMethodHints: Qt.ImhDigitsOnly
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: Theme.accent; visible: parent.activeFocus }
            }
        }
    }
    BodyText { text: field.hint; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
}
