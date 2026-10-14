import QtQuick
import FluentUI 1.0
FluText {
    font.family: Language.fontFamily
    font.pixelSize: 14
    color: Theme.text
    wrapMode: Text.WordWrap
    lineHeight: Language.code === "th" ? 1.3 : 1.18
}
