"""Isolated production startup: background, activation and one real primary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from backend.startup import WindowsStartup
startup=WindowsStartup(ROOT)
before=startup.capture()
script=r'''
import sys,json
from PySide6.QtCore import Slot,QObject,QTimer
from backend.lifecycle import TrayLifecycle
class Probe(TrayLifecycle):
    @Slot(QObject)
    def windowReady(self,window):
        super().windowReady(window)
        print('READY '+json.dumps(dict(visible=window.isVisible(),tray=self.trayAvailable,auto=self.automatic.enabled)),flush=True)
        QTimer.singleShot(10000,self.exit)
    @Slot(object)
    def activate(self,data):
        super().activate(data)
        print('ACTIVE '+json.dumps(dict(theme=self.preferences.theme,visible=self.window.isVisible())),flush=True)
        QTimer.singleShot(300,self.exit)
import backend.lifecycle
backend.lifecycle.TrayLifecycle=Probe
import main
sys.argv=['main.py','--background','--theme','light']
raise SystemExit(main.main())
'''
with tempfile.TemporaryDirectory() as temp:
    env=dict(os.environ,LOCALAPPDATA=temp)
    primary=subprocess.Popen([sys.executable,'-c',script],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        ready=primary.stdout.readline().strip()
        assert ready.startswith('READY '),ready
        state=json.loads(ready[6:])
        assert state==dict(visible=False,tray=True,auto=False),state
        secondary=subprocess.run([sys.executable,'main.py','--theme','dark'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=8)
        assert secondary.returncode==0,secondary.stderr
        active=primary.stdout.readline().strip()
        assert active.startswith('ACTIVE '),active
        assert json.loads(active[7:])==dict(theme='dark',visible=True)
        primary.wait(8)
        stderr=primary.stderr.read()
        assert primary.returncode==0,stderr
        log=(Path(temp)/'ThrashingMitigatorRedesign/application.log').read_text()
        assert 'Error:' not in log and 'Traceback' not in log,log
        assert startup.capture()==before,'Default launch changed Windows startup registration'
        report=dict(backgroundHidden=True,defaultAutoOff=True,secondaryActivatedPrimary=True,
                    themeForwarded=True,cleanExit=True,startupRegistryUnchanged=True,
                    elevatedActivationTested=False)
        (QA_ROOT/'auto_production_qa.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PASS production startup: hidden Tray, Auto off, one primary, forwarded Dark, clean Exit, startup untouched',flush=True)
    finally:
        if primary.poll() is None: primary.terminate(); primary.wait(5)
