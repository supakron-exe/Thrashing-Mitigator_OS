pragma Singleton
import QtQuick
QtObject {
    readonly property bool dark: Preferences.theme === "dark"
    readonly property bool motion: Preferences.animations
    readonly property int hoverDuration: motion ? 140 : 0
    readonly property int pageDuration: 240
    readonly property int resultDuration: 280
    readonly property int pressDuration: 90
    readonly property int detailsDuration: 160
    readonly property color background: dark ? "#11151D" : "#F5F7FB"
    readonly property color surface: dark ? "#1C2330" : "#FFFFFF"
    readonly property color inset: dark ? "#151C27" : "#F8FAFD"
    readonly property color text: dark ? "#F3F6FC" : "#172033"
    readonly property color muted: dark ? "#A5B0C0" : "#586579"
    readonly property color border: dark ? "#303A49" : "#E0E5EE"
    readonly property color accent: dark ? "#78A9FF" : "#1765D1"
    readonly property color accentText: dark ? "#0B1220" : "#FFFFFF"
    readonly property color accentSoft: dark ? "#253751" : "#EAF2FF"
    readonly property color success: dark ? "#77D9AD" : "#16714C"
    readonly property color successSoft: dark ? "#20372F" : "#EAF7EF"
    readonly property color warning: dark ? "#F0C579" : "#8A5800"
    readonly property color warningSoft: dark ? "#3B3021" : "#FFF5DF"
    readonly property color error: dark ? "#FF9F9F" : "#B42332"
    readonly property color errorSoft: dark ? "#3F2831" : "#FFF0F1"
    function tone(name) { return name === "error" ? error : name === "warning" ? warning : success }
    function toneSurface(name) { return name === "error" ? errorSoft : name === "warning" ? warningSoft : successSoft }
    function gb(bytes) { return (Number(bytes || 0) / Math.pow(1024, 3)).toFixed(2) }
}
