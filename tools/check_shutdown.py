"""Exercise the real window-close path while a Qt worker is still running."""
from pathlib import Path
import os
import sys
import time
import json
import tempfile
import faulthandler
import argparse
faulthandler.enable()
parser = argparse.ArgumentParser()
parser.add_argument("--idle", action="store_true")
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from qa_support import QA_ROOT, qa_path
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController

completed = []
def runner(mode, progress):
    progress("Completing shutdown test")
    time.sleep(.6)
    completed.append(True)
    return {"supported": True, "elevated": True, "trimmed": 0}

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([])
memory = MemoryController(runner=runner)
temporary = tempfile.TemporaryDirectory(prefix="shutdown-")
engine, memory, preferences = create_engine(app, controller=memory, settings=SettingsController("light", Path(temporary.name) / "settings.json"))

def start():
    print("Starting close test", flush=True)
    window = next(w for w in app.allWindows() if w.objectName() == "mainWindow")
    if not args.idle:
        memory.startOptimization()
    QTimer.singleShot(100, window.close)

print("Engine loaded", flush=True)
QTimer.singleShot(100, start)
QTimer.singleShot(5000, app.quit)
started = time.monotonic()
app.exec()
print("Event loop finished", flush=True)
assert args.idle or completed, "Window close exited before the worker finished"
assert memory.closing and memory._thread is None
assert args.idle or time.monotonic() - started >= .6
dispose_engine(app, engine, memory)
temporary.cleanup()
qa_path("shutdown_idle.json" if args.idle else "shutdown_worker.json").write_text(
    json.dumps(dict(passed=True, idle=args.idle, workerFinished=bool(completed)), indent=2), encoding="utf-8")
faulthandler.cancel_dump_traceback_later()
print("PASS: native close waited for the worker and disposed the QML engine cleanly")
