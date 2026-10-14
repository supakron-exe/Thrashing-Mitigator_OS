import QtQuick
import QtQuick.Layouts
import FluentUI 1.0
ColumnLayout {
    id: page
    objectName: "autoPage"
    property var draft: ({})
    property string feedback: ""
    property bool applied: false
    property bool advanced: false
    readonly property bool wide: width >= 900
    readonly property bool dirty: JSON.stringify(draft) !== JSON.stringify(Auto.configuration)
    readonly property string validationError: !draft.intervalEnabled && !draft.ramEnabled ? qsTr("Enable at least one trigger.") : draft.intervalEnabled && draft.intervalMinutes < draft.cooldownMinutes ? qsTr("The interval must be at least the cooldown.") : ""
    spacing: 20
    function load() { draft = JSON.parse(JSON.stringify(Auto.configuration)) }
    function edit(key, value) {
        var next = JSON.parse(JSON.stringify(draft)); next[key] = value; draft = next
        feedback = ""; applied = false
    }
    function duration(seconds) { return Math.floor(seconds / 60) + ":" + (seconds % 60 < 10 ? "0" : "") + seconds % 60 }
    function summary() {
        var triggers = []
        if (draft.intervalEnabled) triggers.push((draft.intervalMinutes === 1 ? qsTr("every %1 minute") : qsTr("every %1 minutes")).arg(draft.intervalMinutes))
        if (draft.ramEnabled) triggers.push(qsTr("when RAM stays at or above %1% for %2 seconds").arg(draft.ramPercent).arg(draft.sustainSeconds))
        return qsTr("%1 %2. At least %3 minutes between runs.").arg(draft.mode || "Maximum").arg(triggers.join(qsTr(" or "))).arg(draft.cooldownMinutes)
    }
    Component.onCompleted: load()
    Card {
        Layout.fillWidth: true
        implicitHeight: statusContent.implicitHeight + 48
        ColumnLayout {
            id: statusContent
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 24
            spacing: 20
            RowLayout {
                Layout.fillWidth: true; spacing: 16
                Rectangle {
                    Layout.preferredWidth: 48; Layout.preferredHeight: 48; radius: 14; color: Theme.accentSoft
                    FluIcon { anchors.centerIn: parent; iconSource: FluentIcons.Sync; iconSize: 24; iconColor: Theme.accent; Accessible.ignored: true }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    BodyText { text: qsTr("Automatic memory care"); font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    BodyText { text: Presenter.autoDetail; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                }
                FluToggleSwitch { font.family: Language.fontFamily; font.pixelSize: 14;
                    objectName: "autoEnabledToggle"
                    text: Auto.enabled ? qsTr("On") : qsTr("Off"); checked: Auto.enabled
                    textColor: Theme.text; checkColor: Theme.accent
                    disabled: Memory.closing || (page.dirty && !Auto.enabled)
                    Accessible.name: qsTr("Auto Optimize")
                    contentDescription: qsTr("Apply any changes before enabling. Disabling stops future runs.")
                    clickListener: function() { Auto.setEnabled(!Auto.enabled) }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            RowLayout {
                Layout.fillWidth: true; spacing: 20
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    BodyText { text: qsTr("STATUS"); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                    BodyText { objectName: "autoStatusText"; text: Presenter.autoStatus; font.pixelSize: 20; font.weight: Font.DemiBold; color: Auto.status === "Paused" ? Theme.error : Auto.enabled ? Theme.accent : Theme.muted; Layout.fillWidth: true }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    BodyText { text: Auto.status === "Cooldown" ? qsTr("COOLDOWN") : qsTr("NEXT TIMED RUN"); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                    BodyText { text: !Auto.enabled ? "—" : Auto.status === "Cooldown" ? page.duration(Auto.cooldownSeconds) : Auto.configuration.intervalEnabled ? page.duration(Auto.nextRunSeconds) : qsTr("RAM trigger"); font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    BodyText { text: qsTr("CURRENT RAM"); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                    BodyText { text: Number(Memory.snapshot.percent).toFixed(1) + "%"; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
                }
            }
            BodyText { text: page.dirty ? qsTr("Apply your changes before enabling Auto. Active automation keeps using the saved settings.") : Lifecycle.trayAvailable ? qsTr("Closing hides this window in Tray. Auto follows your saved On/Off state.") : qsTr("Tray is unavailable. Auto runs while this application is open."); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
        }
    }
    Card {
        visible: !!Auto.error
        Layout.fillWidth: true
        implicitHeight: errorContent.implicitHeight + 40
        border.color: Theme.error
        ColumnLayout {
            id: errorContent
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 20
            spacing: 8
            BodyText { text: Auto.status === "Paused" ? qsTr("Auto paused") : qsTr("Unable to update Auto"); color: Theme.error; font.weight: Font.DemiBold; Layout.fillWidth: true }
            BodyText { text: Presenter.autoError; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
        }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: page.wide ? 2 : 1
        columnSpacing: 20; rowSpacing: 20
        Card {
            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: page.wide ? page.width * .56 : page.width
            implicitHeight: triggers.implicitHeight + 48
            ColumnLayout {
                id: triggers
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 24
                spacing: 20
                BodyText { text: qsTr("When to optimize"); font.pixelSize: 18; font.weight: Font.DemiBold }
                BodyText { text: qsTr("Enable either trigger, or both. The first condition met starts one run."); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                RowLayout {
                    Layout.fillWidth: true
                    BodyText { text: qsTr("Time interval"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                    FluToggleSwitch { font.family: Language.fontFamily; font.pixelSize: 14; objectName: "autoIntervalToggle"; checked: !!page.draft.intervalEnabled; textColor: Theme.text; checkColor: Theme.accent; Accessible.name: qsTr("Time interval trigger"); clickListener: function() { page.edit("intervalEnabled", !page.draft.intervalEnabled) } }
                }
                AutoNumberField { Layout.fillWidth: true; enabled: !!page.draft.intervalEnabled; label: qsTr("Every (minutes)"); hint: qsTr("Counted from the end of the previous optimization."); controlName: "autoIntervalInput"; value: page.draft.intervalMinutes || 3; onEdited: function(value) { page.edit("intervalMinutes", value) } }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                RowLayout {
                    Layout.fillWidth: true
                    BodyText { text: qsTr("RAM threshold"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                    FluToggleSwitch { font.family: Language.fontFamily; font.pixelSize: 14; objectName: "autoRamToggle"; checked: !!page.draft.ramEnabled; textColor: Theme.text; checkColor: Theme.accent; Accessible.name: qsTr("RAM threshold trigger"); clickListener: function() { page.edit("ramEnabled", !page.draft.ramEnabled) } }
                }
                AutoNumberField { Layout.fillWidth: true; enabled: !!page.draft.ramEnabled; label: qsTr("RAM usage (%)"); hint: qsTr("RAM must stay above this level before Auto starts."); controlName: "autoRamInput"; from: 50; to: 95; value: page.draft.ramPercent || 75; onEdited: function(value) { page.edit("ramPercent", value) } }
                Rectangle {
                    Layout.fillWidth: true; implicitHeight: preview.implicitHeight + 32; radius: 12; color: Theme.accentSoft
                    BodyText { id: preview; objectName: "autoRuleSummary"; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; text: page.summary(); font.pixelSize: Language.code === "th" ? 13 : 12 }
                }
            }
        }
        Card {
            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: page.wide ? page.width * .44 : page.width
            implicitHeight: behavior.implicitHeight + 48
            ColumnLayout {
                id: behavior
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 24
                spacing: 20
                BodyText { text: qsTr("How it runs"); font.pixelSize: 18; font.weight: Font.DemiBold }
                BodyText { text: qsTr("Optimization mode"); font.weight: Font.DemiBold }
                FluComboBox {
                    objectName: "autoModeSelector"; Layout.fillWidth: true; Layout.preferredHeight: 40
                    model: ["Standard", "Deep", "Maximum"]
                    currentIndex: model.indexOf(page.draft.mode || "Maximum")
                    normalColor: Theme.inset; hoverColor: Theme.surface
                    font.family: Language.fontFamily; font.pixelSize: 14
                    Accessible.name: qsTr("Automatic optimization mode")
                    onActivated: page.edit("mode", currentText)
                }
                BodyText { text: page.draft.mode === "Standard" ? qsTr("Trims eligible idle background apps.") : page.draft.mode === "Deep" ? qsTr("Trims idle apps and runs system-memory steps.") : qsTr("Includes active apps and system memory. System steps may be skipped without Administrator access."); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 6
                        BodyText { text: qsTr("Start with Windows"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                        BodyText { text: qsTr("Starts quietly in Tray, using your saved Auto state."); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                    }
                    FluToggleSwitch { font.family: Language.fontFamily; font.pixelSize: 14; objectName: "autoStartupToggle"; checked: !!page.draft.startWithWindows; disabled: !Auto.startupAvailable; textColor: Theme.text; checkColor: Theme.accent; Accessible.name: qsTr("Start with Windows"); clickListener: function() { page.edit("startWithWindows", !page.draft.startWithWindows) } }
                }
                OutlineButton { objectName: "autoAdvancedButton"; text: page.advanced ? qsTr("Hide advanced settings") : qsTr("Advanced settings"); Layout.fillWidth: true; onClicked: page.advanced = !page.advanced }
                ColumnLayout {
                    visible: page.advanced; Layout.fillWidth: true; spacing: 20
                    AutoNumberField { Layout.fillWidth: true; label: qsTr("Cooldown (minutes)"); hint: qsTr("Minimum rest after every Manual or Auto run."); controlName: "autoCooldownInput"; to: 60; value: page.draft.cooldownMinutes || 3; onEdited: function(value) { page.edit("cooldownMinutes", value) } }
                    AutoNumberField { Layout.fillWidth: true; enabled: !!page.draft.ramEnabled; label: qsTr("Sustained RAM (seconds)"); hint: qsTr("After cooldown, Auto checks high RAM again before repeating."); controlName: "autoSustainInput"; from: 2; to: 120; value: page.draft.sustainSeconds || 10; onEdited: function(value) { page.edit("sustainSeconds", value) } }
                }
                OutlineButton { visible: !Lifecycle.trayAvailable; text: qsTr("Exit application"); Layout.fillWidth: true; onClicked: Lifecycle.exit() }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 16
        BodyText { text: (page.feedback ? Presenter.text(page.feedback, Language.revision) : "") || page.validationError || (page.dirty ? qsTr("Unsaved changes") : qsTr("Settings are up to date.")); color: page.validationError || (page.feedback && !page.applied) ? Theme.error : Theme.muted; font.pixelSize: Language.code === "th" ? 13 : 12; Layout.fillWidth: true }
        OutlineButton { objectName: "autoDiscardButton"; text: qsTr("Discard"); disabled: !page.dirty; onClicked: { page.load(); page.feedback = "" } }
        ActionButton { objectName: "autoApplyButton"; text: qsTr("Apply changes"); disabled: !page.dirty || !!page.validationError || Memory.closing; onClicked: { page.applied = Auto.applyConfiguration(page.draft); page.feedback = page.applied ? "Changes saved." : Auto.error; if (page.applied) page.load() } }
    }
    Card {
        Layout.fillWidth: true; implicitHeight: activity.implicitHeight + 48
        ColumnLayout {
            id: activity
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 24; spacing: 16
            RowLayout {
                Layout.fillWidth: true
                BodyText { text: qsTr("Recent automatic runs"); font.pixelSize: 18; font.weight: Font.DemiBold; Layout.fillWidth: true }
                BodyText { text: qsTr("This session"); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
            }
            BodyText { visible: !Auto.recentActivity.length; text: qsTr("Your automatic runs will appear here. Enable Auto when you are ready."); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
            Repeater {
                model: Presenter.recentActivity
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true; spacing: 6
                    Rectangle { height: 1; Layout.fillWidth: true; color: Theme.border }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 16
                        BodyText { text: modelData.time; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
                        BodyText { text: modelData.reason + " · " + modelData.mode; Layout.fillWidth: true; font.weight: Font.DemiBold }
                        BodyText { text: modelData.gain; color: Theme.tone(modelData.tone); font.weight: Font.DemiBold }
                    }
                    BodyText { text: modelData.title + " · " + modelData.duration; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                }
            }
        }
    }
}
