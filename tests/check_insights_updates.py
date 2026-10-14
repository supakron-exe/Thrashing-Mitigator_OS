"""Exercise real six-second refreshes and visible QML delegates in a test-only profile."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtCore import QObject,QPointF,Qt,qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickWindow,QSGRendererInterface
from PySide6.QtTest import QTest
from main import create_engine,dispose_engine
from backend.settings import SettingsController
from backend.insights.store import HistoryStore

MIB=1024**2
class Readings:
    def __init__(self):self.calls=0;self.last=0;self.started=time.time()
    def collect(self,snapshot):
        step=self.calls;self.calls+=1;self.last=snapshot['timestamp']
        a=[100,130,120,110,90][min(step,4)]
        b=[100,115,180,190,200][min(step,4)]
        values=[('live-a','First app.exe',a*MIB,True,self.started-3600),
                ('live-b','Second app.exe',b*MIB,True,self.started-3600),
                ('partial','Partial middle.exe',(100+step*20)*MIB,step!=1,self.started-3600),
                ('tiny','Small change.exe',100*MIB+step*4096,True,self.started-3600)]
        if step>=1:values.append(('new','New app.exe',(80+step*10)*MIB,True,self.started+3))
        groups=[dict(id=key,name=name,rss=rss,count=1,complete=complete,processes=[dict(pid=500+i,born=born,rss=rss)]) for i,(key,name,rss,complete,born) in enumerate(values)]
        return dict(timestamp=snapshot['timestamp'],snapshot=snapshot,groups=groups,readable=len(groups),denied=0,duration=.001,complete=True,session='test')

messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(m))
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
(QA_ROOT/'profiles'/'updates').mkdir(parents=True,exist_ok=True)
profile=tempfile.TemporaryDirectory(dir=QA_ROOT/'profiles'/'updates')
prefs=SettingsController('light',Path(profile.name)/'settings.json');prefs.save_language('en');prefs.setAnimations(False)
history=HistoryStore(Path(profile.name)/'insights'/'insights.db')
now=time.time()
for offset,rss in ((120,20*MIB),(114,25*MIB)):
    t=now-offset
    history.write(dict(system=[dict(timestamp=t,percent=40,used=4*1024*MIB,total=10*1024*MIB)],batch=dict(timestamp=t,segment='old',groups=[dict(id='old-id',name='First app.exe',rss=rss,count=1,complete=True,processes=[dict(pid=999,born=now-7200,rss=rss)])]),events=[],segment='old'))
for key,kind,app_id,contributors in [('unrelated','growth','live-b',[]),('related','growth','',[dict(id='live-a',name='First app.exe',delta=5*MIB)]),('optimized','optimize','',[])]:
    history.write(dict(system=[],events=[dict(id=key,kind=kind,app=app_id,timestamp=now-5,startedAt=now-10,before=100*MIB,after=120*MIB,percent=40,contributors=contributors,segment='old',mode='Maximum',source='manual',finishedAt=now-5)],segment='old'))
history.close()
provider=Readings()
with patch('backend.insights.controller.ProcessCollector',lambda:provider):
    engine,memory,prefs=create_engine(app,settings=prefs)
insights=engine._insights
def pump(condition,timeout=10):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        time.sleep(.005)
    raise AssertionError('Live update condition timed out')
def settle():
    end=time.monotonic()+.2
    while time.monotonic()<end:app.processEvents();time.sleep(.005)
def obj(name):
    found=window.findChild(QObject,name)
    if found is None:
        # ListView delegates can have a model QObject parent and a separate
        # visual parent. Inspect the rendered tree rather than only ownership.
        pending=[window.contentItem()]
        while pending:
            item=pending.pop()
            if item.objectName()==name:found=item;break
            pending.extend(item.childItems())
    assert found is not None,name
    return found
def choose(app_id):
    item=obj('insightsRankingRow_'+app_id)
    point=item.mapToScene(QPointF(item.width()/2,item.height()/2))
    QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point.toPoint())
    pump(lambda:insights.selectedApp.get('id')==app_id and bool(insights.selectedApp.get('series')))
    settle()
def latest(call):
    return provider.calls>=call and not insights.loading and insights.selectedApp.get('lastAt',0)>=provider.last-.1
out=QA_ROOT/'insights_visual'
report={}
try:
    pump(lambda:any(w.objectName()=='mainWindow' for w in app.allWindows()))
    window=next(w for w in app.allWindows() if w.objectName()=='mainWindow');window.setProperty('page',3);window.resize(1180,740)
    pump(lambda:latest(2),12)
    settle()
    assert insights.selectedApp['id']!='old-id'
    assert obj('insightsRankingDelta_tiny').property('text')=='+4.0 KB'
    choose('live-a')
    first=obj('insightsRankingDelta_live-a').property('text');assert first=='+30.0 MB',first
    assert [e['id'] for e in insights.selectedAppMarkers]==['related','optimized']
    pump(lambda:latest(3),10)
    settle()
    assert insights.visualRanking.rows[0]['id']=='live-b'
    second=obj('insightsRankingDelta_live-a').property('text');assert second=='+20.0 MB',second
    assert insights.selectedApp['deltaLabel']==second
    assert insights.selectedApp['id']=='live-a'
    assert any(r['id']=='partial' and r['hasPartialReadings'] for r in insights.visualRanking.rows)
    assert any(r['id']=='new' and r['new'] for r in insights.visualRanking.rows)
    choose('new');assert obj('insightsTrendBaseline').property('text')=='Since first observed'
    choose('live-a')
    # Resume is a normal session boundary; observed deltas must keep updating.
    insights.pauseTracking();insights.resumeTracking()
    pump(lambda:latest(4),10)
    settle()
    assert insights.selectedApp['hasGaps'] and insights.selectedApp['comparable']
    assert obj('insightsRankingDelta_live-a').property('text')=='+10.0 MB'
    span=obj('insightsTrendObservedSpan').property('text')
    assert span==insights.selectedApp['observedSpanLabel']
    picture=window.grabWindow()
    picture.save(str(out/'ranking_updates.png'))
    chart=obj('insightsChart')
    endpoint=insights.selectedApp['series'][-1]
    point=chart.mapToScene(QPointF(chart.width()-16,chart.height()-32-(chart.height()-52)*endpoint['percent']/chart.property('ceiling')))
    scale=picture.width()/window.width()
    color=picture.pixelColor(round(point.x()*scale),round(point.y()*scale))
    assert color.blue()>color.red()+70,('latest segment endpoint is not visible',color.name())
    pump(lambda:latest(5),10)
    assert insights.selectedApp['delta']<0
    assert 'live-a' not in [r['id'] for r in insights.visualRanking.rows]
    # A deliberate historical selection remains visible with a truthful age label.
    insights.selectApp('old-id');pump(lambda:insights.selectedApp.get('id')=='old-id' and bool(insights.selectedApp.get('series')))
    settle();assert insights.selectedApp['stale']
    assert 'Last observed' in obj('insightsTrendReadingStatus').property('text')
    assert obj('insightsTrendObservedSpan').property('text')==insights.selectedApp['observedSpanLabel']
    fatal=[m for m in messages if any(t in m for t in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign'))]
    assert not fatal,fatal
    report=dict(passed=True,automaticRefreshSeconds=6,providerCalls=provider.calls,
        visibleDeltaUpdates=[first,second,'+10.0 MB'],newAppRanks=True,partialMiddleRanks=True,
        sessionGapStillUpdates=True,negativeAppRemoved=True,manualSelectionPreserved=True,
        oldIdentityLabeled=True,ownObservationSpan=True,unrelatedMarkersHidden=True,tinyDeltaUsesKB=True,latestPointVisibleAfterGap=True,qmlErrors=fatal)
finally:
    dispose_engine(app,engine,memory);profile.cleanup()
    (out/'ranking_updates.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
