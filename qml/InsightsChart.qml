import QtQuick
import QtQuick.Controls
Item {
    id: chart
    property var points: []
    property var events: []
    property bool memoryScale: false
    property bool filled: false
    property string scaleKey: ""
    property real memoryCeiling: 1048576
    property int cursorIndex: -1
    readonly property real startTime: points.length ? points[0].timestamp : 0
    readonly property real endTime: points.length ? points[points.length-1].timestamp : 1
    readonly property real ceiling: memoryScale ? memoryCeiling : 100
    signal eventSelected(string eventId)
    implicitHeight: 240
    activeFocusOnTab: true
    Accessible.role: Accessible.Chart
    Accessible.name: memoryScale ? qsTr("App memory history") : qsTr("System RAM history")
    Accessible.description: qsTr("Use arrow keys to inspect readings. Events are also available in the event list.")
    function repaint() { if (visible) canvas.requestPaint() }
    function stamp(value) { return new Date(value*1000).toLocaleTimeString(Qt.locale(), "HH:mm:ss") }
    function xAt(t) { return 48 + (width-64)*(t-startTime)/Math.max(1,endTime-startTime) }
    function nearest(x) {
        if (!points.length) return -1
        var target=startTime+Math.max(0,Math.min(1,(x-48)/(width-64)))*(endTime-startTime)
        var best=0
        for(var i=1;i<points.length;i++) if(Math.abs(points[i].timestamp-target)<Math.abs(points[best].timestamp-target)) best=i
        return best
    }
    function updateCeiling(reset) {
        var target=Math.max(1048576,points.reduce(function(m,p){return p.complete===false?m:Math.max(m,p.percent)},0)*1.1)
        memoryCeiling=reset?target:Math.max(memoryCeiling,target)
    }
    function amountLabel(value) { return ceiling>=1073741824 ? (value/1073741824).toFixed(1)+" GB" : Math.round(value/1048576)+" MB" }
    onScaleKeyChanged: {
        memoryCeiling=1048576
        Qt.callLater(function(){chart.updateCeiling(true);chart.repaint()})
    }
    onPointsChanged: { updateCeiling(false);cursorIndex=-1; repaint() }
    onEventsChanged: repaint()
    onWidthChanged: repaint()
    onHeightChanged: repaint()
    onVisibleChanged: repaint()
    Keys.onLeftPressed: { cursorIndex=Math.max(0,cursorIndex-1); repaint() }
    Keys.onRightPressed: { cursorIndex=Math.min(points.length-1,cursorIndex+1); repaint() }
    Keys.onReturnPressed: {
        if(cursorIndex<0) return
        var t=points[cursorIndex].timestamp
        for(var i=0;i<events.length;i++) if(Math.abs(events[i].timestamp-t)<30) { eventSelected(events[i].id); return }
    }
    Rectangle { anchors.fill: parent; color: "transparent"; radius: 8; border.width: chart.activeFocus ? 2 : 0; border.color: Theme.accent }
    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            var ctx=getContext("2d"); ctx.reset()
            var left=48, right=width-16, top=20, bottom=height-32
            ctx.font="12px '"+Language.fontFamily+"'"
            for(var k=0;k<=2;k++) {
                var y=top+(bottom-top)*k/2
                ctx.strokeStyle=Theme.border; ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(left,y); ctx.lineTo(right,y); ctx.stroke()
                ctx.fillStyle=Theme.muted
                var value=chart.ceiling*(1-k/2)
                ctx.fillText(chart.memoryScale ? chart.amountLabel(value) : Math.round(value)+"%", 2, y+4)
            }
            if(!chart.points.length) return
            ctx.fillStyle=Theme.muted
            ctx.fillText(chart.stamp(chart.startTime),left,height-6)
            var ending=chart.stamp(chart.endTime); ctx.fillText(ending,right-ctx.measureText(ending).width,height-6)
            if(!chart.memoryScale) {
                ctx.strokeStyle=Theme.warning; ctx.setLineDash([4,4]); ctx.beginPath()
                var warningY=bottom-(bottom-top)*.85; ctx.moveTo(left,warningY);ctx.lineTo(right,warningY);ctx.stroke();ctx.setLineDash([])
            }
            for(var j=0;j<chart.events.length;j++) {
                var shade=chart.events[j]
                if(shade.kind!=="optimize" || shade.timestamp<chart.startTime || shade.startedAt>chart.endTime) continue
                var sx=chart.xAt(Math.max(chart.startTime,shade.startedAt)),fx=shade.finishedAt?chart.xAt(Math.min(chart.endTime,shade.finishedAt)):right
                ctx.fillStyle=Theme.accentSoft;ctx.fillRect(sx,top,Math.max(2,fx-sx),bottom-top)
            }
            if(chart.filled) {
                var chunk=[]
                function paintChunk() {
                    if(!chunk.length)return
                    ctx.beginPath();ctx.moveTo(chunk[0].x,bottom)
                    for(var c=0;c<chunk.length;c++)ctx.lineTo(chunk[c].x,chunk[c].y)
                    ctx.lineTo(chunk[chunk.length-1].x,bottom);ctx.closePath()
                    ctx.fillStyle=Theme.accent;ctx.globalAlpha=0.09;ctx.fill();ctx.globalAlpha=1
                    chunk=[]
                }
                for(var f=0;f<chart.points.length;f++) {
                    var fp=chart.points[f]
                    if(fp.complete===false) {paintChunk();continue}
                    if(chunk.length&&chunk[chunk.length-1].segment!==fp.segment)paintChunk()
                    chunk.push({x:chart.xAt(fp.timestamp),y:bottom-(bottom-top)*Math.min(1,fp.percent/chart.ceiling),segment:fp.segment})
                }
                paintChunk()
            }
            ctx.strokeStyle=Theme.accent; ctx.lineWidth=2.5; ctx.beginPath()
            var previous=null
            for(var i=0;i<chart.points.length;i++) {
                var p=chart.points[i], x=chart.xAt(p.timestamp), py=bottom-(bottom-top)*Math.min(1,p.percent/chart.ceiling)
                if(p.complete===false) { previous=null;continue }
                if(!previous || previous.segment!==p.segment) ctx.moveTo(x,py);else ctx.lineTo(x,py)
                previous=p
            }
            ctx.stroke()
            // A new segment can contain just one reading. Keep its measured
            // endpoint visible without drawing a line across a history gap.
            for(var latest=chart.points.length-1;latest>=0;latest--) {
                var endpoint=chart.points[latest]
                if(endpoint.complete===false)continue
                ctx.fillStyle=Theme.accent;ctx.beginPath()
                ctx.arc(chart.xAt(endpoint.timestamp),bottom-(bottom-top)*Math.min(1,endpoint.percent/chart.ceiling),3,0,Math.PI*2)
                ctx.fill();break
            }
            for(i=0;i<chart.events.length;i++) {
                var ev=chart.events[i]
                if(ev.timestamp<chart.startTime || ev.timestamp>chart.endTime) continue
                var ex=chart.xAt(ev.timestamp)
                ctx.strokeStyle=ev.kind==="optimize" ? Theme.muted : Theme.warning
                ctx.lineWidth=1;ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(ex,top);ctx.lineTo(ex,bottom);ctx.stroke();ctx.setLineDash([])
                ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.arc(ex,top+3,4,0,Math.PI*2);ctx.fill()
            }
            if(chart.cursorIndex>=0 && chart.cursorIndex<chart.points.length) {
                var cp=chart.points[chart.cursorIndex],cx=chart.xAt(cp.timestamp)
                ctx.strokeStyle=Theme.accent;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(cx,top);ctx.lineTo(cx,bottom);ctx.stroke()
            }
        }
    }
    MouseArea {
        id: hover
        anchors.fill: parent; hoverEnabled: true
        onPositionChanged: { chart.cursorIndex=chart.nearest(mouseX);chart.repaint() }
        onExited: { if(!chart.activeFocus) chart.cursorIndex=-1;chart.repaint() }
        onClicked: {
            chart.forceActiveFocus()
            for(var i=0;i<chart.events.length;i++) if(Math.abs(chart.xAt(chart.events[i].timestamp)-mouseX)<12) { chart.eventSelected(chart.events[i].id);return }
        }
    }
    ToolTip {
        visible: chart.cursorIndex>=0 && (hover.containsMouse || chart.activeFocus)
        text: chart.cursorIndex>=0 && chart.cursorIndex<chart.points.length ? (chart.points[chart.cursorIndex].aggregated?new Date(chart.points[chart.cursorIndex].timestamp*1000).toLocaleTimeString(Qt.locale(),"HH:mm")+" · "+qsTr("1-minute summary"):chart.stamp(chart.points[chart.cursorIndex].timestamp))+" · "+(chart.memoryScale ? (chart.points[chart.cursorIndex].percent/1048576).toFixed(1)+" MB" : chart.points[chart.cursorIndex].percent.toFixed(1)+"%") : ""
        delay: 0
    }
    Connections { target: Preferences; function onChanged(){chart.repaint()} }
    Connections { target: Language; function onChanged(){chart.repaint()} }
}
