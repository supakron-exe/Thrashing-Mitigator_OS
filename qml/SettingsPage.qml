import QtQuick
import QtQuick.Layouts
import FluentUI 1.0
ColumnLayout {
    spacing: 20
    Card {
        Layout.fillWidth: true
        implicitHeight: insightsData.implicitHeight + 48
        ColumnLayout {
            id: insightsData
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 24; spacing: 14
            BodyText { text: qsTr("Insights data"); font.pixelSize: 18; font.weight: Font.DemiBold }
            BodyText { text: qsTr("History stays on this computer for 24 hours. Tracking continues in Tray."); color: Theme.muted; Layout.fillWidth: true }
            BodyText { text: qsTr("Storage: %1 · Last saved: %2").arg(Insights.storageState.sizeLabel).arg(Insights.storageState.savedLabel); Layout.fillWidth: true }
            BodyText { visible: !!Insights.storageState.recovery; text: qsTr("Unreadable history was preserved as a backup: %1").arg(Insights.storageState.recovery || ""); color: Theme.warning; Layout.fillWidth: true }
            BodyText { visible: !!Insights.storageState.error; text: qsTr("History could not be saved. Live tracking continues. %1").arg(Insights.storageState.error || ""); color: Theme.warning; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                OutlineButton { text: qsTr("Clear history"); onClicked: clearInsights.open() }
                OutlineButton { visible: !!Insights.storageState.error; text: qsTr("Retry saving"); onClicked: Insights.retryStorage() }
            }
        }
    }
    FluContentDialog {
        id: clearInsights
        title: qsTr("Clear Insights history?")
        message: qsTr("This removes the collected readings and events from this computer. Tracking will start a new history.")
        negativeText: qsTr("Cancel")
        positiveText: qsTr("Clear history")
        onPositiveClicked: Insights.clearHistory()
    }
    Card {
        Layout.fillWidth: true
        implicitHeight: appearance.implicitHeight + 48
        ColumnLayout {
            id: appearance
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 24
            spacing: 24
            BodyText { text: qsTr("Appearance"); font.pixelSize: 18; font.weight: Font.DemiBold }
            Rectangle { height: 1; color: Theme.border; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true; spacing: 24
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    BodyText { text: qsTr("Language"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                    BodyText { text: qsTr("Choose your display language. Changes apply immediately."); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
                }
                FluComboBox {
                    objectName: "languageSelector"
                    Layout.preferredWidth: 164; Layout.preferredHeight: 40
                    model: ["English", "ไทย"]
                    currentIndex: Language.code === "th" ? 1 : 0
                    font.family: "Leelawadee UI"; font.pixelSize: 14
                    normalColor: Theme.inset; hoverColor: Theme.surface
                    Accessible.name: qsTr("Language")
                    onActivated: {
                        Language.setLanguage(currentIndex === 1 ? "th" : "en")
                        currentIndex = Qt.binding(function() { return Language.code === "th" ? 1 : 0 })
                    }
                }
            }
            BodyText { objectName: "languageError"; visible: !!Language.error; text: Language.error; color: Theme.error; Layout.fillWidth: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: 24
                ColumnLayout { Layout.fillWidth: true; spacing: 6; BodyText { text: qsTr("Color theme"); font.weight: Font.DemiBold } BodyText { text: qsTr("Choose the workspace that suits your surroundings."); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true } }
                OutlineButton { objectName: "lightThemeButton"; text: qsTr("Light"); textColor: !Theme.dark ? Theme.accent : Theme.text; onClicked: Preferences.setTheme("light") }
                OutlineButton { objectName: "darkThemeButton"; text: qsTr("Dark"); textColor: Theme.dark ? Theme.accent : Theme.text; onClicked: Preferences.setTheme("dark") }
            }
            Rectangle { height: 1; color: Theme.border; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 24
                ColumnLayout { Layout.fillWidth: true; spacing: 6; BodyText { text: qsTr("Interface animations"); font.weight: Font.DemiBold } BodyText { text: qsTr("Subtle feedback for buttons, cards and page transitions."); color: Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true } }
                FluToggleSwitch { font.family: Language.fontFamily; font.pixelSize: 14; objectName: "motionToggle"; text: Preferences.animations ? qsTr("On") : qsTr("Off"); textColor: Theme.text; checked: Preferences.animations; checkColor: Theme.accent; clickListener: function() { Preferences.setAnimations(!Preferences.animations) }; Accessible.name: qsTr("Interface animations") }
            }
        }
    }
    Card {
        Layout.fillWidth: true
        implicitHeight: about.implicitHeight + 48
        ColumnLayout {
            id: about
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 24
            spacing: 12
            BodyText { text: qsTr("About this workspace"); font.pixelSize: 18; font.weight: Font.DemiBold }
            BodyText { text: "Thrashing Mitigator"; font.weight: Font.DemiBold }
            BodyText { text: qsTr("Live physical-memory monitoring and on-demand optimization."); color: Theme.muted; Layout.fillWidth: true }
            BodyText { text: qsTr("Readings update every 2 seconds. Memory status reflects RAM usage: Normal below 75%, Warning from 75%, and High RAM usage from 85%."); color: Theme.muted; Layout.fillWidth: true }
            BodyText { text: qsTr("Standard optimizes idle background apps. Deep adds system-memory steps. Maximum also includes active apps. System-memory steps require Administrator access."); color: Theme.muted; Layout.fillWidth: true }
        }
    }
}
