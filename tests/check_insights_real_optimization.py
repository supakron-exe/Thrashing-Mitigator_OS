"""Explicit real Windows optimization validation, isolated application history."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
temporary=tempfile.TemporaryDirectory()
os.environ['LOCALAPPDATA']=temporary.name
from PySide6.QtCore import QCoreApplication
from backend.controller import MemoryController
from backend.insights.controller import InsightsController
app=QCoreApplication([])
memory=MemoryController()
insights=InsightsController(memory,path=Path(temporary.name)/'insights.db')
reports=[]
def pump(condition,timeout=180):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents();time.sleep(.005)
        if condition():return
    raise AssertionError('Real Windows operation timed out')
try:
    insights.setActive(True)
    pump(lambda:insights._last_sample>0)
    for mode in ('Standard','Deep','Maximum'):
        memory.setMode(mode)
        samples=[]
        def sample():samples.append(memory.snapshot.get('timestamp'))
        memory.sampleChanged.connect(sample)
        memory.startOptimization()
        assert memory.busy
        pump(lambda:not memory.busy)
        memory.sampleChanged.disconnect(sample)
        result=dict(memory.lastResult)
        reports.append(dict(mode=mode,result=result,liveSamplesDuringOperation=len(set(samples)),readable=insights.coverage.get('readable'),monitoringLive=memory.live))
        assert memory.live and samples
        print(json.dumps({'mode':mode,'tone':result.get('tone'),'gain':result.get('gain'),'liveSamples':len(set(samples))}),flush=True)
    memory.requestClose();pump(lambda:insights.safeToClose and memory.safeToClose,15)
finally:insights.shutdown();memory.shutdown();temporary.cleanup()
out=QA_ROOT/'insights'/'real_optimization.json';out.write_text(json.dumps(dict(realWindowsOptimization=True,modes=reports),indent=2,ensure_ascii=False),encoding='utf-8')
