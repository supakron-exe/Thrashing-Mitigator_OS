"""Native visual/interaction checks; generated readings stay in this test profile."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
parser=argparse.ArgumentParser()
parser.add_argument('--theme',choices=('light','dark'),default='light')
parser.add_argument('--language',choices=('en','th'),default='th')
parser.add_argument('--scale',type=float,default=1)
parser.add_argument('--size',choices=('minimum','default','maximized'),default='default')
parser.add_argument('--live',action='store_true')
parser.add_argument('--exercise',action='store_true')
args=parser.parse_args()
native_env=dict(os.environ);native_env.pop('QT_SCALE_FACTOR',None)
native=float(subprocess.check_output([sys.executable,'-c','from PySide6.QtGui import QGuiApplication; a=QGuiApplication([]); print(a.primaryScreen().devicePixelRatio())'],env=native_env,text=True).strip())
os.environ['QT_SCALE_FACTOR']=str(args.scale/native)
from PySide6.QtCore import QObject,QMetaObject,Qt,QEvent,qInstallMessageHandler
from PySide6.QtGui import QFont,QKeyEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickWindow,QSGRendererInterface
from main import create_engine,dispose_engine
from backend.settings import SettingsController
from backend.controller import MemoryController
from backend.insights.store import HistoryStore

messages=[]
qInstallMessageHandler(lambda k,c,m:messages.append(m))
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app=QApplication([]);app.setFont(QFont('Segoe UI',10));app.setQuitOnLastWindowClosed(False)
(QA_ROOT/'profiles'/'visual').mkdir(parents=True,exist_ok=True)
temporary=tempfile.TemporaryDirectory(dir=QA_ROOT/'profiles'/'visual')
prefs=SettingsController(args.theme,Path(temporary.name)/'settings.json')
prefs.save_language(args.language);prefs.setAnimations(False)
if not args.live:
    now=time.time()
    store=HistoryStore(Path(temporary.name)/'insights'/'insights.db')
    names=['Example application with a deliberately long name.exe','Browser.exe','Editor.exe','Discord.exe','Music.exe','Decreasing.exe','Partial.exe','Closed.exe','New.exe']
    for i in range(60):
        timestamp=now-360+i*6
        groups=[]
        for j,name in enumerate(names):
            if j==8 and i<50:continue
            rss=int((100+i*(10-j*2) if j<5 else 600-i*5 if j==5 else 100+i*12)*1024**2)
            count=0 if j==7 and i==59 else 1
            if not count:rss=0
            born=now-65 if j==8 else now-7200
            metadata=dict(displayName='Visual Studio Code — deliberately long application name for layout checks',processName=name,nameSource='file_description') if j==0 else {}
            groups.append(dict(id=f'app-{j}',name=name,rss=rss,count=count,complete=not(j==6 and i>45),processes=[dict(pid=100+j,born=born,rss=rss)] if count else [],**metadata))
        system=dict(timestamp=timestamp,percent=40+i*.35,used=int((40+i*.35)/100*16*1024**3),total=16*1024**3)
        store.write(dict(system=[system],batch=dict(timestamp=timestamp,segment='fixture',groups=groups),events=[],segment='fixture'))
    for j,kind in enumerate(('growth','high','optimize')):
        event=dict(id=f'event-{j}',kind=kind,timestamp=now-6-j*12,startedAt=now-306,before=100*1024**2,after=600*1024**2,percent=88,segment='fixture',contributors=[dict(id='app-0',name=names[0],delta=500*1024**2)],mode='Maximum',source='manual',finishedAt=now-12)
        store.write(dict(system=[],events=[event],segment='fixture'))
    store.close()
gate=threading.Event()
def runner(mode,progress):
    progress('test operation');gate.wait(6)
    return dict(supported=True,elevated=False,trimmed=2,failed=1,available_before_mb=2500,available_after_mb=2500,available_delta_mb=0,duration_s=2.5,steps=[],targets=[])
memory=MemoryController(runner=runner,hold_ms=20)
engine,memory,prefs=create_engine(app,settings=prefs,controller=memory)
insights=engine._insights
for _ in range(100):
    app.processEvents()
    if any(w.objectName()=='mainWindow' for w in app.allWindows()):break
    time.sleep(.01)
windows=[w for w in app.allWindows() if w.objectName()=='mainWindow']
if not windows:
    dispose_engine(app,engine,memory)
    temporary.cleanup()
    raise RuntimeError('\n'.join(messages))
window=windows[0]
window.setProperty('page',3)

def pump(seconds=.2,condition=None):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents()
        if condition and condition():return
        time.sleep(.004)
    if condition:raise AssertionError('UI condition timed out')

def item(name):
    result=window.findChild(QObject,name)
    assert result is not None,name
    return result

def click(name):
    assert QMetaObject.invokeMethod(item(name),'clicked')
    pump(.25)

out=QA_ROOT/'insights_visual';out.mkdir(parents=True,exist_ok=True)
tag=f"{'live' if args.live else 'fixture'}_{args.theme}_{args.language}_{args.scale:g}_{args.size}"
report=dict(theme=args.theme,language=args.language,scale=args.scale,size=args.size,live=args.live)
try:
    pump(12 if args.live else 4,lambda:bool(insights.selectedApp.get('series')))
    if args.size=='minimum':window.resize(900,640)
    elif args.size=='default':window.resize(1180,740)
    else:window.showMaximized()
    pump(.5)
    # Startup centering can select a different monitor with a different DPI.
    # Pin every case to the measured primary screen before checking its DPR.
    screen=app.primaryScreen();window.setScreen(screen)
    area=screen.availableGeometry()
    window.setPosition(area.x()+max(0,(area.width()-window.width())//2),area.y()+max(0,(area.height()-window.height())//2))
    if args.size=='maximized':window.showMaximized()
    elif args.size=='minimum':window.resize(900,640)
    else:window.resize(1180,740)
    pump(.5)
    chart=item('insightsChart');ranking=item('insightsRankingCard');trend=item('insightsTrendCard');grid=item('insightsVisualGrid')
    before=(chart.width(),chart.height())
    assert abs(window.devicePixelRatio()-args.scale)<.01,window.devicePixelRatio()
    if args.size!='maximized':assert (window.width(),window.height())==((900,640) if args.size=='minimum' else (1180,740))
    assert chart.height()==220,before
    assert grid.property('columns')==(2 if item('insightsPage').width()>=900 else 1)
    if not args.live:
        assert insights.visualRanking.rowCount()==5
        assert item('insightsRankingList').height()>=276
        assert [r['id'] for r in insights.visualRanking.rows]==[f'app-{i}' for i in range(5)]
        assert insights.selectedApp['id']=='app-0'
        assert item('insightsTrendAppName').property('text')==insights.selectedApp['displayName']
        assert item('insightsTrendProcessName').property('text')==insights.selectedApp['processName']
        assert len(insights.recentEvents)==3
    window.grabWindow().save(str(out/(tag+'.png')))
    report.update(window=[window.width(),window.height()],dpr=window.devicePixelRatio(),chart=list(before),rankingCount=insights.visualRanking.rowCount(),columns=grid.property('columns'))
    if args.size=='default':
        # Both primary cards must fit the first viewport, including all five bars.
        content=item('mainScroll').property('contentItem')
        assert max(ranking.y()+ranking.height(),trend.y()+trend.height())<=content.height()
        report['primaryCardsVisible']=True
    if args.exercise:
        selected=insights.selectedApp['id'];period=insights.selectedRange
        click('insightsAppDetailsButton')
        details=item('insightsDetails');assert details.property('opened')
        window.grabWindow().save(str(out/(tag+'_details.png')))
        app.sendEvent(window,QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier));pump(.25)
        assert not details.property('opened') and insights.selectedApp['id']==selected
        assert item('insightsAppDetailsButton').property('activeFocus')
        if not args.live:
            insights.inspectEvent('event-0')
            assert insights.followLive and insights.selectedRange==period and insights.selectedApp['id']==selected
            details.setProperty('detailKind','event');QMetaObject.invokeMethod(details,'open');pump(.3)
            window.grabWindow().save(str(out/(tag+'_event.png')))
            assert (chart.width(),chart.height())==before
            QMetaObject.invokeMethod(details,'close');pump(.3)
            assert insights.selectedApp['id']==selected
        click('insightsBrowseApps');browser=item('insightsBrowser');assert browser.property('opened')
        pump(.3);window.grabWindow().save(str(out/(tag+'_apps.png')))
        insights.setSearch('definitely missing')
        assert insights.appModel.rowCount()==0
        if not args.live:assert insights.visualRanking.rowCount()==5
        insights.setSearch('');QMetaObject.invokeMethod(browser,'close');pump(.25)
        assert item('insightsBrowseApps').property('activeFocus')
        chart.forceActiveFocus(Qt.TabFocusReason)
        app.sendEvent(window,QKeyEvent(QEvent.KeyPress,Qt.Key_Right,Qt.NoModifier))
        assert chart.property('cursorIndex')>=0
        for mode in ('Standard','Deep','Maximum'):
            gate.clear();memory.setMode(mode);memory.startOptimization()
            first=memory.snapshot['timestamp'];pump(2.3)
            assert memory.snapshot['timestamp']>first
            assert (chart.width(),chart.height())==before
            gate.set();pump(5,lambda:not memory.busy)
        report['interactions']=['inline selection','explicit details','event keeps live range','search independent of ranking','focus restored','chart keyboard','monitoring during all three mock modes']
        if not args.live:
            insights.selectApp('app-4');pump(3,lambda:insights.selectedApp.get('id')=='app-4' and bool(insights.selectedApp.get('series')))
            pump(.1)
            assert not details.property('opened')
            assert chart.property('ceiling')<=insights.selectedApp['peak']*1.11
            insights.inspectEvent('event-0');insights.jumpToInspectedEvent();pump(.3)
            assert not insights.followLive
            insights.closeEventInspection();insights.returnToLive();pump(.3)
        old_period=insights.selectedRange
        engine._language.setLanguage('en' if args.language=='th' else 'th');prefs.setTheme('dark' if args.theme=='light' else 'light');pump(.3)
        assert insights.selectedRange==old_period and chart.height()==220
        prefs.setAnimations(True);pump(.1);prefs.setAnimations(False)
    fatal=[m for m in messages if any(t in m for t in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','failed to load','is not a type'))]
    assert not fatal,'\n'.join(fatal)
    report.update(qmlErrors=fatal,passed=True)
finally:
    gate.set();dispose_engine(app,engine,memory);app.processEvents()
    (out/(tag+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    temporary.cleanup()
print(json.dumps(report))
