"""Live baseline/Tray/page soak plus a separate 24-hour synthetic storage load."""
import argparse
import gc
import json
import sys
import tempfile
import time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickWindow,QSGRendererInterface
from main import create_engine,dispose_engine
from backend.settings import SettingsController
from backend.insights.store import HistoryStore
parser=argparse.ArgumentParser();parser.add_argument('--seconds-per-stage',type=int,default=240);parser.add_argument('--output',default='performance.json');args=parser.parse_args()
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
temporary=tempfile.TemporaryDirectory()
prefs=SettingsController(path=Path(temporary.name)/'settings.json');prefs.setAnimations(False)
engine,memory,prefs=create_engine(app,settings=prefs)
insights=engine._insights
window=next(w for w in app.allWindows() if w.objectName()=='mainWindow')
window.setTitle('Insights validation')
process=psutil.Process()
report=dict(clientDate='2026-10-12',live=True,stages=[])
out=QA_ROOT/'insights'/args.output;out.parent.mkdir(parents=True,exist_ok=True)
def save_progress():out.write_text(json.dumps(report,indent=2),encoding='utf-8')
try:
    for stage in ('baseline','tray','insights'):
        if stage=='baseline':insights.pauseTracking();window.setProperty('page',0);window.show()
        elif stage=='tray':insights.resumeTracking();window.hide()
        else:window.setProperty('page',3);window.show()
        # Warm up separately from the measurement.
        until=time.monotonic()+3
        while time.monotonic()<until:app.processEvents();time.sleep(.005)
        gc.collect()
        before=process.cpu_times();start=time.monotonic();rss=[];next_read=start
        while time.monotonic()-start<args.seconds_per_stage:
            app.processEvents()
            if time.monotonic()>=next_read:
                rss.append(process.memory_info().rss);next_read+=1
            time.sleep(.005)
        after=process.cpu_times();elapsed=time.monotonic()-start
        item=dict(stage=stage,seconds=elapsed,cpuMachinePercent=100*((after.user+after.system)-(before.user+before.system))/elapsed/psutil.cpu_count(),peakRssMiB=max(rss)/1024**2,
                  averageRssMiB=sum(rss)/len(rss)/1024**2,readable=insights.coverage.get('readable'),collectorMs=insights.coverage.get('duration',0)*1000)
        report['stages'].append(item);print(json.dumps(item),flush=True)
        save_progress()
    memory.requestClose()
    until=time.monotonic()+10
    while not insights.safeToClose and time.monotonic()<until:app.processEvents();time.sleep(.005)
    assert insights.safeToClose
    report['cleanShutdown']=True
finally:dispose_engine(app,engine,memory);app.processEvents();temporary.cleanup()

# Stress fixture: 200 apps / 1,000 processes, full 24 hours, never loaded in production.
with tempfile.TemporaryDirectory() as directory:
    store=HistoryStore(Path(directory)/'stress.db');now=int(time.time()//60)*60
    groups=200
    minute_rows=((bucket,f'app-{i}','stress',f'test-{i}.exe',bucket,bucket+54,100000000+i,120000000+i,80000000+i,200000000+i,120000000+i,10,5,1,now-86400) for bucket in range(now-86400,now-1800,60) for i in range(groups))
    store.db.executemany('INSERT INTO app_minutes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',minute_rows)
    system_rows=((bucket,'stress',bucket,bucket+54,40,42,35,65,7*1024**3,16*1024**3,30) for bucket in range(now-86400,now-1800,60))
    store.db.executemany('INSERT INTO system_minutes VALUES(?,?,?,?,?,?,?,?,?,?,?)',system_rows)
    for t in range(now-1800,now,6):
        sample=dict(timestamp=t,percent=45,used=7*1024**3,total=16*1024**3)
        batch=dict(timestamp=t,segment='stress',groups=[dict(id=f'app-{i}',name=f'test-{i}.exe',rss=120000000+i,count=5,complete=True,processes=[dict(pid=i*5+j,born=now-86400,rss=24000000) for j in range(5)]) for i in range(groups)])
        store.write(dict(batch=batch,system=[sample],events=[],segment='stress'))
    store.flush(now)
    timings=[]
    for _ in range(3):
        start=time.perf_counter();data=store.query(now-86400,now,'app-1');timings.append((time.perf_counter()-start)*1000)
    assert len(data['apps'])==200 and max(p['percent'] for p in data['series'])==65
    report['stress']=dict(processes=1000,apps=200,hours=24,queryMs=timings,storageMiB=data['size']/1024**2,chartPoints=len(data['series']))
    store.close()
base=report['stages'][0]
report['addedCpuMachinePercent']=max(s['cpuMachinePercent'] for s in report['stages'][1:])-base['cpuMachinePercent']
report['addedRssMiB']=max(s['peakRssMiB'] for s in report['stages'][1:])-base['peakRssMiB']
report['complete']=True
save_progress()
print(json.dumps(report),flush=True)
