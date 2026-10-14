import QtQuick
Canvas {
    id: spark
    property var points:[]
    Accessible.ignored:true
    function redraw(){if(visible)requestPaint()}
    onPointsChanged:redraw()
    onVisibleChanged:redraw()
    onWidthChanged:redraw()
    onPaint:{
        var ctx=getContext('2d');ctx.reset()
        if(points.length<2)return
        var low=points.reduce(function(m,p){return Math.min(m,p.percent)},Infinity)
        var high=points.reduce(function(m,p){return Math.max(m,p.percent)},0)
        ctx.strokeStyle=Theme.accent;ctx.lineWidth=1.7;ctx.beginPath()
        var previous=null
        for(var i=0;i<points.length;i++){
            var p=points[i]
            if(!p.complete){previous=null;continue}
            var x=2+(width-4)*i/(points.length-1),y=height-3-(height-6)*(p.percent-low)/Math.max(1,high-low)
            if(!previous||p.segment!==previous.segment)ctx.moveTo(x,y);else ctx.lineTo(x,y)
            previous=p
        }
        ctx.stroke()
    }
    Connections {target:Preferences;function onChanged(){spark.redraw()}}
}
