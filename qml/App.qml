import QtQuick
import FluentUI 1.0
FluLauncher {
    id: app
    function applyAppearance() {
        FluTheme.darkMode = Preferences.theme === "dark" ? FluThemeType.Dark : FluThemeType.Light
        FluTheme.accentColor = FluColors.createAccentColor(Theme.accent)
        FluTheme.animationEnabled = Preferences.animations
    }
    Connections { target: Preferences; function onChanged() { app.applyAppearance() } }
    Component.onCompleted: {
        FluApp.init(app, Qt.locale("en_US"))
        Language.initialize()
        FluApp.windowIcon = "qrc:/redesign/assets/logo.png"
        FluApp.useSystemAppBar = false
        applyAppearance()
        FluRouter.routes = {"/": "qrc:/redesign/qml/MainWindow.qml"}
        FluRouter.navigate("/")
    }
}
