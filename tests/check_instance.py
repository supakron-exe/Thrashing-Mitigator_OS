"""Own test processes only; lock, activation IPC and crash recovery."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
parser=argparse.ArgumentParser()
parser.add_argument("--child")
args=parser.parse_args()
if args.child:
    from PySide6.QtCore import QCoreApplication, QTimer
    from backend.instance import SingleInstance
    app=QCoreApplication([])
    instance=SingleInstance(Path(args.child))
    assert instance.primary
    instance.activate.connect(lambda data: print(json.dumps(data),flush=True))
    print("READY",flush=True)
    QTimer.singleShot(30000,app.quit)
    app.exec(); instance.close()
else:
    from PySide6.QtCore import QCoreApplication
    from backend.instance import SingleInstance
    app=QCoreApplication([])
    with tempfile.TemporaryDirectory() as temp:
        child=subprocess.Popen([sys.executable,__file__,"--child",temp],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            assert child.stdout.readline().strip()=="READY"
            second=SingleInstance(Path(temp))
            assert not second.primary, "Second process became primary"
            assert second.forward("dark",False)
            assert json.loads(child.stdout.readline())==dict(theme="dark",background=False)
            second.close()
            # Terminate only the test helper created above to emulate a crash.
            child.terminate(); child.wait(5)
            restored=SingleInstance(Path(temp))
            assert restored.primary, "Dead owner lock did not recover"
            restored.close()
            print("PASS single instance: exclusive lock, same-user activation, crash recovery",flush=True)
        finally:
            if child.poll() is None: child.terminate(); child.wait(5)
