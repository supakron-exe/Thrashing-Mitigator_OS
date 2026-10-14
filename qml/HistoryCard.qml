import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI 1.0
Card {
    id: card
    property real plotHeight: 168
    implicitHeight: content.implicitHeight + 48
    property var samples: Memory.history
    property var events: Presenter.events
    property real selectedTimestamp: 0
    property bool pinned: false
    property int selectedEventId: -1
    signal viewResult()
    readonly property int hoveredIndex: {
        for (var i = 0; i < samples.length; i++) if (samples[i].timestamp === selectedTimestamp) return i
        return -1
    }
    readonly property var selectedEvent: {
        for (var i = 0; i < events.length; i++) if (events[i].id === selectedEventId) return events[i]
        return null
    }
    function nearestSample(x) {
        if (!samples.length) return -1
        var timestamp = samples[samples.length - 1].timestamp - 120 + x / Math.max(1, plot.width - 6) * 120
        var best = 0
        for (var i = 1; i < samples.length; i++) if (Math.abs(samples[i].timestamp - timestamp) < Math.abs(samples[best].timestamp - timestamp)) best = i
        return best
    }
    function chartX(timestamp) {
        if (!samples.length) return 0
        return Math.max(0, Math.min(plot.width - 6, (timestamp - samples[samples.length - 1].timestamp + 120) / 120 * (plot.width - 6)))
    }
    function selectAt(x) {
        var index = nearestSample(x)
        if (index < 0) return
        selectedTimestamp = samples[index].timestamp
        selectEventAt(x)
    }
    function selectEventAt(x) {
        selectedEventId = -1
        for (var i = events.length - 1; i >= 0; i--) {
            if (Math.abs(chartX(events[i].startedAt) - x) < 9 || (events[i].finishedAt && Math.abs(chartX(events[i].finishedAt) - x) < 9)) { selectedEventId = events[i].id; break }
        }
    }
    function selectIndex(index) {
        if (!samples.length) return
        pinned = true; selectedEventId = -1
        selectedTimestamp = samples[Math.max(0, Math.min(samples.length - 1, index))].timestamp
        selectEventAt(chartX(selectedTimestamp))
    }
    function timeOf(timestamp) { return new Date(timestamp * 1000).toLocaleTimeString(Qt.locale("en_US"), "HH:mm:ss") }
    onSamplesChanged: {
        if (selectedTimestamp && hoveredIndex < 0) { selectedTimestamp = 0; pinned = false; selectedEventId = -1 }
        plot.requestPaint()
    }
    onEventsChanged: plot.requestPaint()
    onSelectedTimestampChanged: plot.requestPaint()
    onSelectedEventIdChanged: plot.requestPaint()
    Connections { target: Preferences; function onChanged() { plot.requestPaint() } }
    function timeLabel(offset) {
        if (!card.samples.length) return "—"
        var d = new Date((card.samples[card.samples.length - 1].timestamp - offset) * 1000)
        return d.toLocaleTimeString(Qt.locale("en_US"), "HH:mm:ss")
    }
    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                BodyText {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    text: qsTr("RAM usage history")
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                StatusBadge {
                    Layout.fillWidth: false
                    Layout.minimumWidth: implicitWidth
                    Layout.maximumWidth: implicitWidth
                    Layout.alignment: Qt.AlignVCenter
                    label: Presenter.text(Memory.snapshot.pressure, Language.revision)
                    tone: Memory.snapshot.percent >= 85 ? "error" : Memory.snapshot.percent >= 75 ? "warning" : "success"
                }
            }
            BodyText {
                Layout.fillWidth: true
                text: qsTr("The last 2 minutes of memory activity")
                font.pixelSize: Language.code === "th" ? 13 : 12
                color: Theme.muted
            }
        }
        RowLayout {
            spacing: 10
            BodyText { text: Number(Memory.snapshot.percent).toFixed(1) + "%"; font.pixelSize: 36; font.weight: Font.DemiBold }
            BodyText { text: qsTr("in use right now"); color: Theme.muted; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 7 }
            Item { Layout.fillWidth: true }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: card.plotHeight
            Layout.preferredHeight: card.plotHeight
            Layout.maximumHeight: card.plotHeight
            spacing: 12
            Item {
                Layout.preferredWidth: 32
                Layout.fillHeight: true
                Repeater {
                    model: [100, 75, 50, 25, 0]
                    BodyText { required property var modelData; required property int index; text: modelData + "%"; font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; y: index * (parent.height - height) / 4; width: parent.width; horizontalAlignment: Text.AlignRight }
                }
            }
            Canvas {
                id: plot
                objectName: "historyCanvas"
                activeFocusOnTab: true
                Accessible.role: Accessible.Graphic
                Accessible.name: qsTr("RAM usage history")
                Accessible.description: qsTr("Use Left and Right to inspect readings, Home and End for first and latest, Escape to return to live.") + " " + (card.hoveredIndex >= 0 ? qsTr("%1% at %2").arg(Number(card.samples[card.hoveredIndex].percent).toFixed(1)).arg(card.timeOf(card.selectedTimestamp)) : qsTr("%1% in use").arg(Number(Memory.snapshot.percent).toFixed(1))) + (card.selectedEvent ? ". " + qsTr("%1 started %2. %3").arg(card.selectedEvent.mode).arg(card.timeOf(card.selectedEvent.startedAt)).arg(card.selectedEvent.title) : "")
                Layout.fillWidth: true
                Layout.fillHeight: true
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var top = 8, bottom = height - 8, chartHeight = bottom - top
                    ctx.lineWidth = 1
                    ctx.strokeStyle = Theme.border
                    for (var i = 0; i < 5; i++) {
                        var y = top + i * chartHeight / 4
                        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke()
                    }
                    if (!card.samples.length) return
                    var latest = card.samples[card.samples.length - 1].timestamp
                    // Windows mark when operations ran; they do not attribute RAM movement.
                    for (var e = 0; e < card.events.length; e++) {
                        var event = card.events[e]
                        var end = event.finishedAt || latest
                        if (end < latest - 120 || event.startedAt > latest) continue
                        var left = card.chartX(event.startedAt), right = card.chartX(end)
                        ctx.fillStyle = Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.dark ? 0.10 : 0.06)
                        ctx.fillRect(left, top, Math.max(1, right - left), chartHeight)
                        ctx.strokeStyle = Theme.muted; ctx.lineWidth = 1; ctx.setLineDash([3, 4])
                        ctx.beginPath(); ctx.moveTo(left, top); ctx.lineTo(left, bottom); ctx.stroke()
                        if (event.finishedAt) { ctx.beginPath(); ctx.moveTo(right, top); ctx.lineTo(right, bottom); ctx.stroke() }
                        ctx.setLineDash([])
                        ctx.fillStyle = event.finishedAt ? Theme.tone(event.tone) : Theme.accent
                        ctx.beginPath(); ctx.arc(event.finishedAt ? right : left, top + 2, 3, 0, Math.PI * 2); ctx.fill()
                    }
                    var points = []
                    for (var j = 0; j < card.samples.length; j++) {
                        points.push({x: Math.max(0, (card.samples[j].timestamp - latest + 120) / 120 * (width - 6)), y: bottom - card.samples[j].percent / 100 * chartHeight})
                    }
                    var gradient = ctx.createLinearGradient(0, top, 0, bottom)
                    gradient.addColorStop(0, Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.dark ? 0.24 : 0.18))
                    gradient.addColorStop(1, Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.01))
                    ctx.beginPath(); ctx.moveTo(points[0].x, bottom)
                    for (var k = 0; k < points.length; k++) ctx.lineTo(points[k].x, points[k].y)
                    ctx.lineTo(points[points.length - 1].x, bottom); ctx.closePath(); ctx.fillStyle = gradient; ctx.fill()
                    ctx.beginPath(); ctx.moveTo(points[0].x, points[0].y)
                    for (var n = 1; n < points.length; n++) ctx.lineTo(points[n].x, points[n].y)
                    ctx.strokeStyle = Theme.accent; ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.stroke()
                    var chosen = card.hoveredIndex >= 0 ? Math.min(card.hoveredIndex, points.length - 1) : points.length - 1
                    var p = points[chosen]
                    if (card.hoveredIndex >= 0) {
                        ctx.strokeStyle = Theme.muted; ctx.lineWidth = 1
                        ctx.beginPath(); ctx.moveTo(p.x, top); ctx.lineTo(p.x, bottom); ctx.stroke()
                    }
                    ctx.fillStyle = Theme.accent; ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill()
                }
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton
                    onPositionChanged: function(mouse) {
                        if (!card.pinned) card.selectAt(mouse.x)
                    }
                    onClicked: function(mouse) { plot.forceActiveFocus(Qt.MouseFocusReason); card.selectAt(mouse.x); card.pinned = true }
                    onExited: { if (!card.pinned) { card.selectedTimestamp = 0; card.selectedEventId = -1 } }
                }
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Left) card.selectIndex(card.hoveredIndex < 0 ? card.samples.length - 1 : card.hoveredIndex - 1)
                    else if (event.key === Qt.Key_Right) card.selectIndex(card.hoveredIndex < 0 ? card.samples.length - 1 : card.hoveredIndex + 1)
                    else if (event.key === Qt.Key_Home) card.selectIndex(0)
                    else if (event.key === Qt.Key_End) card.selectIndex(card.samples.length - 1)
                    else if (event.key === Qt.Key_Escape) { card.pinned = false; card.selectedTimestamp = 0; card.selectedEventId = -1 }
                    else return
                    event.accepted = true
                }
                Rectangle { anchors.fill: parent; anchors.margins: -4; radius: 4; color: "transparent"; border.color: Theme.accent; border.width: 2; visible: plot.activeFocus; Accessible.ignored: true }
                Rectangle {
                    visible: card.hoveredIndex >= 0 && card.samples.length > 0
                    x: Math.max(0, Math.min(card.chartX(card.selectedTimestamp) - width / 2, plot.width - width))
                    y: 12
                    width: Math.min(plot.width, Math.max(190, hoverText.implicitWidth + 24))
                    height: hoverText.implicitHeight + 24
                    radius: 8
                    color: Theme.surface
                    border.color: Theme.border
                    BodyText {
                        id: hoverText; anchors.centerIn: parent; width: parent.width - 24; font.pixelSize: Language.code === "th" ? 13 : 12
                        text: {
                            if (card.hoveredIndex < 0) return ""
                            var reading = Number(card.samples[card.hoveredIndex].percent).toFixed(1) + "%  ·  " + card.timeOf(card.selectedTimestamp)
                            var event = card.selectedEvent
                            if (!event) return reading
                            return reading + "\n" + (event.source === "auto" ? qsTr("Auto · ") : "") + event.mode + " · " + card.timeOf(event.startedAt) + (event.finishedAt ? "–" + card.timeOf(event.finishedAt) : qsTr(" · Running")) + "\n" + event.title + (event.hasMeasurements ? " · " + event.gain : "")
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 44
            BodyText { text: card.timeLabel(120); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
            Item { Layout.fillWidth: true }
            BodyText { text: card.timeLabel(60); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
            Item { Layout.fillWidth: true }
            BodyText { text: qsTr("Now"); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
        }
        Rectangle { height: 1; color: Theme.border; Layout.fillWidth: true }
        RowLayout {
            spacing: 8
            Rectangle { width: 8; height: 8; radius: 4; color: Theme.accent; Accessible.ignored: true }
            BodyText { text: qsTr("Memory in use"); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
            Item { Layout.fillWidth: true }
            BodyText { text: qsTr("%1 / 60 readings · 2s interval").arg(card.samples.length); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted }
        }
        Item {
            Layout.fillWidth: true
            implicitHeight: 32
            Layout.minimumHeight: 32
            Layout.maximumHeight: 32
            RowLayout {
                anchors.fill: parent
                visible: card.events.length > 0
                spacing: 8
                BodyText { text: qsTr("Shaded area: optimization window"); font.pixelSize: Language.code === "th" ? 13 : 12; color: Theme.muted; Layout.fillWidth: true }
                OutlineButton { objectName: "chartResultButton"; text: qsTr("View result"); visible: Object.keys(Memory.lastResult).length > 0; implicitHeight: 32; onClicked: card.viewResult() }
            }
        }
    }
}
